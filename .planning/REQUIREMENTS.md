# Requirements: Autonomous Hexapod

**Defined:** 2026-08-06
**Core Value:** The hexapod can move around on its own without crashing into things, pets, or kids.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Auto-Mode Lifecycle

- [ ] **AUTO-01**: User can toggle the robot into/out of auto mode from the desktop client
- [ ] **AUTO-02**: Any manual command from the client immediately preempts auto mode and returns control to manual, with no delay waiting for the current autonomous action to finish
- [ ] **AUTO-03**: Auto mode automatically stops after a bounded duration, returning the robot to a safe/stable stance (not halting mid-stride)
- [ ] **AUTO-04**: Client UI displays a visible indicator when auto mode is active
- [ ] **AUTO-05**: Robot's LED/buzzer indicates auto-mode status (active / obstacle detected / paused for caution) using existing hardware

### Perception

- [ ] **SENSE-01**: Robot detects obstacles ahead using the ultrasonic sensor while in auto mode, treating a no-echo/missing reading as "unknown," never as "clear"
- [ ] **SENSE-02**: Robot sweeps the head (pan servo) across multiple bearings to pick the most-open direction before deciding a move, rather than relying on a single fixed-forward reading

### Obstacle Avoidance

- [ ] **AVOID-01**: Robot stops and turns away when an obstacle is detected within a defined distance threshold, using a stop-and-turn state machine (clear / caution / blocked) with hysteresis to avoid thrashing
- [ ] **AVOID-02**: Robot varies its evasive turn angle/direction across repeated avoidance events so it doesn't get stuck oscillating between two obstacles
- [ ] **AVOID-03**: Robot recognizes repeated consecutive avoidance events and escalates to a different recovery behavior ("stuck" detection)
- [ ] **AVOID-04**: Robot slows down progressively as it approaches an obstacle rather than only doing a binary stop (contingent on the gait engine supporting variable step speed — verify during planning; fall back to binary stop if not feasible)

### Patrol

- [ ] **PATROL-01**: In auto mode, robot performs a reactive wall/boundary-follow patrol, maintaining a roughly constant distance to one side rather than wandering aimlessly — no map, no waypoints, no return-to-start

### Pet/Kid Safety

- [ ] **CAUTION-01**: Any close-range sensor reading during auto mode is treated as "stop and reassess," never "nudge past"
- [ ] **CAUTION-02**: Robot uses camera-based motion detection (frame differencing, not classification) to add extra pause/backoff when something is moving toward it, distinct from a static obstacle

### Tuning & Observability

- [ ] **CONFIG-01**: User can adjust auto-mode parameters (duration, patrol side, caution sensitivity/thresholds) from the client without a code redeploy
- [ ] **CONFIG-02**: User can enable/disable and adjust the LED/buzzer status indicator's behavior via the same configuration mechanism (not hardcoded always-on)
- [ ] **CONFIG-03**: Auto-mode decisions (what triggered each stop/turn/patrol correction, and when) are logged for later tuning against real runs

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Standalone Operation

- **STANDALONE-01**: Robot can boot directly into auto mode without the desktop client being connected at all (headless trigger)

### AI-Piloted Control

- **AIPILOT-01**: A real-time loop where Claude consumes live camera + sensor telemetry and directly pilots the robot for specific tasks, replacing the reactive decision logic via the `decide(snapshot) -> Intent` seam
- **AIPILOT-02**: Voice/audio interaction with the robot (speech recognition + audio output), contingent on adding microphone/speaker hardware

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| SLAM / occupancy-grid mapping | No odometry or localization exists in the codebase; a hexapod's leg-based motion makes dead reckoning unreliable without significant added work |
| Waypoint navigation / return-to-start | Requires a coordinate frame and localization, neither of which exist |
| Coverage-path planning ("mow the lawn" patrol) | Requires a map or reliable odometry to know what's already been covered |
| Persistent environment memory across auto-mode runs | No suitable persistence layer exists; re-introduces a map by the back door |
| ML-based object/person/pet classification | Out of proportion to a v1 safety feature; motion detection alone satisfies the caution requirement — classification is deferred to the future AI-piloting milestone |
| New sensor hardware (LiDAR, IR array, second ultrasonic, depth camera) | Explicit constraint: must work with what exists today (ultrasonic + camera on the pan/tilt head) |
| Networked/remote e-stop command | Explicitly decided against for v1; physical/local access plus bounded auto-mode duration is the safety net |
| Full 360° situational awareness | The sensor is fixed to a forward-mounted pan/tilt head with a limited practical sweep arc; can't see behind or reliably to the sides while moving |
| General-purpose behavior-tree framework | A small, purpose-built state machine is sufficient for the behaviors required; a generalized framework is speculative infrastructure |
| Authenticating/hardening the TCP command protocol | Known issue (unauthenticated socket), but not this milestone's focus unless it becomes a safety blocker |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTO-01 | Phase 1 | Pending |
| AUTO-02 | Phase 1 | Pending |
| AUTO-03 | Phase 1 | Pending |
| AUTO-04 | Phase 1 | Pending |
| AUTO-05 | Phase 3 | Pending |
| SENSE-01 | Phase 1 | Pending |
| SENSE-02 | Phase 1 | Pending |
| AVOID-01 | Phase 1 | Pending |
| AVOID-02 | Phase 2 | Pending |
| AVOID-03 | Phase 2 | Pending |
| AVOID-04 | Phase 2 | Pending |
| PATROL-01 | Phase 2 | Pending |
| CAUTION-01 | Phase 1 | Pending |
| CAUTION-02 | Phase 3 | Pending |
| CONFIG-01 | Phase 4 | Pending |
| CONFIG-02 | Phase 3 | Pending |
| CONFIG-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17 (100%)
- Unmapped: 0

---
*Requirements defined: 2026-08-06*
*Last updated: 2026-08-05 after roadmap creation*
