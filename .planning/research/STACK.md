# Technology Stack — Autonomy Milestone (Obstacle Avoidance + Patrol)

**Project:** Autonomous Hexapod (Freenove Big Hexapod Kit)
**Scope:** Reactive obstacle avoidance + boundary/wall-follow patrol on top of the existing manual-teleop server. No SLAM, no odometry, no new sensors.
**Researched:** 2026-08-05

## Context From Existing Stack

The server already runs Python 3.13.5 on Raspberry Pi OS (Debian 13 "trixie"), with `gpiozero` 2.0.1 (ultrasonic + GPIO), `picamera2` 0.3.36 (camera), `numpy` 2.2.4, and thread-per-concern concurrency (no asyncio anywhere). `opencv-python`/`cv2` is currently **client-only** — the server has never imported OpenCV, though the underlying `libopencv410` C libraries are already installed on the Pi as a dependency of `rpicam-apps`. This matters: it means OpenCV can be added to the server cheaply (via apt, reusing the existing C libs) if needed, but it is **not currently a server dependency** and shouldn't be added reflexively.

The single ultrasonic sensor and the camera are co-mounted on the same 2-axis pan/tilt head — there is no independent "look left while driving straight" capability. Any obstacle-sensing design has to account for this shared-head constraint (sequential scanning, not simultaneous multi-direction sensing).

## Recommended Stack

### Behavior Orchestration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `transitions` (pytransitions) | 0.9.3 (pip) / 0.9.2-2 (apt `python3-transitions`) | Explicit finite-state-machine for auto-mode (`Idle` → `Scanning` → `Advancing`/`Avoiding`/`WallFollowing`/`CautionStop`/`TimeoutStop`) | The codebase's existing `Control.condition_monitor` is a documented anti-pattern: a busy-poll loop dispatching on ad-hoc string membership (`ARCHITECTURE.md` explicitly flags this and warns not to extend it with more of the same). Autonomy adds real behavioral states with real transition guards (obstacle detected, timeout reached, manual override) — implementing that as another if/elif chain compounds the existing problem. `transitions` is a small, mature, pure-Python object-oriented FSM library (first released 2014, still actively maintained, PyPI `transitions` package). Use only the core `Machine` class — skip the `GraphMachine`/`pygraphviz` diagramming extras, which pull in a heavy, often-broken-on-Pi graphviz dependency chain the project doesn't need. **Bonus:** because a `transitions`-based FSM is pure Python with no hardware I/O baked in, it is one of the few pieces of this codebase that's actually unit-testable off-device (mock the sensor callbacks, assert state transitions) — worth flagging for the roadmap given the project has no automated test suite today. Confidence: MEDIUM-HIGH (mature, widely used in robotics/IoT projects; verified current via PyPI/GitHub, not Context7-indexed). |

**Alternative considered and rejected:** `py_trees` (behavior trees). Common in ROS/ROS2 robotics, but it's built for composing many concurrent, hierarchical behaviors — overkill for a single linear "manual ↔ auto, then a handful of auto sub-states" flow, and it pulls in more machinery (visitors, blackboards) than this milestone needs. Revisit only if a future milestone (AI-piloted control loop) needs to arbitrate many concurrent behavior sources.

**Alternative considered and rejected:** Hand-rolled dict-based dispatch (no library). Technically zero-dependency, but this is exactly the pattern already flagged as a maintenance risk in the existing codebase (`command_queue` polling). A tiny, well-tested library is worth the one new dependency here.

### Concurrency / Glue (stdlib only — no new dependency)

| Component | Purpose | Why |
|-----------|---------|-----|
| `threading.Thread` | Run the autonomy FSM loop as a dedicated background thread, following the existing `Control.condition_monitor` pattern | Matches the codebase's established thread-per-concern architecture; introducing `asyncio` here would create two incompatible concurrency models in one process for no benefit. |
| `threading.Event` | Cooperative enable/disable flag for entering/exiting auto mode | The existing `Thread.stop_thread()` (`ctypes`-based `SystemExit` injection) is explicitly documented as an unofficial, unsafe CPython mechanism not to be used as a template for new code. Auto mode needs a clean on/off switch — `threading.Event.wait(timeout=...)`/`.is_set()` is the standard, safe cooperative-cancellation primitive and costs nothing new to add. |
| `queue.Queue` | Thread-safe hand-off of sensor readings (ultrasonic distance, motion-detected flag) from sensing threads to the FSM decision loop | The existing `Control.command_queue` is a plain mutable list shared across threads with no lock, relying on GIL semantics — acceptable for its narrow existing use, but not something to replicate for new code. `queue.Queue` is the stdlib-correct tool and avoids adding another unsynchronized-shared-state pattern. |
| `time.monotonic()` | Bounded auto-mode runtime (hard stop after N minutes) and per-scan/per-decision timeouts | Matches the "auto mode runs for a bounded duration and stops on its own" requirement; no library needed, `monotonic()` (not `time.time()`) avoids wall-clock-adjustment bugs in a long-running loop. |

Confidence: HIGH — these are stdlib, version-independent, and directly address anti-patterns already documented in `ARCHITECTURE.md`.

### Obstacle Sensing (ultrasonic)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `gpiozero.DistanceSensor` | gpiozero **2.0.1.post3** (latest patch; installed version is 2.0.1) | Continue using the existing ultrasonic wrapper, but use more of its built-in API | Verified via Context7 (`/gpiozero/gpiozero`) docs: `DistanceSensor` already supports `queue_len` (default 9-sample rolling **median** — noise smoothing gpiozero does for you), `max_distance`/`threshold_distance`, and event hooks `when_in_range`/`when_out_of_range` plus blocking helpers `wait_for_near()`/`wait_for_far()`. The current codebase (`Code/Server/ultrasonic.py`) only reads `.distance` directly — the new autonomy code should use the threshold/event API instead of hand-rolling comparisons, since it's already smoothed and tested. The 2.0.1.post3 patch specifically fixes an `lgpio` pin-factory install bug on Pi 5 — worth bumping given the kit explicitly supports Pi 5. |

**Scan pattern (no new library, orchestration only):** Because ultrasonic + camera share one pan/tilt head, use the existing head-pan servo (already driven via `CMD_HEAD` in `control.py`/`servo.py`) to sweep the head through a small set of fixed angles (e.g., left/center/right) between forward steps, take an ultrasonic reading at each, and steer away from the closer side — a **Braitenberg-vehicle-style reactive controller**: this is the standard, well-established pattern for single-beam-sensor obstacle avoidance (a narrow-FOV distance sensor mechanically panned to sample multiple headings, one reading at a time) and requires no additional Python library, just direct calls into the existing `Control`/`Servo` classes instead of round-tripping through the TCP protocol to itself. Confidence: MEDIUM (well-established robotics pattern, corroborated across multiple hobbyist and academic sources, not Pi/Python-specific but directly applicable).

### Patrol / Wall-Follow Behavior

**No new library.** Use a reactive **bug-algorithm-inspired wall-follow controller**: maintain a target standoff distance from the nearest detected surface using the same panned ultrasonic readings, correcting heading proportionally to the error (closer than target → steer away, farther than target → steer toward) — this is the standard technique for wall-following with a single distance sensor and no map, and is exactly the class of behavior the "no SLAM/odometry" constraint calls for. Implement as a state within the `transitions` FSM (`WallFollowing`), not a separate subsystem. Confidence: MEDIUM (well-documented in robotics literature; implementation is straightforward proportional control, no exotic library required — plain Python arithmetic).

**Explicitly avoid:** Fuzzy-logic controller libraries (e.g. `scikit-fuzzy`) sometimes used in academic wall-follow papers — adds a dependency and tuning complexity disproportionate to a bounded, cautious-by-default hobby robot; a simple proportional (P or PD) reactive controller is sufficient and far easier to reason about/debug on real hardware.

### Vision (moving-obstacle caution)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `picamera2` (already a dependency) + `numpy` (already a dependency) | 0.3.36 / 2.2.4 | Lightweight motion detection to satisfy "behave cautiously around unpredictable moving obstacles (pets/kids)" | Verified against picamera2's own official example (`examples/capture_motion.py` in `raspberry pi/picamera2` GitHub repo): capture a **second, low-resolution stream** (e.g. 320×240 "lores" config, which `picamera2` supports natively alongside the main streaming resolution) via `capture_array("lores")`, and compute frame-to-frame difference (mean-squared-error or simple absolute-difference threshold) in plain **numpy** — no OpenCV, no ML model. This is the officially-recommended, zero-new-dependency approach and is cheap enough to run continuously on a Pi without competing with the main video-stream encoder (it runs on a small side-stream, not the full-res feed). It directly satisfies the requirement (detect *something is moving nearby*, react cautiously) without needing to classify *what* is moving. Confidence: HIGH (verified against picamera2's own official example code, cross-checked with independent tutorial sources). |

**Escalation path (optional, only if numpy-only motion diffing proves insufficient during on-device testing):** `apt install python3-opencv` (candidate version **4.10.0+dfsg-5** on this exact Pi, confirmed via `apt-cache policy` — matches the `libopencv410` C libraries already installed as an `rpicam-apps` dependency). **Prefer this over `pip install opencv-python`**: the pip wheel bundles its own ~90MB self-contained OpenCV build, which is redundant with the C libraries already on the system and can create ABI/version conflicts; the apt package links against the libraries already present. Use `cv2.absdiff`/`cv2.findContours`/`cv2.Canny` only if simple heuristics are needed (e.g., floor-edge/contour cues to assist wall-follow), not as a v1 requirement. Confidence: HIGH for the apt-vs-pip recommendation (directly verified on this machine); MEDIUM for whether it will actually be needed (depends on on-device testing results).

**Explicitly avoid for this milestone:**
- **`tflite-runtime`** — the official Debian/pip package is effectively unmaintained (stuck at a TensorFlow 2.5-era build, no reliable aarch64 wheels for current Python), per Google's own GitHub issue tracker and community reports. If lightweight on-device ML classification (e.g., "is this a pet vs. a static object") is wanted later, use Google's successor package, **`ai-edge-litert`** (LiteRT, the TFLite rebrand) with a small model (SSD-MobileNet-v2 or EfficientDet-Lite0) — but this is a v2+ capability, not needed to satisfy the "cautious around moving things" requirement, which motion-diffing already covers. Confidence: MEDIUM (multiple corroborating sources: GitHub issue tracker, Google AI Edge docs, community forum reports).
- **Full `tensorflow`** — far too heavy (build size, RAM, CPU) for a Pi already running a real-time gait/balance loop, camera streaming, and I2C/SPI polling concurrently.
- **`ultralytics` (YOLOv8/v11)** — even the "nano" variants are CPU-inference-heavy relative to what a Pi can sustain alongside the existing workload; reported real-world Pi 4/5 CPU-only inference rates (roughly single-digit to ~10 FPS depending on model/resolution) aren't worth the dependency weight for a reactive-caution use case that motion-diffing solves more cheaply.
- **ROS / ROS2** — the standard toolkit for multi-sensor robots with SLAM, but it assumes a pub/sub node graph, a build system (colcon), and (usually) a different OS packaging model; wildly disproportionate to "one ultrasonic sensor and reactive avoidance on a hand-rolled TCP server," and would mean re-architecting the entire project. Not warranted absent SLAM/multi-robot/complex-sensor-fusion needs, none of which apply here.
- **SLAM/mapping libraries** (`gmapping`, `cartographer`, `RTAB-Map`, etc.) and **depth-camera/LIDAR SDKs** — no odometry or depth/LIDAR hardware exists on this robot; explicitly out of scope per `PROJECT.md`.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Behavior orchestration | `transitions` (FSM) | `py_trees` (behavior tree) | Overkill for a linear manual↔auto + handful-of-substates flow; heavier dependency footprint aimed at multi-behavior arbitration this milestone doesn't need. |
| Behavior orchestration | `transitions` (FSM) | Hand-rolled if/elif dispatch | Replicates an anti-pattern already flagged in `ARCHITECTURE.md`; a small mature library is worth the one dependency. |
| Vision | numpy frame-diff on picamera2 lores stream | OpenCV from the start | Zero new dependencies, matches picamera2's own official example, sufficient for "detect motion nearby"; OpenCV adds ~90MB (if pip) or a new server-side dependency (if apt) for a need not yet proven necessary. |
| Vision | numpy frame-diff | TFLite/LiteRT object detection | Requires model selection/quantization, an unmaintained-runtime risk (`tflite-runtime`), and CPU budget the reactive-caution use case doesn't actually need (classification isn't required to justify "slow down, something's moving"). |
| Wall-follow control | Simple proportional (P/PD) reactive controller | Fuzzy-logic controller (`scikit-fuzzy`) | Academic literature favors fuzzy logic for smoothness, but adds tuning complexity and a dependency disproportionate to a bounded, safety-conservative hobby robot; P/PD control is simpler to reason about and debug live on hardware. |
| Sensor smoothing | `gpiozero.DistanceSensor` built-in `queue_len` median + event API | Hand-rolled polling/threshold logic (current `ultrasonic.py` style) | Already implemented, tested, and shipped in the dependency the project already uses — no reason to reinvent it for new code. |
| Multi-sensor coordination | Sequential head-pan sweep (mechanical) | Simultaneous multi-direction sensing | Hardware constraint: ultrasonic + camera are physically co-mounted on one 2-axis head; simultaneous multi-heading sensing isn't physically possible without new hardware, which is explicitly out of scope for v1. |

## Installation

```bash
# Behavior FSM (prefer apt for consistency with existing setup.py package-manager conventions;
# pip gives the very latest patch release if desired)
sudo apt install python3-transitions          # apt candidate: 0.9.2-2
# — or —
pip3 install transitions==0.9.3               # latest PyPI release

# Bump gpiozero to pick up the Pi 5 lgpio pin-factory fix
pip3 install --upgrade gpiozero==2.0.1.post3

# Optional escalation path only — do NOT install unless numpy-based motion diffing
# proves insufficient in on-device testing:
sudo apt install python3-opencv                # apt candidate: 4.10.0+dfsg-5 (matches
                                                # libopencv410 already installed as an
                                                # rpicam-apps dependency)
```

No new dependency is required for: concurrency glue (`threading`, `queue`, `time` — stdlib), ultrasonic sensing (`gpiozero`, already present), or vision motion-detection (`picamera2` + `numpy`, both already present).

## Sources

- gpiozero `DistanceSensor` API (`queue_len`, `threshold_distance`, `when_in_range`/`when_out_of_range`, `wait_for_near`/`wait_for_far`) — verified via Context7 (`/gpiozero/gpiozero`, sourced from `github.com/gpiozero/gpiozero/blob/master/docs/api_input.md` and `docs/recipes.md`). HIGH confidence.
- picamera2 official motion-detection example (`examples/capture_motion.py`, numpy MSE frame-diff on a lores capture stream) — [raspberrypi/picamera2 GitHub](https://github.com/raspberrypi/picamera2), cross-checked with independent tutorials. HIGH confidence.
- `transitions` (pytransitions) — [PyPI](https://pypi.org/project/transitions/), [GitHub](https://github.com/pytransitions/transitions). MEDIUM-HIGH confidence (mature/maintained, not Context7-indexed).
- `python3-opencv` / `libopencv410` availability and version — directly verified on this Raspberry Pi via `apt-cache policy python3-opencv` and `apt list --installed | grep opencv`. HIGH confidence (machine-verified, not just documentation).
- `tflite-runtime` deprecation / `ai-edge-litert` (LiteRT) migration — [google-ai-edge/LiteRT GitHub issue #71](https://github.com/google-ai-edge/LiteRT/issues/71), [Google AI Edge LiteRT docs](https://ai.google.dev/edge/litert/microcontrollers/python), Google AI Developer forum. MEDIUM confidence (multiple corroborating sources, no single authoritative deprecation announcement found).
- Reactive wall-following / Braitenberg-vehicle / bug-algorithm approaches for single-sensor mobile robots — academic sources via WebSearch: ["Wall Following with a Single Ultrasonic Sensor" (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-16587-0_13), [Reactive-Wall-Following-Robot (GitHub)](https://github.com/Octanas/Reactive-Wall-Following-Robot), [Chaotic Transitions in Wall Following Robots (arXiv)](https://arxiv.org/abs/0908.3653). MEDIUM confidence (well-established domain literature, not Python/Pi-specific implementations).
- TFLite/SSD-MobileNet Raspberry Pi 4 inference FPS figures (cited to justify avoiding ML classification for v1) — [EdjeElectronics TensorFlow-Lite-Object-Detection tutorial](https://github.com/EdjeElectronics/TensorFlow-Lite-Object-Detection-on-Android-and-Raspberry-Pi), [EJ Technology Consultants TFLite model comparison](https://www.ejtech.io/learn/tflite-object-detection-model-comparison). MEDIUM confidence (figures vary widely by source/model/quantization — used only as directional justification, not a precise benchmark).
- Existing project docs read for context: `.planning/PROJECT.md`, `.planning/codebase/STACK.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/INTEGRATIONS.md`.
