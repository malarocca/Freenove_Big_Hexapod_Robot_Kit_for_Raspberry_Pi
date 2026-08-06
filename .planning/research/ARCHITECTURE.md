# Architecture Patterns: Autonomy Layer for the Hexapod

**Domain:** Reactive obstacle-avoidance / boundary-patrol autonomy bolted onto an existing threaded, command-queue-driven robot server (not a rewrite)
**Researched:** 2026-08-05
**Confidence:** HIGH for the "fit into existing system" analysis (grounded directly in `Code/Server/control.py`, `server.py`, `ultrasonic.py`, `camera.py`, `command.py`); MEDIUM-HIGH for general reactive-robotics architecture framing (well-established literature: Brooks' subsumption architecture, sense-think-act loop, behavior-based robotics).

## Recommended Architecture

Add autonomy as a **new, separate module that behaves like an additional "client"** of the existing `Control.command_queue`/`condition_monitor` pipeline — not as new logic inside `Control` or `Server`. The existing actuation path (`Server.receive_commands` → `Control.command_queue` → `Control.condition_monitor` → IK/gait → `Servo`) is left completely untouched. Autonomy only ever produces the same command shapes a human already produces from the desktop client.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         Code/Server/autonomy/  (NEW)                     │
│                                                                            │
│  ┌───────────────────┐      ┌────────────────────┐      ┌─────────────┐  │
│  │  perception.py     │      │  behavior.py        │      │  bridge.py  │  │
│  │  SensorHub          │─snap→│  AutonomyController │─Intent→│ (translator)│  │
│  │  (sensing loop,     │      │  (decision loop,    │      │  Intent →   │  │
│  │   own thread,       │      │   own thread,       │      │  command_   │  │
│  │   ~10Hz)             │      │   ~5-10Hz)           │      │  queue list │  │
│  └─────────┬───────────┘      └──────────┬──────────┘      └──────┬──────┘  │
│            │ reads                        │ reads SensorSnapshot   │ writes  │
│            ▼                              ▼                        ▼         │
└─────────────────────────────────────────────────────────────────────────┘
     Ultrasonic.get_distance()                                Control.command_queue
     Camera (optional, light use)                             (existing, unmodified)
     head Servo (pan sweep, direct)                                    │
                                                                        ▼
                                                        Control.condition_monitor()
                                                        (existing, unmodified — the
                                                         ONE actuator of the robot)
```

**Core idea:** three loops, three files, one narrow interface between each pair. Sensing produces data. Decision consumes data and produces *intent*. A thin translator turns intent into the exact list shape `Control.condition_monitor` already knows how to consume (`['CMD_MOVE', gait, x, y, speed, angle]`, `['CMD_POSITION', x, y, z]`, etc.). Nothing downstream of the translator changes. This is exactly the classic **sense → think → act** decomposition from reactive/behavior-based robotics (Brooks' subsumption architecture generalizes this into priority-ordered behavior layers — see Sources) — obstacle-avoidance is a higher-priority layer than wall-follow-patrol, which is higher priority than idle/cruise.

### Why this shape, specifically

1. **`Control` must not grow.** It's already flagged as a god-object (IK math + polling state machine in one 410-line file). Adding "if obstacle then turn" logic into `condition_monitor` would be the single worst thing to do here — it would fuse kinematics, protocol parsing, *and* decision-making into one class. Autonomy logic belongs in its own module that has zero knowledge of IK.
2. **The `command_queue` interface is already the actuation contract.** It's a blunt one (a 6-slot list overwritten wholesale, not a real queue — single-producer/single-consumer today, relying on the GIL for atomicity), but it's the *existing* seam between "decide" and "act." Reusing it means the autonomy loop needs zero new actuation code and zero new IK/gait code. This is the cheapest, least invasive integration point available.
3. **The sensing/decision boundary is what makes this AI-swappable later.** If `SensorHub` produces a small, well-defined `SensorSnapshot` (distance reading + timestamp + optionally a camera frame reference) and `AutonomyController.decide(snapshot) -> Intent` is the *only* function that encodes "what should the robot do," then swapping the reactive decision function for a Claude-driven one later means replacing exactly one function/class — nothing about perception plumbing or actuation plumbing needs to change. This is the most important architectural decision in this research: **treat `decide(snapshot) -> Intent` as a stable, swappable interface from day one**, even though v1's implementation is a simple reactive state machine.

## Component Boundaries

| Component | New file | Responsibility | Talks to | Does NOT do |
|---|---|---|---|---|
| `SensorHub` (sensing loop) | `Code/Server/autonomy/perception.py` | Poll `Ultrasonic.get_distance()` on a fixed-rate background thread; optionally sweep the head servo (pan) between reads to build a coarse left/center/right distance picture; expose the latest reading via a small thread-safe accessor (`get_snapshot()`). Never blocks the decision loop. | `Ultrasonic` (existing), the **shared head `Servo` instance already owned by `Server`** (do not construct a third `Servo()`), optionally `Camera.get_frame()` for a cheap motion/brightness heuristic | No decision logic. No servo/gait commands to the legs. No knowledge of `Control` or `command_queue`. |
| `AutonomyController` (decision loop) | `Code/Server/autonomy/behavior.py` | Reactive state machine consuming `SensorSnapshot`s at ~5-10Hz: obstacle-avoidance (highest priority) → wall/boundary-follow patrol → forward cruise (lowest priority), each layer able to override the one below it (subsumption-style). Tracks its own bounded runtime and self-stops. Defaults to "stop" whenever sensor data is stale/missing. | `SensorHub.get_snapshot()` (read-only), emits `Intent` objects to `bridge.py` | No I2C/GPIO access. No IK math. No socket/protocol code. This is the piece designed to be swapped for an AI decision loop later. |
| Intent → command bridge | `Code/Server/autonomy/bridge.py` (or a function inside `behavior.py` if it stays tiny) | Translate an `Intent` (e.g. `Intent(kind="TURN", angle=-30, speed=3)`, `Intent(kind="FORWARD", speed=4)`, `Intent(kind="STOP")`) into the exact list shape `Control.condition_monitor` already parses, and write it into `Control.command_queue` (plus `Control.timeout = time.time()`, matching what `Server.receive_commands` does today). | `Control.command_queue`, `command.py` (`COMMAND` constants, reused as-is) | No new actuation path — writes to the *same* attribute the manual client path writes to. |
| Mode arbiter / auto-mode toggle | Small addition to `Server` (`server.py`), a new `CMD_AUTO` protocol constant | Own the on/off lifecycle of the autonomy thread(s); guarantee mutual exclusion between manual and autonomous command producers (see "Arbitration" below); enforce the bounded-duration requirement (auto-stop after N minutes). | `AutonomyController` (start/stop), `Control.command_queue` (to hand control back cleanly) | Does not itself contain any avoidance/patrol logic — pure lifecycle/arbitration. |
| `Control` (existing, unmodified) | `Code/Server/control.py` | Sole actuator: IK, gait, posture, `condition_monitor` polling loop. | `Servo` (legs) | Must not gain any new knowledge of sensors, autonomy, or "why" a command arrived — it already doesn't know whether a command came from a human, and that should remain true for autonomy too. |
| `Server` (existing, minimally extended) | `Code/Server/server.py` | Networking + command dispatch, now also dispatches `CMD_AUTO` on/off to the mode arbiter, exactly like it already dispatches `CMD_RELAX`/`CMD_SERVOPOWER` as special-cased branches rather than routing them through `command_queue`. | `Control`, mode arbiter | Should not embed avoidance/patrol logic directly in `receive_commands()` — that would just relocate the anti-pattern from `Control` into `Server`. |

## Data Flow

### Autonomy command path (new, parallel to the existing manual path)

1. `SensorHub` thread calls `Ultrasonic.get_distance()` on a fixed interval (e.g. every ~100-150ms; the underlying `gpiozero.DistanceSensor` echo/trigger round-trip plus settle time makes faster polling low-value), and periodically re-aims the head servo (pan/tilt, channels 0/1 — the same channels `CMD_HEAD`/`CMD_CAMERA` already drive directly in `server.py`, bypassing `Control` entirely) to sample left/center/right. It stores the latest `SensorSnapshot` (distance + heading + timestamp) behind a lock (or a single-attribute GIL-atomic assignment, matching the existing `command_queue` convention) — it never blocks waiting for a consumer.
2. `AutonomyController` thread wakes on its own tick (~5-10Hz), reads the latest `SensorSnapshot` (never triggers a new sensor read itself — sensing and deciding are decoupled so a slow/blocked sensor read can never stall decision-making), and runs the reactive state machine:
   - **Obstacle-avoidance layer** (highest priority): if the nearest reading is inside a stop/turn threshold, emit `Intent(STOP)` or `Intent(TURN, direction, speed)`.
   - **Boundary/wall-follow layer**: if no immediate obstacle but the side-looking or drifting reading indicates the robot is near/parallel to a boundary, emit `Intent(TURN, small_angle)` to keep the wall-following offset.
   - **Cruise layer** (lowest priority): otherwise emit `Intent(FORWARD, speed)`.
   - **Freshness guard**: if the snapshot is older than a small staleness threshold (sensor thread stalled, hardware glitch), emit `Intent(STOP)` — never act on stale data. This is the concrete mechanism for the "err toward caution around pets/kids" requirement.
3. The bridge translates the `Intent` into the exact `command_queue` list shape (e.g. `['CMD_MOVE', '1', str(x), str(y), str(speed), str(angle)]`) and assigns it to `Control.command_queue`, plus sets `Control.timeout`.
4. From here on, the data flow is **identical to the existing manual path**: `Control.condition_monitor()` polls `command_queue` exactly as it does today, runs `run_gait`/`move_position`, computes IK, and calls `Servo.set_servo_angle()`. `Control` cannot tell whether the command came from the desktop client or from the autonomy loop — that's the point.

### Manual override / arbitration (data flow, safety-critical)

Because `command_queue` is a single-slot mailbox (not a real multi-producer queue) with no lock today, having two producers — the manual command thread (`Server.receive_commands`) and the new autonomy thread — write to it concurrently is a real hazard (a manual command and an autonomy command could interleave/clobber each other mid-tick). Resolve with an explicit **arbitration flag**, not by adding locking complexity to `Control`:

1. Introduce a `threading.Event` (e.g. `auto_mode_active`), owned by the mode arbiter in `Server`.
2. `AutonomyController`'s loop checks `auto_mode_active.is_set()` before every write to `command_queue`; if clear, it stops producing entirely (does not just idle — exits its write path).
3. `Server.receive_commands()`, on receiving **any** manual movement command (`CMD_MOVE`, `CMD_POSITION`, `CMD_ATTITUDE`, `CMD_BALANCE`) while `auto_mode_active` is set, clears the event *before* writing the manual command to `command_queue`. This satisfies "manual control remains available at all times" without a dedicated e-stop command — any joystick input from the desktop client instantly and unconditionally reclaims control.
4. `CMD_AUTO#0` (explicit toggle-off from the client) and the bounded-duration timer both also clear the event.
5. This event is the *entire* extent of new shared mutable state touching the existing system — everything else about `Control`/`condition_monitor` is untouched.

### Sensor telemetry to the client (existing, unaffected)

The existing `CMD_SONIC`/`CMD_POWER` request/response telemetry path (`Server.receive_commands` reading `Ultrasonic.get_distance()`/`ADC.read_battery_voltage()` on client request) is unaffected by adding `SensorHub`. `SensorHub` should read the same `Ultrasonic` instance already owned by `Server` (pass it in, don't construct a second one — a raw `gpiozero.DistanceSensor` has its own GPIO pin claim; a second instance would either fail to acquire the pin or produce inconsistent readings from two independent sensor objects). If the client polls `CMD_SONIC` while auto mode's `SensorHub` is also polling, both simply call `get_distance()` on the same shared object — `DistanceSensor.distance` is a plain synchronous read, safe to call from multiple threads (no shared mutable state inside it beyond what `gpiozero` itself manages).

## Patterns to Follow

### Pattern 1: Sense/decide/act as three independent threads with narrow, typed handoffs

**What:** `SensorHub` owns sensing, `AutonomyController` owns decisions, the bridge + existing `command_queue` own actuation dispatch. Each thread reads the *previous* stage's latest output, never calls into the previous stage's internals, and never blocks waiting for the next stage.
**When:** Any reactive/behavior-based control loop on a resource-constrained single-board computer where sensor I/O (ultrasonic round-trip, camera frame wait) and actuation (servo writes, gait timing with `time.sleep`) each have their own natural latency — decoupling them via a "latest value" handoff (not a blocking queue) keeps one slow stage from stalling another. This mirrors how `Control.condition_monitor` already treats `command_queue` as a mailbox rather than a FIFO — follow the codebase's existing convention rather than introducing `queue.Queue` machinery that doesn't match anything else in the project.
**Example (shape, not literal code):**
```python
# perception.py
class SensorHub:
    def __init__(self, ultrasonic, head_servo):
        self._ultrasonic = ultrasonic
        self._head_servo = head_servo
        self._latest = SensorSnapshot(distance=None, heading=0, ts=0.0)
        self._lock = threading.Lock()

    def get_snapshot(self) -> SensorSnapshot:
        with self._lock:
            return self._latest   # cheap, GIL-safe copy of an immutable dataclass

    def run(self, stop_event: threading.Event):
        while not stop_event.is_set():
            distance = self._ultrasonic.get_distance()
            with self._lock:
                self._latest = SensorSnapshot(distance, self._current_heading, time.time())
            time.sleep(0.1)
```
```python
# behavior.py
class AutonomyController:
    def decide(self, snapshot: SensorSnapshot) -> Intent:
        if snapshot.is_stale(max_age=0.5):
            return Intent.stop()
        if snapshot.distance is not None and snapshot.distance < STOP_THRESHOLD_CM:
            return Intent.turn(direction=self._pick_turn_direction(), speed=SLOW)
        if self._near_boundary(snapshot):
            return Intent.turn(angle=SMALL_CORRECTION, speed=CRUISE)
        return Intent.forward(speed=CRUISE)
```

### Pattern 2: Cooperative thread shutdown via `threading.Event`, not `stop_thread()`

**What:** New autonomy threads should be created fresh on `CMD_AUTO#1` and torn down cooperatively (loop checks an `Event`, thread `join()`s with a short timeout) on `CMD_AUTO#0`/timeout, mirroring the *intent* of the existing `led_thread`/`stop_thread()` pattern but without reusing `Thread.stop_thread()`'s `ctypes`/`PyThreadState_SetAsyncExc` mechanism.
**When:** Always, for new code. The codebase's own architecture notes flag `stop_thread()` as "not to be used as a template for new cancellable-thread code" — autonomy threads that might be mid-way through a servo write when killed are exactly the scenario where async-exception injection is riskiest (an interrupted I2C transaction could leave the head servo in an inconsistent PWM state).

### Pattern 3: Reuse the existing `COMMAND` vocabulary and add exactly one new constant

**What:** `Intent → command_queue` translation should emit the *existing* `CMD_MOVE`/`CMD_POSITION` shapes verbatim — do not invent a parallel "autonomy command" vocabulary. Add exactly one new protocol constant, `CMD_AUTO`, to both `Code/Server/command.py` and `Code/Client/Command.py` (the codebase's existing, if awkward, convention for protocol changes — keep both copies in lockstep, per the existing anti-pattern note).
**When:** For any new top-level mode toggle exposed to the client. Reusing `CMD_MOVE` etc. for the actual movement payload (rather than adding `CMD_AUTO_MOVE` or similar) is what keeps `Control` from ever needing to know autonomy exists.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Deciding inside `condition_monitor`

**What:** Adding `if self.ultrasonic.get_distance() < 20: ...` (or any sensor read/decision logic) directly into `Control.condition_monitor()`'s loop body.
**Why bad:** This is the single most tempting shortcut ("it's already an always-on loop, just add a check") and the single worst outcome for this codebase — it fuses IK math, gait timing, protocol-adjacent state (`status_flag`), *and* obstacle-avoidance decision logic into one already-overloaded class, and makes the "swap for AI later" goal much harder because the decision logic would be entangled with kinematics code.
**Instead:** Keep `Control` exactly as it is. It only ever consumes `command_queue`; it never reads sensors.

### Anti-Pattern 2: Decision loop calling `Servo`/`Control` methods directly

**What:** Having `AutonomyController` call `self.control.move_position(...)` or `self.servo.set_servo_angle(...)` directly instead of writing to `command_queue`.
**Why bad:** This creates a second actuation path that bypasses `condition_monitor`'s existing state machine (`status_flag`, timeout/relax handling, calibration-aware `set_leg_angles`), risking a second source of truth for "what is the robot currently doing" and making the manual-override arbitration (above) unenforceable — a direct call can't be preempted by clearing an `Event` the way a `command_queue` write can.
**Instead:** The bridge is the *only* thing that ever writes leg-movement commands, and it always writes through `command_queue`, never around it.

### Anti-Pattern 3: A blocking `queue.Queue`/pub-sub framework between sensing and deciding

**What:** Introducing a real multi-producer/multi-consumer queue, message broker, or a ROS-style topic system for `SensorSnapshot` delivery.
**Why bad:** Massive over-engineering for one sensor, one consumer, running on a Pi with an already GIL-serialized thread model; it also fights the codebase's existing "shared mutable attribute, GIL-protected" convention (`command_queue` itself works this way) rather than fitting into it.
**Instead:** A "latest value" accessor (single attribute behind a lock or relying on GIL-atomic reference reassignment, exactly like `command_queue` today) is sufficient and consistent with the rest of the codebase.

### Anti-Pattern 4: Building real computer-vision obstacle detection for v1

**What:** Standing up an ML/CV pipeline (object detection model, depth-from-mono, optical flow) on the camera feed as part of this milestone's obstacle-avoidance logic.
**Why bad:** No such pipeline exists today; the camera path today is purely a JPEG streaming pipe to the client (`Camera.get_frame()`/`picamera2` JpegEncoder). Building real vision inference on a Pi, inside this milestone, is a scope explosion relative to "one ultrasonic sensor is enough to avoid crashing into things," and it's also explicitly the kind of rich-perception work better suited to the *later* AI-piloted milestone (where a vision-capable model, not hand-rolled CV, does the interpretation).
**Instead:** v1 `SensorHub` should be ultrasonic-primary, with the head pan sweep as the mechanism for "look left/right," and the camera left doing exactly what it does today (streaming). If time allows, a *very* cheap heuristic (e.g., frame-to-frame brightness/motion delta as a "something is moving nearby, be extra cautious" signal feeding the freshness/caution logic) is the ceiling for camera involvement in v1 — not object recognition.

## Constrained-Hardware Considerations

| Concern | v1 (this milestone) | Later (AI-piloted loop) |
|---|---|---|
| Sensor poll rate | Ultrasonic ~100-150ms interval is plenty (sensor's own round-trip + settle time dominates; faster polling wastes CPU/I2C bus time for no gain) | An AI decision loop is likely tick-rate-bound by model latency, not sensor latency — `SensorHub`'s interface doesn't need to change, only what reads from it |
| Decision loop rate | 5-10Hz reactive state machine is cheap (pure Python arithmetic on a handful of floats) — negligible CPU/thread overhead alongside `condition_monitor`'s own ~10ms-tick gait loop | Same `decide(snapshot) -> Intent` seam; a Claude-driven decide() would likely run far slower (network round-trip) — the seam should tolerate variable/slower decision cadence without changing the sensing or actuation sides |
| I2C/GPIO bus contention | Head servo (pan) shares the same two PCA9685 chips the legs use; `SensorHub`'s head sweeps and `Control`'s leg writes are on independent channels but the same physical I2C bus — keep sweeps infrequent/short, and route them through the *same* `Servo` instance `Server` already owns (don't add a third `Servo()`/`PCA9685()` object contending for the bus with no coordination) | Unaffected — actuation path is unchanged |
| Memory/CPU headroom | Pi (server also runs a PyQt5 GUI, camera encoder, and now two more lightweight threads) — pure-Python reactive logic is negligible; avoid adding heavyweight deps (numpy is already a dependency via `control.py`, fine to reuse; avoid adding OpenCV/ML frameworks for v1) | If AI piloting eventually needs frame preprocessing, that's a deliberate later decision, not something v1's architecture should pre-optimize for |
| Bounded runtime / battery | Autonomy loop must self-stop after a configured duration (mirrors `Control`'s existing 10s idle-timeout-to-relax pattern in `condition_monitor`) — implement as an elapsed-time check inside `AutonomyController`'s loop, enforced independently of the mode arbiter as a second safety layer | Same mechanism should still apply — a runaway AI loop is exactly the scenario a hard wall-clock cutoff protects against |

## Suggested Build Order

1. **`SensorHub` (perception.py), standalone.** Depends on nothing new — reuses the existing `Ultrasonic` and `Servo` instances. Buildable and smoke-testable on its own (a `myCode.py`-style standalone script, matching the codebase's existing convention for hardware bring-up scripts) before any decision logic exists. Validates poll rate, head-sweep timing, and the `SensorSnapshot`/staleness contract.
2. **`Intent` type + `AutonomyController` (behavior.py), fed by (1).** Pure logic, no new hardware access — can be developed and unit-adjacent-tested (even without automated tests, it's trivially exercisable by feeding hand-constructed `SensorSnapshot`s and asserting the emitted `Intent`) independent of the robot being powered on. This is where obstacle-avoidance-over-patrol priority ordering gets built and tuned.
3. **Bridge (`Intent` → `command_queue` list shape), depends on (2) + existing `command.py` vocabulary.** Small, mechanical. First point where autonomy actually moves the robot — test by driving `Control.command_queue` directly from a script (bypassing the network layer entirely, same pattern as `myCode.py`), before touching `server.py` at all.
4. **Mode arbiter + `CMD_AUTO` protocol wiring in `server.py`/`command.py`/`Command.py`, depends on (1)-(3) working standalone.** This is where the manual-override `Event` arbitration and bounded-duration timer get wired into the live command-receive path — the highest-risk integration step, but by this point the sense/decide/act pieces are already validated independently.
5. **Desktop client toggle button, depends on (4).** Thin GUI addition (`Code/Client/ui_client.py` + a slot in `Main.py` sending `CMD_AUTO#1`/`#0`) — last, and lowest-risk, since the protocol and server-side behavior are already proven.

This ordering means every phase before (4) is testable on real hardware without touching the network/GUI layers at all, and (4)-(5) only need to wire together pieces that already work.

## Sources

- Direct code review (HIGH confidence, primary source for all "fits into existing system" claims): `Code/Server/control.py`, `Code/Server/server.py`, `Code/Server/ultrasonic.py`, `Code/Server/camera.py`, `Code/Server/command.py`.
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md` (existing codebase-mapping research, HIGH confidence).
- General reactive/behavior-based robotics architecture framing (sense-think-act loop, subsumption architecture, priority-ordered behavior layers), MEDIUM-HIGH confidence, well-established robotics literature:
  - [The Reactive Paradigm — Intro-to-AI-Robotics](https://github.com/turhancan97/Intro-to-AI-Robotics/blob/master/1.Robotic_Paradigms/d.The_Reactive_Paradigm/README.md)
  - [Sense-Plan-Act in Robotic Applications (ResearchGate)](https://www.researchgate.net/publication/349248621_Sense-Plan-Act_in_Robotic_Applications)
  - [A Brief Introduction to Behavior-Based Robotics (EPFL)](https://baibook.epfl.ch/exercises/behaviorBasedRobotics/BBSummary.pdf)
  - [Robotic Paradigms and Control Architectures (CTU Prague, Faigl)](https://cw.fel.cvut.cz/old/_media/courses/b4m36uir/lectures/b4m36uir-lec02-slides.pdf)
