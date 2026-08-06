# Codebase Concerns

**Analysis Date:** 2026-08-06

## Tech Debt

**No `.gitignore` file at all:**
- Issue: The repo has zero `.gitignore` file at any level. As a result, `Code/Client/__pycache__/*.pyc` (9 compiled bytecode files) are checked into git, while `Code/Server/__pycache__/` and `Code/Server/params.json` sit as untracked cruft in the working tree (visible in `git status`). Any future `git add -A` / `git add .` will accidentally commit compiled bytecode and machine-specific hardware config.
- Files: repo root (missing), `Code/Client/__pycache__/*.pyc` (tracked), `Code/Server/params.json` (untracked, contains local `Pcb_Version`/`Pi_Version`)
- Impact: Repo bloat, stale bytecode shipped to users, risk of committing local hardware-calibration state that doesn't apply to other users' boards.
- Fix approach: Add a `.gitignore` covering `__pycache__/`, `*.pyc`, `params.json`, `build/`, `dist/`, `*.egg-info/`; run `git rm -r --cached` on the already-tracked `.pyc` files.

**Massive binaries committed to git history:**
- Issue: `Application/mac/mac` (97MB) and `Application/windows/windows.exe` (70MB) prebuilt client binaries are committed directly to git, along with several 900KB+ assets (`Datasheet/MPU6050.pdf`, `Code/Client/Face/haarcascade_frontalface_default.xml` duplicated 3x, `Code/Client/Face/face.yml` duplicated 3x, `Tutorial.pdf` at 9.7MB).
- Files: `Application/mac/mac`, `Application/windows/windows.exe`, `Tutorial.pdf`, `Code/Client/Face/*`, `Application/mac/Face/*`, `Application/windows/Face/*`
- Impact: `.git` directory is 414MB for a ~6K-line Python project; every clone pays this cost; no Git LFS in use. Duplicated Face/Picture assets exist identically in three locations (`Code/Client/`, `Application/mac/`, `Application/windows/`) with no single source of truth.
- Fix approach: Move large binaries/PDFs to release artifacts or Git LFS; deduplicate the three copies of `Face/` and `Picture/` assets by referencing one canonical location or documenting they are intentionally bundled per-platform.

**Vendored third-party libraries include build artifacts:**
- Issue: `Code/Libs/mpu6050/` and `Code/Libs/rpi-ws281x-python/` are vendored copies of external PyPI packages, complete with `build/`, `dist/`, `*.egg-info/`, and compiled `.so`/`.o` object files checked into git (e.g. `Code/Libs/rpi-ws281x-python/library/build/lib.linux-aarch64-cpython-313/_rpi_ws281x.cpython-313-aarch64-linux-gnu.so`).
- Files: `Code/Libs/mpu6050/build/`, `Code/Libs/mpu6050/dist/`, `Code/Libs/rpi-ws281x-python/library/build/`, `Code/Libs/rpi-ws281x-python/library/dist/`
- Impact: Compiled artifacts are architecture-specific (aarch64, cpython-313) and will not work on other platforms/Python versions; bloats repo; unclear whether these are meant to be installed via `pip install -e` or imported directly.
- Fix approach: Exclude `build/`/`dist/`/`*.egg-info/` from vendored libs, or replace vendoring with a `requirements.txt`/`pyproject.toml` pinned dependency plus install instructions in `Code/setup.py`.

**Duplicated `COMMAND` class and protocol constants between Server and Client:**
- Issue: `Code/Server/command.py` and `Code/Client/Command.py` define the identical `COMMAND` class with the same string constants, hand-copied and kept in sync manually. Same duplication pattern exists for `Code/Server/Thread.py` / `Code/Client/Thread.py` (both implement `stop_thread` via ctypes async exception injection) and `Code/Server/pid.py` / `Code/Client/PID.py`.
- Files: `Code/Server/command.py`, `Code/Client/Command.py`, `Code/Server/Thread.py`, `Code/Client/Thread.py`, `Code/Server/pid.py`, `Code/Client/PID.py`
- Impact: Adding/renaming a command requires editing two files; drift between client and server command sets is easy to introduce silently (a typo in one file won't raise an error, commands will simply be silently ignored by `receive_commands`).
- Fix approach: Extract a shared `protocol.py` module (or document `Code/robot_control_communication_protocol.md` as the single source of truth and add a sync-check script/test).

**Broken/dead `tcp_flag` vs `is_tcp_active` state sync:**
- Issue: `Code/Server/main.py` sets `self.server.tcp_flag = True/False` (lines 26, 49, 57) on the `Server` instance, but the `Server` class (`Code/Server/server.py`) never defines or reads an attribute named `tcp_flag` — it only has `self.is_tcp_active` (set once to `False` in `__init__`, line 32). Because Python allows setting arbitrary attributes, `main.py` silently creates an unused `tcp_flag` attribute instead of erroring, and `is_tcp_active` is never set to `True` anywhere.
- Files: `Code/Server/main.py:26,49,57`, `Code/Server/server.py:32,128,133`
- Impact: The auto-reconnect/`reset_server()` logic in `Server.receive_commands` (`if self.is_tcp_active: self.reset_server()`, `Code/Server/server.py:128,133`) is permanently dead code — a dropped/failed client connection will always fall through to the `break` path and stop the command-receiving thread entirely, requiring a full app restart to reconnect instead of the intended auto-reset.
- Fix approach: Rename `tcp_flag` references in `main.py` to `is_tcp_active` (or vice versa), and add a smoke test that exercises the reconnect path.

**`closeEvent` references non-existent `Server` attributes:**
- Issue: `Code/Server/main.py:72-73` calls `self.server.server_socket.shutdown(2)` and `self.server.server_socket1.shutdown(2)`, but `Server` (`Code/Server/server.py`) never defines `server_socket` or `server_socket1` — it uses `video_socket` and `command_socket` instead. The call is wrapped in a bare `try/except: pass` (`main.py:71-76`), so the `AttributeError` is silently swallowed on every window close.
- Files: `Code/Server/main.py:65-79`, `Code/Server/server.py:56-63`
- Impact: Sockets/threads may not be cleanly shut down on app close; failure is invisible because the exception is discarded.
- Fix approach: Update `closeEvent` to reference the correct socket attribute names, and log (rather than swallow) exceptions during shutdown.

**Widespread bare `except:` clauses swallow all errors, including `SystemExit`/`KeyboardInterrupt`:**
- Issue: 16+ bare `except:` blocks (no exception type) across `Code/Server/server.py`, `Code/Server/main.py`, `Code/Client/Client.py`, `Code/Client/Main.py`. Examples: `server.py:71` (`stop_server`), `server.py:96` (`transmit_video` accept), `server.py:120` (`receive_commands` accept), `server.py:127,159,165,174,211,216` (multiple command handlers).
- Files: `Code/Server/server.py`, `Code/Server/main.py`, `Code/Client/Client.py`, `Code/Client/Main.py`
- Impact: Masks real bugs (e.g. malformed command payloads, hardware I2C failures) as silent no-ops; makes debugging field failures on the physical robot very difficult since nothing is logged; can also intercept `SystemExit` raised by the `stop_thread()` ctypes hack (see Fragile Areas), interfering with thread shutdown.
- Fix approach: Replace bare `except:` with specific exception types (`OSError`, `socket.error`, `ValueError`) and always log the caught exception, even at debug level.

## Known Bugs

**`CMD_HEAD` accepts unvalidated servo channel/angle from the network:**
- Symptoms: Any connected client can send `CMD_HEAD#<channel>#<angle>\n` with arbitrary integers; unlike `CMD_CAMERA` (which clamps via `self.control_system.restrict_value(...)`, `Code/Server/server.py:186-189`), the `CMD_HEAD` handler passes `int(command_parts[1])`/`int(command_parts[2])` straight to `Servo.set_servo_angle()` with no range check (`Code/Server/server.py:181-183`).
- Files: `Code/Server/server.py:181-183`, `Code/Server/servo.py:19-34`
- Trigger: Send `CMD_HEAD#99#9999\n` (or a negative channel) over the command TCP socket (port 5002).
- Workaround: None currently; `PCA9685.set_pwm` (`Code/Server/pca9685.py:59-64`) will compute out-of-range register offsets for `channel` values ≥16 that aren't caught by `Servo.set_servo_angle`'s `elif channel >= 16 and channel < 32` check, and extreme `angle` values translate to duty cycles far outside safe servo pulse widths (500–2500us), risking servo/mechanical damage.

**Unhandled `ValueError`/`IndexError` on malformed commands can kill the receive-commands thread:**
- Symptoms: `int(command_parts[1])` type conversions in `Code/Server/server.py` (`CMD_HEAD`, `CMD_CAMERA`, `CMD_SERVOPOWER`) and the equivalent `int(self.command_queue[...])` conversions in `Code/Server/control.py` (`condition_monitor`, `run_gait`, calibration branches) are not wrapped in try/except. A malformed or truncated command (e.g. dropped network byte splitting a message mid-`#`) raises an uncaught exception.
- Files: `Code/Server/server.py:181-203`, `Code/Server/control.py:139-218,329-337`
- Trigger: Send a non-numeric or missing field, e.g. `CMD_HEAD#abc#90\n`, or a partial TCP read that truncates a command.
- Workaround: None; in `server.py` this crashes the `receive_commands` thread (command channel stops responding until app restart); in `control.py`, `condition_monitor` runs in a `while True` background thread with no top-level try/except at all, so an exception here silently kills the entire movement/balance control loop.

**`Led.__init__` leaves object in a broken state for unhandled PCB/Pi version combos:**
- Symptoms: `Code/Server/led.py:18-29` only handles three specific `(pcb_version, pi_version)` combinations explicitly and has no `else` branch. If `ParameterManager.get_pcb_version()`/`get_pi_version()` return any other value (e.g. `None`, or a future PCB version 3), neither `self.strip` nor `self.is_support_led_function` is ever set.
- Files: `Code/Server/led.py:18-30`
- Trigger: Missing/corrupt `params.json`, or hardware version values outside `{1,2}`.
- Workaround: None; any subsequent call to `led.color_wipe()`/`led.process_light_command()` raises `AttributeError: 'Led' object has no attribute 'strip'`.

**`Camera.__init__` silently returns a half-constructed object on missing camera:**
- Symptoms: `Code/Server/camera.py:25-29` catches `IndexError` when `Picamera2()` fails to find a camera device, prints an error, and does a bare `return` from `__init__` — but the rest of `__init__` (setting `self.transform`, `self.stream_config`, `self.streaming_output`, `self.streaming`) never runs.
- Files: `Code/Server/camera.py:22-39`
- Trigger: Boot the server without a camera module attached/detected.
- Workaround: None; any later call (`start_stream`, `get_frame`, `close`) raises `AttributeError` because the `Camera` instance is missing expected attributes.

## Security Considerations

**No authentication on any network-facing service:**
- Risk: The TCP command socket (`Code/Server/server.py`, port 5002) and video streaming socket (port 8002) accept the first connecting client with zero authentication, encryption, or origin checking. `Code/Server/tcp_server.py` (an alternate/legacy server implementation) has the same behavior on port 12345. Anyone on the same Wi-Fi/LAN segment as the robot can send movement, LED, buzzer, camera, and servo-power commands, or read the live video feed.
- Files: `Code/Server/server.py:53-64,115-218`, `Code/Server/tcp_server.py:28-41`
- Current mitigation: None (relies entirely on physical/network isolation, e.g. a private home Wi-Fi network).
- Recommendations: At minimum, add a shared-secret handshake or token check before accepting commands; consider binding to a specific interface/AP mode by default; document the trust model clearly in the README given this ships as a hobbyist/educational kit.

**Command protocol has no message framing length limits:**
- Risk: `Code/Server/server.py:126` reads `recv(1024)` and naively splits on `\n` and `#`, with no maximum command length or field-count validation before indexing (`command_parts[1]`, `command_parts[2]`, etc.). A malformed or truncated multi-command payload spanning TCP packet boundaries can produce commands with wrong field counts, feeding directly into the unvalidated `int()` conversions described above.
- Files: `Code/Server/server.py:124-144`
- Current mitigation: `len(command_parts) == 3` checks exist for `CMD_HEAD`/`CMD_CAMERA` but not uniformly for all commands (e.g. `CMD_BUZZER` indexes `command_parts[1]` with no length check at all, `Code/Server/server.py:145-146`).
- Recommendations: Validate field counts before every index access; consider replacing the ad hoc `#`/`\n`-delimited text protocol with a length-prefixed or JSON-based protocol with schema validation (there is already a `Code/robot_control_communication_protocol.md` describing the format — enforce it in code).

**`params.json` lacks a `.gitignore` entry (see Tech Debt) and could leak local hardware config into commits:**
- Risk: Low-severity, but combined with the missing `.gitignore`, a contributor could accidentally commit their personal `Pcb_Version`/`Pi_Version` config or, in future, richer per-device secrets/calibration data if the schema grows.
- Files: `Code/Server/params.json`, `Code/Server/parameter.py`
- Current mitigation: None.
- Recommendations: Add to `.gitignore`; ship a `params.json.example` template instead.

## Performance Bottlenecks

**Busy-wait / tight polling loops instead of event-driven waits:**
- Problem: `Control.condition_monitor` (`Code/Server/control.py:133-218`) runs an unbounded `while True` loop with no sleep on most iterations (only the timeout branch touches time), continuously checking `self.command_queue` from another thread. `Code/Server/main.py:92-93` has a literal `while True: pass` busy-spin as its main loop when `user_ui` is enabled but the app has already handed control to `sys.exit(myshow.app.exec_())` on the line before it (dead/unreachable code, but if ever reached it will peg a CPU core).
- Files: `Code/Server/control.py:133-218`, `Code/Server/main.py:92-93`
- Cause: No condition variables/queue-based blocking wait between the network-receiving thread and the control thread; they communicate via a plain shared list (`self.command_queue`) polled in a spin loop.
- Improvement path: Replace `command_queue` polling with a `queue.Queue` (blocking `get()`) or `threading.Event`/`Condition` to eliminate CPU spin between commands, matching the pattern already used correctly in `Code/Server/tcp_server.py` (which uses `queue.Queue` for `message_queue`).

**Synchronous, one-command-at-a-time gait execution blocks the network thread pathway:**
- Problem: `run_gait()` (`Code/Server/control.py:329-404`) executes tight `for` loops with `time.sleep(delay)` (10ms) per step, iterating up to `F` (up to ~171) times per gait command, entirely inside `condition_monitor`'s thread. There is no way to interrupt an in-progress gait cycle except by the 10-second timeout relaxation logic.
- Files: `Code/Server/control.py:329-404`
- Cause: Straight-line procedural animation code with `time.sleep` driving timing, no cooperative cancellation checked mid-stride.
- Improvement path: Check `self.command_queue` for a new command inside the inner loops (partially done for CMD_MOVE via re-entry on next queue update, but not for balance/attitude interrupts) to allow faster response to new commands or emergency stop.

## Fragile Areas

**Thread termination via `ctypes.pythonapi.PyThreadState_SetAsyncExc`:**
- Files: `Code/Server/Thread.py`, `Code/Client/Thread.py` (duplicated implementations)
- Why fragile: `stop_thread()` uses CPython-internal, undocumented, implementation-specific APIs to forcibly inject a `SystemExit` into another thread. This is well known to be unsafe: it can leave locks held, corrupt partially-updated shared state (e.g. `self.leg_positions`, `self.command_queue` in `control.py`), and only works on CPython (not PyPy or other interpreters). It's called with a `for i in range(5)` retry loop (`Thread.py:20-22`) suggesting the original authors already encountered unreliability.
- Safe modification: Do not add more state that must be consistent across a `stop_thread()` call without introducing a lock; prefer migrating to a cooperative-cancellation flag (`threading.Event`) checked periodically inside the long-running loops (`led.process_light_command`'s `while True` animation loops, `control.condition_monitor`, `run_gait`).
- Test coverage: None — there are no automated tests exercising thread cancellation.

**Shared mutable state across threads without locks:**
- Files: `Code/Server/control.py` (`self.command_queue`, `self.leg_positions`, `self.current_angles`, `self.calibration_leg_positions`, `self.status_flag`, `self.timeout` all read/written from both the TCP `receive_commands` thread in `server.py` and the `condition_monitor` background thread), `Code/Server/server.py` (`self.led_thread`, `self.ultrasonic_thread` reassigned across threads without synchronization)
- Why fragile: Relies entirely on the CPython GIL for safety of simple attribute assignment; compound operations (e.g. `self.command_queue[i] = int(...)` following a length check on a separate line) are not atomic against a concurrent list replacement by the network thread, which can raise `IndexError` intermittently under load.
- Safe modification: Any new cross-thread state should use `threading.Lock`/`queue.Queue` rather than following the existing pattern of unsynchronized shared attributes.
- Test coverage: None.

**Hand-written inverse/forward kinematics with magic numbers and no bounds documentation:**
- Files: `Code/Server/control.py:49-95` (`coordinate_to_angle`, `angle_to_coordinate`, `calibrate`, `set_leg_angles`), `226-307` (`transform_coordinates`, `calculate_posture_balance`)
- Why fragile: Leg geometry constants (`l1=33, l2=90, l3=110`), per-leg offsets (`-94`, `-85`, `-14`, rotation angles `54`/`0`/`-54`/`-126`/`180`/`126` degrees), and servo channel-to-leg mappings (channels `15,14,13` for leg 1, `31` for leg 3's third joint, etc., `Code/Server/control.py:96-119`) are hardcoded inline with no named constants, diagrams, or references back to the physical PCB layout. `check_point_validity()` (`control.py:123-131`) uses hardcoded leg-length bounds (`90`–`248`) with no comment on where these numbers come from.
- Safe modification: Changing hexapod geometry (e.g. supporting a different chassis) requires touching many scattered magic numbers with no single source of truth; a change to one constant without corresponding others risks generating invalid/out-of-range leg targets that only fail at runtime via `check_point_validity`.
- Test coverage: None; there is no unit test validating that `coordinate_to_angle`/`angle_to_coordinate` round-trip correctly or that generated angles stay within `0-180`.

## Scaling Limits

**Single-client TCP server by design:**
- Current capacity: `TCPServer.max_clients` defaults to `1` (`Code/Server/tcp_server.py:16,28`); the primary `Server` class in `server.py` uses raw `accept()` once per socket with no loop to accept additional clients.
- Limit: Only one client (one phone/PC app instance) can control the robot or view video at a time; this is an inherent product design for this project, not necessarily a "limit" to fix, but is undocumented in code (no comment explaining the intentional single-client design) and combined with the lack of auto-reconnect (`is_tcp_active`/`tcp_flag` bug above) it means any client disconnect can leave the server in a state requiring an app restart.
- Scaling path: Not applicable to this project's scope; if multi-client support were desired, `tcp_server.py`'s `max_clients`/`select()`-based accept loop is the more scalable template versus `server.py`'s one-shot `accept()`.

## Dependencies at Risk

**Vendored libraries pinned to a specific Python/arch build:**
- Risk: `Code/Libs/rpi-ws281x-python/library/build/lib.linux-aarch64-cpython-313/_rpi_ws281x.cpython-313-aarch64-linux-gnu.so` and `Code/Libs/mpu6050/dist/mpu6050_raspberrypi-1.2-py3.13.egg` are committed pre-built for CPython 3.13 on aarch64 Linux specifically.
- Impact: Will not function on other Python versions (e.g. system Python 3.9, evidenced by the tracked `Code/Client/__pycache__/*.cpython-39.pyc` files showing the project has run under at least two different Python versions historically) or on 32-bit Raspberry Pi OS.
- Migration plan: Document the required Python version explicitly (README/setup docs currently don't pin one clearly across the two observed versions, 3.9 vs 3.13); prefer installing these libraries via `pip` from PyPI/git submodule rather than vendoring prebuilt binaries.

## Missing Critical Features

**No graceful command-channel reconnect (see Known Bugs: `tcp_flag`/`is_tcp_active`):**
- Problem: Despite `reset_server()` (`Code/Server/server.py:74-81`) existing and being fully implemented, it's unreachable dead code due to the attribute-name bug, so a dropped client connection permanently ends the command-receiving thread.
- Blocks: Reliable field operation of the robot without requiring a full application restart after any Wi-Fi hiccup.

## Test Coverage Gaps

**No automated test suite exists anywhere in the repository:**
- What's not tested: 100% of the codebase. `Code/Server/test.py` is a manual, hardware-in-the-loop script requiring a command-line argument (`Led`/`Ultrasonic`/`Servo`/`ADC`/`Buzzer`) and physical robot hardware — it is not runnable in CI and has no assertions, just print statements and manual observation.
- Files: `Code/Server/test.py` (only test-like file in the entire repo; no `pytest`/`unittest` files, no `tests/` directory, no CI config such as `.github/workflows/`)
- Risk: Kinematics math (`Code/Server/control.py`), the command-protocol parser (`Code/Server/server.py`), and the `ParameterManager` validation logic (`Code/Server/parameter.py`) are all pure-enough logic that could be unit tested without hardware, but currently any regression (e.g. the `tcp_flag` bug, the `CMD_HEAD` missing bounds check) ships silently.
- Priority: High for `control.py` kinematics (`coordinate_to_angle`/`angle_to_coordinate` round-trip, `restrict_value` clamping) and `server.py` command parsing, since both directly affect physical hardware safety and are pure-Python testable without real GPIO/I2C access (would need mocking `gpiozero`/`smbus`).

---

*Concerns audit: 2026-08-06*
