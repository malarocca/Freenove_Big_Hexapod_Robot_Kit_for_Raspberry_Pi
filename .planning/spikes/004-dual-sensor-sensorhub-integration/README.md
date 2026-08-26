---
spike: 004
name: dual-sensor-sensorhub-integration
type: standard
validates: "Given both sensors polled on independent schedules, when read concurrently, then confirm no GPIO/I2C contention (re-testing the class of bug fixed in 12a7fda) and sketch arbitration for VL53L1X as a near-field cross-check inside STOP_THRESHOLD_CM/RESUME_THRESHOLD_CM"
verdict: VALIDATED
related: [001, 002, 003]
tags: [integration, architecture]
---

# Spike 004: Dual-Sensor / SensorHub Integration

## What This Validates

Given both sensors polled on independent schedules (ultrasonic via gpiozero's own
background thread, VL53L1X via a dedicated polling thread), when read concurrently, then
(a) confirm no contention re-emerges -- the class of bug already fixed once in this project
(`12a7fda`: a second independent poller thread corrupting ultrasonic's GPIO-pulse-width
timing) -- and (b) sketch what arbitration logic would look like if VL53L1X is added as a
near-field cross-check per spikes 002/003's findings.

## Research

No new libraries. Reuses `Ultrasonic` and `VL53L1X` exactly as spikes 001-003 configured
them. The one piece of prior-art research that matters here is re-reading the actual fix
from commit `12a7fda` (`Code/Server/autonomy/perception.py`, unmerged worktree branch
`worktree-agent-ab149f1102043bce0`) rather than re-deriving it:

- The original dual-poller bug was **two threads calling gpiozero's `_read()` on the SAME
  ultrasonic sensor** -- the fix (`SensorHub._install_capture`) doesn't add a second thread
  at all; it monkeypatches `_ultrasonic.sensor._read` so gpiozero's own existing background
  thread is the sole caller, and `SensorHub` just observes results passively.
- VL53L1X is different hardware on a different bus (I2C, not the ultrasonic's dedicated
  trigger/echo GPIO pins), and the Python `VL53L1X` wrapper (`/usr/local/lib/python3.13/
  dist-packages/VL53L1X.py`) has **no background thread of its own** -- `get_distance()` is
  a synchronous call straight into the C extension (`_TOF_LIBRARY.getDistance`), confirmed
  via `inspect.getsource`. So the *exact* prior bug (two threads racing on one sensor's GPIO
  pins) cannot recur here by construction -- but a new question exists: if a production
  integration runs VL53L1X polling in its own thread (the only way to read it continuously,
  since it has no background thread to piggyback on the way ultrasonic does), does that
  thread's I2C blocking calls introduce enough CPU/GIL scheduling jitter to degrade
  gpiozero's precise GPIO pulse-width timing on the ultrasonic thread? That's what
  `test_dual_sensor_contention.py` actually measures, via an A/B comparison rather than
  assumption.

## How to Run

```
cd .planning/spikes/004-dual-sensor-sensorhub-integration
sudo python3 -u test_dual_sensor_contention.py
```

Two phases, ~15s each: Phase A runs ultrasonic alone (VL53L1X sensor object is constructed
and ranging but nothing polls it yet); Phase B adds a dedicated VL53L1X polling thread
(20Hz, matching a plausible production poll rate) while re-measuring the exact same fixed
target with the ultrasonic. Keep the target still and identical between phases -- this is a
contention test, not an accuracy test (spikes 002/003 already covered accuracy).

## What to Expect

The script prints ultrasonic's internal read rate (gpiozero's own thread call count) and
value stdev for each phase, then a direct A-vs-B delta. If VL53L1X's polling thread is
contending for GPIO timing, expect phase B's ultrasonic read rate to drop and/or stdev to
rise noticeably versus phase A. If not, the two numbers should be close.

## Observability

Stdout printout + CSV log (`contention_log.csv`: timestamp, phase, ultrasonic_cm) is
sufficient given the low data volume and the two-phase A/B structure -- no separate
forensic log layer needed.

## Investigation Trail

Ran with a rigidly-propped hard target (~19.6cm) so any noise increase in phase B would be
attributable to contention rather than the target itself moving:

- **Phase A (ultrasonic alone):** 150 samples over 15s, internal read rate 15.5/s. Values:
  11x 19.5cm, 137x 19.6cm, 2x 19.7cm (stdev 0.03cm).
- **Phase B (ultrasonic + concurrent VL53L1X polling thread at 20Hz):** 150 samples over 15s,
  internal read rate 15.5/s -- identical to phase A. Values: 10x 19.5cm, 138x 19.6cm, 2x
  19.7cm (stdev 0.03cm) -- a near-identical but *not* bit-identical distribution (checked the
  raw per-sample CSV specifically to rule out a logging bug producing duplicate data; the two
  phases' value distributions differ by one sample each at 19.5/19.6, confirming these are two
  genuinely independent captures that both happened to land in the same tight noise floor).
- **VL53L1X during phase B:** 140 total poll attempts over 15s (9.3/s, below the intended 20Hz
  request -- each `get_distance()` call blocks for roughly the 140ms timing budget plus the
  150ms inter-measurement period configured in spikes 002/003, i.e. ~290ms/read, capping the
  achievable rate well under 20Hz regardless of contention). All 140 were valid reads on the
  fixed target, no failures.

No follow-up iteration was needed -- the A/B delta was effectively zero on every measured
axis (read rate, value distribution, stdev), which directly answers the spike's question.

## Results

**Verdict: VALIDATED.** Running a dedicated VL53L1X polling thread concurrently with
gpiozero's own ultrasonic background thread introduces no detectable contention: identical
internal read rate (15.5/s both phases) and near-identical value distributions (differing by
one sample out of 150, well within the sensor's own noise floor) between ultrasonic-alone
and ultrasonic-plus-VL53L1X. This confirms the architectural reasoning from Research holds in
practice, not just in theory: the original dual-poller bug (`12a7fda`) was two threads racing
on the *same* sensor's GPIO pins, and VL53L1X's I2C-based polling thread doesn't touch those
pins at all, so there was never a shared-resource path for that specific bug class to
reappear through. The remaining, different question -- GIL/CPU scheduling jitter from a
second thread affecting gpiozero's precise pulse-width timing -- was empirically tested here
and shows no measurable effect either.

One methodology note for future spikes: `get_distance()` blocks for close to the full
timing-budget + inter-measurement duration (~290ms with spike 002/003's 140ms/150ms
settings), so a "20Hz" polling *request* only actually achieves ~9.3Hz in practice. Anyone
wiring VL53L1X into a production polling loop needs to budget for that real achievable rate,
not the requested one.

The Arbitration Sketch below (written before this run, based on spikes 001-003's findings)
is unaffected by this spike's result -- it already assumed ultrasonic stays authoritative and
VL53L1X is consulted only within a narrow band, which holds regardless of the contention
question this spike answered.

## Arbitration Sketch

Design-level sketch only (spike output, not implementation) -- informed by every finding
from spikes 001-003:

```python
# Illustrative, not final code. Would live alongside autonomy/perception.py's SensorHub.

def decide_stop(ultrasonic_cm, tof_mm, tof_status, prev_tof_mm=None):
    """
    Ultrasonic stays primary/authoritative for the full STOP/RESUME range (spike 002).
    VL53L1X only ever narrows the stop decision when ultrasonic itself is in its own
    known-weak near-field band (STOP_THRESHOLD_CM=20 .. RESUME_THRESHOLD_CM=35, per
    settings.py) -- it never overrides ultrasonic outside that band, and never extends
    trust past its own proven-clean zone (spike 003: keep <=20-30cm, not the full <=60cm
    spike 002 called "reliable").
    """
    # 1. Ultrasonic is always authoritative first -- it has no observed surface-specific
    #    failure mode (spike 003) and covers the full range (spike 002).
    if ultrasonic_cm is None:
        return "STOP"  # unknown is never treated as clear -- existing behavior.py convention

    if ultrasonic_cm > RESUME_THRESHOLD_CM:
        return "CLEAR"  # outside the ambiguous band entirely, VL53L1X not consulted

    # 2. Inside the 20-35cm ambiguous band: ultrasonic alone already says stop-and-reassess.
    #    VL53L1X can only be consulted here, and only to the extent its own spike-003-proven
    #    clean zone overlaps this band (<=20-30cm) -- never trusted past that.
    if tof_status != "Range Valid":
        return "STOP"  # honest failure code -- fall back to ultrasonic's STOP, don't guess

    # 3. Value-plausibility check (spike 003's 0mm-while-"Range Valid" finding) -- a status
    #    of Range Valid is NOT sufficient alone. Reject implausible jumps from the previous
    #    reading before trusting the value at all.
    if prev_tof_mm is not None and abs(tof_mm - prev_tof_mm) > MAX_PLAUSIBLE_JUMP_MM:
        return "STOP"  # can't trust this reading -- fall back to ultrasonic's STOP

    if tof_mm > TOF_TRUSTED_CEILING_MM:  # e.g. 300mm / 30cm, per spike 003
        return "STOP"  # outside VL53L1X's proven-clean zone -- don't extend trust further

    # 4. Both sensors agree the near-field zone is genuinely close -- still STOP either way
    #    in this band (ultrasonic already said so in step 1). VL53L1X's real value here is
    #    not overriding ultrasonic's stop decision but providing corroboration/precision for
    #    a *future* feature (e.g. sweep-and-pick-open-side in plan 01-03) inside this band,
    #    not for the binary stop/clear decision itself.
    return "STOP"
```

**Key implication of this sketch:** given spike 002's finding that ultrasonic is accurate
across its *entire* tested range including the 20-35cm ambiguous band, VL53L1X cannot
actually *relax* a stop decision ultrasonic already made -- it can only ever agree or get
ignored (steps 2-3 both fall back to ultrasonic's STOP on any doubt). Its practical value
isn't in the binary walk/stop decision at all; it's as a **precision input for a future
directional decision** (e.g. "which way is more open" for plan 01-03's sweep/turn logic),
where its near-field mm-resolution is a genuine advantage ultrasonic's cm-resolution
doesn't offer. This should be surfaced as an open question for whoever plans 01-03: is
VL53L1X worth the integration complexity for a directional-precision assist, given it
provides no additional stop/clear safety margin over ultrasonic alone?
