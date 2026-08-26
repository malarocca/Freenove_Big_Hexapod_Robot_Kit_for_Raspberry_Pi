---
id: SEED-001
status: dormant
planted: 2026-08-08
planted_during: v1.0 / Phase 01 (auto-mode-core-walk-avoid)
trigger_when: (fired 2026-08-25/26, see Update below) originally: when the user reports the replacement ultrasonic sensor has arrived and been installed. Next trigger: when the user is ready to make the product-scope call in the Update section (directional-precision-only VL53L1X — build it or archive this seed), or during Phase 01-03 planning (sweep/pick-open-side logic) where VL53L1X's remaining plausible use case actually lives; also surface during any /bm:new-milestone scan for sensing/perception scope
scope: medium
---

# SEED-001: Add a VL53L1X Time-of-Flight sensor as a replacement/complement for the ultrasonic sensor

## Why This Matters

The existing ultrasonic sensor (HC-SR04-style, `Code/Server/ultrasonic.py`) failed physically
mid-Phase-01 (a transducer dish was dislodged) — user is buying a cheap replacement. While
shopping for parts, the user asked whether to also add a LiDAR sensor, since GPIO capacity
looks available.

Two software fixes this session (hysteresis `ff87cda`, dual-poller GPIO contention `12a7fda`)
already worked around real bugs in how the ultrasonic sensor is polled, but the sensor's
underlying physics still have a known weakness already flagged as an open concern in
STATE.md: real-world ultrasonic behavior against soft/angled/low-profile obstacles
(pillows, rugs, furniture edges) is unvalidated and likely unreliable — ultrasonic echoes
bounce away from angled/absorbent surfaces rather than returning, common in a home with
pets and kids.

A **360-degree spinning LiDAR** (e.g. RPLIDAR A1, ~$99) was considered and **rejected** as a
recommendation: it draws ~500mA continuous plus motor spin-up, and its main payoff — building
an occupancy map — is unused because CLAUDE.md's project constraints explicitly rule out
SLAM/localization (reactive sensing only, no mapping).

A **directional VL53L1X Time-of-Flight sensor** (ST, I2C, ~$10, ~20mA active, up to 50Hz,
mm-precision, ~4m range) was recommended instead: it's a drop-in fit for the existing
single-sensor-on-pan/tilt-head architecture (same physical mounting pattern as today's
ultrasonic), doesn't share ultrasonic's soft/angled-surface weakness, and its own known
failure modes (glass/mirrors, extremely IR-absorptive black surfaces) are less common in a
home environment than ultrasonic's failure modes.

**Open question, resolved 2026-08-08, then INVERTED 2026-08-25/26 by live testing:** does the
VL53L1X *replace* the ultrasonic outright, or should both be kept? Claude's initial
recommendation was "replace, don't fuse" (simplicity, since both are single narrow-beam
sensors on the same panning head). At the time, the user preferred keeping the ultrasonic as
a failover — i.e. **VL53L1X as primary sensor, ultrasonic retained as fallback/cross-check**
for the ToF's known weak spots (glass/mirrors, very IR-absorptive black surfaces).

**This assumption did not survive contact with real hardware.** A 4-spike evaluation track
(`.planning/spikes/001-004`, see Update below) found the *opposite* is true: ultrasonic is
the more reliable sensor overall, and VL53L1X's usefulness is much narrower than assumed at
seed-planting time.

### Update 2026-08-25/26: Spike Track Findings (roles inverted)

Once the replacement ultrasonic *and* a newly-installed VL53L1X were both physically present,
this seed was worked as a proper `/bm:spike` track instead of jumping straight to
implementation. Full detail in `.planning/spikes/MANIFEST.md` and each spike's `README.md`;
summary:

- **Ultrasonic is accurate across its entire practical range (10cm-100cm+)** and showed *no*
  surface-specific failure mode when deliberately tested against soft fabric, angled hard
  surfaces, and low-profile targets (spike 003) — the soft/angled-surface weakness this seed
  was originally planted to solve did not reproduce under test.
- **VL53L1X is only reliable out to ~50-60cm** — beyond that it doesn't fail honestly, it
  reports a confident but wrong short distance (ToF phase wrap-around) (spike 002). Worse,
  spike 003 found its instability is **range-triggered, not surface-triggered**: clean at
  ~20cm for every surface tested including glass and dark cloth, but unstable at ~45cm for
  every surface including plain glossy material — including one `Range Valid`-status reading
  of literally 0mm. A `Range Valid` status alone is not sufficient to trust a reading.
- **No dual-sensor contention** running both concurrently (spike 004, empirically A/B
  tested, not just assumed) — so a dual-sensor design is technically clean to build, whenever
  it's decided to be worth building.
- **Net effect: the roles from the "resolved 2026-08-08" paragraph above are reversed.**
  Ultrasonic should stay **primary** across the full range. VL53L1X is at best a **near-field
  (<=20-30cm) precision corroboration input**, not a primary sensor and not really a
  "fallback" in the failover sense either — spike 004's arbitration sketch found it can only
  ever *agree with or defer to* ultrasonic's stop decision within the one band where it'd be
  consulted (the existing 20-35cm `STOP_THRESHOLD_CM`/`RESUME_THRESHOLD_CM` hysteresis band),
  never relax it. Its more plausible value is as a directional-precision assist for a
  *future* capability (e.g. plan 01-03's sweep/pick-open-side logic) rather than for the
  binary walk/stop decision this seed originally targeted.
- **Open question for whoever picks this seed up next:** given VL53L1X can't improve
  stop/clear safety margin over ultrasonic alone, is the integration complexity (new driver
  module, arbitration logic, CLAUDE.md constraint update) worth it purely for a directional-
  precision assist? That's a real product-scope call, not a technical unknown — the technical
  unknowns this seed originally carried (does it work, what breaks it, does it fight with
  ultrasonic for resources) are now all answered.

**Scope note:** Adding this sensor means updating CLAUDE.md's current stated hardware
constraint — "Obstacle sensing must work with what exists today — one ultrasonic sensor +
camera... No new sensors planned for v1." That's an explicit project-scope decision the user
has not yet made; this seed exists so it isn't forgotten, not to pre-decide it.

## When to Surface

**Trigger:** Ask the user about this the next time they report the replacement ultrasonic
sensor is installed (i.e., right when Phase 01 Plan 01-01 Task 3's hardware checkpoint is
about to resume) — don't wait for a full new-milestone cycle, this is timely while they're
already ordering hardware parts. Also surface normally during any `/bm:new-milestone` scan
touching sensing/perception scope, in case the near-term nudge is missed.

## Scope Estimate

**Medium, but narrower than originally scoped** — VL53L1X is now a corroboration input, not
a primary-sensor swap. Likely touches:
- A new driver module wrapping the already-installed `VL53L1X` Python package (Pimoroni;
  already present at `/usr/local/lib/python3.13/dist-packages/VL53L1X.py`, used as-is
  throughout spikes 001-004 — no new vendoring needed) — `tof.open(reset=True)`,
  `start_ranging(2)`, `tof.set_timing(140000, 150)` are the spike-validated init sequence.
- `Code/Server/autonomy/perception.py` (`SensorHub`, currently only in the unmerged worktree
  branch `worktree-agent-ab149f1102043bce0`) — **add** VL53L1X as a second, independently-
  polled input (spike 004 confirmed no contention running both concurrently), do not swap out
  ultrasonic. Real achievable poll rate is ~9.3Hz at the validated timing settings, not the
  naively-requested rate — budget accordingly.
- `Code/Server/autonomy/behavior.py` (or wherever `decide()` ends up) — implement spike 004's
  arbitration sketch: ultrasonic authoritative for STOP/CLEAR across the full range; VL53L1X
  consulted only inside the 20-35cm band, only trusted to <=30cm of its own reading, only on
  `Range Valid` status AND a plausibility/continuity check on the value (reject implausible
  jumps — spike 003 saw one `Range Valid`-status 0mm reading).
- `CLAUDE.md` constraint update (explicit scope decision, not just code) — still needed if
  adopted at all.
- Re-verification of the full Phase 01 Task 3 hardware checkpoint (steps 4/5/7/8/9 — still
  incomplete as of this writing) — this is independent of the VL53L1X decision and should
  happen regardless, now that the ultrasonic hardware itself is confirmed repaired.
- **Before any of the above:** resolve the open product-scope question from the Update above
  — is a directional-precision-only VL53L1X worth building at all, or does this seed get
  archived/deprioritized now that its original safety rationale (ultrasonic's soft/angled-
  surface weakness) didn't reproduce under test?

## Breadcrumbs

- `.planning/spikes/MANIFEST.md` and `.planning/spikes/001-004-*/README.md` — the full
  evaluation trail and evidence behind the Update above; read these before re-deriving
  anything about VL53L1X behavior.
- `.planning/spikes/004-dual-sensor-sensorhub-integration/README.md` — the arbitration sketch
  (illustrative pseudocode) to implement from, plus the achievable-poll-rate gotcha.
- `Code/Server/ultrasonic.py` — current `gpiozero.DistanceSensor` wrapper (trigger=GPIO27,
  echo=GPIO22); confirmed accurate across its full range and free of the soft/angled/low-
  profile failure modes this seed worried about (spike 003) — stays primary, unchanged.
- `Code/Server/autonomy/perception.py` (worktree branch `worktree-agent-ab149f1102043bce0`,
  not yet merged to `autonomy`) — `SensorHub`, the consumer of ultrasonic readings for the
  autonomy decision loop; the dual-poller fix (commit `12a7fda`) lives here, and is the
  reference point spike 004 re-tested against for the GPIO-contention question.
- `Code/Server/autonomy/settings.py` (same worktree) — `RESUME_THRESHOLD_CM`/
  `STOP_THRESHOLD_CM` (35/20), the existing band the arbitration sketch is designed around.
- `.planning/STATE.md` — "Real-world ultrasonic behavior against soft/angled/low-profile
  obstacles is unvalidated" (Blockers/Concerns) — spike 003 has now directly addressed this;
  STATE.md itself is stale (last updated 2026-08-07) and should be refreshed to reflect it.
- `CLAUDE.md` — "Hardware" constraint line to be updated if any VL53L1X integration proceeds.

## Notes

Captured live during a `/bm:resume-work` session (2026-08-08) while the user was mid-way
through diagnosing a physically broken ultrasonic sensor for Phase 01. User explicitly asked
to be reminded of this "when I come back with the new ultrasonic sensor" — treat that as the
primary trigger, ahead of any milestone-scan surfacing.
