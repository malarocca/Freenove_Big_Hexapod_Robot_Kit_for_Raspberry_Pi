---
phase: 01-auto-mode-core-walk-avoid
plan: 01
subsystem: robotics
tags: [autonomy, tcp-protocol, gpiozero, ultrasonic, gait, hysteresis]

requires: []
provides:
  - "CMD_AUTO#1/#0 wire protocol — hexapod walks/stops autonomously with no client GUI involved"
  - "SensorHub — no-echo-honest ultrasonic reads via a passive gpiozero._read() capture wrapper, no second poller thread"
  - "AutoModeController — three-state hysteresis walk/stop decision loop, bounded 300s runtime halt, manual-command preempt, settle-to-stance"
  - "Fixed dead TCP reconnect path (reset_server() now actually runs)"
affects: [01-02-auto-mode-client-gui, 01-03-real-avoidance-sweep-turn]

tech-stack:
  added: []
  patterns:
    - "Passive read-capture (monkeypatch gpiozero's own _read()) instead of a second polling thread, to avoid GPIO timing contention (12a7fda)"
    - "Three-state hysteresis (STOP_THRESHOLD_CM=20 / RESUME_THRESHOLD_CM=35) instead of single-threshold stop/clear, to prevent flicker-induced contact (ff87cda)"

key-files:
  created:
    - Code/Server/autonomy/__init__.py
    - Code/Server/autonomy/settings.py
    - Code/Server/autonomy/perception.py
    - Code/Server/autonomy/behavior.py
  modified:
    - Code/Server/command.py
    - Code/Server/control.py
    - Code/Server/server.py
    - Code/Server/main.py

key-decisions:
  - "Fixed the step-4 obstacle-contact finding live rather than deferring to plan 01-03, since actual physical contact occurred during testing and CLAUDE.md's core value (never crash into things) is non-negotiable (D-06 pulled forward)."
  - "Re-verified that fix on this session's resume (2026-08-26) rather than trusting the unverified code from 2026-08-08 — confirmed live, no contact across two repeated hold/remove cycles."
  - "Step 8 (bounded 300s halt) verified via a naturally-occurring real-timer firing during the session rather than the plan's suggested shortened 30s override — direct evidence at the production value, no settings.py edit/restart needed."

patterns-established:
  - "Live hardware checkpoints for this phase use a FIFO-backed persistent socket client (scratchpad, not committed) so the walkthrough can proceed command-by-command across a multi-turn conversation instead of a one-shot script."

requirements-completed: [AUTO-02, AUTO-03, SENSE-01, CAUTION-01]

duration: ~25min (this session's portion; original Tasks 1-2 + step 1-3/6 verification were 2026-08-08)
completed: 2026-08-26
---

# Phase 01, Plan 01-01: Walking Skeleton Summary

**CMD_AUTO wire command drives autonomous walk/stop with hysteresis-based obstacle avoidance, verified live against real hardware across two sessions.**

## Performance

- **Duration:** Tasks 1-2 + partial Task 3 walkthrough: 2026-08-08. Task 3 completion (steps 4-9 + supplementary CMD_BALANCE variant): 2026-08-26, ~25 min.
- **Started:** 2026-08-08 (Tasks 1-2)
- **Completed:** 2026-08-26T05:00:00.000Z
- **Tasks:** 3 (all complete)
- **Files modified:** 8

## Accomplishments

- Hexapod walks and stops fully autonomously over the existing TCP command socket (`CMD_AUTO#1`/`#0`), with no client GUI required — verified live.
- Obstacle-stop hysteresis fix (`ff87cda`, pulling D-06 forward from plan 01-03) re-verified live this session: held a box at ~15cm twice, clean stop-and-settle both times, **zero contact** — this closes out the one real safety gap found during the original 2026-08-08 checkpoint.
- Full 9-step hardware checkpoint now passed end-to-end, plus a supplementary `CMD_BALANCE#1` manual-override variant.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the autonomy package** - `cdf822c` (feat)
2. **Task 2: Wire CMD_AUTO into the server, interruptible run_gait, fix dead TCP reconnect** - `ba4efbb` (feat)
3. **Task 3: On-device walkthrough** - live-verified across two sessions; fixes landed as `ff87cda` (fix, hysteresis) and `12a7fda` (fix, dual-poller GPIO contention)

**Plan metadata:** this commit (docs: complete plan 01-01)

## Files Created/Modified
- `Code/Server/autonomy/__init__.py` - package marker
- `Code/Server/autonomy/settings.py` - all auto-mode tunables (thresholds, timing, pan/tilt safety window)
- `Code/Server/autonomy/perception.py` - `SensorHub`, passive ultrasonic read capture
- `Code/Server/autonomy/behavior.py` - `AutoModeController`, hysteresis decide loop, bounded-runtime timer
- `Code/Server/command.py` - `CMD_AUTO` constant
- `Code/Server/control.py` - `run_gait` manual-interrupt support (`manual_preempt` event)
- `Code/Server/server.py` - `CMD_AUTO` dispatch, malformed-payload rejection, unsolicited status push, TCP reconnect fix
- `Code/Server/main.py` - wiring for the above at server construction

## Decisions Made

- Fix-now (not defer to 01-03) for the step-4 obstacle-contact finding — see `key-decisions` above.
- Step 8 satisfied via natural observation of the real 300s timer rather than a shortened synthetic test — equally valid evidence, avoids an unnecessary settings edit + server restart mid-checkpoint.

## Deviations from Plan

None beyond the already-recorded D-06 pull-forward (documented in the plan's own must_haves as an anticipated, not accidental, deviation) and the dual-poller fix (`12a7fda`), which corrected a bug the pulled-forward hysteresis change exposed (a second ultrasonic poller thread corrupting GPIO pulse-width timing) — not a scope change, a correctness fix for the walking-skeleton's existing sensor read path.

## Issues Encountered

- **2026-08-08:** Original ultrasonic sensor hardware faulted (dislodged transducer dish) mid-checkpoint, unrelated to this plan's code — required physical hardware repair (user replaced the sensor) before the walkthrough could resume. This also triggered a substantial side-track: a 4-spike VL53L1X-vs-ultrasonic evaluation (`.planning/spikes/001-004`), run to decide whether a newly-installed second sensor should change this plan's sensor architecture. Verdict: no — ultrasonic stays primary/sole sensor for this plan, VL53L1X evaluation is fully separate from and does not block this plan (see `.planning/seeds/SEED-001-vl53l1x-tof-sensor.md`).
- **2026-08-26 (this session):** No blocking issues. Walked through steps 4-9 command-by-command using a FIFO-backed persistent socket client script (scratchpad-only, not committed) to allow multi-turn live interaction within the conversation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Wave 2 (plan 01-02, client GUI auto-mode toggle + status badge) and Wave 3 (plan 01-03, real avoidance sweep/turn — note the hysteresis piece originally scoped for 01-03 was already pulled forward into this plan via `ff87cda`, so 01-03's remaining scope is narrower: sweep + pick-open-side + turn).

Two non-blocking observations from this session's live testing, worth a follow-up (not part of this plan's scope):
- Gait stance looks lower/more dragging than expected during autonomous walking — may need a stance-height parameter or the client's "raise up" equivalent; same `run_gait` code path as manual teleop, so not autonomy-specific.
- One leg sits slightly off the ground during `CMD_BALANCE#1` stance — likely needs `Code/Client/Calibration.py`-driven recalibration of `point.txt` leg offsets.

---
*Phase: 01-auto-mode-core-walk-avoid*
*Completed: 2026-08-26*
