<!-- refreshed: 2026-08-06 -->
# Architecture

**Analysis Date:** 2026-08-06

## System Overview

The project is a two-process, network-connected robot control system: a **Server** process runs on the Raspberry Pi mounted in the hexapod and drives the hardware (servos, sensors, camera, LEDs), while a **Client** process (PC/desktop app, PyQt5 GUI) connects over Wi-Fi TCP sockets to send movement/LED/camera commands and receive a live video stream and telemetry (battery voltage, ultrasonic distance). There is no shared codebase between Client and Server — `Code/Client/Command.py` and `Code/Server/command.py` independently define the same string-based command protocol that both sides must keep in sync by hand.

```text
┌───────────────────────────────┐        Wi-Fi / TCP        ┌───────────────────────────────┐
│      Client (PC / laptop)     │◄──────────────────────────►│    Server (Raspberry Pi)      │
│  `Code/Client/Main.py`        │  port 5002: text commands  │  `Code/Server/main.py`        │
│  PyQt5 GUI (`ui_client.py`)   │  port 8002: JPEG video      │  PyQt5 GUI (`ui_server.py`)   │
├───────────────┬────────────────┤        stream               ├───────────────┬────────────────┤
│  Client.py    │  Calibration.py│                             │  server.py    │  control.py    │
│ (net + video) │  Face.py       │                             │ (net + video) │ (kinematics/IK)│
└───────┬────────┴────────────────┘                             └───────┬────────┴────────────────┘
        │                                                                │
        ▼                                                                ▼
┌───────────────────┐                                          ┌────────────────────────────────────┐
│ PID.py (client-side│                                          │ Hardware Driver Layer                │
│ smoothing filter)  │                                          │ `servo.py` → `pca9685.py` (I2C PWM)  │
└───────────────────┘                                          │ `imu.py` → `kalman.py` + `mpu6050`   │
                                                                 │ `adc.py`, `ultrasonic.py`,           │
                                                                 │ `buzzer.py`, `camera.py`, `led.py`   │
                                                                 └────────────────────────────────────┘
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

**Overall:** Layered, thread-per-concern client/server architecture with a hand-rolled text protocol over raw TCP sockets. There is no MVC/service-layer abstraction, no dependency injection, and no message broker — every "service" (LED, servo, IMU, camera, ultrasonic) is a plain Python class instantiated once inside `Server`/`Control` and driven by long-running background threads.

**Key Characteristics:**
- Two independent OS processes (Client GUI, Server GUI) connected only via sockets; the "API" is an informal `#`-delimited string protocol (see Data Flow).
- Command dispatch is a large `if/elif` chain inside `Server.receive_commands()` (`Code/Server/server.py`) keyed on substring membership in `command_parts`, not a routing table.
- Continuous background loop (`Control.condition_monitor`, `Code/Server/control.py`) polls a shared mutable `command_queue` list on a dedicated thread — this is the de facto state machine driving gait/posture/balance modes.
- Hardware drivers are organized in a shallow stack: command dispatcher → domain controller (`Control`, `Led`) → low-level driver (`Servo`/`PCA9685`, `rpi_ledpixel`/`spi_ledpixel`) → bus library (`smbus`, `spidev`, `gpiozero`).
- PyQt5 is used for both Client and Server GUIs; GUI layout classes (`Ui_server`, `Ui_client`, `Ui_led`, `Ui_Face`) are Qt Designer-generated and imported as mixins into the "real" window classes.
- Persistent state is stored in flat files, not a database: `Code/Server/point.txt` (per-leg calibration offsets, tab-separated), `Code/Server/params.json` (PCB/Pi hardware version), `Code/Client/IP.txt` (last-used server IP).

## Layers

**Presentation (GUI):**
- Purpose: On/off toggle and live telemetry (Server); full teleoperation console — movement, camera pan/tilt, LEDs, face ID, calibration (Client).
- Location: `Code/Server/main.py` + `Code/Server/ui_server.py`; `Code/Client/Main.py` + `Code/Client/ui_client.py`, `ui_led.py`, `ui_face.py`, `Calibration.py`.
- Contains: PyQt5 `QMainWindow` subclasses, Qt Designer-generated layout mixins, signal/slot wiring.
- Depends on: Networking layer (`Server`/`Client` classes).
- Used by: End users running the desktop apps (also distributed as pre-built binaries in `Application/mac/mac` and `Application/windows/windows.exe`).

**Networking:**
- Purpose: Own the TCP sockets, encode/decode the text command protocol, stream video frames.
- Location: `Code/Server/server.py` (`Server` class), `Code/Server/tcp_server.py` (unused alternate implementation), `Code/Client/Client.py` (`Client` class).
- Contains: Socket setup/teardown, `send_data`/`receive_data`, per-thread `transmit_video`/`receive_commands` (server) and `receiving_video` (client).
- Depends on: Domain/hardware layer (Server) or PID/Face helpers (Client).
- Used by: GUI layer.

**Domain / Control:**
- Purpose: Translate high-level commands into physical leg trajectories; run the always-on condition-monitor state machine (gait, posture balance, IMU balance, calibration).
- Location: `Code/Server/control.py` (`Control`), `Code/Server/pid.py` (`Incremental_PID`).
- Contains: Inverse kinematics (`coordinate_to_angle`/`angle_to_coordinate`), leg-position transforms, gait waveform generators (`run_gait`), posture-balance rotation math (`calculate_posture_balance`).
- Depends on: Hardware driver layer (`Servo`, `IMU`), file I/O (`point.txt`).
- Used by: Networking layer (`Server.receive_commands`).

**Hardware Driver:**
- Purpose: Talk directly to physical peripherals over I2C/SPI/GPIO.
- Location: `Code/Server/servo.py`, `pca9685.py`, `imu.py`, `kalman.py`, `adc.py`, `ultrasonic.py`, `buzzer.py`, `camera.py`, `led.py`, `rpi_ledpixel.py`, `spi_ledpixel.py`.
- Contains: Register-level I2C writes (`pca9685.py`), sensor polling loops (`imu.py`, `adc.py`), `gpiozero`/`picamera2`/`smbus`/`spidev` wrappers.
- Depends on: Vendored libraries in `Code/Libs/` (`mpu6050`, `rpi_ws281x`) and system libraries (`smbus`, `spidev`, `gpiozero`, `picamera2`).
- Used by: Domain layer (`Control` uses `Servo`, `IMU`) and networking layer directly (`Server` uses `Led`, `Buzzer`, `ADC`, `Ultrasonic`, `Camera`).

**Persistence (flat-file config):**
- Purpose: Store per-robot calibration and hardware identification across restarts.
- Location: `Code/Server/point.txt`, `Code/Server/params.json`, `Code/Server/parameter.py` (`ParameterManager`).
- Contains: Tab-separated leg offsets; JSON hardware version flags.
- Depends on: Nothing (plain file I/O).
- Used by: `Control.calibrate()`/`save_to_txt()`, `Led.__init__` (via `ParameterManager`).

## Data Flow

### Primary Command Path (Client → Server → Servos)

1. User interacts with a GUI control (e.g. drags the movement joystick or a slider) in `Code/Client/ui_client.py`.
2. `MyWindow` (in `Code/Client/Main.py`) builds a `#`-delimited command string (e.g. `"CMD_MOVE#1#0#35#10#0\n"`) and calls `self.client.send_data(...)` (`Code/Client/Client.py:68`).
3. Data is sent over the command TCP socket (port 5002) to the Server process.
4. `Server.receive_commands()` (`Code/Server/server.py:115`) reads the socket, splits on `\n` then `#`, and dispatches via the `if/elif cmd.CMD_* in command_parts` chain.
5. For movement/posture/calibration commands, the parsed parts are simply assigned to `self.control_system.command_queue` (`Code/Server/server.py:206`) — no direct function call.
6. A separate always-running thread, `Control.condition_monitor()` (`Code/Server/control.py:133`), polls `command_queue` on every loop iteration and dispatches to `move_position`, `run_gait`, `calculate_posture_balance`/`imu6050`, or calibration handlers.
7. Kinematics functions (`transform_coordinates`, `coordinate_to_angle`) compute the 18 target servo angles and call `Servo.set_servo_angle()` (`Code/Server/servo.py:19`) for each.
8. `Servo` maps angle → PWM duty cycle and writes it to one of two `PCA9685` chips over I2C (`Code/Server/pca9685.py:59`).

### Video Streaming Path (Server → Client)

1. `Server.transmit_video()` (`Code/Server/server.py:91`) accepts a connection on the video socket (port 8002) and calls `Camera.start_stream()`.
2. `Camera` (`Code/Server/camera.py`) uses `picamera2` with a `JpegEncoder` writing into a `StreamingOutput` buffer guarded by a `threading.Condition`.
3. The transmit loop calls `Camera.get_frame()`, which blocks on the condition until a new JPEG is ready, then writes a 4-byte little-endian length prefix followed by the JPEG bytes to the socket.
4. `Client.receiving_video()` (`Code/Client/Client.py:47`) reads the 4-byte length, then reads exactly that many bytes, validates the JPEG (`is_valid_image_4_bytes`), decodes with OpenCV, and optionally runs `Face.face_detect()`.
5. The decoded frame (`self.image`) is polled by the GUI's `QTimer`-driven `refresh_image` slot (`Code/Client/Main.py`) and rendered into the video `QLabel`.

### Sensor Telemetry Path (Server → Client, request/response)

1. Client sends `"CMD_POWER\n"` or `"CMD_SONIC\n"` on a `QTimer` tick (`Code/Client/Main.py`, `power`/`getSonicData` slots).
2. `Server.receive_commands()` matches `cmd.CMD_POWER`/`cmd.CMD_SONIC`, reads `ADC.read_battery_voltage()` or `Ultrasonic.get_distance()`, and sends a `"CMD_POWER#v1#v2\n"` / `"CMD_SONIC#dist\n"` string back over the same command socket via `send_data`.
3. Client's `receive_data()` (`Code/Client/Client.py:74`) does a blocking `recv` and the GUI parses the response to update labels.

**State Management:**
- Server-side runtime state lives in plain instance attributes on long-lived singletons: `Server` owns `led_controller`, `control_system`, etc. (constructed once in `Server.__init__`); `Control` owns `command_queue`, `leg_positions`, `status_flag`, `calibration_angles` as mutable lists/attributes shared across threads without locks (relies on GIL + the single-producer/single-consumer pattern of `command_queue`).
- Client-side state is held on the `MyWindow`/`Client` instances and mutated directly from Qt slot callbacks (single GUI thread) plus one background video thread.

## Key Abstractions

**Command protocol (`COMMAND` class):**
- Purpose: Enumerates the string tokens that form the wire protocol between Client and Server (`CMD_MOVE`, `CMD_LED`, `CMD_SONIC`, `CMD_POWER`, `CMD_HEAD`, `CMD_CAMERA`, `CMD_RELAX`, `CMD_ATTITUDE`, `CMD_POSITION`, `CMD_BALANCE`, `CMD_CALIBRATION`, `CMD_BUZZER`, `CMD_SERVOPOWER`, `CMD_LED_MOD`).
- Examples: `Code/Server/command.py`, `Code/Client/Command.py` (two separate copies that must be kept in sync manually — see CONCERNS).
- Pattern: Plain class with class-level string constants, no enum, no versioning.

**Hardware controller classes:**
- Purpose: One class per physical subsystem (`Servo`, `Led`, `Buzzer`, `ADC`, `Ultrasonic`, `Camera`, `IMU`), each owning its own driver handle (I2C bus, GPIO pin, camera device) and exposing imperative methods.
- Examples: `Code/Server/servo.py`, `Code/Server/led.py`, `Code/Server/buzzer.py`, `Code/Server/adc.py`, `Code/Server/ultrasonic.py`, `Code/Server/camera.py`, `Code/Server/imu.py`.
- Pattern: Constructor opens the hardware resource immediately (no lazy init, no context manager except `Ultrasonic`); most expose `__main__` self-test blocks for standalone use.

**Kinematics engine (`Control`):**
- Purpose: Central "brain" translating body-frame commands (move, tilt, gait, balance) into 18 servo angles via forward/inverse kinematics over a fixed 6-leg, 3-joint-per-leg geometry.
- Examples: `Code/Server/control.py`.
- Pattern: God-object holding both kinematics math and the polling state machine (`condition_monitor`); mixes concerns (IK math, gait timing, calibration persistence, IMU balance loop) in one ~410-line class.

**Thread-kill helper:**
- Purpose: Cooperatively-unsafe but pragmatic way to stop long-running/blocking threads (video stream, LED animation loop, command receive loop) on demand, since Python has no built-in thread cancellation.
- Examples: `Code/Server/Thread.py` (`stop_thread`), `Code/Client/Thread.py` (duplicated).
- Pattern: Uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to inject `SystemExit` into a target thread — an unofficial CPython mechanism, not to be used as a template for new cancellable-thread code.

## Entry Points

**Server GUI/service:**
- Location: `Code/Server/main.py`
- Triggers: Run directly (`python3 main.py`) on the Raspberry Pi, optionally with `-t` (auto-start TCP server) and/or `-n` (headless, no Qt UI).
- Responsibilities: Construct `Server`, show/hide the on/off Qt window, spawn `transmit_video`/`receive_commands` threads, handle process teardown (`closeEvent`).

**Client GUI:**
- Location: `Code/Client/Main.py`
- Triggers: Run directly on a PC (`python3 Main.py`); pre-built binaries exist for mac (`Application/mac/mac`) and Windows (`Application/windows/windows.exe`).
- Responsibilities: Full teleoperation console; on connect, spawns the video-receive thread and starts telemetry timers.

**Standalone hardware scripts (no networking):**
- Location: `Code/Server/myCode.py` (gait demo via `Control` directly), `Code/Server/test.py` (interactive hardware smoke test), and the `if __name__ == '__main__':` blocks in nearly every driver module (`servo.py`, `led.py`, `adc.py`, `buzzer.py`, `ultrasonic.py`, `imu.py`, `camera.py`, `pca9685.py`).
- Triggers: Run individually for bring-up/debugging on the Pi.
- Responsibilities: Exercise one hardware subsystem in isolation without the client/server stack.

**Vendored library entry points:**
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

**What happens:** `Control` (`Code/Server/control.py`) combines inverse-kinematics math, gait waveform generation, IMU-based balance looping, calibration persistence, and a busy-poll `while True` state machine (`condition_monitor`) all in one ~410-line class.
**Why it's wrong:** Any change to command handling risks breaking kinematics and vice versa; the `condition_monitor` loop spins continuously checking `command_queue` membership with string comparisons instead of an explicit state machine or command dispatch table, making new command types error-prone to add.
**Do this instead:** When extending, add new gait/posture behaviors as separate methods invoked from a small dispatch table keyed by `command_queue[0]`, and avoid adding more responsibilities (e.g. new persistence formats) directly onto `Control`.

### Duplicated protocol/utility code between Client and Server

**What happens:** `Code/Server/command.py` and `Code/Client/Command.py` define an identical `COMMAND` class; `Code/Server/Thread.py` and `Code/Client/Thread.py` define an identical `stop_thread`; a duplicate `PID`/`Incremental_PID` implementation exists in both `Code/Server/pid.py` and `Code/Client/PID.py`.
**Why it's wrong:** Any protocol or utility fix must be applied twice, and the two directories can silently drift out of sync (e.g. a new `CMD_*` added on one side but not the other breaks the integration invisibly at runtime).
**Do this instead:** Keep both copies in lockstep whenever one is edited; when adding a new command, update `Code/Server/command.py` and `Code/Client/Command.py` in the same change, and prefer treating one as the canonical source to diff against.

### Two parallel, inconsistent TCP server implementations

**What happens:** `Code/Server/server.py` implements the actual video/command server used by `main.py`, while `Code/Server/tcp_server.py` implements a second, more robust `select()`-based, multi-client TCP server with its own `if __name__ == "__main__"` demo — but nothing in the running application imports or uses `tcp_server.py`.
**Why it's wrong:** A contributor could reasonably assume `tcp_server.py` is the live networking layer and modify it with no effect, or duplicate effort re-solving problems (multi-client support, graceful shutdown) that `TCPServer` already solves.
**Do this instead:** Treat `Code/Server/tcp_server.py` as dead/experimental code; if the blocking-accept model in `server.py` needs to be replaced, migrate `Server` to use `TCPServer` explicitly rather than maintaining both.

## Error Handling

**Strategy:** Defensive but silent — most I/O and hardware calls are wrapped in broad `try/except Exception` (or bare `except:`) blocks that `print()` the error and continue, rather than propagating typed exceptions or logging structurally.

**Patterns:**
- Socket operations wrap failures in `try/except`/bare `except:` and print a message (`Code/Server/server.py:68-72`, `Code/Client/Client.py:29-35`).
- `IMU.handle_exception()` (`Code/Server/imu.py:130`) prints, shells out to `i2cdetect -y 1` for diagnostics, then re-raises — the only place that re-raises after handling.
- `Camera.save_image`/`stop_stream` catch and print exceptions, returning `None` or silently continuing (`Code/Server/camera.py:46-53`, `71-78`).
- `Thread.stop_thread` failures are caught and printed at every call site (`Code/Server/server.py`, `Code/Server/main.py`) rather than centrally handled.

## Cross-Cutting Concerns

**Logging:** No logging framework; all diagnostics go through `print()` statements scattered across modules (no log levels, no timestamps, no structured output).
**Validation:** Minimal — numeric command arguments are clamped via `Control.restrict_value()`/`map_value()` (`Code/Server/control.py:252-261`) rather than rejected; malformed commands are mostly ignored by falling through the `if/elif` chain in `Server.receive_commands()`.
**Authentication:** None — the command and video TCP sockets accept the first client that connects (`socket.listen(1)`), with no credential exchange or encryption.

---

*Architecture analysis: 2026-08-06*
