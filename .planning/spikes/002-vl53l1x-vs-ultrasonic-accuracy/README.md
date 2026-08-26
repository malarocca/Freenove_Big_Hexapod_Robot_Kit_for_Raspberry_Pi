---
spike: 002
name: vl53l1x-vs-ultrasonic-accuracy
type: comparison
validates: "Given both sensors aimed at the same target at fixed distances (10/20/30/50/100cm), when read side-by-side, then measure each sensor's accuracy, noise, and effective range"
verdict: PARTIAL
related: [001]
tags: [hardware, comparison]
---

# Spike 002: VL53L1X vs. Ultrasonic Accuracy

## What This Validates

Given both sensors aimed at the same target at known tape-measured distances, when read
side by side, then measure each sensor's accuracy, noise, and effective range.

## How to Run

```
cd .planning/spikes/002-vl53l1x-vs-ultrasonic-accuracy
sudo python3 -u test_compare.py                # both sensors, medium mode, live comparison
sudo python3 -u test_longmode_farrange.py      # VL53L1X alone, long mode, default (~33ms) budget
sudo python3 -u test_longmode_longbudget.py    # VL53L1X alone, long mode, 140ms budget
```

## Investigation Trail

1. **Dual-sensor comparison** (`test_compare.py`, medium mode) at tape-measured 10/20/30/50/100cm:
   - **Ultrasonic tracked ground truth well across the whole range**: ~9-10cm, ~19-20cm,
     ~29-30cm, ~45-51cm, ~92-99cm at each respective mark (a useful side-confirmation that
     the replacement ultrasonic sensor, see prior HANDOFF hardware-fault history, is fully
     functional and accurate).
   - **VL53L1X agreed closely with ultrasonic from 10cm to 50cm**, consistently reading
     ~2-3cm farther than the ultrasonic at each mark (~125-136mm at the 10cm mark,
     ~218-238mm at 20cm, ~316-326mm at 30cm, ~451-499mm at 50cm) — consistent with the
     VL53L1X's physical mount position sitting a few cm behind the ultrasonic on the shared
     pan/tilt head, not a real disagreement.
   - **At the 100cm mark, VL53L1X failed badly**: while ultrasonic correctly read ~92-99cm,
     VL53L1X locked onto a stable `Range Valid` reading of only ~20-27cm — a confidently
     wrong result, not an honest failure code.
2. **Ruled out interference from the ultrasonic sensor**: reproduced the same false-close
   reading with the VL53L1X running completely standalone (ultrasonic not even instantiated).
   Not electrical/I2C crosstalk between the two sensors.
3. **Ruled out beam-divergence/field-of-view capturing a nearer object**: reproduced in an
   open area with nothing else near the sensor's line of sight. Not a stray-reflector problem.
4. **Characterized the failure as range-dependent, not distance-independent**
   (`test_longmode_farrange.py`, long mode, default ~33ms timing budget): starting the target
   at a true 100cm and slowly bringing it toward the sensor, readings stayed falsely low
   (~167-294mm) until the target passed roughly the 50-55cm true-distance mark, at which point
   the reading suddenly jumped to a correct value (~554mm) and then tracked perfectly,
   monotonically, all the way down to point-blank range. This is consistent with a classic
   ToF **phase wrap-around** artifact: past a certain range the return signal gets too weak
   for the sensor's phase-based distance calculation to stay unambiguous, and it aliases to a
   shorter apparent distance while still reporting `Range Valid`.
5. **Tried the standard mitigation**: ST's guidance for weak-signal-at-range is a longer
   integration/timing budget. Raised it from the ~33ms default to 140ms
   (`tof.set_timing(140000, 150)`, `test_longmode_longbudget.py`) and repeated the same
   100cm-in-and-out sweep. Result: the dangerous discontinuous jump disappeared — the reading
   now rose and fell **smoothly and monotonically** with no error frames at all across the
   full 65-second sweep — but it still topped out at a max of ~589mm (58.9cm) even though the
   target was tape-measured out to a true 100cm. The failure mode improved (predictable
   saturation near a ceiling, always erring toward reporting things as closer than they are,
   never farther) but the underlying range limitation did not go away.

## Results

**Verdict: PARTIAL.** The VL53L1X and ultrasonic sensors are both working hardware with no
wiring/connection faults (see spike 001) — this is a genuine sensing-capability difference,
not a defect to fix.

- **Ultrasonic**: accurate across the full tested range, 10cm-100cm+.
- **VL53L1X**: accurate and in good agreement with ultrasonic (±2-3cm, explained by mount
  offset) from roughly 10cm out to ~50-60cm. Beyond that, in this physical setup/lighting/
  target reflectivity, it cannot reliably resolve true distance — it either falsely aliases to
  a much shorter reading (default timing budget) or smoothly saturates near an effective
  ceiling around 55-60cm (extended 140ms timing budget). Its failure direction is
  safety-conservative (always reports "closer than reality," never "farther/clear when it
  isn't") but this would make an autonomous walker built on VL53L1X-as-primary see a phantom
  obstacle at every distance beyond ~60cm, which would cripple normal walking rather than
  just make it cautious.
- The VL53L1X's real strength shown here is **near-field precision** (mm-resolution, tight
  agreement with ground truth inside ~60cm) — not long-range coverage.

## Signal for Later Spikes / the Real Build

**This inverts SEED-001's original framing.** The seed assumed VL53L1X would become the
primary sensor with ultrasonic demoted to fallback. The evidence here points the other way:
**ultrasonic should stay primary for range coverage** (it's the only one of the two that
reliably covers the 60cm-100cm+ band where early obstacle warning matters most for a walking
robot), with **VL53L1X potentially valuable as a high-precision near-field cross-check**
inside the zone where it's proven accurate (~60cm and under) — which happens to overlap
exactly with the existing stop-threshold band (`STOP_THRESHOLD_CM`/`RESUME_THRESHOLD_CM` in
`autonomy/behavior.py`, 20-35cm) where ultrasonic's own known weakness against soft/angled/
low-profile surfaces is most safety-critical. Spike 003 (failure modes on real household
surfaces) and spike 004 (integration/arbitration) should be designed around this
near-field-cross-check framing, not a wholesale sensor swap.

If VL53L1X integration proceeds, any production use must include the `open(reset=True)`
requirement from spike 001, and should default to a long-ish timing budget (100-150ms range)
given the smoother, more predictable failure behavior it produced here — never the untuned
default.
