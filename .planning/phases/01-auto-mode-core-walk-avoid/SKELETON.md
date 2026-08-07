# Walking Skeleton — Autonomous Hexapod

**Phase:** 1
**Generated:** 2026-08-07

> This project is not a web application. The standard skeleton template's framework/DB/auth/deploy
> axes have been mapped onto the equivalent decomposition for an embedded robot: client GUI ↔
> server networking ↔ decision layer ↔ hardware drivers ↔ persistent state. The skeleton is the
> thinnest end-to-end autonomy loop that exercises every one of those tiers on real hardware.

## Capability Proven End-to-End

An operator clicks one button on the desktop client and the hexapod walks across the floor by
itself, stops for what it sees ahead of it, hands control straight back the instant a human touches
an arrow key, and switches itself off after five minutes.

That single sentence crosses the whole stack: PyQt5 widget → TCP command protocol → server command
dispatch → arbitration gate → autonomy decision loop → ultrasonic driver → gait engine → 18 servos →
status ack back up to the client badge.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Autonomy placement | New `Code/Server/autonomy/` package — the first Python package in an otherwise flat module directory | Keeps the decision layer physically separate from `Control`'s kinematics god-object. `Control` is never modified except for one 6-line interruptibility change. The package boundary is what makes the future AI-piloting milestone a drop-in replacement of `decide()` rather than a rewrite. |
| Package internals | `settings.py` (tunables only) + `perception.py` (SensorHub) + `behavior.py` (AutoModeController + pure `decide()`) | Three files, one concern each. `bridge.py` from the research sketch is deliberately folded into `behavior.py` — the intent-to-`command_queue` translation is a dozen lines and does not earn its own module. |
| Import style inside the package | Explicit relative imports (`from . import settings`); self-tests run as `python3 -m autonomy.behavior` from `Code/Server/` | The rest of `Code/Server/` uses flat sibling imports (`from servo import Servo`). A package cannot, so this is the one deliberate departure. Server-side entry stays `from autonomy.behavior import AutoModeController`. |
| Actuation path | Autonomy writes intent lists into the existing `Control.command_queue`; it never calls `Servo` or `Control` kinematics methods for leg movement | The gait engine is the only tested path to safe leg motion. Autonomy is a command producer, exactly like the network thread — one new producer, not a second control stack. |
| Hardware ownership | Autonomy receives `Server.ultrasonic_sensor` and `Server.servo_controller` as constructor arguments and never constructs `Ultrasonic()` or `Servo()` | `Ultrasonic()` claims GPIO 27/22; a second instance would fight for the pins. Reusing `Server.servo_controller` also means autonomy drives the exact object the human-tested `CMD_HEAD` path already drives. |
| Concurrency model | One `threading.Event` (`auto_mode_active`) as the arbitration gate, plus one `threading.Event` (`Control.manual_preempt`) as the gait abort. Cooperative stop and `thread.join(timeout=...)` only | Matches D-09/D-10 and the codebase's GIL-based shared-attribute convention. `Code/Server/Thread.py`'s `stop_thread()` (`PyThreadState_SetAsyncExc` injection) is explicitly banned from all autonomy code — it can fire mid-I2C-write. `command_queue` is NOT refactored into a `queue.Queue`; the gate is sufficient because manual and autonomy are mutually exclusive writers. |
| Arbitration rule | Manual always wins, immediately. Autonomy-initiated stops wait for the current gait cycle | D-10 vs D-09. `run_gait` gained a `manual_preempt.is_set()` check in its two animation loops, dropping worst-case override latency from ~1.71 s to one 10 ms frame. Autonomy never sets that flag, so its own stops remain boundary-checked and never cut a stride mid-motion. |
| Sensing contract | Bypass `Ultrasonic.get_distance()`; read `sensor._read()` directly. Any `None` — no echo, stale snapshot, or exception — is UNKNOWN, and UNKNOWN is BLOCKED | gpiozero 2.0.1 builds `DistanceSensor` with `ignore=frozenset({None})`, so the public API silently discards no-echo samples and freezes on the last good reading. It structurally cannot deliver the signal CAUTION-01 requires. The private-method dependency is the documented cost; pin/verify gpiozero on upgrade. |
| Wire protocol | One new constant, `CMD_AUTO`, hand-duplicated into `Code/Server/command.py` and `Code/Client/Command.py`. `CMD_AUTO#1` / `CMD_AUTO#0` both directions | Follows the codebase's existing flat string-constant + `#`-delimited convention. Server-to-client `CMD_AUTO` is also pushed unsolicited on self-halt and on connect, which is what makes the client badge honest. Protocol duplication is a known anti-pattern here and is deliberately followed, not fixed, this phase. |
| Tunable configuration | Every threshold, duration, speed, angle and bearing lives in `Code/Server/autonomy/settings.py`; nothing is inlined | This is the deliberate seam for Phase 4's CONFIG-01 client-side tuning. A grep for inlined `20.0`/`35.0`/`300` in the logic modules must return nothing. |
| Bounded-runtime safety net | 300 s deadline computed from `time.monotonic()` inside `AutoModeController`, enforced server-side, never reset by client traffic, checked as the first statement in the loop body | D-02/D-08. The robot self-stops on schedule with no client connected at all. `Control`'s unrelated 10 s idle-relax timer is deliberately not reused. |
| Client-disconnect policy | Auto mode survives a client disconnect by default (`STOP_AUTO_ON_DISCONNECT = False`); the bounded timer is the safety net. Flipping the flag gives stop-on-disconnect with no silent auto-resume | D-03. On connect and reconnect the server pushes the true state, so a client never guesses. |
| Verification model | Live on-device manual walkthrough, plus hardware-free `if __name__ == '__main__':` assertion blocks for the pure decision logic, run via `python3 -m autonomy.behavior` | CLAUDE.md's standing constraint: no CI, no test framework for first-party code. The self-test blocks match the existing `ultrasonic.py`/`adc.py`/`test.py` convention and give the one hardware-independent piece a repeatable check. |
| Error handling | `except Exception as e: print(f"...: {e}")` everywhere in new code; never bare `except:` | CLAUDE.md's stated preference for new code, against the codebase's legacy numeric majority. The autonomy loop additionally wraps its whole body and fails safe to a stop — `Control.condition_monitor` has no handler at all and silently dies, which must not be copied. |
| Prerequisite bug fixes taken in-scope | D-01 `tcp_flag` → `is_tcp_active` rename in `main.py` (3 sites), making `reset_server()` reachable | "Manual override is always available" is structurally false if the command channel cannot survive a reconnect. |

## Stack Touched in Phase 1

- [x] Project scaffold — first Python package under `Code/Server/`, with the import/self-test convention it implies
- [x] Wire protocol — one real new command (`CMD_AUTO`), bidirectional, with input validation
- [x] Persistent/shared state — one real read (ultrasonic via `_read()`) and one real write (intent into `Control.command_queue`) per loop tick
- [x] UI — one interactive control (`Button_Auto`) and one live status surface (`label_Auto_Status`) wired to the server's ack
- [x] Deployment / run command — `cd Code/Server && python3 main.py -t -n` on the Pi, `cd Code/Client && python3 Main.py` on the desktop; the full stack runs from those two commands with no build step

## Out of Scope (Deferred to Later Slices)

Explicit, so later phases do not re-litigate Phase 1's minimalism:

- Varied or clearance-scaled evasive turn angles — Phase 2 (AVOID-02)
- Consecutive-avoidance "stuck" detection and escalation — Phase 2 (AVOID-03)
- Proximity-proportional gait slowdown — Phase 2 (AVOID-04)
- Wall-follow / boundary patrol — Phase 2 (PATROL-01)
- Camera-based motion detection for pets and kids — Phase 3 (CAUTION-02); the camera stays a pure streaming pipe this phase
- Onboard LED/buzzer status signalling and its configuration — Phase 3 (AUTO-05, CONFIG-02)
- Sub-state client indicators (walking / avoiding / stopped) — Phase 3; the Phase 1 badge is binary by decision D-13
- Client-side tuning of any `settings.py` value without a redeploy — Phase 4 (CONFIG-01)
- Decision logging to a durable, analysable format — Phase 4 (CONFIG-03); Phase 1 logs to stdout only
- Refactoring `command_queue` into a `queue.Queue`, deduplicating the client/server `COMMAND` classes, retiring `Thread.stop_thread()` from the legacy paths, and fixing `main.py`'s `closeEvent` dead-attribute bug — all known, all deliberately untouched
- Authenticating the TCP protocol, SLAM/odometry/waypoints, ML object classification, new sensor hardware — out of scope for the whole v1 milestone per REQUIREMENTS.md

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without renegotiating its
architectural decisions. In particular: the `autonomy/` package boundary, the single-Event
arbitration rule, the "unknown is blocked" sensing contract, the `settings.py` tunables seam, and
"autonomy writes intents into `command_queue`, never servo angles" are all fixed contracts.

- **Phase 2** — Robust avoidance and patrol. Extends `behavior.py`'s state machine (varied turns,
  stuck escalation, proximity slowdown) and adds a wall-follow behaviour. New tunables go in
  `settings.py`. If AVOID-04's variable step speed proves unsupported by `run_gait`, the binary-stop
  fallback is documented rather than forcing a gait-engine rewrite.
- **Phase 3** — Pet/kid safety and status signalling. Adds a camera-based motion detector as a
  second perception source feeding the same `decide()` input, and drives the existing `Led`/`Buzzer`
  singletons from auto-mode state transitions. Note the head-sweep blinds the camera while it runs.
- **Phase 4** — Tuning and observability. Turns `settings.py` into client-tunable state over the
  existing protocol, and turns the loop's stdout prints into a structured decision log.
- **v2 / AI piloting** — Replaces the pure `decide(snapshot) -> intent` function with a model-driven
  one. The whole point of keeping `decide()` pure, hardware-free and self-testable is that this
  becomes a swap rather than a rewrite.
