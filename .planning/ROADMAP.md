# Roadmap: Autonomous Hexapod

## Overview

The hexapod goes from purely teleoperated to genuinely autonomous in four end-to-end, hardware-testable increments. Phase 1 stands up the entire sense→decide→act→arbitrate→lifecycle pipeline at once, in its simplest form: toggle auto mode from the client, walk forward, sense obstacles via head-sweep ultrasonic, stop-and-turn away from them, always yield instantly to manual input, and stop automatically after a bounded time. That thin vertical slice is the whole core value ("moves around without crashing into things") proven live on the robot before anything else is added. Phase 2 deepens that same loop so it holds up over repeated real-world encounters — varied evasive turns, stuck-recovery escalation, proximity-based slowdown — and adds a second reactive behavior, wall/boundary-follow patrol, built on the same foundation. Phase 3 layers pet/kid-safety-specific perception (camera motion detection) and physical status signaling (LED/buzzer) onto the now-proven core. Phase 4 closes the loop with client-side tunability and decision logging, so every threshold and behavior from the prior three phases can be adjusted and audited from real runs without a code redeploy.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Auto-Mode Core — Walk & Avoid** - Robot can be toggled into auto mode, walks forward, senses and avoids obstacles with an ultrasonic head-sweep, always yields instantly to manual input, and stops itself after a bounded duration
- [ ] **Phase 2: Behavior Expansion — Robust Avoidance & Patrol** - Avoidance holds up over repeated encounters (varied turns, stuck escalation, proximity slowdown) and the robot can perform reactive wall/boundary-follow patrol
- [ ] **Phase 3: Pet/Kid Safety & Status Signaling** - Camera-based motion detection adds extra caution around moving obstacles, and the robot's own LED/buzzer visibly communicates auto-mode status
- [ ] **Phase 4: Tuning & Observability** - User can retune auto-mode parameters from the client without a redeploy, and every auto-mode decision is logged for later analysis

## Phase Details

### Phase 1: Auto-Mode Core — Walk & Avoid

**Goal**: Robot can be toggled into/out of auto mode from the desktop client and, while active, walks forward and reactively avoids obstacles using the head-mounted ultrasonic sensor — the smallest possible end-to-end slice of the core value ("moves around without crashing into things"), safe by construction (instant manual override, bounded runtime, unknown-readings never treated as clear).
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: AUTO-01, AUTO-02, AUTO-03, AUTO-04, SENSE-01, SENSE-02, AVOID-01, CAUTION-01
**Success Criteria** (what must be TRUE):

  1. Toggling auto mode from the client starts the robot walking forward on its own, and the client UI shows a visible "auto mode active" indicator while it runs
  2. Sending any manual command (e.g. an arrow-key move) while auto mode is active immediately stops autonomous motion and hands control back to the user, with no wait for the current autonomous action to finish
  3. Placing an object in the robot's path causes it to stop, sweep its head across multiple bearings, and turn toward the more-open direction — a no-echo/missing ultrasonic reading is never treated as "clear," and a close-range reading is always treated as "stop and reassess," never "nudge past"
  4. Left running unattended, auto mode automatically halts on its own after the configured duration, settling into a stable stance rather than stopping mid-stride

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Walking Skeleton: CMD_AUTO lifecycle, autonomy package, no-echo-honest sensing, interruptible gait, D-01 reconnect fix

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02-PLAN.md — Desktop client Auto Mode toggle and always-visible status badge

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-03-PLAN.md — Three-bearing head sweep, CLEAR/CAUTION/BLOCKED hysteresis, ~45° evasive turn

**UI hint**: yes

### Phase 2: Behavior Expansion — Robust Avoidance & Patrol

**Goal**: The walk-and-avoid loop from Phase 1 holds up under real, repeated use — no bounce-loop oscillation, a distinct recovery when genuinely stuck, and speed that tapers as obstacles approach — and the robot gains a second reactive auto-mode behavior, boundary/wall-follow patrol, exercised live against real walls and furniture.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: AVOID-02, AVOID-03, AVOID-04, PATROL-01
**Success Criteria** (what must be TRUE):

  1. Repeatedly placing the same obstacle in the robot's path produces varied evasive turn angles/directions across events, rather than the robot bouncing between the same two turns
  2. After several consecutive avoidance events in a short window, the robot switches to a visibly different "stuck" recovery maneuver instead of repeating the same turn
  3. As the robot approaches an obstacle it visibly slows its gait before stopping rather than moving at full speed until a binary stop (or, if the gait engine doesn't support variable step speed, this is confirmed and documented as an accepted binary-stop fallback during planning)
  4. Placed near a wall or boundary in auto mode, the robot follows it forward while maintaining a roughly constant standoff distance to one side, with no map or waypoints involved

**Plans**: TBD

### Phase 3: Pet/Kid Safety & Status Signaling

**Goal**: Auto mode behaves cautiously around unpredictable moving obstacles (pets/kids) using the camera, distinct from its reaction to static obstacles, and the robot's own onboard LED/buzzer visibly communicates its auto-mode status without requiring the user to look at the client screen.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CAUTION-02, AUTO-05, CONFIG-02
**Success Criteria** (what must be TRUE):

  1. Moving toward the robot (e.g. walking or waving a hand into frame) while it's in auto mode triggers an extra pause/backoff via camera-based frame-differencing motion detection, even in situations where the static ultrasonic threshold alone wouldn't have triggered it
  2. The robot's physical LED/buzzer visibly changes between at least three distinct states: auto-mode active, obstacle detected, and paused for caution
  3. The user can enable, disable, and adjust the LED/buzzer indicator's behavior via the same client-side configuration mechanism, with the change taking effect without a code redeploy

**Plans**: TBD

### Phase 4: Tuning & Observability

**Goal**: Every tunable auto-mode parameter established in Phases 1-3 (duration, patrol side, caution sensitivity/thresholds) can be adjusted from the client without a code redeploy, and every auto-mode decision (what triggered each stop/turn/patrol correction, and when) is logged so behavior can be tuned against real runs.
**Mode:** mvp
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: CONFIG-01, CONFIG-03
**Success Criteria** (what must be TRUE):

  1. From the desktop client, the user can change auto-mode duration, patrol side, and caution sensitivity/thresholds, and see the robot's live behavior reflect the new values on the next run, with no code redeploy
  2. After an auto-mode run, a log exists that records what triggered each stop/turn/patrol correction and when, in enough detail to reconstruct the run's decision sequence for later tuning

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Auto-Mode Core — Walk & Avoid | 1/3 | In Progress|  |
| 2. Behavior Expansion — Robust Avoidance & Patrol | 0/TBD | Not started | - |
| 3. Pet/Kid Safety & Status Signaling | 0/TBD | Not started | - |
| 4. Tuning & Observability | 0/TBD | Not started | - |
