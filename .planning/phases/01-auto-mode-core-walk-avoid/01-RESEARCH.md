# Phase 1: Auto-Mode Core — Walk & Avoid - Research

**Researched:** 2026-08-07
**Domain:** Reactive obstacle-avoidance autonomy bolted onto an existing threaded, command-queue-driven hexapod server (Freenove Big Hexapod, Raspberry Pi, `gpiozero`/`picamera2`/PyQt5 stack)
**Confidence:** MEDIUM-HIGH — architecture/integration findings are HIGH confidence (verified by direct reading of the actual installed source, both this repo's code and the installed `gpiozero` 2.0.1 package on this machine); behavioral/tuning findings (thresholds, turn angles) are already locked by CONTEXT.md decisions; a few structural risks (gait-interrupt latency, ultrasonic no-echo semantics) are new findings from this session not previously identified in prior milestone research.

## Summary

This phase adds the smallest possible end-to-end autonomy slice — toggle, walk, sense, stop-and-turn, bounded-timeout, manual-override — on top of a codebase that already has three known, documented hazards sitting directly in this phase's critical path: an unsynchronized multi-writer `command_queue`, a dead TCP reconnect path, and (newly confirmed this session) a `gpiozero.DistanceSensor` smoothing layer that structurally cannot surface "no echo" as a distinguishable signal through the wrapper's current public API. All three must be addressed by this phase's plans, not deferred, because all three sit directly underneath this phase's stated safety properties (AUTO-02 manual override, CAUTION-01 never-treat-unknown-as-clear).

The two most consequential findings from direct source verification this session, beyond what prior milestone research already flagged:

1. **`Ultrasonic.get_distance()` (`Code/Server/ultrasonic.py:21-33`) cannot currently return `None` on a real no-echo condition.** Its own `except RuntimeWarning` clause is dead code (gpiozero raises a `warnings.warn()`, not an exception, and the module already suppresses that warning category). Worse: gpiozero's `DistanceSensor` is built on `SmoothedInputDevice`, which is constructed with `ignore=frozenset({None})` — meaning every no-echo `_read()` result is silently dropped from the smoothing queue rather than surfaced. A transient no-echo is invisible (the median just uses the remaining valid samples); a **persistent** no-echo freezes the reported distance at whatever was last known-good, indefinitely, with no signal that anything is wrong. And if the sensor has *never* had a single successful echo since boot, `.distance` blocks the calling thread forever (`GPIOQueue.value`'s `self.full.wait()` has no timeout). New autonomy code must not rely on the existing `get_distance()` wrapper for "unknown" detection — see Pitfall 1 below for the concrete fix.
2. **`run_gait()` (`Code/Server/control.py:329-404`) cannot be interrupted mid-call.** It's a synchronous loop with no `command_queue` check inside its inner `for`/`time.sleep(delay)` iterations. At the slowest configurable speed, a single call blocks the shared `condition_monitor` thread for up to ~1.7 seconds before the next command (including a manual override) can take effect. This directly conflicts with the literal wording of AUTO-02 / ROADMAP success criterion #2 ("no wait for the current autonomous action to finish") unless either (a) auto-mode's own forward-walk speed is chosen high enough to keep worst-case latency low, or (b) `run_gait`'s inner loop is modified to check an interrupt signal every iteration — see Pitfall 2.

Everything else — command_queue arbitration strategy, the TCP reconnect bug, the cooperative-stop pattern, head-servo channel/range mapping — was already scoped by CONTEXT.md's decisions (D-01 through D-13) or by prior milestone research (`.planning/research/*.md`); this document verifies those claims against the actual source and adds the file:line precision the planner needs, plus the two new findings above.

**Primary recommendation:** Build auto-mode as a new, self-contained `Code/Server/autonomy/` module that never modifies `Control`'s kinematics, reuses the *existing* `Server.ultrasonic_sensor` and `Server.servo_controller` instances (do not construct new ones), arbitrates with the manual path via a single `threading.Event` gate around every write to `Control.command_queue`, and treats "no fresh confirmed sensor reading" (not "get_distance() returned None") as the unknown/unsafe signal — because the latter cannot currently happen through the existing wrapper.

## Architectural Responsibility Map

This project has no web-style tiers (browser/SSR/API/CDN/DB); the equivalent decomposition is Client GUI ↔ Server networking ↔ Server domain/control ↔ hardware drivers. Mapped accordingly:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Auto-mode toggle UI + status badge (AUTO-01, AUTO-04) | Client GUI (`Code/Client/`) | Server networking (new `CMD_AUTO`) | User-facing control belongs in the PyQt5 client; server just needs a new protocol constant to receive it |
| Manual-preempts-auto arbitration (AUTO-02) | Server networking (`Server.receive_commands`) | New autonomy module | Arbitration must live where both manual and autonomous writers converge — `server.py`'s command dispatch is that point |
| Bounded-runtime auto-stop (AUTO-03) | New autonomy module | Server networking (lifecycle owner) | Timer logic belongs with the decision loop that owns "am I still allowed to move"; must run independent of client connection state (D-02) |
| Ultrasonic sensing + head sweep (SENSE-01, SENSE-02) | New autonomy module (`perception.py`) | Hardware driver (`Ultrasonic`, `Servo`) | New pure-sensing code reusing existing driver objects — never inside `Control` |
| Stop/turn decision + hysteresis (AVOID-01, CAUTION-01) | New autonomy module (`behavior.py`) | — | Pure decision logic, hardware-independent, the AI-swappable seam per prior architecture research |
| Actuation (walk, turn, stand) | Existing `Control`/`condition_monitor` (unmodified) | New autonomy module writes intents into it | `Control.command_queue` is reused as-is; autonomy never calls `Servo`/`Control` methods directly for leg movement |
| TCP reconnect fix (`tcp_flag`/`is_tcp_active`) | Server networking (`server.py`, `main.py`) | — | Structural prerequisite for AUTO-02's "manual override always available" safety claim (D-01) |

## Project Constraints (from CLAUDE.md)

These are binding, not optional, and shape both this research and the plan:

- **No new sensor hardware.** Ultrasonic + camera on the existing pan/tilt head only — no LiDAR/IR/second ultrasonic. Auto-mode sensing in this phase is ultrasonic-only (camera stays as today's streaming pipe; camera-based caution is explicitly Phase 3/CAUTION-02).
- **Safety bias:** "auto mode must err toward slowing/stopping rather than pushing through when something unexpected is nearby" — directly reinforces D-04/D-06/CAUTION-01 (stop-and-reassess, never nudge past, never treat unknown as clear).
- **No localization/SLAM** — not relevant to Phase 1 (walk-forward + reactive stop/turn only; PATROL-01 is Phase 2).
- **No CI, no automated test framework for first-party code.** "Verification relies on live, on-device hardware testing (feasible here since the session runs on the robot's own Pi)." This is a standing project constraint, not a gap to fill — see Validation Architecture below for how this reshapes the usual Wave-0-gap-filling approach.
- **GSD workflow enforcement:** file-changing work must go through a GSD command (`/gsd-execute-phase` etc.), not ad hoc edits — applies to whoever executes this phase's plan, not to this research document.
- Naming/style conventions from CLAUDE.md's Conventions section apply to all new server-side files: `snake_case.py` filenames, `PascalCase` classes, heavy inline `#` comments matching the "modernized files" style (`adc.py`, `camera.py`, `buzzer.py`, `pca9685.py` are the reference examples), `except Exception as e: print(f"...: {e}")` rather than bare `except:` for new code (the codebase's dominant *existing* style is bare `except:`, but CLAUDE.md's own Error Handling guidance singles this out as the pattern **new/modernized code should still prefer** — do not copy the legacy bare-except style into autonomy code, which doubles as Pitfall 6 below).

## Standard Stack

### Core (all already present — zero new required dependencies for Phase 1's minimum scope)

| Library | Version (verified installed) | Purpose | Provenance |
|---------|-------|---------|--------------|
| `gpiozero` | 2.0.1 (`pip3 show gpiozero`, this machine) | Ultrasonic distance sensing (existing `Ultrasonic` class) | [VERIFIED: local install, confirmed via `pip3 show`] |
| Python stdlib `threading` (`Event`, `Thread`, `Lock`) | 3.13.5 | Cooperative stop flag, arbitration gate, new autonomy threads — matches existing thread-per-concern model | [VERIFIED: stdlib, no install needed] |
| Python stdlib `time` (`monotonic()`) | 3.13.5 | Bounded 5-minute runtime timer (D-08), sensor-reading staleness checks | [VERIFIED: stdlib] |
| Existing `Servo` (`Code/Server/servo.py`) | n/a (in-repo) | Head pan/tilt servo writes for head-sweep | [VERIFIED: read directly, `Code/Server/servo.py:19-34`] |
| Existing `command.py`/`Command.py` `COMMAND` class | n/a (in-repo) | Add exactly one new constant (`CMD_AUTO`) to both copies, following the existing (if awkward) dual-file convention | [VERIFIED: read directly] |

### Supporting (optional, discretionary)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `transitions` (pytransitions) | 0.9.3 on PyPI (confirmed via `pip3 index versions transitions`); apt candidate `python3-transitions` 0.9.2-2 | Small explicit FSM for auto-mode states (Idle/Walking/Scanning/Avoiding/Stopping) | **Optional for Phase 1.** Phase 1 needs only ~4-5 states with simple, mostly-linear transitions (walk → sense → [continue \| stop-and-turn] → walk, plus timeout/manual-override exits from any state). A hand-rolled `enum` + small dispatch function is likely sufficient and avoids adding a dependency + Package Legitimacy Audit burden for an MVP phase. Reconsider `transitions` in Phase 2 when wall-follow/patrol adds more real states (per prior milestone research's original recommendation). |

**Alternatives considered:**

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled state dispatch (recommended for Phase 1) | `transitions` library | `transitions` gives cleaner transition-guard semantics and is more testable, but is unnecessary machinery for ~5 states; adds a new dependency + legitimacy-audit + install step to an MVP phase whose core risk is concurrency/safety, not state-machine complexity |
| `queue.Queue`-based sensor handoff | Lock-protected "latest value" attribute (recommended, matches existing `command_queue` convention) | A real multi-producer queue is over-engineering for one producer (SensorHub) / one consumer (decision loop); a GIL-safe single-attribute handoff matches how `command_queue` itself already works |

**Installation (only if `transitions` is chosen):**
```bash
pip3 install transitions==0.9.3
# or: sudo apt install python3-transitions
```

**Version verification performed this session:**
```
$ pip3 show gpiozero
Version: 2.0.1                              # matches prior milestone research
$ pip3 index versions transitions
transitions (0.9.3)  Available versions: 0.9.3, 0.9.2, ...
$ pip3 show pytest
WARNING: Package(s) not found: pytest       # not installed — see Validation Architecture
```

## Package Legitimacy Audit

Phase 1's **required** dependency set is zero new packages (everything needed is already installed or stdlib). The audit below covers the one **optional** package surfaced above, in case the planner elects to use it.

Package name provenance: `transitions` was originally surfaced by prior milestone research via WebSearch/PyPI/GitHub, not Context7 or official docs — per the package-name provenance rule, it is tagged `[ASSUMED]` regardless of the clean slopcheck/registry results below.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `transitions` | PyPI | First released 2014 (per PyPI history); still actively releasing (0.9.3 current) | Not machine-verified this session (no download-count check performed) | `github.com/pytransitions/transitions` | `[OK]` (`slopcheck scan transitions --pkg pypi`, this session) | Approved-if-used — not required for Phase 1's minimum scope; tag `[ASSUMED]` per provenance rule despite clean scan |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Packages required for Phase 1's minimum viable implementation:** none (zero new installs needed)

## Architecture Patterns

### System Architecture Diagram

```text
                         Wi-Fi / TCP (existing, unmodified)
 ┌────────────────────┐  port 5002 commands   ┌──────────────────────────────────────────────┐
 │  Client (PyQt5)     │───────────────────────►│  Server (Raspberry Pi)                       │
 │  new: Auto Mode     │                        │  server.py: receive_commands()                │
 │  toggle + status    │                        │   ├─ existing manual dispatch (CMD_MOVE, ...) │
 │  badge (D-11..D-13) │                        │   │    └─ writes Control.command_queue        │
 └────────────────────┘                        │   └─ NEW: CMD_AUTO#1 / CMD_AUTO#0              │
                                                 │        └─ sets/clears auto_mode_active Event   │
                                                 │                                                │
                                                 │  NEW Code/Server/autonomy/ (this phase)        │
                                                 │  ┌──────────────┐  ┌─────────────────────────┐ │
                                                 │  │ perception.py │  │ behavior.py              │ │
                                                 │  │ SensorHub      │─►│ small state dispatch     │ │
                                                 │  │ (own thread)   │  │ (own thread, ~5-10Hz)    │ │
                                                 │  │ ultrasonic +   │  │ stop/turn/walk decisions │ │
                                                 │  │ head-sweep     │  │ + bounded-runtime timer  │ │
                                                 │  └──────┬─────────┘  └───────────┬─────────────┘ │
                                                 │         │ reads                  │ writes         │
                                                 │         ▼                        ▼                │
                                                 │  Server.ultrasonic_sensor   Control.command_queue │
                                                 │  Server.servo_controller    (existing, gated by    │
                                                 │  (existing instances,        auto_mode_active +    │
                                                 │   reused, NOT duplicated)    manual-preempt check) │
                                                 │                                     │              │
                                                 │                                     ▼              │
                                                 │                     Control.condition_monitor()    │
                                                 │                     (existing, UNMODIFIED except   │
                                                 │                     possibly run_gait's inner-loop │
                                                 │                     interrupt check — see Pitfall 2)│
                                                 └────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
Code/Server/
├── autonomy/                  # NEW package for this phase
│   ├── __init__.py
│   ├── perception.py          # SensorHub: ultrasonic + head-sweep polling, "latest snapshot" accessor
│   ├── behavior.py            # Decision loop: stop/turn/walk state dispatch, bounded-runtime timer
│   └── bridge.py              # Intent -> Control.command_queue translation (or fold into behavior.py if small)
├── command.py                 # + one new CMD_AUTO constant
├── server.py                  # + CMD_AUTO dispatch, auto_mode_active Event, manual-preempt hook
├── main.py                    # + tcp_flag/is_tcp_active rename fix (D-01)
├── control.py                 # UNMODIFIED except possibly run_gait interrupt-check (Pitfall 2)
└── ultrasonic.py               # UNMODIFIED (autonomy bypasses its smoothing for staleness-critical reads — Pitfall 1)
```

### Pattern 1: Reuse existing hardware singletons — do not construct new ones

**What:** `SensorHub` must take `server.ultrasonic_sensor` and `server.servo_controller` as constructor arguments (the exact instances created at `Code/Server/server.py:35,39` inside `Server.__init__`), not create its own `Ultrasonic()`/`Servo()`.
**Why:** `Ultrasonic()` claims GPIO pins 27 (trigger) and 22 (echo) via `gpiozero.DistanceSensor` (`Code/Server/ultrasonic.py:6,13`) — a second instance would either fail to claim the pins (`GPIOPinInUse`-class error) or produce two independent, uncoordinated sensor objects reading the same physical hardware. Similarly, `Servo()` opens two `PCA9685` I2C handles (`Code/Server/servo.py:11-12`); the codebase already has two separate `Servo()` instances in memory (`Control.servo` at `control.py:17` for legs, `Server.servo_controller` at `server.py:36` for head/camera) — adding a third specifically for autonomy would be a step further into an already-imperfect pattern. Reuse `Server.servo_controller`, since that is the exact object the existing, human-tested `CMD_HEAD`/`CMD_CAMERA` paths already drive (`server.py:181-189`).
**Example:**
```python
# Source: pattern derived from Code/Server/server.py:29-43 (Server.__init__)
class SensorHub:
    def __init__(self, ultrasonic_sensor, head_servo, pan_channel=1, tilt_channel=0):
        self._ultrasonic = ultrasonic_sensor   # the Server's existing instance — do not construct a new one
        self._servo = head_servo               # Server.servo_controller — same object CMD_HEAD/CMD_CAMERA use
        self._pan_channel = pan_channel
        self._tilt_channel = tilt_channel
```

### Pattern 2: Bypass `Ultrasonic.get_distance()`'s smoothing for the no-echo signal

**What:** For staleness/unknown detection specifically, read the underlying `gpiozero.DistanceSensor._read()` result directly (via `ultrasonic_sensor.sensor._read()`) rather than `ultrasonic_sensor.get_distance()`, because — per this session's direct verification of the installed gpiozero 2.0.1 source — `get_distance()`'s smoothing layer silently discards `None` (no-echo) results and can never surface them to the caller (see Pitfall 1 for the full mechanism).
**When:** Any time the "is this reading trustworthy right now" decision matters — i.e., exactly the CAUTION-01/SENSE-01 requirement this phase must satisfy.
**Example:**
```python
# Source: verified against installed gpiozero 2.0.1 (/usr/lib/python3/dist-packages/gpiozero/input_devices.py),
# read directly this session via `python3 -c "import inspect; ..."`.
# DistanceSensor._read() is bounded (<=150ms worst case) and returns:
#   - a float in [0.0, 1.0] (normalized value, multiply by max_distance for meters) on success
#   - None on genuine no-echo (bypasses the smoothing queue's ignore={None} swallowing)
def read_raw_distance_cm(ultrasonic_sensor):
    raw = ultrasonic_sensor.sensor._read()   # bypasses SmoothedInputDevice averaging deliberately
    if raw is None:
        return None                           # genuine "unknown" — never treat as clear
    return round(raw * ultrasonic_sensor.max_distance * 100, 1)
```
**Caveat:** `_read()` is a semi-private method (leading underscore) on a third-party class not covered by gpiozero's public API contract — it could change across gpiozero releases without notice in a changelog. This is a deliberate, documented tradeoff to get an honest no-echo signal; the alternative (staying on the public `.distance` API) cannot satisfy CAUTION-01 as written — see Pitfall 1's "Alternative, less invasive mitigation" for a public-API-only fallback if the planner prefers not to touch a private method.

### Pattern 3: Single `threading.Event` arbitration gate, manual always wins

**What:** One `auto_mode_active = threading.Event()`, owned by `Server`. Autonomy's decision loop checks `is_set()` before every write to `command_queue` and stops producing entirely (not just idling) when clear. `Server.receive_commands()` clears the event on receipt of any manual movement command (`CMD_MOVE`, `CMD_POSITION`, `CMD_ATTITUDE`, `CMD_BALANCE`) — i.e. the existing final `else` branch at `server.py:205-207` — *before* writing the manual command to `command_queue`.
**Why:** `Control.command_queue` (`control.py:32`) is a plain 6-element list read/written from `Control.condition_monitor` (`control.py:133-218`) and from `Server.receive_commands` (`server.py:206-207`) with zero locks today — this is a pre-existing, documented hazard (`.planning/codebase/CONCERNS.md` "Shared mutable state across threads without locks"). Adding autonomy as a third unsynchronized writer would make an already-fragile pattern safety-load-bearing. A single boolean gate checked before every autonomy write (not a queue/lock refactor of `command_queue` itself) is the minimal change that fixes the specific new hazard without touching `Control`.
**Example (shape, not literal code):**
```python
# server.py — inside receive_commands(), replacing the final else branch
else:
    if command_parts[0] in (cmd.CMD_MOVE, cmd.CMD_POSITION, cmd.CMD_ATTITUDE, cmd.CMD_BALANCE):
        self.auto_mode_active.clear()          # manual always preempts, checked first
    self.control_system.command_queue = command_parts
    self.control_system.timeout = time.time()
```

### Pattern 4: Cooperative stop via `threading.Event`, never `Thread.stop_thread()`

**What:** New autonomy threads created on `CMD_AUTO#1`, torn down via a cooperative `stop_event.is_set()` check + `thread.join(timeout=...)` on `CMD_AUTO#0`/bounded-timeout/manual-override, never via `Code/Server/Thread.py`'s `stop_thread()` (`ctypes.pythonapi.PyThreadState_SetAsyncExc` injection, `Thread.py:20-22`).
**Why:** `stop_thread()` is explicitly documented in this repo's own architecture notes as "not to be used as a template for new cancellable-thread code" — it can fire mid-I2C-write and leave hardware state inconsistent. D-09 already locks this decision ("cooperative, `threading.Event`-style stop checked at step boundaries").
**Where the boundary naturally falls:** Each `run_gait()` call is already a bounded unit (F frames × 0.01s ≈ 0.22s–1.71s depending on speed — see Pitfall 2 for the exact numbers) that `condition_monitor` re-invokes from its `while True` top on every pass when a `CMD_MOVE` with nonzero x/y stays in `command_queue` (`control.py:159-167`). This existing call boundary is the natural place for D-09's "finishes current gait step, then settles" behavior — but it is **not** fast enough by itself to satisfy D-10's stricter "immediate" manual-override requirement (Pitfall 2).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-thread cooperative cancellation | A new ad hoc "stop flag" convention per thread | `threading.Event` (stdlib) | Standard, safe, already the pattern this phase's own D-09/D-10 specify |
| Sensor/decision handoff | A hand-rolled polling protocol with custom locking | A single lock-protected "latest value" object (mirrors how `command_queue` already works) OR `queue.Queue` if truly multi-consumer later | Don't invent new concurrency primitives when the codebase already has an established (if imperfect) convention to match |
| No-echo detection | Trusting `Ultrasonic.get_distance()`'s `None` return (it can't produce one — Pitfall 1) | Direct `sensor._read()` bypass, or a staleness/timeout wrapper around the public API if avoiding private methods | The public wrapper structurally cannot deliver the signal CAUTION-01 requires; building a "wait for None that never comes" detector would silently fail |
| Bounded-runtime timer | Reusing `Control.condition_monitor`'s existing 10-second idle-to-relax timeout (`control.py:135-138`) for auto-mode's 5-minute cutoff | A dedicated timer inside the new autonomy decision loop, independent of `Control`'s unrelated idle-relax timer | Different concern, different duration, different owner — conflating them would make `Control` aware of autonomy, violating the "never modify Control's state machine" principle |

**Key insight:** Every piece of new infrastructure this phase might be tempted to build (a queue, a lock, a cancellation mechanism, a no-echo detector) either already exists in the stdlib/gpiozero or has an existing in-repo convention to extend — the actual engineering work is arbitration and honest failure-mode handling, not new primitives.

## Common Pitfalls

### Pitfall 1: `Ultrasonic.get_distance()` structurally cannot return `None` on no-echo (new finding, HIGH confidence — verified against installed gpiozero 2.0.1 source this session)

**What goes wrong:** Code written to satisfy CAUTION-01/SENSE-01 by checking `if get_distance() is None: treat_as_unknown()` will never trigger that branch in practice — the check is dead on arrival.

**Why it happens (mechanism, verified via direct source read of `/usr/lib/python3/dist-packages/gpiozero/input_devices.py`, gpiozero 2.0.1):**
1. `Code/Server/ultrasonic.py:13` constructs `DistanceSensor(echo=22, trigger=27, max_distance=3.0)` with no `queue_len`/`partial` override, so gpiozero defaults apply: `queue_len=9`, `partial=False`.
2. `DistanceSensor.__init__` passes `ignore=frozenset({None})` to its parent `SmoothedInputDevice.__init__` — meaning the background `GPIOQueue.fill()` thread's `if value not in self.ignore: self.queue.append(value)` (gpiozero `input_devices.py`, `GPIOQueue.fill`) **never appends a `None` (no-echo) reading to the smoothing deque at all.**
3. `GPIOQueue.value` (gpiozero `input_devices.py`) computes `self.average(self.queue)` (default `statistics.median`) over whatever valid readings remain — a no-echo simply doesn't participate, so a **transient** no-echo is invisible (median just uses the other 8 samples), and a **persistent** no-echo freezes the reported value at the last-known-good reading indefinitely, since nothing ever evicts the frozen entries when no new valid samples arrive to replace them.
4. If the sensor has had **zero** successful echoes since the queue was created (e.g. boot-time miswiring, or genuinely nothing in range at all — unlikely indoors but not impossible), `GPIOQueue.value` calls `self.full.wait()` with `partial=False`, which is a bare `threading.Event.wait()` with **no timeout** — this blocks the calling thread **forever**, not for a bounded time.
5. `Code/Server/ultrasonic.py:31` catches `except RuntimeWarning` — but gpiozero raises `DistanceSensorNoEcho` via `warnings.warn(...)`, a warning, not a raised exception, and `ultrasonic.py:8` already suppresses that warning category globally. This except clause is dead code (matches `.planning/codebase/CONCERNS.md`'s existing finding, now confirmed to also be functionally irrelevant even if it weren't dead, since the exception path it guards against cannot occur).

**Consequences:** A robot that walks toward a couch cushion, pet fur, or a steeply-angled surface (Pitfall 1's classic mechanism from prior milestone research) will, under this specific driver's actual behavior, either (a) keep reporting the last valid distance from before it got close enough to lose the echo — i.e., report itself as further away than it actually is, the exact opposite of caution — or (b), in the boot-time all-zero-echo edge case, hang the sensing thread forever with no error, silently disabling obstacle detection entirely.

**Prevention:**
- **Preferred:** Bypass the smoothing layer for autonomy's reads — call `ultrasonic_sensor.sensor._read()` directly (Pattern 2 above). This is bounded (≤150ms worst case: 50ms + 100ms per gpiozero's own internal timeouts) and returns a genuine `None` on no-echo, unfiltered.
- **Fallback if avoiding the private `_read()` call is a hard requirement:** Construct a second lightweight staleness tracker around the public API: record `time.monotonic()` alongside every `get_distance()` result; treat N consecutive **bit-identical** readings (rounded to the wrapper's existing 1-decimal precision) over more than a few poll intervals as suspect/stale and fall back to "unknown." This is a heuristic (a genuinely static scene could coincidentally repeat), weaker than the `_read()` bypass, but avoids touching gpiozero internals.
- Either way, wrap the **very first** distance read at autonomy startup in an explicit bounded-wait (e.g. run it in a helper thread and `join(timeout=1.0)`) to guard against the boot-time "queue never fills, `.value` hangs forever" case — do not let auto-mode's first sensor read be an unbounded blocking call.
- Empirically characterize this on real hardware (pillow, rug edge, person's leg at an angle) before trusting any threshold in production, per prior milestone research's Pitfall 1/12 guidance — this remains valid and is now more urgent given the mechanism above.

**Detection (warning signs):** During testing, log every raw `get_distance()`/`_read()` value; watch for long runs of bit-identical values (indicates the frozen-median failure mode) or a hang at startup with no console output after "Client connection successful."

**Phase mapping:** Sensing/perception work within this phase (SENSE-01) — this must be resolved before any avoidance decision logic is built on top of raw readings, not discovered during hardware testing.

### Pitfall 2: `run_gait()` has no per-iteration interrupt check — worst case ~1.7s before manual override takes effect (new finding, HIGH confidence — verified by direct read of `control.py:329-404`)

**What goes wrong:** A literal reading of AUTO-02/D-10 ("manual override cuts in immediately, no wait for the current autonomous action to finish") is not met by the existing gait-execution boundary alone.

**Why it happens (verified):**
- `Control.condition_monitor()`'s `CMD_MOVE` branch (`control.py:159-167`): when `x!=0 or y!=0` (i.e. walking, not just rotating in place), it calls `self.run_gait(self.command_queue)` **without clearing `command_queue` afterward**, so the very next `while True` pass re-enters the same branch and calls `run_gait` again — this is how continuous walking works. But within a single `run_gait()` call, the inner `for j in range(F): ... time.sleep(delay)` (gait 1, `control.py:349-385`) or the nested `for i / for j / for k` loop (gait 2, `control.py:386-404`) never checks `command_queue` — it always runs to completion.
- `F` is derived from the commanded speed (`data[4]`, protocol range 2-10) via `map_value`: gait "1" → `F = map_value(speed, 2, 10, 126, 22)` (`control.py:334`), else (gait "2") → `F = map_value(speed, 2, 10, 171, 45)` (`control.py:336`). At `delay=0.01` (`control.py:339`), worst case (slowest speed=2) is **F≈171 iterations × 0.01s ≈ 1.71s** for gait 2, **F≈126 × 0.01s ≈ 1.26s** for gait 1, before `condition_monitor` re-checks `command_queue` and could pick up a manual command that arrived mid-call.
- At the fastest speed (10), F drops to 22–45, giving a much smaller worst case (~0.22–0.45s).

**Consequences:** If auto-mode's forward-walk speed is chosen low (e.g. speed=2-3 for a slow, cautious gait — an intuitively "safe" choice), a manual override sent while a `run_gait()` call is in flight could take up to ~1.3-1.7 seconds to actually stop the robot — this is a real gap against the roadmap's literal "no wait" wording, not a hypothetical.

**Prevention (two non-exclusive options for the planner to weigh):**
1. **Speed choice mitigation (no code change to `Control`):** Choose a relatively brisk default auto-walk speed (e.g. 6-8 of the 2-10 range) to keep worst-case single-call latency in the ~0.3-0.6s range. Cheap, but doesn't make the "no wait" guarantee literally true, only smaller.
2. **Interrupt-check mitigation (touches `Control`, deviates from prior research's "never modify Control" architectural purity, but is the only way to bound latency to ~10ms):** Add a per-iteration check inside `run_gait`'s inner loops (e.g. `if self._override_requested(): return` checked once per `time.sleep(delay)` tick) gated behind a new, narrow method/flag that only autonomy's arbitration path sets — not a general refactor of `Control`'s command handling. `.planning/codebase/CONCERNS.md`'s own "Performance Bottlenecks" section already independently identifies and recommends this exact fix ("Check `self.command_queue` for a new command inside the inner loops... to allow faster response to new commands or emergency stop").

**Recommendation for planning:** This is a genuine architectural trade-off between "leave `Control` untouched" (prior milestone research's stated principle) and "meet AUTO-02 literally." Flag as an explicit decision point for the planner/discuss-phase rather than resolving unilaterally here — see Open Questions.

**Detection:** Time from manual key-press to observed motion stop during testing, specifically while the robot is auto-walking at a slow speed setting.

**Phase mapping:** Concurrency/arbitration work within this phase (AUTO-02) — must be resolved before claiming success criterion #2 is met, not discovered during acceptance testing.

### Pitfall 3: Race condition between manual (TCP) and autonomous writers on `Control.command_queue` (confirmed pre-existing hazard — HIGH confidence, `.planning/codebase/CONCERNS.md` + direct read)

**What goes wrong:** Without an explicit arbitration point, autonomy becomes a third unsynchronized writer alongside `Server.receive_commands` (`server.py:206-207`) and reader `Control.condition_monitor` (`control.py:133-218`), all touching the same plain 6-element list with zero locks.

**Prevention:** Pattern 3 above (single `threading.Event` gate, manual always clears it first). This does not require refactoring `command_queue` itself into a `Queue`/locked structure — the Event gate is sufficient because there is still only ever one active writer at a time (manual XOR autonomy), not concurrent writers.

**Phase mapping:** This phase, as the concurrency/arbitration slice — CONTEXT.md's D-01 through D-13 already scope the required behavior; this pitfall confirms the underlying mechanism precisely.

### Pitfall 4: Unsafe thread-kill (`stop_thread()`) must not be reused for auto-mode shutdown (confirmed — HIGH confidence, D-09 already locks the correct behavior)

Covered by Pattern 4 above. `Thread.py:20-22`'s `stop_thread()` retry loop (`for i in range(5): _async_raise(...)`) is itself evidence the original authors already found this mechanism unreliable — do not extend it to autonomy.

### Pitfall 5: Dead TCP reconnect path undermines "manual override always available" (confirmed — HIGH confidence, exact lines verified this session)

**What goes wrong:** `Code/Server/main.py:26,49` set `self.server.tcp_flag = True` and `main.py:57` sets it `False`, but `Server` (`server.py`) never defines or reads an attribute called `tcp_flag` anywhere — it only has `self.is_tcp_active`, set once to `False` at `server.py:32` and **never set to `True` anywhere in the codebase**. `server.py:128` (`if self.is_tcp_active: self.reset_server()`) and `server.py:133` (`if received_data == "" and self.is_tcp_active:`) are therefore permanently dead — a dropped/failed client connection always falls through to `break` (`server.py:130,135`), ending the command-receive thread until a full app restart.

**Fix (per D-01, in scope for this phase):** Rename `main.py:26,49,57`'s `self.server.tcp_flag` references to `self.server.is_tcp_active` (three call sites: `main.py:26` in `__init__`, `main.py:49` in `on_and_off_server`'s "turn on" branch, `main.py:57` in the "turn off" branch — note `main.py:57` should set it `False`, matching the existing intent). This is a minimal, mechanical rename; `reset_server()` (`server.py:74-81`) is already fully implemented and just needs its guard condition to actually become reachable.

**Also verify while fixing:** `main.py:72-73`'s `closeEvent` references `self.server.server_socket`/`server_socket1`, which don't exist on `Server` either (it uses `video_socket`/`command_socket`, `server.py:56,60`) — wrapped in a bare `try/except: pass` (`main.py:71-76`) so it fails silently today. Not required by D-01's scope (D-01 only names the `tcp_flag` bug), but directly adjacent and worth flagging for the planner to decide in/out of scope, since it's the same class of dead-attribute bug in the same shutdown path.

**Phase mapping:** This phase, per D-01 — server-side prerequisite for AUTO-02's safety claim.

### Pitfall 6: Silent failure via bare `except:` in new autonomy code (CLAUDE.md + prior research both flag this — MEDIUM-HIGH confidence)

Covered in Project Constraints above. The autonomy loop's default on any unexpected exception must be a fail-safe stop with a logged message (`print(f"...: {e}")` at minimum, matching CLAUDE.md's preferred new-code pattern), never a silent `pass`/continue-on-stale-command. `Control.condition_monitor` today has **no top-level try/except at all** (`control.py:133`) — an uncaught exception there kills the entire movement thread silently; the new autonomy loop must not replicate this by omission.

### Pitfall 7: Unclamped `CMD_HEAD` / head-servo range — confirm exact safe bounds before sweeping (confirmed — HIGH confidence, verified this session including a doc/implementation mismatch)

**What goes wrong:** `Servo.set_servo_angle()` (`servo.py:19-34`) applies **zero clamping** — any integer angle is mapped straight through `map_value(angle, 0, 180, 500, 2500)` to a PWM duty cycle. The `CMD_HEAD` dispatch path (`server.py:181-183`) also applies no clamping (`int(command_parts[2])` passed straight through) — unlike `CMD_CAMERA` (`server.py:184-189`), which clamps channel-0 (`x`) to `[50,180]` and channel-1 (`y`) to `[0,180]` via `restrict_value`.

**New finding this session — `CMD_CAMERA` is dead code from the real client's perspective, and the protocol doc's axis labels don't match actual usage:** `grep` across `Code/Client/*.py` shows `CMD_CAMERA` is defined in `Command.py` but **never sent** by the working PyQt5 client — the only live, human-tested head-control path is `CMD_HEAD`, driven by two sliders in `Code/Client/Main.py:46-56,592-606`:
  - `slider_head` (range 50-180, default 90) → `CMD_HEAD#0#<value>` (`Main.py:592-597`, function named `headUpAndDown`)
  - `slider_head_1` (range 0-180, default 90) → `CMD_HEAD#1#<180-value>` (`Main.py:601-606`, function named `headLeftAndRight`, note the value is sent **inverted**)
  
  This means: **channel 0 = tilt (up/down), safe tested range 50-180; channel 1 = pan (left/right), safe tested range 0-180, with the client's own convention of sending `180 - desired_angle`.** `Code/robot_control_communication_protocol.md`'s CMD_CAMERA section (§12) labels its own x/y parameters "left-right"/"up-down" in the *opposite* order from what the client's function names and channel numbers imply — a pre-existing documentation/implementation mismatch, not something this phase needs to resolve, but the planner should trust the client's actual channel/range usage (which real users exercise) over the markdown doc.

**Prevention:** New autonomy code sweeping the head for SENSE-02 must clamp its own generated pan angles to a safe window (recommend staying inside the client's tested range for channel 1, e.g. roughly 30-150 rather than the full 0-180, to leave margin from mechanical hard-stops for bearings picked programmatically without a human watching) and must call `Server.servo_controller.set_servo_angle(1, angle)` for pan (not channel 0, which is tilt) — do not reuse the unclamped `CMD_HEAD` network path at all, since autonomy talks to `Servo` directly per Pattern 1.

**Phase mapping:** This phase, SENSE-02 (head-sweep implementation).

## Code Examples

### Bounded startup read (guards against Pitfall 1's hang-forever case)
```python
# Source: pattern derived from stdlib threading + verified gpiozero 2.0.1 blocking behavior
import threading

def get_first_reading_or_none(ultrasonic_sensor, timeout=1.0):
    result = {}
    def _read():
        result['value'] = ultrasonic_sensor.sensor._read()
    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None   # treat as unknown — sensor never produced a first reading in time
    return result.get('value')
```

### Manual-preempt hook in the existing dispatch chain
```python
# Source: Code/Server/server.py:205-207 (existing final else branch), extended per Pattern 3
else:
    if command_parts[0] in (cmd.CMD_MOVE, cmd.CMD_POSITION, cmd.CMD_ATTITUDE, cmd.CMD_BALANCE):
        self.auto_mode_active.clear()
    self.control_system.command_queue = command_parts
    self.control_system.timeout = time.time()
```

### Head-sweep angle clamp
```python
# Source: derived from Code/Client/Main.py:592-606 (client's tested slider ranges)
PAN_CHANNEL = 1
TILT_CHANNEL = 0
PAN_SAFE_MIN, PAN_SAFE_MAX = 30, 150   # narrower than the client's full 0-180 slider range,
                                         # deliberate margin for unattended/unsupervised sweeps
def sweep_to(servo, bearing_angle):
    clamped = max(PAN_SAFE_MIN, min(PAN_SAFE_MAX, bearing_angle))
    servo.set_servo_angle(PAN_CHANNEL, clamped)
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `transitions` (pytransitions) 0.9.3 is a legitimate, actively maintained package suitable for this project | Standard Stack / Package Legitimacy Audit | Low — package is optional for Phase 1's minimum scope; slopcheck+registry checks passed this session, but package name was originally sourced via WebSearch (prior milestone research), not Context7/official docs, so tagged `[ASSUMED]` per provenance rule regardless |
| A2 | The recommended narrower pan-sweep safe range (30-150) is a reasonable margin inside the client's tested 0-180 slider range | Pitfall 7 / Code Examples | Low-medium — this is a conservative judgment call, not verified against physical hardware hard-stop positions; should be confirmed/adjusted during on-hardware testing of this phase |
| A3 | The `_read()` bypass (Pattern 2) remains stable across future gpiozero point releases | Pitfall 1 | Medium — relies on a semi-private method not covered by gpiozero's public API contract; if gpiozero changes `_read()`'s signature/behavior in a future release, this breaks silently. Mitigation: pin/verify gpiozero version at deploy time; the public-API fallback (staleness heuristic) in Pitfall 1 is the safer-but-weaker alternative if this is a concern |

## Open Questions

1. **How should AUTO-02's "no wait" requirement be reconciled with `run_gait()`'s ~0.2-1.7s uninterruptible call boundary (Pitfall 2)?**
   - What we know: The existing call-boundary alone cannot guarantee sub-second (let alone sub-100ms) manual-override latency at slow auto-walk speeds; a per-iteration interrupt check inside `run_gait` would fix this but touches `Control`, which prior research recommended never modifying.
   - What's unclear: Whether the roadmap's "immediately"/"no wait" wording is meant literally (sub-100ms) or as "no *additional* queuing delay beyond the current physical step" (i.e., the existing call-boundary is acceptable).
   - Recommendation: Surface this explicitly to the user during `/bm:discuss-phase` or resolve as a planning decision — pick a brisk-enough default auto-walk speed as the cheap mitigation, and decide whether the `run_gait` interrupt-check is in scope for this phase or deferred with the latency gap explicitly accepted/documented.

2. **Is the `_read()` private-API bypass (Pitfall 1 / Pattern 2) acceptable, or should the phase use only public gpiozero API plus the weaker staleness heuristic?**
   - What we know: The public `.distance`/`.value` API cannot deliver a genuine no-echo signal under gpiozero 2.0.1's actual behavior (verified this session); the private `_read()` method can, and is itself well-bounded.
   - What's unclear: Whether reliance on a semi-private third-party method is acceptable given the project has no CI to catch a future gpiozero upgrade breaking it.
   - Recommendation: Use the `_read()` bypass for Phase 1 (it's the only mechanism that actually satisfies CAUTION-01 as written), but pin the verified-working gpiozero version (2.0.1) in whatever dependency documentation this project adopts, and note this as a fragility point for future maintainers.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `gpiozero` | Ultrasonic sensing (SENSE-01), head servo control | ✓ | 2.0.1 | — |
| Python stdlib `threading`/`time` | Arbitration, cooperative stop, bounded timer | ✓ | 3.13.5 | — |
| `transitions` (pytransitions) | Optional FSM (not required for Phase 1 minimum scope) | ✗ (not installed) | — | Hand-rolled `enum` + dispatch function (recommended default for this phase) |
| `pytest` | Automated test framework | ✗ (not installed) | — | Not applicable — CLAUDE.md constraint mandates live on-device hardware verification instead; see Validation Architecture |
| PyQt5 (client) | Auto Mode toggle UI (AUTO-01, AUTO-04) | Not checked this session (client runs on a separate PC, not this Pi) | — | N/A — client-side dependency, assumed present per existing teleop client functioning today |

**Missing dependencies with no fallback:** none — Phase 1's required scope has zero unmet dependencies.
**Missing dependencies with fallback:** `transitions` (fallback: hand-rolled dispatch), `pytest` (fallback: live hardware verification per CLAUDE.md).

## Validation Architecture

> Adapted per CLAUDE.md's explicit constraint: "No CI, no automated test framework for first-party code. Verification relies on live, on-device hardware testing." This project-level directive takes precedence over the default nyquist_validation pytest-oriented template. This section documents how verification should actually work for this phase, not a pytest suite to build.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None (project constraint) — live, on-device hardware verification, matching the existing convention of `Code/Server/test.py` (interactive hardware smoke test) and `Code/Server/myCode.py` (standalone `Control` exercise script) |
| Config file | none |
| Quick run command | Manual: run the new autonomy module's standalone entry point directly on the Pi (e.g. `python3 Code/Server/autonomy/behavior.py` self-test block, matching the codebase's existing `if __name__ == '__main__':` convention used in `servo.py`, `led.py`, `ultrasonic.py`, etc.) |
| Full suite command | Manual: full `CMD_AUTO#1` toggle from the desktop client with a real obstacle placed in the robot's path, observing all four ROADMAP success criteria live |

### Phase Requirements → Verification Map
| Req ID | Behavior | Verification Type | Method | 
|--------|----------|-----------|-------------------|
| AUTO-01 | Toggle auto mode on/off from client | manual | Click new toggle button; observe robot starts/stops walking |
| AUTO-02 | Manual command instantly preempts auto | manual (timed) | Send arrow-key move while auto-walking; stopwatch/observe latency, cross-check against Pitfall 2's worst-case numbers |
| AUTO-03 | Bounded-duration auto-stop, stable stance | manual (timed) | Leave auto mode running unattended 5+ minutes; observe automatic halt into a settled stance |
| AUTO-04 | Visible auto-mode-active indicator | manual (visual) | Confirm status badge shows on toggle, updates on auto-stop |
| SENSE-01 | No-echo never treated as clear | manual + code-level self-check | Physically block/absorb the ultrasonic beam (soft object at an angle) during auto mode; confirm robot does not proceed. Additionally, the `_read()` bypass logic itself (Pattern 2) is pure enough to sanity-check directly on the Pi via a short standalone script asserting `None` is returned when the sensor is covered — not a pytest suite, but a runnable, assertion-based check consistent with CLAUDE.md's "verification relies on live, on-device hardware testing" |
| SENSE-02 | Head sweeps 3 bearings before deciding | manual (visual) | Observe head pan movement (left/center/right) on obstacle-triggered stop |
| AVOID-01 | Stop-and-turn with hysteresis, no thrashing | manual | Place obstacle at ~20-35cm boundary repeatedly; observe no rapid oscillation |
| CAUTION-01 | Close-range always stop, never nudge past | manual | Place obstacle well inside 20cm; confirm stop, never partial-approach |

### Sampling Rate
- **Per task:** Manual smoke test of the specific behavior just implemented, on real hardware, following the existing `test.py`/`myCode.py` standalone-script convention
- **Phase gate:** Full live walkthrough of all four ROADMAP success criteria before `/bm:verify-work`, since no automated suite substitutes for this per CLAUDE.md

### Wave 0 Gaps
- None in the pytest sense (no framework to install, per project constraint).
- Recommended (not required) lightweight addition consistent with the codebase's own convention: a standalone `if __name__ == '__main__':` block in `behavior.py` that constructs hand-built `SensorSnapshot`-equivalent inputs and asserts the expected stop/turn/walk decision — mirrors `servo.py`/`ultrasonic.py`'s existing self-test pattern, runnable directly on the Pi without pytest, and gives the pure-logic decision function (the one piece of this phase that genuinely doesn't need hardware) a repeatable check.

## Security Domain

> `security_enforcement` absent from config.json = enabled by default per instructions. Adapted for this project's actual threat model: a hobbyist home robot on a private LAN, not a web application — REQUIREMENTS.md explicitly places "Authenticating/hardening the TCP command protocol" **out of scope** for this milestone ("Known issue... but not this milestone's focus unless it becomes a safety blocker"). ASVS categories below are mapped accordingly; most web-auth categories don't apply to this system's actual architecture.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Explicitly out of scope per REQUIREMENTS.md — single-client, unauthenticated-by-design TCP socket on a private LAN; not a Phase 1 concern |
| V3 Session Management | No | No session concept in this protocol; N/A |
| V4 Access Control | No | Single implicit "whoever is connected controls the robot" model, unchanged by this phase |
| V5 Input Validation | **Yes** | New `CMD_AUTO` command parsing must validate field count/type before indexing (matching the existing gap noted in CONCERNS.md for `CMD_HEAD` et al. — do not repeat the unvalidated-`int()`-conversion pattern for the new command). Head-sweep angle generation must self-clamp (Pitfall 7) since neither `CMD_HEAD` nor `Servo.set_servo_angle` validates |
| V6 Cryptography | No | No crypto surface added by this phase; protocol remains plaintext TCP per existing, explicitly-accepted project posture |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/truncated `CMD_AUTO` payload crashing the receive-commands thread (matches existing documented risk for `CMD_HEAD`/`CMD_CAMERA` in CONCERNS.md) | Denial of Service | Validate `len(command_parts)` before indexing; wrap the new command's `int()` conversion in a narrow `try/except ValueError` that logs and ignores the malformed command rather than propagating |
| Out-of-range servo angle from a logic bug in autonomous head-sweep code (Pitfall 7) | Tampering (self-inflicted, not adversarial) | Self-clamp all programmatically generated angles before calling `set_servo_angle`, since no layer beneath autonomy's own code enforces bounds |
| A runaway/stuck autonomy loop that never honors the bounded-runtime timer (e.g. due to an uncaught exception silently killing only part of the loop) | Denial of Service (of the safety mechanism itself) | Explicit try/except around the decision loop's body with a fail-safe stop on any unexpected exception (Pitfall 6); the bounded-runtime timer itself should be checked in a location that survives a partial failure elsewhere in the loop |

## Sources

### Primary (HIGH confidence)
- Direct source read this session: `Code/Server/control.py`, `Code/Server/server.py`, `Code/Server/main.py`, `Code/Server/ultrasonic.py`, `Code/Server/servo.py`, `Code/Server/command.py`, `Code/Server/Thread.py`, `Code/Client/Client.py`, `Code/Client/Command.py`, `Code/Client/Main.py`, `Code/Client/ui_client.py`, `Code/robot_control_communication_protocol.md`
- Direct read of installed `gpiozero` 2.0.1 source this session (`/usr/lib/python3/dist-packages/gpiozero/input_devices.py`, via `python3 -c "import inspect; ..."`): `DistanceSensor._read`, `DistanceSensor.distance`/`.value`, `SmoothedInputDevice.__init__`/`.value`, `GPIOQueue.__init__`/`.value`/`.fill` — this is the basis for Pitfall 1, the most significant new finding in this document
- `pip3 show gpiozero`, `pip3 index versions transitions`, `pip3 show pytest` — version/availability verification, this session
- `slopcheck scan transitions --pkg pypi --json` — package legitimacy check, this session (result: `[OK]`)
- `.planning/CONTEXT.md` (this phase) — locked decisions D-01 through D-13
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — requirement text and prior-session blockers/concerns
- `CLAUDE.md` — project constraints (testing posture, safety bias, conventions)

### Secondary (MEDIUM-HIGH confidence, prior milestone research — re-verified where checkable this session)
- `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md` — codebase-wide hazard analysis; `tcp_flag`/`is_tcp_active` bug and `run_gait`'s uninterruptible-loop finding both independently corroborated by this session's direct reads
- `.planning/research/PITFALLS.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/STACK.md`, `.planning/research/SUMMARY.md` — prior milestone-level research; this document narrows/refines several of its findings with Phase-1-specific file:line precision and the two new structural findings (Pitfalls 1 and 2)

### Tertiary (not independently re-verified this session)
- `transitions` package maturity/history claims (first released 2014, PyPI release cadence) — carried from prior milestone research's WebSearch findings, not re-verified beyond the registry/slopcheck checks performed this session

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new required dependencies; the one optional dependency (`transitions`) was directly verified against PyPI and slopcheck this session
- Architecture: HIGH — every claim about which files/objects to reuse is grounded in direct reads of this exact repo's source this session, not inference from prior research alone
- Pitfalls: HIGH for Pitfalls 1, 2, 3, 4, 5, 7 (all directly verified against installed source this session); MEDIUM-HIGH for Pitfall 6 (well-established codebase pattern, not a new mechanism finding)

**Research date:** 2026-08-07
**Valid until:** ~30 days for the architectural/integration findings (stable, tied to this repo's current state); the `gpiozero` 2.0.1 behavioral analysis (Pitfall 1) should be re-verified if `gpiozero` is ever upgraded on the target Pi.
