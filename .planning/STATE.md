---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 01 Plan 01-01 COMPLETE and merged; Wave 2 (plan 01-02, client GUI) not yet started
last_updated: "2026-08-26T05:05:00.000Z"
last_activity: 2026-08-26 -- Plan 01-01 Task 3 hardware walkthrough finished live (steps 4-9 + CMD_BALANCE variant, all passed), worktree merged to autonomy, worktree removed
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
  percent: 8
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-06)

**Core value:** The hexapod can move around on its own without crashing into things, pets, or kids.
**Current focus:** Phase 01 — auto-mode-core-walk-avoid (Plan 01-01 complete; Wave 2 / plan 01-02 next)

## Current Position

Phase: 01 (auto-mode-core-walk-avoid) — EXECUTING
Plan: 1 of 3 (01-01 "Walking Skeleton") — COMPLETE, merged to `autonomy` (commit `db67780`)
Status: Plan 01-01 fully done. All four implementation commits (`cdf822c`, `ba4efbb`,
`ff87cda` hysteresis, `12a7fda` dual-poller GPIO contention) merged from the worktree branch
`worktree-agent-ab149f1102043bce0` (now deleted, along with its worktree). Task 3's 9-step
hardware checkpoint passed end-to-end live on 2026-08-26: steps 1,2,3,6 (passed 2026-08-08),
step 4 re-verified with the hysteresis fix in place (two hold/remove cycles, zero contact),
step 5 (no-echo -> stop), step 7 (malformed CMD_AUTO rejected), step 8 (300s bounded halt,
observed via a naturally-occurring real timer firing, not the plan's shortened-timer
suggestion), step 9 (disconnect/reconnect sync). A supplementary CMD_BALANCE#1
manual-override variant was also verified. SUMMARY.md written and merged
(`.planning/phases/01-auto-mode-core-walk-avoid/01-01-SUMMARY.md`).
Next: Wave 2 (plan 01-02, client GUI Auto Mode toggle + status badge) — not yet started.
Last activity: 2026-08-26 -- Task 3 walkthrough completed, worktree merged and cleaned up

Progress: [█░░░░░░░░░] 8% (1 of 3 plans in Phase 01 complete; 0 of 4 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Reshaped research's horizontal layer sequence (perception → decision → arbitration → protocol wiring → polish) into 4 vertical MVP slices, each end-to-end testable on real hardware; Phase 1 stands up the full sense-decide-act-arbitrate-lifecycle pipeline minimally rather than building layers in isolation.
- [Roadmap]: CAUTION-01 (close-range → stop and reassess) folded into Phase 1 with AVOID-01, since it's the same stop-on-close-range decision logic, not a separate increment.
- [Roadmap]: CONFIG-01/CONFIG-03 (tuning + logging) placed last (Phase 4) since they parameterize/observe behavior established across all three prior phases.
- [2026-08-08]: Original ultrasonic sensor failed physically (dislodged transducer dish); user replaced it and additionally installed a VL53L1X ToF sensor, asking whether it should become the primary obstacle sensor (SEED-001 planted).
- [2026-08-26, INVERTS the above]: A 4-spike evaluation track (`.planning/spikes/001-004`) found the opposite of SEED-001's original assumption: **ultrasonic stays primary** (accurate across its full 10-100cm+ range, no surface-specific failure mode found against soft/angled/low-profile targets). **VL53L1X is at best a near-field (<=20-30cm) corroboration input** — reliable only to ~50-60cm, with instability that's range-triggered rather than surface-triggered, and a `Range Valid` status alone isn't trustworthy (one 0mm-while-"valid" reading observed). No dual-sensor contention when running both concurrently (empirically verified). SEED-001 updated accordingly (commit `d49f7fc`); CLAUDE.md's "ultrasonic + camera only, no new sensors" constraint has NOT yet been updated to reflect this decision either way — VL53L1X integration is still an open product-scope call, not a settled plan.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2 planning]: Gait engine variable-speed support (AVOID-04) is unverified — check `control.py`/`run_gait` during Phase 2 planning; fall back to binary stop if not feasible.
- [Phase 1 planning]: `command_queue` locking/arbitration strategy (lock vs. Queue refactor) is an unresolved design decision — research flags this as the highest-risk integration point; resolve during Phase 1 planning, not deferred.
- ~~[Phase 1 planning]: TCP reconnect dead-code bug undermines "manual override always available"~~ — **RESOLVED**, fixed in `ba4efbb`, merged to `autonomy` 2026-08-26.
- ~~[Phase 1/2]: Real-world ultrasonic behavior against soft/angled/low-profile obstacles is unvalidated~~ — **RESOLVED by spike 003** (2026-08-26): no surface-specific failure mode found; ultrasonic tracked pillow/blanket, angled hard, and low-profile targets accurately across the full tested range.
- ~~[Phase 01 Plan 01-01 Task 3]: On-device hardware walkthrough is still incomplete~~ — **RESOLVED 2026-08-26**: all 9 steps passed live, plan merged.
- ~~[Phase 01 Plan 01-01]: Worktree branch unmerged~~ — **RESOLVED**: merged to `autonomy` (`db67780`), worktree and branch removed.
- [SEED-001, open product-scope question]: Given VL53L1X can't improve stop/clear safety margin over ultrasonic alone (per the spike track), is the integration complexity worth it purely for a directional-precision assist (e.g. future plan 01-03 sweep/pick-open-side logic)? Not yet decided.
- [New, 2026-08-26 live testing]: Gait stance looks lower/more dragging than expected during autonomous walking — not autonomy-specific (same `run_gait` code path as manual teleop), worth a look during Phase 2 gait-quality work.
- [New, 2026-08-26 live testing]: One leg sits slightly off the ground during `CMD_BALANCE#1` stance — likely needs `Code/Client/Calibration.py`-driven recalibration of `point.txt` leg offsets. Not blocking, not caused by this phase's code.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-08-26T05:05:00.000Z
Stopped at: Phase 01 Plan 01-01 complete and merged. Next up: plan 01-02 (Wave 2, client GUI Auto Mode toggle + status badge) -- not yet started, no blockers.
Resume file: .planning/phases/01-auto-mode-core-walk-avoid/01-02-PLAN.md (Wave 2 plan, ready to execute); .planning/phases/01-auto-mode-core-walk-avoid/01-01-SUMMARY.md for what Wave 1 delivered; .planning/phases/01-auto-mode-core-walk-avoid/.continue-here.md is now stale (describes the just-finished Task 3 walkthrough) and should be refreshed or retired at the start of the next session.
