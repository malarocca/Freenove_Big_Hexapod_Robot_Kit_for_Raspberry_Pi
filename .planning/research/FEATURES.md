# Feature Landscape

**Domain:** On-device autonomous "auto mode" for a hobbyist hexapod robot (reactive obstacle avoidance + boundary/wall-follow patrol), single ultrasonic + camera on a shared pan/tilt head, no SLAM/odometry, safety-sensitive (pets/kids present).
**Researched:** 2026-08-05

## How Hobbyist/Small-Robot Projects Typically Build This

Across Arduino/Raspberry-Pi obstacle-avoidance projects, wall-following research, and forks of this exact Freenove hexapod, the pattern is remarkably consistent and simple — because it has to be, with one distance sensor and no map:

1. **Threshold-based reactive state machine, not planning.** The overwhelming majority of hobbyist obstacle-avoidance robots (Arduino+HC-SR04 tutorials, Raspberry Pi ultrasonic-car tutorials) work off a small number of hand-tuned distance thresholds (e.g. "clear ahead," "obstacle getting close," "critical/too close") and map each zone directly to a movement action (go, slow+scan, stop+turn). No environment model is built or kept between decisions. (MEDIUM confidence, WebSearch cross-referenced with the pattern below.)
2. **Servo-swept single sensor as a poor-man's array.** Because one narrow-beam ultrasonic sensor only sees straight ahead, hobbyist builds mount it on a servo (here: the existing pan/tilt head) and sweep it left/center/right — or continuously while walking — to get several bearings per decision cycle, then pick the most-open direction. This is exactly the pattern already prototyped by a public fork of this Freenove Big Hexapod (`UEA-envsoft/FreenoveBigHexapod`), which modified `Control.py` to sweep the head and collect ultrasonic readings while moving, and used a `wander.py` script with tunable thresholds (`aheadClear`, `obstDanger`, plus edge/cliff thresholds not applicable here since this robot has no downward-facing sensor). (MEDIUM confidence — direct architectural precedent on this exact hardware, but the fork's author noted it was untested/needs tuning.)
3. **Reactive wall-following, not path planning.** The published pattern (bug-algorithm-style, fuzzy-logic wall followers) is: measure current distance to the wall/boundary, compare to a target set-point distance, steer proportionally (too close → steer away, too far → steer in) — a pure feedback loop with no map, exactly what "no SLAM" forces here. Reactive navigation deliberately never builds a representation of the walls/obstacles it has seen. (MEDIUM confidence, academic + tutorial sources agree.)
4. **Camera as a second, coarser sensor, not a depth sensor.** Hobbyist projects without stereo/depth cameras do not attempt real depth-from-vision; they use cheap monocular cues instead — frame differencing / optical flow to detect *motion* (something moving toward the robot) rather than to compute distance. This is the standard trick for "cheap camera + no depth hardware" setups, and it maps well onto detecting a pet or child moving into frame versus a static obstacle the ultrasonic already sees. (MEDIUM confidence.)
5. **Binary avoidance is the default; speed modulation is a step up.** Most tutorial-grade projects (Arduino obstacle cars) just stop-and-turn at a fixed threshold. More polished hobbyist and commercial (robot-vacuum-class) implementations instead *slow down progressively* as obstacles get closer and reserve a hard stop for the closest zone, and explicitly call out reacting differently to moving objects (pets, kids) versus static furniture — treating the "unpredictable and possibly not yet detected" case as the reason to be cautious rather than fast. (MEDIUM confidence, commercial robot-vacuum marketing/support content — directionally reliable on *behavioral intent* even if the underlying sensor stack, LiDAR/dual-RGB-AI, is far more advanced than this project's.)
6. **Real ultrasonic limitations shape the design, not just the algorithm.** Ultrasonic sensors have a narrow beam cone (blind to anything not roughly straight ahead), can miss soft/absorptive or steeply angled surfaces, and have a real "too close to measure" dead zone (~2cm) — this is *why* sweeping and pairing with a camera is the standard mitigation, not a nice-to-have. (HIGH confidence — well-documented sensor physics, consistent across sources.)

## Table Stakes

Features a hobbyist "auto mode" doesn't feel real without. Direct requirements from `.planning/PROJECT.md`'s Active list map almost 1:1 here.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Enter/exit auto mode from the client (explicit toggle) | Already a stated Active requirement; every hobbyist "auto mode" project has a clear on/off trigger (button, command) | Low | New `CMD_AUTO`-style command + a mode flag consumed by `Control.condition_monitor`; fits the existing command_queue dispatch pattern |
| Forward obstacle detection via ultrasonic before/while moving | The baseline behavior of literally every ultrasonic obstacle-avoidance tutorial found | Low–Med | Poll `Ultrasonic.get_distance()` on a cadence; gate forward gait commands on a "clear ahead" threshold |
| Head-sweep scan to pick a direction (not just stop) | Standard mitigation for single narrow-beam sensor's blind spot; directly precedented in the `UEA-envsoft/FreenoveBigHexapod` fork on this same kit | Med | Reuses existing `CMD_HEAD` servo control; sweep 2–3 fixed bearings (e.g. left/center/right), pick most-open reading |
| Stop-and-turn reactive avoidance state machine | Table stakes for "avoids obstacles" to be true at all; matches the threshold → action mapping seen across every source | Med | Small explicit state machine (clear / caution / blocked), not the existing string-membership `if/elif` style — avoid extending the God-object pattern further per architecture's own anti-pattern note |
| Reactive wall/boundary-follow patrol (maintain distance to one side, no map) | Explicit Active requirement; matches published "measure distance, steer to set-point" wall-follow pattern (bug-algorithm family) | Med–High | Depends on obstacle avoidance state machine existing first; hexapod turning-in-place vs. arcing affects how smooth the follow behavior can be — needs on-hardware tuning, not just algorithm |
| Bounded-duration auto-run with automatic stop | Explicit Active requirement; the project's stated safety net given no remote e-stop | Low | Simple timer alongside the mode flag; stop = return to a safe stance, not just halt mid-stride |
| Manual override always available (auto mode is preemptible) | Explicit Active requirement; also the standard hobbyist pattern (a manual-mode button/command always wins) | Low–Med | Requires any manual command arriving on the socket to immediately clear the auto-mode flag before the next `condition_monitor` tick — must not require waiting for the current auto-mode action to "finish" |
| Cautious (not aggressive) behavior near unpredictable movement — pets/kids | Explicit Active requirement, and the one place robot-vacuum industry practice is directly on point: slow/reroute near detected motion rather than push through | Med | Minimum viable version: treat *any* close-range reading as "stop and reassess" rather than "nudge past"; doesn't strictly require motion detection to satisfy "cautious," see Differentiators for the fuller version |
| Visible/legible "auto mode is active" state | Not explicitly called out in PROJECT.md but implicit — a person in the room needs to know the robot is about to move on its own, especially with kids/pets present | Low | Cheapest version: client UI label already showing telemetry; existing buzzer/LED hardware could double as a physical indicator (see Differentiators for a fuller version) |

## Differentiators

Nice-to-have polish beyond the minimum "it avoids things and follows walls" bar. None of these are required to satisfy PROJECT.md's Active requirements, but they materially improve safety/robustness within the *same* hardware constraint (no new sensors).

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Proximity-proportional speed modulation (slow down progressively, not binary stop) | Matches commercial best practice for safety around unpredictable movers; less jarring/startling near pets and kids than instant stop | Med | Needs the gait engine to accept a variable speed parameter — check `control.py`'s `run_gait` supports this before committing; if it only supports fixed-speed steps this becomes higher complexity |
| Motion-vs-static disambiguation using the camera (frame differencing/optical flow) | Lets "cautious around pets/kids" be a real behavioral distinction (extra pause/backoff for something moving toward the robot) rather than treating every obstacle identically | Med–High | Cheap frame-differencing is feasible on-Pi in real time; true optical flow may be too CPU-heavy for the Pi alongside gait control — validate compute budget during implementation, not here |
| Physical status indicator via existing LEDs/buzzer (auto-mode-active, obstacle-detected, paused-for-caution) | Improves the "no dedicated remote e-stop, rely on physical/local access" safety story — bystanders get an audible/visual cue the robot is in an unpredictable-behavior mode | Low–Med | Pure reuse of existing `Led`/`Buzzer` hardware classes; no new hardware or protocol beyond a few new LED/buzzer calls tied to mode-state transitions |
| Randomized/varied evasive turns to avoid getting stuck in a loop | Hobbyist wander-mode pattern (add randomness to turn angle/direction) prevents the classic "bounce between two obstacles forever" failure that a purely deterministic threshold rule can fall into | Low–Med | Pure software addition on top of the state machine; no new dependencies |
| Escalating recovery behavior after repeated consecutive avoidance events ("stuck" detection) | Catches the case where reactive rules alone oscillate or wedge the robot in a corner; still fully reactive (a counter, not a map) so stays inside the no-SLAM constraint | Med | Depends on the avoidance state machine already existing; needs a small consecutive-event counter, not persistent memory |
| Client-configurable auto-mode parameters (duration, patrol side, caution sensitivity) | Turns fixed thresholds (like the untested/needs-tuning ones in the precedent fork) into something adjustable without a code change/redeploy, useful given this is genuinely new, untested behavior on real hardware | Low–Med | Extends existing command protocol; must be added to both `Code/Server/command.py` and `Code/Client/Command.py` per architecture's documented duplication constraint |
| Session logging of auto-mode decisions (what triggered stop/turn/patrol-correction, when) | No logging framework exists today (architecture notes print-only diagnostics); even minimal structured logging of auto-mode transitions would materially help tuning thresholds against real runs | Low | Independent of the state machine's correctness; can be added incrementally, doesn't block v1 |

## Anti-Features

Deliberately NOT building these, given the explicit no-mapping/no-localization constraint and v1 safety scope. Building any of these would be over-engineering relative to what the sensors and codebase can actually support.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|---------------------|
| SLAM / occupancy-grid mapping | No odometry or localization exists anywhere in the codebase (confirmed in ARCHITECTURE.md and PROJECT.md); a hexapod's leg-based motion also makes wheel-odometry-style dead reckoning unreliable without significant added work — this is explicitly Out of Scope in PROJECT.md | Reactive wall-follow using live ultrasonic distance to a set-point only |
| Waypoint navigation / return-to-start | Requires a coordinate frame and localization, neither of which exist; explicitly Out of Scope in PROJECT.md | Time-boxed auto-run that returns to a *known safe stance*, not a *known place* |
| Coverage-path planning (e.g. boustrophedon "mow the lawn" patrol like robot vacuums use) | Requires either a map or reliable odometry to know what's already been covered; neither exists here | Reactive boundary-follow patrol only — "hug a wall/edge," not "systematically cover the room" |
| Persistent environment memory across auto-mode runs (e.g. remembering where obstacles were last time) | There is no persistence layer suited to this (only flat-file calibration/config exist) and it re-introduces a map by the back door | Every auto-mode session starts fresh and reacts to what it senses right now |
| ML-based object/person/pet classification (e.g. "is this specifically a dog vs. a chair leg") | Out of proportion to a v1 safety feature — real-time classification on-Pi alongside gait control is a meaningfully larger compute/complexity commitment than motion detection, and the requirement is "cautious around unpredictable movement," not "identify what it is" | Camera-based *motion* detection (has something changed/moved in frame) is enough to satisfy the caution requirement; save classification for the explicitly-deferred future AI-piloting milestone |
| New sensor hardware (LiDAR, IR array, second ultrasonic, depth camera) | Explicit constraint: "must work with what exists today," no new sensors planned for v1 | Get more out of the existing ultrasonic+camera pair via head-sweeping and motion cues, as above |
| Networked/remote e-stop command | Explicitly decided against for v1 in PROJECT.md — physical/local access is the safety net, paired with bounded auto-mode duration | Keep manual-command-always-preempts-auto-mode as the override path, plus the runtime bound |
| Full 360° situational awareness / continuous omnidirectional obstacle field | The sensor is fixed to a forward-mounted pan/tilt head with a limited practical sweep arc — the robot cannot see behind or reliably to its sides while moving forward, no matter how the software is written | Design the caution behavior around the robot's real blind spots (e.g. move slowly enough, or pause-and-scan before executing turns) rather than pretending omnidirectional awareness exists |
| Multi-behavior arbitration framework / general-purpose behavior tree engine | A small explicit state machine (clear / caution / blocked / patrol) is sufficient for the two behaviors required (avoidance, wall-follow); a generalized framework is speculative infrastructure for behaviors not yet requested | Purpose-built state machine scoped to exactly the two behaviors in PROJECT.md's Active requirements |

## Feature Dependencies

```
Enter/exit auto mode (mode flag + command)
  → Forward obstacle detection (ultrasonic polling)
      → Head-sweep scan (reuses CMD_HEAD servo control)
          → Stop-and-turn reactive avoidance state machine
              → Reactive wall/boundary-follow patrol (extends the same state machine)
              → Escalating recovery / stuck detection (differentiator, extends the same state machine)
      → Proximity-proportional speed modulation (differentiator; needs gait engine variable-speed support — verify before committing)
  → Bounded-duration auto-run timer (independent, gates the mode flag)
  → Manual override preemption (independent, must intercept before condition_monitor acts on auto-mode state)

Cautious behavior near pets/kids (table stakes, minimum version)
  → uses same ultrasonic close-range threshold as avoidance state machine
  → Motion-vs-static disambiguation via camera (differentiator, adds camera frame-differencing as a second input)

Visible auto-mode status (table stakes, minimum version: client UI label)
  → Physical LED/buzzer status indicator (differentiator, reuses existing Led/Buzzer classes)

Client-configurable auto-mode parameters (differentiator)
  → depends on the state machine's thresholds being named/exposed, not hardcoded
  → requires updating command.py in both Code/Server/ and Code/Client/ (documented duplication constraint)

Session logging of auto-mode decisions (differentiator)
  → independent, can be layered onto the state machine after it exists
```

## MVP Recommendation

Prioritize (in this order, mirroring the dependency chain above):
1. Enter/exit auto mode + manual-override preemption + bounded duration timer — the safety scaffolding, must exist before any autonomous movement happens at all.
2. Forward obstacle detection (ultrasonic) + head-sweep scan + stop-and-turn state machine — the actual "avoids things" behavior, and the precedented pattern (`UEA-envsoft/FreenoveBigHexapod`) for this exact hardware.
3. Minimum-viable caution near unpredictable movement: treat any close-range reading during auto mode as "stop and reassess" rather than "nudge past" — satisfies the requirement without yet requiring camera motion detection.
4. Reactive wall/boundary-follow patrol, built on top of the same state machine's distance-threshold plumbing.
5. Visible auto-mode status (minimum version: client UI, since that surface already exists for telemetry).

Defer to a fast-follow inside the same milestone (or explicitly punt to next milestone if time-boxed):
- Proximity-proportional speed modulation — depends on verifying `Control`/gait engine supports variable step speed; don't let this block the binary-threshold version from shipping.
- Camera-based motion detection for pet/kid disambiguation — the minimum caution behavior (stop on any close reading) already satisfies the stated requirement; this is the "do it well" upgrade, not the "do it at all" requirement.
- Client-configurable thresholds and session logging — valuable for tuning against real hardware but not required for the behavior to exist.

## Sources

- [Wall Following with a Single Ultrasonic Sensor (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-16587-0_13) — MEDIUM, reactive set-point wall-follow pattern
- [UEA-envsoft/FreenoveBigHexapod (GitHub)](https://github.com/UEA-envsoft/FreenoveBigHexapod) — MEDIUM, direct precedent fork of this exact hardware kit with head-sweep + threshold-based `wander.py`
- [Obstacle Avoidance with Ultrasonic Sensors (kevsrobots.com)](https://www.kevsrobots.com/learn/micropython_robotics/05_ultrasonic_sensor.html) — MEDIUM, standard hobbyist threshold pattern
- [Obstacle Avoiding Robot Using Arduino and Ultrasonic Sensor (IJFMR)](https://www.ijfmr.com/papers/2026/3/79205.pdf) — MEDIUM, baseline stop/turn pattern
- [Optical Flow Based Robot Obstacle Avoidance (SAGE)](https://journals.sagepub.com/doi/10.5772/5715) — MEDIUM, monocular motion-cue detection without depth hardware
- [Adaptive Visual Obstacle Detection for Mobile Robots Using Monocular Camera and Ultrasonic Sensor (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-33868-7_52) — MEDIUM, camera+ultrasonic fusion precedent
- Robot vacuum obstacle-avoidance vendor content (Ecovacs, Narwal, eufy) — LOW–MEDIUM (marketing-adjacent, directionally useful for *behavioral intent* re: caution near pets/children, not for technical implementation detail)
- Ultrasonic sensor limitation sources (Zbotic, IJFMR, general HC-SR04 documentation patterns) — HIGH, well-established sensor physics
- `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` — HIGH, project-internal ground truth for constraints and existing hardware/command surface
