# Project Research Summary

**Project:** Autonomous Hexapod (Freenove Big Hexapod Kit)
**Domain:** Reactive robotics autonomy — obstacle avoidance + boundary/wall-follow patrol bolted onto an existing teleoperated hexapod server (single ultrasonic sensor + camera on a shared pan/tilt head, no SLAM/odometry, safety-sensitive around pets/kids)
**Researched:** 2026-08-05
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a **reactive, sensor-thresholded autonomy layer**, not a planning/mapping robot — and every research thread converges on that same conclusion independently. With one narrow-beam ultrasonic sensor and a camera co-mounted on a single pan/tilt head, no odometry, and no SLAM, the only viable approach (and the one universally used by hobbyist and academic precedent, including a direct fork of this exact hardware kit) is: sweep the head across a few fixed bearings, read distance at each, and drive a small reactive state machine off distance thresholds — Braitenberg/bug-algorithm style. No new sensor hardware, no ROS, no SLAM libraries, and (for v1) no computer vision inference are needed or recommended. The existing stack (`gpiozero`, `picamera2`, `numpy`, plain threading) already covers everything except behavior orchestration, where a small, mature FSM library (`transitions`) is worth adding to avoid extending the codebase's already-flagged `Control.condition_monitor` string-dispatch anti-pattern.

The recommended approach is architecturally conservative: add autonomy as an entirely new module (`Code/Server/autonomy/`) structured as three decoupled threads — sensing, deciding, and an intent-to-command translator — that writes into the *existing* `Control.command_queue` exactly the way the manual TCP client already does. `Control` itself is never modified and never learns that autonomy exists. This both respects the codebase's existing architecture (avoiding further bloat of the already-god-object `Control` class) and, critically, is explicitly designed so the `decide(snapshot) -> Intent` function is a swappable seam — v1's reactive state machine can later be replaced by an AI-piloted decision function without touching sensing or actuation code, directly serving the project's stated long-term vision.

The dominant risk is not algorithmic novelty but **safety-critical concurrency and failure-mode handling on top of a codebase with known, documented hazards**: `Control.command_queue` is already an unsynchronized, multi-writer shared list; the existing thread-kill mechanism (`stop_thread()`) is explicitly flagged as unsafe for anything mid-motion; the TCP reconnect path is confirmed dead code; and ultrasonic sensors structurally cannot distinguish "no echo, nothing there" from "no echo, sensor missed a soft/angled obstacle." Every one of these interacts directly with the stated safety model ("manual override always available, no e-stop, bounded runtime, err toward caution near pets/kids"), which means the arbitration/lifecycle/error-handling work is not incidental plumbing — it is the actual safety feature this milestone is building, and research strongly recommends sequencing it early (built alongside the first reactive behavior, not retrofitted after).

## Key Findings

### Recommended Stack

The existing stack (Python 3.13.5, `gpiozero` 2.0.1, `picamera2` 0.3.36, `numpy` 2.2.4, thread-per-concern concurrency, no asyncio) covers nearly everything this milestone needs with zero new dependencies. The one clear addition is a lightweight finite-state-machine library for behavior orchestration; everything else is either already present or deliberately avoided as over-engineering for a single-sensor reactive robot.

**Core technologies:**
- `transitions` (pytransitions) 0.9.3 — explicit FSM for auto-mode states (Idle/Scanning/Advancing/Avoiding/WallFollowing/CautionStop/TimeoutStop) — avoids extending the codebase's already-flagged busy-poll if/elif dispatch anti-pattern; small, mature, pure-Python, and incidentally the one piece of new code that's unit-testable off-hardware.
- `threading.Event` / `queue.Queue` / `time.monotonic()` (stdlib only) — cooperative on/off flag for auto mode, thread-safe sensor handoff, and bounded-runtime timing — matches the codebase's existing thread-per-concern model and specifically avoids the unsafe `ctypes`-based `stop_thread()` pattern already flagged in this codebase.
- `gpiozero.DistanceSensor`'s built-in `queue_len`/threshold/event API (already a dependency, bump to 2.0.1.post3 for a Pi 5 fix) — use the smoothing/event helpers already shipped in the library instead of hand-rolling comparisons on raw `.distance` reads.
- `picamera2` lores stream + `numpy` frame-diff (both already dependencies) — the officially-documented, zero-new-dependency approach for lightweight motion detection (pet/kid caution), explicitly preferred over OpenCV/TFLite/YOLO/ROS/SLAM, all of which are disproportionate to this milestone and explicitly rejected in research.

### Expected Features

Research (hobbyist precedent, a direct fork of this exact kit, and academic wall-follow literature) maps almost 1:1 onto `PROJECT.md`'s Active requirements — there is no feature-discovery gap here, mainly a sequencing question.

**Must have (table stakes):**
- Explicit enter/exit auto-mode toggle from the client
- Forward obstacle detection via ultrasonic, gated on a distance threshold
- Head-sweep scan (reuse `CMD_HEAD`) to pick a direction rather than just stopping — directly precedented on this exact hardware
- Stop-and-turn reactive avoidance state machine (clear/caution/blocked)
- Reactive wall/boundary-follow patrol (proportional steering to a set-point distance, no map)
- Bounded-duration auto-run with automatic, graceful stop
- Manual override always preempts auto mode, with no delay
- Minimum-viable caution near unpredictable movement (any close reading → stop and reassess)
- Visible "auto mode active" indicator (minimum: client UI label)

**Should have (differentiators, same hardware, no new sensors):**
- Proximity-proportional speed modulation (verify gait engine supports variable speed first)
- Camera-based motion detection for pet/kid disambiguation (frame-differencing only, not classification)
- Physical LED/buzzer status indicator reusing existing hardware
- Randomized evasive turns + "stuck" escalation to avoid infinite bounce loops
- Client-configurable thresholds; session logging of auto-mode decisions

**Defer (explicit anti-features, out of proportion to v1 constraints):**
- SLAM/mapping, waypoint/return-to-start navigation, coverage-path planning, persistent environment memory — no odometry/localization exists and none is in scope
- ML-based object/pet/person classification — motion detection alone satisfies "cautious near movement"
- New sensor hardware, networked e-stop, full 360° awareness, general-purpose behavior-tree framework

### Architecture Approach

Add autonomy as a new, self-contained module (`Code/Server/autonomy/`) implementing a classic sense→think→act decomposition as three independent threads with narrow, typed handoffs — `SensorHub` (perception), `AutonomyController` (decision, exposing a swappable `decide(snapshot) -> Intent` seam), and a thin bridge that translates `Intent` into the *existing* `command_queue` list shape. `Control` and `condition_monitor` are never modified; autonomy is architecturally indistinguishable from "another client" of the existing actuation contract, which keeps the god-object risk contained and keeps the eventual AI-piloting swap to a single-function replacement.

**Major components:**
1. `SensorHub` (`perception.py`) — polls ultrasonic + sweeps the shared head servo, exposes a `SensorSnapshot` via a lock-protected "latest value" accessor; never blocks, never decides.
2. `AutonomyController` (`behavior.py`) — reactive, priority-layered state machine (avoidance > wall-follow > cruise) at ~5-10Hz; owns bounded-runtime self-stop and the "stale data → stop" fail-safe; this is the swappable-for-AI seam.
3. Bridge (`bridge.py`) — translates `Intent` into existing `CMD_MOVE`/`CMD_POSITION`-shaped commands, writes to `Control.command_queue` exactly as the manual TCP path does — no second actuation path.
4. Mode arbiter (small addition to `server.py`, one new `CMD_AUTO` protocol constant) — owns the autonomy thread lifecycle and the manual-preempts-auto arbitration flag; contains no avoidance logic itself.

### Critical Pitfalls

1. **Ultrasonic false negatives on soft/angled surfaces treated as "clear"** — `None`/no-echo must be coded as "unknown," never "safe"; require multiple consecutive clear readings to trust an opening but only one close reading to trigger caution. Address in the sensing/perception phase, before any avoidance logic is built on top of raw readings.
2. **Oscillation/thrashing near obstacles from a single symmetric threshold** — use two thresholds with hysteresis, commit to a turn for a minimum duration/angle rather than re-evaluating every tick, and add a stuck/thrash detector. This is core avoidance-algorithm design, not a later tuning pass.
3. **Unsynchronized multi-writer race on `Control.command_queue`** — this codebase's existing two-writer hazard (network thread + `condition_monitor`) becomes safety-load-bearing the moment autonomy adds a third writer; requires a single explicit arbitration point (lock or `Queue`) with manual commands always preempting auto, designed before or alongside the first autonomous behavior, not retrofitted.
4. **Unsafe thread-kill (`stop_thread()`) applied to auto-mode shutdown** could freeze the hexapod mid-stride in an unstable pose; use cooperative `threading.Event`-based stop that reaches a stable stance before halting, never async-exception injection.
5. **Silent failure via bare `except:` in the new decision loop** — any unexpected exception in autonomy code must trigger a fail-safe stop, never a silent continue-on-last-command; this codebase's dominant existing error-handling style (swallow-and-print) must not be copied into safety-relevant new code.

## Implications for Roadmap

Based on combined research, autonomy should be built bottom-up through independently hardware-testable layers, with the concurrency/safety arbitration work sequenced early rather than bolted on at the end — this is the single strongest, most consistent signal across all four research files (STACK, FEATURES, ARCHITECTURE, and especially PITFALLS all converge on "build sensing → decision → arbitration → integration, in that order, and don't defer the arbitration/lifecycle work").

### Phase 1: Perception foundation (SensorHub)
**Rationale:** Everything downstream depends on trustworthy sensor data; ARCHITECTURE.md's suggested build order and PITFALLS.md's Pitfall 1/10/13 all identify this as the correct, self-contained starting point — buildable and hardware-testable standalone before any decision logic exists, with zero new server dependencies beyond the existing `gpiozero`/`Servo` instances.
**Delivers:** `SensorHub` thread producing a `SensorSnapshot` (distance + heading + timestamp) via head-sweep polling; None/no-echo treated as "unknown"; rolling-median smoothing on top of gpiozero's own; clamped head-sweep angles.
**Addresses:** Table-stakes "forward obstacle detection" and "head-sweep scan" from FEATURES.md.
**Avoids:** Pitfall 1 (false-negative-as-clear), Pitfall 10 (single-ping lurching), Pitfall 13 (unclamped `CMD_HEAD` angles).

### Phase 2: Reactive decision logic (AutonomyController)
**Rationale:** Pure logic, no new hardware access — can be developed and exercised with hand-constructed `SensorSnapshot`s independent of the robot being powered on, per ARCHITECTURE.md's suggested build order. This is also where the core safety posture (stop-biased, hysteresis-based, moving-target-aware) gets designed, which PITFALLS.md is emphatic must happen here, not as a later tuning pass.
**Delivers:** Priority-layered reactive state machine (avoidance > wall-follow > cruise) emitting `Intent` objects; two-threshold hysteresis; committed-maneuver turns; stuck/thrash escalation; default-to-stop-not-maneuver for unknown/close/possibly-moving obstacles; explicit fail-safe exception handling.
**Uses:** `transitions` FSM library from STACK.md.
**Implements:** `AutonomyController` component from ARCHITECTURE.md, designed as the swappable `decide(snapshot) -> Intent` seam for future AI-piloting.

### Phase 3: Concurrency, arbitration, and safe actuation bridge
**Rationale:** PITFALLS.md identifies this as the highest-risk integration step and explicitly recommends sequencing it *before or alongside* first building autonomous behavior, not after — the existing `command_queue` is already an unsynchronized two-writer hazard, and autonomy's third writer makes that hazard safety-load-bearing for the first time. ARCHITECTURE.md's bridge component and manual-override `Event` arbitration both live here.
**Delivers:** Bridge translating `Intent` → existing `command_queue` shape; single arbitration point (lock or `Event`-gated) where manual commands always preempt in-flight autonomous commands; cooperative (not `stop_thread()`-based) shutdown reaching a stable stance.
**Addresses:** Table-stakes "manual override always available" and "bounded-duration auto-run with automatic stop" from FEATURES.md.
**Avoids:** Pitfall 3 (command_queue race), Pitfall 4 (unsafe thread-kill mid-stride).

### Phase 4: Auto-mode lifecycle, protocol wiring, and client toggle
**Rationale:** By this point sense/decide/act pieces are already validated independently on real hardware without touching the network/GUI layers; this phase only wires already-working pieces together, per ARCHITECTURE.md's suggested build order (steps 4-5). It's also where the known dead-code TCP-reconnect bug (PITFALLS.md Pitfall 5) becomes directly relevant to the "manual override always available" safety claim and should be fixed or explicitly accepted as risk.
**Delivers:** `CMD_AUTO` protocol constant (server + client), mode arbiter in `server.py`, server-side-enforced bounded runtime independent of client connection, desktop client toggle button.
**Addresses:** Table-stakes "enter/exit auto mode from the client" and "visible auto-mode status" from FEATURES.md.
**Avoids:** Pitfall 5 (dead TCP reconnect undermining the safety-net assumption).

### Phase 5 (optional / fast-follow): Caution polish and patrol refinement
**Rationale:** FEATURES.md's MVP recommendation explicitly defers these — proximity-proportional speed modulation, camera-based motion disambiguation, and wall-follow tuning — as "do it well" upgrades layered onto an already-working, already-safe core, not blockers to shipping the core behavior.
**Delivers:** Speed modulation (if gait engine supports it), camera frame-diff motion caution signal, tuned wall-follow standoff distance, physical LED/buzzer status indicators.
**Addresses:** Differentiators from FEATURES.md.

### Phase Ordering Rationale

- Perception before decision before arbitration before protocol wiring mirrors both the dependency graph in FEATURES.md and the explicit "Suggested Build Order" in ARCHITECTURE.md — each phase is independently hardware-testable via direct scripts (matching the codebase's existing `myCode.py` convention) before the network/GUI layer is touched at all.
- Concurrency/arbitration is deliberately phase 3, not phase 5, because PITFALLS.md treats it as a pre-existing hazard in the codebase that autonomy makes safety-critical — retrofitting locking after avoidance behavior already exists is explicitly called out as riskier than designing the arbitration point up front.
- This ordering also naturally front-loads the pieces most amenable to unit-style testing (perception's pure data contract, decision's pure logic) given the codebase has zero automated tests today (Pitfall 14) — get the parts that can be verified without hardware right first.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (concurrency/arbitration):** The exact locking strategy (single `threading.Lock` vs. `queue.Queue` refactor of `command_queue`) touches existing, already-fragile shared state — worth a focused look at exactly how `Server.receive_commands()` and `Control.condition_monitor()` currently interact before finalizing the design.
- **Phase 5 (patrol/wall-follow tuning):** PITFALLS.md and FEATURES.md both flag that proportional wall-follow control needs real on-hardware tuning (hexapod turning-in-place vs. arcing affects achievable smoothness) — algorithm shape is well-researched, but constants/behavior will need empirical iteration not resolvable from research alone.

Phases with standard patterns (skip research-phase):
- **Phase 1 (perception):** Directly precedented (a fork of this exact kit already prototyped head-sweep + ultrasonic sensing); `gpiozero`/`picamera2` APIs are well-documented and already verified against source.
- **Phase 2 (reactive decision logic):** Braitenberg/bug-algorithm reactive control is extremely well-established robotics literature; `transitions` library usage is straightforward and mature.
- **Phase 4 (protocol wiring):** Mechanical extension of the codebase's existing, already-understood `CMD_*` command-constant convention.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | gpiozero/picamera2 APIs verified via Context7/official examples (HIGH); `transitions` library maturity verified via PyPI/GitHub but not Context7-indexed (MEDIUM-HIGH); apt-vs-pip OpenCV recommendation directly machine-verified on this Pi (HIGH) |
| Features | MEDIUM | Strong direct precedent (a fork of this exact hardware kit) plus consistent hobbyist/academic pattern cross-referencing; commercial robot-vacuum sourcing is directionally reliable for behavioral intent only, not technical detail (LOW-MEDIUM for that subset) |
| Architecture | HIGH for codebase-fit analysis (grounded directly in this repo's own `control.py`/`server.py`/`ultrasonic.py`/`camera.py`/`command.py`); MEDIUM-HIGH for general reactive-robotics framing (well-established literature: subsumption architecture, sense-think-act loop) |
| Pitfalls | MEDIUM overall — general reactive-avoidance and concurrency failure modes are well documented (HIGH); several findings grounded directly in this repo's own code and known bugs (HIGH); gpiozero no-echo semantics verified against source (MEDIUM-HIGH); household-pet-safety-specific literature is thin, so those specific recommendations lean on general safety-engineering principles (MEDIUM) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Gait engine variable-speed support is unverified.** Proximity-proportional speed modulation (a differentiator) depends on `Control`/`run_gait` accepting a variable speed parameter — STACK/FEATURES research flags this as unverified; check `control.py` directly during Phase 2/5 planning before committing to this feature.
- **`command_queue` locking strategy is a design decision, not yet made.** Research agrees a single arbitration point is required (lock or `Queue`) but doesn't prescribe which; this should be resolved during Phase 3 planning, informed by how invasive each option is relative to `condition_monitor`'s existing polling behavior.
- **TCP reconnect bug (`tcp_flag`/`is_tcp_active`) fix-vs-accept decision is unresolved.** PITFALLS.md recommends fixing or explicitly accepting this known bug given it undermines the "manual override always available" safety claim during auto mode — this is a scoping decision for Phase 4 planning, not something research can resolve unilaterally.
- **Real-world sensor behavior against soft/angled/low-profile obstacles is unvalidated.** All ultrasonic-limitation findings (Pitfall 1, 10, 12) are physics-and-literature-based, not validated against this specific sensor/mounting/environment combination; field-testing against pillows, rug edges, and low coffee-table legs should happen early, not just at the end.
- **Wall-follow standoff/turn-arc constants require on-hardware tuning.** Algorithm shape is well-established; specific thresholds are not derivable from research and are explicitly flagged as needing empirical iteration during Phase 5.

## Sources

### Primary (HIGH confidence)
- Direct code review of this repository: `Code/Server/control.py`, `server.py`, `ultrasonic.py`, `camera.py`, `command.py`, `Thread.py`
- `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/STACK.md`, `.planning/codebase/INTEGRATIONS.md`
- gpiozero `DistanceSensor` API and source — verified via Context7 (`/gpiozero/gpiozero`) and directly against `input_devices.py`
- picamera2 official motion-detection example (`examples/capture_motion.py`) — [raspberrypi/picamera2 GitHub](https://github.com/raspberrypi/picamera2)
- `python3-opencv`/`libopencv410` availability — directly verified via `apt-cache policy` on this machine

### Secondary (MEDIUM confidence)
- [UEA-envsoft/FreenoveBigHexapod (GitHub)](https://github.com/UEA-envsoft/FreenoveBigHexapod) — direct precedent fork of this exact kit, head-sweep + threshold-based wander
- `transitions` (pytransitions) — [PyPI](https://pypi.org/project/transitions/), [GitHub](https://github.com/pytransitions/transitions)
- [Wall Following with a Single Ultrasonic Sensor (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-16587-0_13)
- Reactive/subsumption robotics framing — [EPFL Behavior-Based Robotics](https://baibook.epfl.ch/exercises/behaviorBasedRobotics/BBSummary.pdf), [CTU Prague robotic paradigms slides](https://cw.fel.cvut.cz/old/_media/courses/b4m36uir/lectures/b4m36uir-lec02-slides.pdf)
- Force-field/potential-field oscillation literature (ScienceDirect, multiple corroborating academic sources)
- `tflite-runtime` deprecation / `ai-edge-litert` migration — [google-ai-edge/LiteRT GitHub issue #71](https://github.com/google-ai-edge/LiteRT/issues/71)

### Tertiary (LOW confidence)
- Robot-vacuum vendor content (Ecovacs, Narwal, eufy) — marketing-adjacent, used only for directional behavioral-intent framing, not technical detail
- Household-robot/pet-safety-specific academic literature (e.g. "Designing Multispecies Worlds for Robots, Cats, and Humans") — directionally relevant, not hexapod/ultrasonic-specific

---
*Research completed: 2026-08-05*
*Ready for roadmap: yes*
