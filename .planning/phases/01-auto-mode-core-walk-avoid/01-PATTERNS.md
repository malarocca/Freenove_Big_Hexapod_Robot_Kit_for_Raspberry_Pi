# Phase 1: Auto-Mode Core — Walk & Avoid - Pattern Map

**Mapped:** 2026-08-07
**Files analyzed:** 11
**Analogs found:** 9 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `Code/Server/autonomy/__init__.py` | module | n/a | — | no analog needed (empty package marker) |
| `Code/Server/autonomy/perception.py` (`SensorHub`) | service (hardware-facing) | streaming/polling | `Code/Server/ultrasonic.py` + `Code/Server/adc.py` (polling driver wrapper style) | role-match |
| `Code/Server/autonomy/behavior.py` (decision loop + bounded timer) | service (state machine) | event-driven | `Control.condition_monitor` (`Code/Server/control.py:133-218`) | role-match (pattern to follow, not code to reuse — see D-09/D-10 caveats) |
| `Code/Server/autonomy/bridge.py` (intent → `command_queue`) | service (adapter) | request-response | `Server.receive_commands`'s final `else` branch (`Code/Server/server.py:205-207`) | role-match |
| `Code/Server/command.py` (+`CMD_AUTO`) | config/constants | n/a | itself (existing `COMMAND` class) | exact |
| `Code/Client/Command.py` (+`CMD_AUTO`) | config/constants | n/a | itself (existing `COMMAND` class, duplicate) | exact |
| `Code/Server/server.py` (+`CMD_AUTO` dispatch, `auto_mode_active` Event, manual-preempt hook) | controller (command dispatcher) | request-response | itself — extend `Server.receive_commands()`'s existing `if/elif` chain | exact |
| `Code/Server/main.py` (D-01 `tcp_flag`→`is_tcp_active` fix) | controller (process/GUI shell) | request-response | itself — mechanical rename, no external analog needed | exact |
| `Code/Server/control.py` (optional `run_gait` interrupt-check, Pitfall 2) | domain/state-machine | event-driven | itself — surgical edit to existing `run_gait()` (`control.py:329-404`) | exact (edit-in-place, not new-file pattern) |
| `Code/Client/ui_client.py` (+`Button_Auto`, +`label_Auto_Status`) | component (generated Qt layout) | n/a (declarative widget tree) | `Button_Face_ID` (button, `ui_client.py:548-558`) + `states` label (`Code/Server/ui_server.py:53-60`) | exact |
| `Code/Client/Main.py` (+auto-mode wiring, connection-guard error text) | controller (GUI event handlers) | request-response | `Button_Buzzer`/`buzzer()` toggle pattern (`Main.py:42-43,611-621`) + `connect()` (`Main.py:521-552`) | exact |

## Pattern Assignments

### `Code/Server/autonomy/perception.py` (`SensorHub`) — service, polling/streaming

**Analog:** `Code/Server/ultrasonic.py` (driver wrapper shape) + `Code/Server/adc.py` (polling-loop/self-test style) + RESEARCH.md Pattern 1/2 (mandatory reuse + `_read()` bypass, already vetted this session)

**Imports pattern** (`Code/Server/ultrasonic.py:1-3`):
```python
from gpiozero import DistanceSensor, PWMSoftwareFallback, DistanceSensorNoEcho
import warnings
import time
```
New file's imports should follow the same flat, no-package-prefix style used throughout `Code/Server/` (no relative imports, e.g. `from servo import Servo`), plus `threading` for the bounded-wait helper.

**Constructor / hardware-reuse pattern** — do NOT construct new hardware objects; mirror how `Server.__init__` builds each driver once (`Code/Server/server.py:34-40`):
```python
# Code/Server/server.py:34-40 — the objects SensorHub must receive, not recreate
self.led_controller = Led()
self.adc_sensor = ADC()
self.servo_controller = Servo()
self.buzzer_controller = Buzzer()
self.control_system = Control()
self.ultrasonic_sensor = Ultrasonic()
self.camera_device = Camera()
```
`SensorHub.__init__(self, ultrasonic_sensor, head_servo, pan_channel=1, tilt_channel=0)` takes `server.ultrasonic_sensor` / `server.servo_controller` as constructor args (RESEARCH.md Pattern 1, `perception.py` design already spelled out there) — this is the one place in the whole phase where "closest analog" is explicitly "do not copy the object-construction pattern, only the polling-loop shape."

**No-echo / core sensing pattern** (bypasses `Ultrasonic.get_distance()`'s smoothing per RESEARCH.md Pitfall 1 — this is the load-bearing CAUTION-01 logic):
```python
# RESEARCH.md Pattern 2 / Code Examples — verified against installed gpiozero 2.0.1 this session
def read_raw_distance_cm(ultrasonic_sensor):
    raw = ultrasonic_sensor.sensor._read()   # bypasses SmoothedInputDevice averaging deliberately
    if raw is None:
        return None                           # genuine "unknown" — never treat as clear
    return round(raw * ultrasonic_sensor.max_distance * 100, 1)

# Bounded startup read — guards the boot-time "queue never fills, .value hangs forever" case
def get_first_reading_or_none(ultrasonic_sensor, timeout=1.0):
    result = {}
    def _read():
        result['value'] = ultrasonic_sensor.sensor._read()
    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None
    return result.get('value')
```

**Head-sweep clamp pattern** (Pitfall 7 — `CMD_HEAD`'s network path does NOT clamp; new code must self-clamp):
```python
# derived from Code/Client/Main.py:592-606 (client's tested slider ranges)
PAN_CHANNEL = 1
TILT_CHANNEL = 0
PAN_SAFE_MIN, PAN_SAFE_MAX = 30, 150
def sweep_to(servo, bearing_angle):
    clamped = max(PAN_SAFE_MIN, min(PAN_SAFE_MAX, bearing_angle))
    servo.set_servo_angle(PAN_CHANNEL, clamped)
```
Note channel 1 = pan (left/right), channel 0 = tilt (up/down) — confirmed against the real client's live-tested wiring (`Main.py:592-606`), NOT the protocol doc's mismatched axis labels (RESEARCH.md Pitfall 7).

**Self-test / `__main__` block pattern** — match `Code/Server/ultrasonic.py:39-49` and `Code/Server/adc.py:50-59`'s convention of a runnable, assertion-free manual smoke test guarded by `if __name__ == '__main__':`, `try/except KeyboardInterrupt` around the loop, `time.sleep(...)` between polls. RESEARCH.md's Validation Architecture explicitly recommends this shape for `behavior.py`'s decision-logic self-check too (no pytest, per CLAUDE.md's project-level testing constraint).

**Error handling pattern** — every hardware read must be wrapped per CLAUDE.md's explicit new-code guidance (not the codebase's dominant legacy bare-`except:`):
```python
# CLAUDE.md Error Handling: "New/modernized code should still prefer
# except Exception as e: print(f"...: {e}")" — apply this, not bare except:
```

---

### `Code/Server/autonomy/behavior.py` (decision loop + bounded-runtime timer) — service, event-driven

**Analog:** `Control.condition_monitor()` (`Code/Server/control.py:133-218`) for the "always-on polling loop reading shared mutable state" shape — pattern to follow structurally, but this is explicitly a NEW, separate loop/thread, never a modification of `condition_monitor` itself (RESEARCH.md: "never modifies Control's kinematics").

**Core loop shape to imitate** (`Code/Server/control.py:133-138`):
```python
def condition_monitor(self):
    while True:
        if (time.time() - self.timeout) > 10 and self.timeout != 0 and self.command_queue[0] == '':
            self.timeout = time.time()
            self.relax(True)
            self.status_flag = 0x00
        # ... elif chain keyed on command_queue[0] ...
```
`behavior.py`'s decision loop should follow the same "always-on `while` loop on its own thread, polling shared state, no blocking waits" shape, but:
- Use `threading.Event` for cooperative stop (see Shared Patterns below), checked every iteration — `condition_monitor` itself has NO such check today (it is not a template for cancellation, only for loop structure).
- Use `time.monotonic()` (per RESEARCH.md Standard Stack) for the 5-minute bounded-runtime timer, kept entirely inside `behavior.py` — do not reuse or extend `Control`'s unrelated 10-second idle-to-relax timeout (`control.py:135-138`) for this purpose (RESEARCH.md "Don't Hand-Roll" table).

**State dispatch pattern** — mirror the existing `if/elif` chain style (not a class-hierarchy/visitor pattern) used throughout this codebase for command_queue dispatch (`control.py:139-218`, `server.py:143-207`) — this project's established convention is flat conditional dispatch, not polymorphism. A hand-rolled `enum` + dispatch function (RESEARCH.md's recommended default, `transitions` library explicitly optional/deferred) fits this existing convention.

**Error handling pattern (Pitfall 6 — do not replicate `condition_monitor`'s gap)**: `condition_monitor` has **no top-level try/except at all** (`control.py:133`) — an uncaught exception there silently kills the movement thread. `behavior.py` must NOT copy this omission; wrap the loop body:
```python
# Required shape per RESEARCH.md Pitfall 6 / Security Domain (DoS-of-safety-mechanism row)
while not stop_event.is_set():
    try:
        # sense -> decide -> act
        ...
    except Exception as e:
        print(f"autonomy loop error: {e}")
        # fail-safe: stop producing, do not silently continue
        break
```

---

### `Code/Server/autonomy/bridge.py` (intent → `Control.command_queue`) — service, request-response

**Analog:** `Server.receive_commands()`'s final `else` branch (`Code/Server/server.py:205-207`) — the exact existing write-site to `command_queue` that all new intent-writes must match the shape of:
```python
# Code/Server/server.py:205-207 (existing pattern for writing command_queue)
else:
    self.control_system.command_queue = command_parts
    self.control_system.timeout = time.time()
```
`bridge.py` composes a `command_parts`-shaped list (e.g. `['CMD_MOVE', gait, x, y, speed, angle]`, matching `run_gait`'s expected `data` shape at `control.py:329`) and writes it the same way, gated by the arbitration Event (see Shared Patterns).

---

### `Code/Server/command.py` / `Code/Client/Command.py` (+`CMD_AUTO`) — config, n/a

**Analog:** itself — both files are currently byte-for-byte identical `COMMAND` classes (verified this session).

**Pattern** (`Code/Server/command.py:1-18`):
```python
class COMMAND:
    CMD_MOVE = "CMD_MOVE"
    CMD_LED_MOD = "CMD_LED_MOD"
    ...
    CMD_SERVOPOWER = "CMD_SERVOPOWER"

    def __init__(self):
        pass
```
Add `CMD_AUTO = "CMD_AUTO"` as one new class-level string constant in **both** files (dual-copy convention, no shared schema — RESEARCH.md/ARCHITECTURE.md "Protocol duplication" anti-pattern, not to be fixed this phase, just followed).

---

### `Code/Server/server.py` (+`CMD_AUTO` dispatch, `auto_mode_active` Event, manual-preempt hook) — controller, request-response

**Analog:** itself — extend the existing `if/elif` chain in `receive_commands()` (`Code/Server/server.py:141-207`).

**Dispatch-chain pattern to copy** (`Code/Server/server.py:178-183`, representative branch shape):
```python
elif cmd.CMD_SONIC in command_parts:
    response_command = cmd.CMD_SONIC + "#" + str(self.ultrasonic_sensor.get_distance()) + "\n"
    self.send_data(self.command_connection, response_command)
elif cmd.CMD_HEAD in command_parts:
    if len(command_parts) == 3:
        self.servo_controller.set_servo_angle(int(command_parts[1]), int(command_parts[2]))
```
New `CMD_AUTO` branch should follow this exact shape: `elif cmd.CMD_AUTO in command_parts:` + field-count validation before indexing (per RESEARCH.md Security Domain V5 — do not repeat `CMD_HEAD`'s unvalidated-`int()` gap for the new command).

**Manual-preempt hook** — insert into the existing final `else` branch (`Code/Server/server.py:205-207`), per RESEARCH.md Pattern 3 (already vetted, concrete diff shape):
```python
# Code/Server/server.py:205-207 — existing code
else:
    self.control_system.command_queue = command_parts
    self.control_system.timeout = time.time()

# extended shape (RESEARCH.md Pattern 3 / Code Examples)
else:
    if command_parts[0] in (cmd.CMD_MOVE, cmd.CMD_POSITION, cmd.CMD_ATTITUDE, cmd.CMD_BALANCE):
        self.auto_mode_active.clear()          # manual always preempts, checked first
    self.control_system.command_queue = command_parts
    self.control_system.timeout = time.time()
```

**Constructor pattern** — add `self.auto_mode_active = threading.Event()` alongside the other singleton state in `Server.__init__` (`Code/Server/server.py:31-43`), same style as `self.is_tcp_active = False` / `self.is_servo_relaxed = False` (plain instance attributes, no config object).

**D-01 reconnect-fix context** (`Code/Server/server.py:124-135`):
```python
while True:
    try:
        received_data = self.command_connection.recv(1024).decode('utf-8')
    except:
        if self.is_tcp_active:
            self.reset_server()
            break
        else:
            break
    if received_data == "" and self.is_tcp_active:
        self.reset_server()
        break
```
`is_tcp_active` is already correctly read here — the bug is entirely on the `main.py` write side (see below); `server.py` itself needs no line-level change for D-01, only confirmation the attribute name matches.

**Error handling convention already established in this file**: bare `except:` dominates (`server.py:71,96,120,127,159`) — CLAUDE.md flags this as legacy style; new `CMD_AUTO` code should prefer `except Exception as e: print(f"...: {e}")` per the project's stated preference for new/modernized code, without rewriting the surrounding legacy branches.

---

### `Code/Server/main.py` (D-01 fix) — controller/process shell, request-response

**Analog:** itself — mechanical rename across 3 call sites.

**Bug pattern** (`Code/Server/main.py:26,49,57`):
```python
self.server.tcp_flag=True     # main.py:26 (__init__) and :49 (on_and_off_server, "turn on")
...
self.server.tcp_flag=False    # main.py:57 (on_and_off_server, "turn off")
```
`Server` (`server.py`) never defines `tcp_flag` — only `is_tcp_active`, initialized `False` at `server.py:32` and never set `True` anywhere. **Fix:** rename all three `self.server.tcp_flag` references to `self.server.is_tcp_active`, preserving each site's existing `True`/`False` intent. This is the entire scope of D-01 — no other logic changes in `main.py`.

**Adjacent-but-optional bug (flagged, not required by D-01):** `main.py:72-73`'s `closeEvent` references `self.server.server_socket`/`server_socket1`, which don't exist on `Server` (`video_socket`/`command_socket` are the real names, `server.py:56,60`) — wrapped in a bare `try/except: pass` so it fails silently today. Planner should explicitly decide in/out of scope; not required by D-01's literal wording.

---

### `Code/Server/control.py` (optional `run_gait` interrupt-check, Pitfall 2) — domain, event-driven

**Analog:** itself — surgical, narrow edit only if the planner elects Pitfall 2's option 2 (interrupt-check) over option 1 (brisk default speed, no code change).

**Current uninterruptible shape** (`Code/Server/control.py:348-385`, gait 1 inner loop — representative, gait 2's nested loop at `386-404` has the same property):
```python
elif gait == "1":
    for j in range(F):
        for i in range(3):
            ... # points math, no command_queue check
        self.transform_coordinates(points)
        self.set_leg_angles()
        time.sleep(delay)
```
If in scope: add a narrow, autonomy-specific override-check (e.g. `if self._override_requested(): return`) once per `time.sleep(delay)` tick, gated behind a flag/method only the arbitration path sets — NOT a general refactor of `command_queue` handling. This exact fix is independently recommended in `.planning/codebase/CONCERNS.md`'s "Performance Bottlenecks" section.

---

### `Code/Client/ui_client.py` (+`Button_Auto`, +`label_Auto_Status`) — component, declarative

**Analog:** `Button_Face_ID` (button widget, `Code/Client/ui_client.py:548-558`) for the toggle button; `states` (`QLabel`, `Code/Server/ui_server.py:53-60`) for the always-visible status badge shape.

**Button construction pattern to copy exactly** (`Code/Client/ui_client.py:548-558`):
```python
self.Button_Face_ID = QtWidgets.QPushButton(client)
self.Button_Face_ID.setGeometry(QtCore.QRect(40, 510, 90, 30))
font = QtGui.QFont()
font.setFamily("Arial")
font.setPointSize(9)
font.setBold(False)
font.setItalic(False)
font.setWeight(50)
self.Button_Face_ID.setFont(font)
self.Button_Face_ID.setStyleSheet("font: 10pt \"Arial\";")
self.Button_Face_ID.setObjectName("Button_Face_ID")
```
`Button_Auto` uses `QtCore.QRect(150, 510, 110, 30)` per UI-SPEC.md's exact geometry contract, otherwise identical construction order (instantiate → setGeometry → setFont → setStyleSheet → setObjectName → later `.raise_()` call in the z-order block, `setText` in `retranslateUi`).

**Label construction pattern to copy** (`Code/Server/ui_server.py:53-60`, `states` label — closest existing "status text that changes with backend state" widget):
```python
self.states = QtWidgets.QLabel(server)
self.states.setGeometry(QtCore.QRect(120, 80, 160, 90))
font = QtGui.QFont()
...
self.states.setFont(font)
self.states.setAlignment(QtCore.Qt.AlignCenter)
self.states.setObjectName("states")
# retranslateUi:
self.states.setText(_translate("server", "Off"))
```
`label_Auto_Status` uses `QtCore.QRect(270, 510, 160, 30)` per UI-SPEC.md, plus `font.setBold(True)` (UI-SPEC.md Typography — the one new bold-weight exception this phase introduces) and a `setStyleSheet` color per UI-SPEC.md's Color table (`#35C759` active / `#DCDCDC` idle), set dynamically from `Main.py`, not hardcoded in `retranslateUi`'s static text.

**Required generated-file discipline** (do not deviate): construction order instantiate → `setGeometry` → `setFont` → `setStyleSheet` → `setText`/`setObjectName`, matching every existing widget in this file — `ui_client.py`'s own header warns against manual edits outside this exact pattern.

---

### `Code/Client/Main.py` (+auto-mode wiring, connection-guard) — controller, request-response

**Analog:** `Button_Buzzer`'s dynamic-label toggle (`Code/Client/Main.py:42-43,611-621`) for `Button_Auto`'s "Start Auto Mode"/"Stop Auto Mode" toggle; `connect()`'s not-connected guard shape (`Main.py:521-552`) for the "Not connected" inline error text.

**Signal wiring pattern** (`Code/Client/Main.py:42-43`):
```python
self.Button_Buzzer.pressed.connect(self.buzzer)
self.Button_Buzzer.released.connect(self.buzzer)
```
(Simple click-toggle analog is more directly `Button_Connect.clicked.connect(self.connect)`, `Main.py:33` — use `clicked.connect`, not `pressed`/`released`, since Auto Mode is a click-to-toggle, not a hold-to-activate control like the buzzer.)

**Dynamic toggle-label + command-send pattern** (`Code/Client/Main.py:611-621`):
```python
def buzzer(self):
    if self.Button_Buzzer.text() == 'Buzzer':
        command=cmd.CMD_BUZZER+'#1'+'\n'
        self.client.send_data(command)
        self.Button_Buzzer.setText('Noise')
    else:
        command=cmd.CMD_BUZZER+'#0'+'\n'
        self.client.send_data(command)
        self.Button_Buzzer.setText('Buzzer')
```
`auto_mode_toggle()` follows this exact shape: check `Button_Auto.text()`, send `CMD_AUTO#1`/`CMD_AUTO#0`, flip button text between "Start Auto Mode"/"Stop Auto Mode" (verb-first per UI-SPEC.md Copywriting), and separately update `label_Auto_Status`'s text/color per UI-SPEC.md's Interaction Contract (badge reflects server-confirmed state, not just click state — may require reading a server ack rather than assuming success, consistent with how `connect()` below gates on actual socket state).

**Not-connected guard pattern** (`Code/Client/Main.py:521-552`, `connect()`):
```python
def connect(self):
    try:
        ...
        if self.Button_Connect.text()=='Connect':
            self.IP = self.lineEdit_IP_Adress.text()
            self.client.turn_on_client(self.IP)
            ...
            self.Button_Connect.setText('Disconnect')
        else:
            ...
            self.Button_Connect.setText('Connect')
    except Exception as e:
        print(e)
```
This file already uses the CLAUDE.md-preferred `except Exception as e: print(e)` style (not bare `except:`) — match it for the new `auto_mode_toggle()`/connection-guard code, and route the "Not connected" inline message per UI-SPEC.md's Error State row (check connection state before sending `CMD_AUTO#1`; if not connected, show the inline text and leave `label_Auto_Status` in its idle state — never optimistically flip to "ACTIVE").

**Head-servo slider pattern** (context only, for perception.py's channel/range choices — already covered above): `Code/Client/Main.py:592-606` (`headUpAndDown`/`headLeftAndRight`).

---

## Shared Patterns

### Cooperative stop / arbitration (`threading.Event`)
**Source:** RESEARCH.md Patterns 3 & 4 (stdlib `threading.Event`, no in-repo precedent to copy from — `Code/Server/Thread.py`'s `stop_thread()` is the explicit anti-pattern, NOT to be extended)
**Apply to:** `behavior.py` (main loop gate + stop_event), `server.py` (`auto_mode_active` Event set/clear), `bridge.py` (check-before-write)
```python
# Thread.py:20-22 — the pattern to AVOID for new autonomy shutdown code
def stop_thread(thread):
    for i in range(5):
        _async_raise(thread.ident, SystemExit)

# Use instead (stdlib, no existing in-repo analog — this is genuinely new infrastructure per D-09/D-10):
stop_event = threading.Event()
# ... loop checks stop_event.is_set() every iteration; thread.join(timeout=...) on shutdown
```

### Command dispatch (flat `if/elif` on `command_parts`)
**Source:** `Code/Server/server.py:141-207` (`receive_commands`), `Code/Server/control.py:139-218` (`condition_monitor`)
**Apply to:** `server.py`'s new `CMD_AUTO` branch, `behavior.py`'s internal state dispatch
```python
elif cmd.CMD_SONIC in command_parts:
    ...
elif cmd.CMD_HEAD in command_parts:
    if len(command_parts) == 3:
        ...
```
No routing table, no class hierarchy — flat conditional chain keyed on substring membership is this codebase's one and only established dispatch convention.

### Error handling — new code prefers `except Exception as e: print(f"...: {e}")`
**Source:** CLAUDE.md Error Handling section; live examples at `Code/Client/Main.py:551-552` (`connect()`), `Code/Server/led.py`-style modernized files
**Apply to:** every new file in `Code/Server/autonomy/`, the new `CMD_AUTO` branch in `server.py`, the new `Main.py` wiring
**Do NOT copy:** bare `except:` (dominant in `server.py`/`Client.py` legacy code) into any new autonomy code — CLAUDE.md explicitly singles this distinction out.

### Hardware-singleton reuse (never construct a second driver instance)
**Source:** `Code/Server/server.py:34-40` (`Server.__init__`); RESEARCH.md Pattern 1
**Apply to:** `perception.py`'s `SensorHub` (must take `server.ultrasonic_sensor`/`server.servo_controller` as constructor args)
Reason: `Ultrasonic()` claims GPIO pins 27/22 (`ultrasonic.py:13`); a second instance either fails to claim pins or produces two uncoordinated readers of the same hardware.

### Modernized-file commenting/docstring style
**Source:** `Code/Server/adc.py`, `Code/Server/buzzer.py`, `Code/Server/ultrasonic.py`
**Apply to:** all new `Code/Server/autonomy/*.py` files
```python
def read_battery_voltage(self) -> float:
    """Read the battery voltage using ADS7830."""
    battery1 = self.read_channel_voltage(0)                                   # Read the battery voltage from channel 0
    battery2 = self.read_channel_voltage(4)                                   # Read the battery voltage from channel 4
    return battery1,battery2
```
One-line `"""Summary."""` docstrings on methods (not classes/modules), heavy trailing `#` comments on nearly every line, type-hinted signatures where practical (`-> float`, `: bool`), 4-space indentation, no formatter.

### Self-test `__main__` block (Validation Architecture — no pytest, per CLAUDE.md)
**Source:** `Code/Server/ultrasonic.py:39-49`, `Code/Server/adc.py:50-59`, `Code/Server/buzzer.py:18-25`
**Apply to:** `perception.py`, `behavior.py` (RESEARCH.md's recommended standalone decision-logic self-check)
```python
if __name__ == '__main__':
    try:
        ...
    except KeyboardInterrupt:
        print("\nEnd of program")
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `Code/Server/autonomy/__init__.py` | module marker | n/a | No existing Python package (`__init__.py`) exists anywhere under `Code/Server/` — it is a flat module directory today; this is genuinely new project structure, not a pattern gap. Keep it empty/minimal per stdlib convention. |
| Bounded-runtime 5-minute timer construct | timer/service | event-driven | No existing in-repo timer of this shape (`Control`'s 10s idle-relax timeout is a different concern, explicitly not to be reused per RESEARCH.md's "Don't Hand-Roll" table) — use `time.monotonic()` per RESEARCH.md Standard Stack, no closer analog than the one already cited above. |

## Conventions

Convention derivation skipped (`no-readable-files` — the shared `gsd-tools verify conventions --derive` module scans JS/TS-family source files only; this is a pure-Python/PyQt5 project with zero `.js`/`.ts`/`.tsx`/`.jsx` files, so the deterministic scanner found nothing to analyze in either `Code/Server` scope or repo-wide scope).

In its place, the table below captures the equivalent axes as already documented, majority-vote style, in `CLAUDE.md`'s own Conventions section (derived by the codebase-analysis agents in an earlier session, not by this pattern-mapping pass):

| Axis | Dominant | Share (qualitative) | Status |
|------|----------|----------------------|--------|
| File-name casing (`Code/Server/`) | `snake_case.py` | Named contract — universal in `Code/Server/` (`adc.py`, `ultrasonic.py`, `servo.py`, `control.py`, ...) | Named contract |
| File-name casing (`Code/Client/`) | mixed `PascalCase.py` (class-matching) and `snake_case.py`/`ui_*.py` | Contested — `Main.py`/`Client.py`/`Command.py` vs. `ui_client.py`/`ui_led.py`/`ui_face.py` | Contested hotspot |
| Identifier casing (functions/locals) | `snake_case` | Named contract in modernized files (`adc.py`, `buzzer.py`, `camera.py`, `pca9685.py`); legacy files (`Client.py`, `Main.py`) mix in short/cryptic names | Named contract for new code; legacy carve-out acknowledged |
| Class casing | `PascalCase` | Named contract — universal (`Control`, `Servo`, `Camera`, `TCPServer`, `ADC`, `COMMAND`) | Named contract |
| Export/module style | Flat top-level classes, no `__init__.py` packages, no relative imports | Named contract — every `Code/Server/*.py` file imports siblings as bare module names (`from servo import Servo`), not package-relative | Named contract (new `autonomy/` package is the first departure — see No Analog Found) |
| Error handling (new code) | `except Exception as e: print(f"...: {e}")` | Contested — CLAUDE.md explicitly prefers this for new code, but bare `except:` remains the numeric majority across the existing codebase (`server.py`, `Client.py`) | Contested hotspot — new code must follow the named (CLAUDE.md-preferred) contract, not the numeric-majority legacy style |

**Contested hotspots (author's choice):** This project has no CJS/ESM-style dual-resolver split (it is pure Python), so the canonical "contested-by-design" example from other GSD projects doesn't directly apply here. The closest analogous, intentional split is the **Client vs. Server file-naming divergence** (`Code/Client/`'s mixed `PascalCase.py`/`ui_*.py` vs. `Code/Server/`'s uniform `snake_case.py`) and the **new-code-vs-legacy error-handling divergence** (CLAUDE.md's stated preference for new code vs. the numeric-majority bare-`except:` legacy style) — each half is internally consistent within its own directory/vintage, contested only when compared across the whole repo. Planners/executors should match the local directory's/file-vintage's established style rather than forcing repo-wide uniformity: new `Code/Server/autonomy/*.py` files follow `Code/Server/`'s `snake_case.py` + CLAUDE.md's preferred exception style; new `Code/Client/` widgets/handlers follow whichever of `Main.py`'s (legacy-tier) or `ui_client.py`'s (generated-tier) conventions applies to the specific file being touched.

## Metadata

**Analog search scope:** `Code/Server/` (all `.py` files), `Code/Client/` (`Main.py`, `Command.py`, `ui_client.py`), `Code/Server/ui_server.py`, plus targeted reads of `control.py`'s `condition_monitor`/`run_gait` and `Thread.py`
**Files scanned:** `Code/Server/server.py`, `Code/Server/main.py`, `Code/Server/control.py`, `Code/Server/ultrasonic.py`, `Code/Server/servo.py`, `Code/Server/buzzer.py`, `Code/Server/adc.py`, `Code/Server/command.py`, `Code/Server/Thread.py`, `Code/Server/imu.py` (partial), `Code/Client/Command.py`, `Code/Client/Main.py` (partial), `Code/Client/ui_client.py` (partial), `Code/Server/ui_server.py` (partial)
**Pattern extraction date:** 2026-08-07
