<!-- GSD:project-start source:PROJECT.md -->
## Project

**Autonomous Hexapod**

A Raspberry Pi-powered hexapod robot (Freenove Big Hexapod kit), currently controlled purely by manual teleoperation from a desktop client, being upgraded with real sensor-driven autonomy — obstacle avoidance and boundary-follow patrol — as the foundation for an eventual AI-piloted control loop and, further out, voice interaction.

**Core Value:** The hexapod can move around on its own without crashing into things, pets, or kids. That's the non-negotiable foundation everything else (AI piloting, voice) gets built on top of.

### Constraints

- **Hardware**: Obstacle sensing must work with what exists today — one ultrasonic sensor + camera, both on the pan/tilt head. No new sensors planned for v1.
- **Safety**: Real physical hardware operating near pets and kids — auto mode must err toward slowing/stopping rather than pushing through when something unexpected is nearby.
- **No localization**: Patrol/boundary behavior must be achievable via reactive sensing (wall-follow), not mapping — there is no SLAM/odometry to build on.
- **Testing**: No CI, no automated test framework for first-party code. Verification relies on live, on-device hardware testing (feasible here since the session runs on the robot's own Pi).
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3 (developed/run against Python 3.13.5 on the target Raspberry Pi OS install) - all robot server code (`Code/Server/*.py`), desktop client code (`Code/Client/*.py`), and bundled hardware libraries (`Code/Libs/`)
- C - native extension source for the WS281x LED driver, compiled via a Python C extension (`Code/Libs/rpi-ws281x-python/library/*.c`, `Code/Libs/rpi-ws281x-python/library/lib/`)
- Shell/Bash - install helper invoked via `subprocess`/`os.system` calls in `Code/setup.py`
## Runtime
- Raspberry Pi OS (Debian-based; observed dev environment is Debian 13 "trixie") running on Raspberry Pi hardware (Pi 3, Pi 4/generic, and Pi 5 are all explicitly detected/handled — see `Code/Server/parameter.py:get_raspberry_pi_version` and `Code/setup.py:get_raspberry_pi_version`)
- Python 3.13.5 observed on the dev/target machine; `Code/Libs/mpu6050/setup.py` still declares Python 2.7 classifier compatibility (legacy metadata, not enforced) while `Code/Libs/rpi-ws281x-python/library/setup.py` declares `python_requires >= 3.6`
- Client-side desktop app (`Code/Client/`) is intended to run on a separate PC (Windows/macOS/Linux) with PyQt5, connecting to the robot over TCP/Wi-Fi
- pip3 (invoked via `sudo pip3 install {package}` in `Code/setup.py:check_and_install`)
- apt / apt-get for system packages (`Code/setup.py:apt_install`, e.g. `libqt5gui5 python3-dev python3-pyqt5`)
- No lockfile present (no `requirements.txt`, `Pipfile.lock`, or `poetry.lock`); dependencies are installed ad hoc by `Code/setup.py` and via manual `setup.py install` of vendored libraries
## Frameworks
- PyQt5 - desktop GUI framework for both the on-robot control panel (`Code/Server/ui_server.py`, `Code/Server/main.py`) and the remote control client (`Code/Client/ui_client.py`, `Code/Client/ui_face.py`, `Code/Client/ui_led.py`). UI modules are Qt Designer-generated (`# Created by: PyQt5 UI code generator 5.11.3`) and must not be hand-edited per their own header warnings.
- picamera2 - Raspberry Pi camera stack (`Code/Server/camera.py`), used with `libcamera.Transform`, `H264Encoder`/`JpegEncoder`, `FileOutput`
- gpiozero - GPIO abstraction for ultrasonic sensor and servo-power output (`Code/Server/ultrasonic.py`, `Code/Server/control.py`)
- OpenCV (`cv2`) - video frame decoding on the client and face detection/recognition (`Code/Client/Client.py`, `Code/Client/Face.py` uses `cv2.face.LBPHFaceRecognizer_create()` and `cv2.CascadeClassifier`, requiring `opencv-contrib-python`)
- No automated test framework (no pytest/unittest suite found). `Code/Server/test.py` is a manual, interactive hardware smoke-test script (`test_Led`, `test_Ultrasonic`, etc.), not an automated test suite.
- `setuptools` - used to build/install the two vendored native/Python libraries: `Code/Libs/mpu6050/setup.py` (pure Python, MIT) and `Code/Libs/rpi-ws281x-python/library/setup.py` (C extension `_rpi_ws281x`, compiled per-target as seen in `Code/Libs/rpi-ws281x-python/library/build/lib.linux-aarch64-cpython-313/`)
- `Code/setup.py` - top-level install orchestrator: runs `apt-get update`, installs vendored libs via `python3 setup.py install`, installs `libqt5gui5 python3-dev python3-pyqt5` via apt, and edits `/boot/firmware/config.txt` (enables SPI, configures camera overlay, disables audio on Pi 3) — this is provisioning/bootstrap code, not a Python packaging build for this project itself.
## Key Dependencies
- `smbus` - I2C bus communication with the PCA9685 PWM driver (`Code/Server/pca9685.py`) and ADS7830 ADC (`Code/Server/adc.py`)
- `spidev` - SPI communication for LED strips on newer PCB/Pi versions (`Code/Server/spi_ledpixel.py`)
- `numpy` - vector/array math for LED color buffers, IMU math, and image frame handling (`Code/Server/spi_ledpixel.py`, `Code/Server/control.py`, `Code/Client/Client.py`)
- `mpu6050` (vendored, `Code/Libs/mpu6050`) - accelerometer/gyroscope driver used by `Code/Server/imu.py` alongside a custom `Kalman_filter` (`Code/Server/kalman.py`) for orientation fusion
- `rpi_ws281x` (vendored, `Code/Libs/rpi-ws281x-python`) - low-level WS281x/NeoPixel LED strip driver used by `Code/Server/rpi_ledpixel.py`
- `PIL` (Pillow) - image handling on the client (`Code/Client/Client.py`, `Code/Client/Face.py`)
- `multiprocessing`, `threading`, `queue` (stdlib) - concurrency for video streaming, command handling, and LED animation threads (`Code/Server/server.py`, `Code/Server/tcp_server.py`, `Code/Client/Client.py`)
- `ctypes`, `inspect` (stdlib) - used by the custom thread-kill utility (`Code/Server/Thread.py`, `Code/Client/Thread.py`) to forcibly terminate long-running threads
## Configuration
- No `.env`/environment-variable-based configuration. Hardware/runtime configuration is file-based:
- `/boot/firmware/config.txt` on the Pi is modified directly by `Code/setup.py` (`config_file()`) to enable SPI (`dtparam=spi=on`), select the camera overlay (`ov5647`/`imx219`), and (on Pi 3) disable onboard audio
- `Code/Libs/mpu6050/setup.py`, `Code/Libs/rpi-ws281x-python/library/setup.py` - `setuptools`-based build/install scripts for vendored dependencies
- No `pyproject.toml`, no `tsconfig.json`/`package.json` (not applicable — pure Python/embedded project)
## Platform Requirements
- Any machine with Python 3 + PyQt5 to run/edit the Client desktop app (`Code/Client/`); no Pi hardware required for pure UI/protocol work, but hardware-dependent server code (I2C/SPI/GPIO/camera) can only run on a Raspberry Pi
- OpenCV with the `cv2.face` contrib module (`opencv-contrib-python`) is required for face recognition features on the client
- Raspberry Pi (3, 4, or 5) running Raspberry Pi OS / Debian, with camera module, PCA9685 servo driver, ADS7830 ADC, MPU6050 IMU, ultrasonic sensor, and WS281x/SPI LED strip attached via I2C/SPI/GPIO as wired per the hexapod hardware kit
- Server process (`Code/Server/main.py`) launched on the Pi; opens two TCP sockets on the Pi's `wlan0` IP — port `8002` for video streaming and `5002` for command/telemetry (`Code/Server/server.py`)
- Remote client (`Code/Client/Main.py`) run on a separate PC/laptop on the same network, connecting to the robot's IP (from `IP.txt`) on those same ports
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Overview
## Naming Patterns
- Server-side files (`Code/Server/`): all lowercase, `snake_case.py` (e.g. `adc.py`,
- Client-side files (`Code/Client/`): mixed — some `PascalCase.py` matching the class
- `Thread.py` exists identically in both `Code/Server/` and `Code/Client/`.
- `PascalCase` throughout: `Control`, `Servo`, `Camera`, `TCPServer`, `ADC`,
- A few classes use inconsistent casing inherited from the original codebase:
- Constant/enum-style classes are `SCREAMING_CASE` as a class name with class-level
- `snake_case` in Server code, e.g. `set_servo_angle`, `read_battery_voltage`,
- Client code (legacy tier) is inconsistent: `turn_on_client`, `is_valid_image_4_bytes`
- Private/internal helpers are prefixed with a single underscore in modernized files
- `snake_case` for locals and instance attributes in modernized files:
- Legacy files mix short/cryptic names (`a`, `b`, `c`, `w`, `v`, `u`, `l1`, `l2`, `l3`
- Command/protocol values are transmitted as strings, not typed constants:
- No project-level type aliases or `TypedDict`/`dataclass` usage found. Data is passed
## Code Style
- No formatter (no Black/autopep8 config). Indentation is 4 spaces throughout.
- Modernized files (`adc.py`, `camera.py`, `buzzer.py`, `pca9685.py`) show a
- Legacy files (`Code/Client/Client.py`, `Code/Client/Main.py`) frequently omit spaces
- File encoding markers are inconsistent but common at the top of Server files:
- No linter configured or run. No CI pipeline exists (no `.github/workflows/`).
## Import Organization
## Error Handling
- New/modernized code should still prefer `except Exception as e: print(f"...: {e}")`
- One file demonstrates **precise errno-based handling** and should be treated as the
- Hardware-facing scripts use `try/except KeyboardInterrupt` around their
- No custom exception classes are defined anywhere in the project. Errors are either
- `Code/Server/imu.py` has one custom pattern worth reusing for I2C failures —
## Logging
## Comments
- Modernized files comment nearly every line with a trailing `#` explanation
- Legacy files comment sparingly, mostly as section dividers for repetitive blocks:
- Commented-out debug `print` statements are left in place rather than deleted, e.g.
- Present only in modernized files, one-line `"""Summary."""` style at the top of
- No module-level docstrings anywhere in the project.
- No class-level docstrings — only `__init__` methods get a one-liner in modernized
## Function Design
- Positional parameters dominate; keyword defaults used for tunable numeric constants,
- Protocol/command data is passed as a raw list of strings (`data`), then indexed and
- Multi-value returns use plain tuples, not named tuples/dataclasses:
- Functions that can fail return `None` on failure rather than raising, e.g.
## Module Design
## Protocol/Command Conventions
- Commands are `#`-delimited strings terminated with `\n`, e.g.
- Command dispatch in `Code/Server/server.py::receive_commands` and
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| Server entry point / GUI shell | Parses `-t`/`-n` CLI flags, owns the PyQt5 on/off window, starts/stops server threads | `Code/Server/main.py` |
| Server networking | Opens TCP sockets (video :8002, command :5002), dispatches text commands to the right hardware controller, streams JPEG frames | `Code/Server/server.py` |
| Alternate select()-based TCP server | Multi-client, non-blocking socket server with a message queue; not wired into `main.py`/`server.py` — a standalone/experimental component | `Code/Server/tcp_server.py` |
| Command vocabulary | Shared string constants (`CMD_MOVE`, `CMD_LED`, ...) defining the wire protocol | `Code/Server/command.py`, `Code/Client/Command.py` (duplicated, not shared) |
| Kinematics & gait engine | Inverse kinematics (leg angle ⇄ Cartesian), posture balancing (IMU-based), gait generation, per-leg calibration persistence | `Code/Server/control.py` |
| PID smoothing | Incremental PID controller used to smooth IMU roll/pitch before feeding into posture balance | `Code/Server/pid.py` |
| IMU sensor fusion | Reads MPU6050 accel/gyro, applies Kalman filtering per axis, computes roll/pitch/yaw via quaternion integration | `Code/Server/imu.py`, `Code/Server/kalman.py` |
| Servo abstraction | Converts angle (0-180°) to PWM duty cycle, dispatches to one of two PCA9685 chips (channels 0-15 / 16-31) | `Code/Server/servo.py` |
| PWM driver (I2C) | Low-level PCA9685 register access via `smbus` | `Code/Server/pca9685.py` |
| LED strip abstraction | Picks WS281X (RPi PWM) or SPI LED driver based on PCB/Pi hardware version, exposes animations (rainbow, chase, wipe) | `Code/Server/led.py`, `Code/Server/rpi_ledpixel.py`, `Code/Server/spi_ledpixel.py` |
| Hardware version detection | Reads/writes `params.json`, detects Raspberry Pi model to select LED driver at runtime | `Code/Server/parameter.py` |
| Battery/ADC sensing | Reads dual battery voltages via ADS7830 over I2C | `Code/Server/adc.py` |
| Distance sensing | Wraps `gpiozero.DistanceSensor` for the ultrasonic sensor | `Code/Server/ultrasonic.py` |
| Buzzer control | GPIO on/off wrapper for the piezo buzzer | `Code/Server/buzzer.py` |
| Camera streaming | Wraps `picamera2` to produce JPEG frames for the video socket or save still images | `Code/Server/camera.py` |
| Thread-kill utility | Forcibly raises `SystemExit` inside a running thread (used to stop video/command/LED threads on demand) | `Code/Server/Thread.py` |
| Server GUI layout | Generated PyQt5 `.ui`-derived widget layout for the on/off window | `Code/Server/ui_server.py` |
| Standalone gait demo | Script showing direct `Control` usage without the network layer | `Code/Server/myCode.py` |
| Hardware smoke test | Interactive script exercising LED, ultrasonic, servo, ADC, buzzer in sequence | `Code/Server/test.py` |
| Client entry point / GUI shell | PyQt5 main window, wires buttons/sliders to `Client` network calls, owns Calibration/LED/Face sub-windows | `Code/Client/Main.py`, `Code/Client/ui_client.py` |
| Client networking | Opens two sockets to the server (video, command), receives/decodes JPEG stream, sends text commands | `Code/Client/Client.py` |
| Client PID smoothing | Mirrors server's incremental PID for smoothing client-side inputs | `Code/Client/PID.py` |
| Face detection/recognition | OpenCV-based face detect/record/recognize used by the client video pipeline | `Code/Client/Face.py`, `Code/Client/Face/` |
| Calibration GUI | Standalone PyQt5 window for per-leg calibration, sends `CMD_CALIBRATION` commands | `Code/Client/Calibration.py` |
| LED control GUI | Standalone PyQt5 window sending `CMD_LED`/`CMD_LED_MOD` commands | `Code/Client/ui_led.py` |
| Face ID GUI | Standalone PyQt5 window for face recognition workflows | `Code/Client/ui_face.py` |
| Thread-kill utility (client) | Same pattern as server's `Thread.py`, duplicated | `Code/Client/Thread.py` |
| Vendored MPU6050 driver | Third-party I2C driver for the 6-axis IMU, installed as a local package | `Code/Libs/mpu6050/` |
| Vendored WS281x driver | Third-party `rpi_ws281x` Python bindings, installed as a local package | `Code/Libs/rpi-ws281x-python/` |
## Pattern Overview
- Two independent OS processes (Client GUI, Server GUI) connected only via sockets; the "API" is an informal `#`-delimited string protocol (see Data Flow).
- Command dispatch is a large `if/elif` chain inside `Server.receive_commands()` (`Code/Server/server.py`) keyed on substring membership in `command_parts`, not a routing table.
- Continuous background loop (`Control.condition_monitor`, `Code/Server/control.py`) polls a shared mutable `command_queue` list on a dedicated thread — this is the de facto state machine driving gait/posture/balance modes.
- Hardware drivers are organized in a shallow stack: command dispatcher → domain controller (`Control`, `Led`) → low-level driver (`Servo`/`PCA9685`, `rpi_ledpixel`/`spi_ledpixel`) → bus library (`smbus`, `spidev`, `gpiozero`).
- PyQt5 is used for both Client and Server GUIs; GUI layout classes (`Ui_server`, `Ui_client`, `Ui_led`, `Ui_Face`) are Qt Designer-generated and imported as mixins into the "real" window classes.
- Persistent state is stored in flat files, not a database: `Code/Server/point.txt` (per-leg calibration offsets, tab-separated), `Code/Server/params.json` (PCB/Pi hardware version), `Code/Client/IP.txt` (last-used server IP).
## Layers
- Purpose: On/off toggle and live telemetry (Server); full teleoperation console — movement, camera pan/tilt, LEDs, face ID, calibration (Client).
- Location: `Code/Server/main.py` + `Code/Server/ui_server.py`; `Code/Client/Main.py` + `Code/Client/ui_client.py`, `ui_led.py`, `ui_face.py`, `Calibration.py`.
- Contains: PyQt5 `QMainWindow` subclasses, Qt Designer-generated layout mixins, signal/slot wiring.
- Depends on: Networking layer (`Server`/`Client` classes).
- Used by: End users running the desktop apps (also distributed as pre-built binaries in `Application/mac/mac` and `Application/windows/windows.exe`).
- Purpose: Own the TCP sockets, encode/decode the text command protocol, stream video frames.
- Location: `Code/Server/server.py` (`Server` class), `Code/Server/tcp_server.py` (unused alternate implementation), `Code/Client/Client.py` (`Client` class).
- Contains: Socket setup/teardown, `send_data`/`receive_data`, per-thread `transmit_video`/`receive_commands` (server) and `receiving_video` (client).
- Depends on: Domain/hardware layer (Server) or PID/Face helpers (Client).
- Used by: GUI layer.
- Purpose: Translate high-level commands into physical leg trajectories; run the always-on condition-monitor state machine (gait, posture balance, IMU balance, calibration).
- Location: `Code/Server/control.py` (`Control`), `Code/Server/pid.py` (`Incremental_PID`).
- Contains: Inverse kinematics (`coordinate_to_angle`/`angle_to_coordinate`), leg-position transforms, gait waveform generators (`run_gait`), posture-balance rotation math (`calculate_posture_balance`).
- Depends on: Hardware driver layer (`Servo`, `IMU`), file I/O (`point.txt`).
- Used by: Networking layer (`Server.receive_commands`).
- Purpose: Talk directly to physical peripherals over I2C/SPI/GPIO.
- Location: `Code/Server/servo.py`, `pca9685.py`, `imu.py`, `kalman.py`, `adc.py`, `ultrasonic.py`, `buzzer.py`, `camera.py`, `led.py`, `rpi_ledpixel.py`, `spi_ledpixel.py`.
- Contains: Register-level I2C writes (`pca9685.py`), sensor polling loops (`imu.py`, `adc.py`), `gpiozero`/`picamera2`/`smbus`/`spidev` wrappers.
- Depends on: Vendored libraries in `Code/Libs/` (`mpu6050`, `rpi_ws281x`) and system libraries (`smbus`, `spidev`, `gpiozero`, `picamera2`).
- Used by: Domain layer (`Control` uses `Servo`, `IMU`) and networking layer directly (`Server` uses `Led`, `Buzzer`, `ADC`, `Ultrasonic`, `Camera`).
- Purpose: Store per-robot calibration and hardware identification across restarts.
- Location: `Code/Server/point.txt`, `Code/Server/params.json`, `Code/Server/parameter.py` (`ParameterManager`).
- Contains: Tab-separated leg offsets; JSON hardware version flags.
- Depends on: Nothing (plain file I/O).
- Used by: `Control.calibrate()`/`save_to_txt()`, `Led.__init__` (via `ParameterManager`).
## Data Flow
### Primary Command Path (Client → Server → Servos)
### Video Streaming Path (Server → Client)
### Sensor Telemetry Path (Server → Client, request/response)
- Server-side runtime state lives in plain instance attributes on long-lived singletons: `Server` owns `led_controller`, `control_system`, etc. (constructed once in `Server.__init__`); `Control` owns `command_queue`, `leg_positions`, `status_flag`, `calibration_angles` as mutable lists/attributes shared across threads without locks (relies on GIL + the single-producer/single-consumer pattern of `command_queue`).
- Client-side state is held on the `MyWindow`/`Client` instances and mutated directly from Qt slot callbacks (single GUI thread) plus one background video thread.
## Key Abstractions
- Purpose: Enumerates the string tokens that form the wire protocol between Client and Server (`CMD_MOVE`, `CMD_LED`, `CMD_SONIC`, `CMD_POWER`, `CMD_HEAD`, `CMD_CAMERA`, `CMD_RELAX`, `CMD_ATTITUDE`, `CMD_POSITION`, `CMD_BALANCE`, `CMD_CALIBRATION`, `CMD_BUZZER`, `CMD_SERVOPOWER`, `CMD_LED_MOD`).
- Examples: `Code/Server/command.py`, `Code/Client/Command.py` (two separate copies that must be kept in sync manually — see CONCERNS).
- Pattern: Plain class with class-level string constants, no enum, no versioning.
- Purpose: One class per physical subsystem (`Servo`, `Led`, `Buzzer`, `ADC`, `Ultrasonic`, `Camera`, `IMU`), each owning its own driver handle (I2C bus, GPIO pin, camera device) and exposing imperative methods.
- Examples: `Code/Server/servo.py`, `Code/Server/led.py`, `Code/Server/buzzer.py`, `Code/Server/adc.py`, `Code/Server/ultrasonic.py`, `Code/Server/camera.py`, `Code/Server/imu.py`.
- Pattern: Constructor opens the hardware resource immediately (no lazy init, no context manager except `Ultrasonic`); most expose `__main__` self-test blocks for standalone use.
- Purpose: Central "brain" translating body-frame commands (move, tilt, gait, balance) into 18 servo angles via forward/inverse kinematics over a fixed 6-leg, 3-joint-per-leg geometry.
- Examples: `Code/Server/control.py`.
- Pattern: God-object holding both kinematics math and the polling state machine (`condition_monitor`); mixes concerns (IK math, gait timing, calibration persistence, IMU balance loop) in one ~410-line class.
- Purpose: Cooperatively-unsafe but pragmatic way to stop long-running/blocking threads (video stream, LED animation loop, command receive loop) on demand, since Python has no built-in thread cancellation.
- Examples: `Code/Server/Thread.py` (`stop_thread`), `Code/Client/Thread.py` (duplicated).
- Pattern: Uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to inject `SystemExit` into a target thread — an unofficial CPython mechanism, not to be used as a template for new cancellable-thread code.
## Entry Points
- Location: `Code/Server/main.py`
- Triggers: Run directly (`python3 main.py`) on the Raspberry Pi, optionally with `-t` (auto-start TCP server) and/or `-n` (headless, no Qt UI).
- Responsibilities: Construct `Server`, show/hide the on/off Qt window, spawn `transmit_video`/`receive_commands` threads, handle process teardown (`closeEvent`).
- Location: `Code/Client/Main.py`
- Triggers: Run directly on a PC (`python3 Main.py`); pre-built binaries exist for mac (`Application/mac/mac`) and Windows (`Application/windows/windows.exe`).
- Responsibilities: Full teleoperation console; on connect, spawns the video-receive thread and starts telemetry timers.
- Location: `Code/Server/myCode.py` (gait demo via `Control` directly), `Code/Server/test.py` (interactive hardware smoke test), and the `if __name__ == '__main__':` blocks in nearly every driver module (`servo.py`, `led.py`, `adc.py`, `buzzer.py`, `ultrasonic.py`, `imu.py`, `camera.py`, `pca9685.py`).
- Triggers: Run individually for bring-up/debugging on the Pi.
- Responsibilities: Exercise one hardware subsystem in isolation without the client/server stack.
- Location: `Code/Libs/mpu6050/` (installable `mpu6050` package with its own `setup.py`), `Code/Libs/rpi-ws281x-python/library/` (installable `rpi_ws281x` package with C extension, its own `setup.py`, tests, examples).
- Triggers: `pip install .` from within each library directory (per `Tutorial.pdf` setup instructions).
- Responsibilities: Provide the IMU and addressable-LED drivers consumed by `Code/Server/imu.py` and `Code/Server/rpi_ledpixel.py`.
## Architectural Constraints
- **Threading:** Not a single-threaded event loop. Each side runs several Python threads sharing GIL-protected state: Server has the Qt main thread, a video-transmit thread, a command-receive thread, an LED-animation thread (recreated per LED command), and the always-on `Control.condition_monitor` thread. Client has the Qt main thread and a video-receive thread. No thread synchronization primitives protect `Control.command_queue` beyond relying on CPython's GIL for atomic list reassignment.
- **Global state:** `Server.__init__` and `Control.__init__` construct all hardware singletons (`Led`, `ADC`, `Servo`, `Buzzer`, `Control`, `Ultrasonic`, `Camera`, `IMU`) at process start and hold them for the process lifetime — there is no re-init/teardown path for individual peripherals other than full process exit. `Code/Server/point.txt`, `Code/Server/params.json` act as implicit global mutable config shared across all `Control`/`Led` instances (there is normally only one).
- **Thread cancellation:** Video, command-receive, and LED threads are stopped via `Thread.stop_thread()` injecting `SystemExit` asynchronously (`Code/Server/Thread.py`), not via cooperative flags/events — this can leave hardware resources (sockets, I2C transactions) in an inconsistent state if the exception fires mid-operation.
- **Protocol duplication:** The command vocabulary (`COMMAND` class) and the general command-parsing convention (`#`-delimited fields, `\n`-delimited messages) are duplicated independently in `Code/Server/command.py`/`Code/Server/server.py` and `Code/Client/Command.py`/`Code/Client/Client.py` — there is no shared schema or code generation, so protocol changes must be made in two places.
- **Hardware coupling:** Almost every module imports Raspberry Pi-specific libraries at module load time (`smbus`, `spidev`, `gpiozero`, `picamera2`) — the server codebase cannot be imported or unit-tested off-device without mocking these imports.
## Anti-Patterns
### God-object controller mixing IK math with a polling state machine
### Duplicated protocol/utility code between Client and Server
### Two parallel, inconsistent TCP server implementations
## Error Handling
- Socket operations wrap failures in `try/except`/bare `except:` and print a message (`Code/Server/server.py:68-72`, `Code/Client/Client.py:29-35`).
- `IMU.handle_exception()` (`Code/Server/imu.py:130`) prints, shells out to `i2cdetect -y 1` for diagnostics, then re-raises — the only place that re-raises after handling.
- `Camera.save_image`/`stop_stream` catch and print exceptions, returning `None` or silently continuing (`Code/Server/camera.py:46-53`, `71-78`).
- `Thread.stop_thread` failures are caught and printed at every call site (`Code/Server/server.py`, `Code/Server/main.py`) rather than centrally handled.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
