# Coding Conventions

**Analysis Date:** 2026-08-06

## Overview

This is a Python-only hardware/robotics project (no JS/TS, no package.json). There is
**no linter, formatter, or style-config file anywhere in the repo** (`grep`/`find` for
`.flake8`, `pyproject.toml`, `setup.cfg`, `.pylintrc`, `.editorconfig` all return
nothing at the project root). Conventions below are inferred from reading actual
source files, not from tooling.

The codebase has two clearly distinguishable quality tiers:

1. **Modernized files** (recently rewritten, on Raspberry Pi 5 / PCA9685-v2 hardware
   path): `Code/Server/adc.py`, `Code/Server/buzzer.py`, `Code/Server/camera.py`,
   `Code/Server/pca9685.py`, `Code/Server/ultrasonic.py`, `Code/Server/servo.py`,
   `Code/Server/led.py`, `Code/Server/parameter.py`, `Code/Server/tcp_server.py`,
   `Code/Server/Thread.py`. These use type hints, docstrings, and consistent
   `snake_case`.
2. **Legacy files** (largely unmodified vendor/original Freenove code):
   `Code/Server/control.py`, `Code/Server/imu.py`, `Code/Server/server.py`, most of
   `Code/Client/*.py` (especially `Client.py`, `Main.py`, `Calibration.py`). These use
   no type hints, mixed naming, wildcard imports, and bare `except:` clauses.

**When adding new code, follow the modernized-file style** (see `adc.py`, `camera.py`,
`buzzer.py` as reference examples) even when editing inside a legacy file — do not
propagate the legacy anti-patterns.

## Naming Patterns

**Files:**
- Server-side files (`Code/Server/`): all lowercase, `snake_case.py` (e.g. `adc.py`,
  `tcp_server.py`, `rpi_ledpixel.py`, `spi_ledpixel.py`).
- Client-side files (`Code/Client/`): mixed — some `PascalCase.py` matching the class
  they define (`Client.py`, `Command.py`, `Face.py`, `Calibration.py`, `Main.py`,
  `PID.py`), some `lowercase.py` for UI-generated modules (`ui_client.py`,
  `ui_face.py`, `ui_led.py`, `point.txt`, `IP.txt`).
- `Thread.py` exists identically in both `Code/Server/` and `Code/Client/`.

**Classes:**
- `PascalCase` throughout: `Control`, `Servo`, `Camera`, `TCPServer`, `ADC`,
  `ParameterManager`, `IMU`, `Led`, `Buzzer`, `Ultrasonic`, `PCA9685`.
- A few classes use inconsistent casing inherited from the original codebase:
  `Kalman_filter` (`Code/Server/kalman.py`), `Incremental_PID`
  (`Code/Server/pid.py`, `Code/Client/PID.py`), `Freenove_RPI_WS281X`
  (`Code/Server/rpi_ledpixel.py`), `Freenove_SPI_LedPixel`
  (`Code/Server/spi_ledpixel.py`). Do not "fix" these names in unrelated changes —
  preserve them to avoid breaking imports; only rename in a dedicated refactor.
- Constant/enum-style classes are `SCREAMING_CASE` as a class name with class-level
  constants: `COMMAND` (`Code/Server/command.py`, `Code/Client/Command.py`) — a plain
  class used as a namespace of string constants, not an `Enum`.

**Functions/methods:**
- `snake_case` in Server code, e.g. `set_servo_angle`, `read_battery_voltage`,
  `get_interface_ip`, `calculate_posture_balance`.
- Client code (legacy tier) is inconsistent: `turn_on_client`, `is_valid_image_4_bytes`
  mixed with `receiving_video`, all still `snake_case` but with no spacing/PEP8
  discipline (see Code Style below).
- Private/internal helpers are prefixed with a single underscore in modernized files
  only, e.g. `_read_stable_byte` in `Code/Server/adc.py`. Legacy files do not use this
  convention (no private-method markers at all).

**Variables:**
- `snake_case` for locals and instance attributes in modernized files:
  `body_height`, `leg_positions`, `command_queue`, `is_support_led_function`.
- Legacy files mix short/cryptic names (`a`, `b`, `c`, `w`, `v`, `u`, `l1`, `l2`, `l3`
  in `Code/Server/control.py`'s `coordinate_to_angle`/`angle_to_coordinate` — these are
  inverse-kinematics variables named after the math, not descriptive) with verbose
  ones. New code should prefer descriptive names; math-heavy geometry code may keep
  short algebraic names if a comment nearby explains the formula.
- Command/protocol values are transmitted as strings, not typed constants:
  `self.status_flag = 0x01` (hex flag as int) but `self.command_queue[1] == "1"`
  (gait/flag values as string literals) — see `Code/Server/control.py`.

**Types:**
- No project-level type aliases or `TypedDict`/`dataclass` usage found. Data is passed
  as plain lists/dicts, e.g. `leg_positions = [[140, 0, 0], ...]` (6x3 nested list) and
  `accel_data['x']` (dict from `mpu6050` sensor library).

## Code Style

**Formatting:**
- No formatter (no Black/autopep8 config). Indentation is 4 spaces throughout.
- Modernized files (`adc.py`, `camera.py`, `buzzer.py`, `pca9685.py`) show a
  distinctive habit of **aligned trailing comments**, padded with spaces so the `#`
  column lines up across consecutive lines:
  ```python
  self.ADS7830_COMMAND = 0x84                                           # Set the command byte for ADS7830
  self.adc_voltage_coefficient = 3                                      # Set the ADC voltage coefficient based on the PCB version
  self.i2c_bus = smbus.SMBus(1)                                         # Initialize the I2C bus
  ```
  Match this style when editing those specific files; it is not used project-wide.
- Legacy files (`Code/Client/Client.py`, `Code/Client/Main.py`) frequently omit spaces
  around `=` in assignments and function calls: `self.face=Face()`,
  `self.tcp_flag=False`, `def turn_on_client(self,ip):`. Do not introduce this style in
  new code — use standard PEP 8 spacing (`self.face = Face()`).
- File encoding markers are inconsistent but common at the top of Server files:
  `# -*- coding: utf-8 -*-` (`control.py`, `server.py`, `led.py`) vs `# coding:utf-8`
  (`servo.py`, `imu.py`). Either is acceptable; prefer `# -*- coding: utf-8 -*-` for
  new files to match the majority.

**Linting:**
- No linter configured or run. No CI pipeline exists (no `.github/workflows/`).

## Import Organization

**Order:** No enforced convention. Typical pattern in modernized files is: stdlib
imports first, then local project imports, e.g. `Code/Server/led.py`:
```python
import time
from parameter import ParameterManager
from rpi_ledpixel import Freenove_RPI_WS281X
from spi_ledpixel import Freenove_SPI_LedPixel
```
`Code/Server/control.py` mixes stdlib, third-party, and local without grouping/blank
lines:
```python
import time
import math
import copy
import threading
import numpy as np
from gpiozero import OutputDevice

from pid import Incremental_PID
from command import COMMAND as cmd
from imu import IMU
from servo import Servo
```

**Wildcard imports:** Present in legacy Client code — avoid in new code:
```python
# Code/Client/Client.py
from PID import *
from Face import *
from Thread import *
```

**Aliasing:** `COMMAND` is consistently aliased to `cmd` at import time on both
Server and Client: `from command import COMMAND as cmd` /
`from Command import COMMAND as cmd`. Follow this alias when referencing protocol
constants.

**No path aliases / no package `__init__.py`** — `Code/Server/` and `Code/Client/`
are flat script directories, not installable packages. Modules import each other by
bare module name, relying on the script's own directory being on `sys.path` (i.e. you
must run scripts from within `Code/Server/` or `Code/Client/`).

## Error Handling

**Dominant pattern: broad or bare `except`.** 16 bare `except:` clauses and 37
`except Exception` clauses across Server+Client (excluding vendored libs in
`Code/Libs/`). Typical shapes:
```python
# Bare except swallowing everything, Code/Server/server.py
try:
    self.video_connection.close()
    self.command_connection.close()
except:
    print('\n' + "No client connection")
```
```python
# Broad Exception with print-only handling, Code/Server/camera.py
try:
    metadata = self.camera.capture_file(filename)
    return metadata
except Exception as e:
    print(f"Error capturing image: {e}")
    return None
```
- New/modernized code should still prefer `except Exception as e: print(f"...: {e}")`
  over bare `except:` — this is the better half of the existing pattern and is used
  consistently in `adc.py`, `camera.py`, `parameter.py`.
- One file demonstrates **precise errno-based handling** and should be treated as the
  best-practice example in this codebase — `Code/Server/tcp_server.py`:
  ```python
  except OSError as e:
      if e.errno == 9 or e.errno == 32:
          # Handle broken pipe errors
          client_address = self.client_sockets[s]
          print(client_address, "disconnected")
          self.remove_client(s)
      else:
          print(f"Unexpected error: {e}")
  ```
- Hardware-facing scripts use `try/except KeyboardInterrupt` around their
  `if __name__ == '__main__':` demo loop to leave hardware in a safe state on Ctrl-C
  (turn off LEDs/buzzer, relax servos). This is a strong repo-wide convention for any
  new `__main__` hardware test block:
  ```python
  # Code/Server/led.py
  try:
      ...
      led.color_wipe([0, 0, 0], 10)
  except KeyboardInterrupt:
      led.color_wipe([0, 0, 0], 10)
  finally:
      print("\nEnd of program")
  ```
- No custom exception classes are defined anywhere in the project. Errors are either
  printed and swallowed, or allowed to propagate as built-in exceptions.
- `Code/Server/imu.py` has one custom pattern worth reusing for I2C failures —
  `handle_exception` prints the error, shells out to `i2cdetect -y 1` for diagnostics,
  then re-raises:
  ```python
  def handle_exception(self, exception):
      print(exception)
      os.system("i2cdetect -y 1")
      raise exception
  ```

## Logging

**No logging framework** — `import logging` does not appear anywhere in
`Code/Server/` or `Code/Client/`. All diagnostics use `print()`, frequently with
`f"..."` f-strings in modernized files and `str()` concatenation
(`"text" + str(value) + "text"`) in legacy files:
```python
# modernized (Code/Server/adc.py)
print(f"Device found at address: 0x{device:02X}")

# legacy (Code/Server/test.py)
print ("Obstacle distance is "+str(data)+"CM")
```
New code should use f-strings and `print()` — there is no logging infrastructure to
plug into.

## Comments

**When to comment:**
- Modernized files comment nearly every line with a trailing `#` explanation
  (see Code Style above) — this is heavier than typical Python style but is the
  established local convention for hardware-interfacing code (`adc.py`, `camera.py`,
  `pca9685.py`, `buzzer.py`, `ultrasonic.py`).
- Legacy files comment sparingly, mostly as section dividers for repetitive blocks:
  ```python
  # Leg 1
  self.servo.set_servo_angle(15, self.current_angles[0][0])
  ...
  # Leg 2
  self.servo.set_servo_angle(12, self.current_angles[1][0])
  ```
  (`Code/Server/control.py`, repeated for all 6 legs in `set_leg_angles` and
  `transform_coordinates`).
- Commented-out debug `print` statements are left in place rather than deleted, e.g.
  `# print(f"{param_name} set to {value}")` in `Code/Server/parameter.py`,
  `# print("send",data)` in `Code/Server/server.py`. This is tolerated existing
  practice but should not be imitated in new code — remove dead code instead.

**Docstrings:**
- Present only in modernized files, one-line `"""Summary."""` style at the top of
  each method body, occasionally with `:param:` Sphinx-style tags for public API
  methods with multiple parameters:
  ```python
  # Code/Server/servo.py
  def set_servo_angle(self, channel, angle):
      """
      Convert the input angle to the value of PCA9685 and set the servo angle.

      :param channel: Servo channel (0-31)
      :param angle: Angle in degrees (0-180)
      """
  ```
- No module-level docstrings anywhere in the project.
- No class-level docstrings — only `__init__` methods get a one-liner in modernized
  files, e.g. `"""Initialize the ADC class."""`.

## Function Design

**Size:** No enforced limit. Ranges from tiny one-liners (`map_value`) to very large
methods — `Code/Server/control.py`'s `run_gait` is ~80 lines with deeply nested
`if`/`elif` gait-phase logic, and `condition_monitor` is ~85 lines dispatching on
`command_queue` contents. New command-dispatch code should prefer extracting a
per-command handler method rather than growing `condition_monitor` further, but no
such extraction currently exists in the codebase — the pattern as-is is a single large
dispatcher.

**Parameters:**
- Positional parameters dominate; keyword defaults used for tunable numeric constants,
  e.g. `def run_gait(self, data, Z=40, F=64):`, `def color_wipe(self, color,
  wait_ms=50):`. Modernized files add type hints to parameters:
  `def read_channel_voltage(self, channel: int) -> float:`.
- Protocol/command data is passed as a raw list of strings (`data`), then indexed and
  `int()`-cast inline (`int(data[2])`) rather than parsed into a typed structure — see
  `run_gait`, `condition_monitor` in `control.py`. Follow this existing pattern for
  consistency with the wire protocol rather than introducing a new parsing layer
  unless doing a larger refactor.

**Return values:**
- Multi-value returns use plain tuples, not named tuples/dataclasses:
  `return round(math.degrees(a)), round(math.degrees(b)), round(math.degrees(c))`
  (`Code/Server/control.py`), `return self.pitch_angle, self.roll_angle,
  self.yaw_angle` (`Code/Server/imu.py`).
- Functions that can fail return `None` on failure rather than raising, e.g.
  `save_image` in `Code/Server/camera.py` returns `None` and prints an error instead
  of propagating the exception.

## Module Design

**Exports:** No `__all__` declarations anywhere. Everything at module scope is
importable; consumers import specific names (`from led import Led`) rather than the
whole module.

**Structure:** One primary class per file, named to match the filename
(`servo.py` → `Servo`, `camera.py` → `Camera`). Every Server/Client module ends with
an `if __name__ == '__main__':` block used as a standalone hardware smoke-test/demo
for that module — this is a strict repo-wide convention. When adding a new
hardware-facing module, include a `__main__` block that exercises the class
end-to-end with a `KeyboardInterrupt`-safe cleanup path.

**Barrel files:** Not applicable — no `__init__.py` package structure exists.

## Protocol/Command Conventions

- Commands are `#`-delimited strings terminated with `\n`, e.g.
  `cmd.CMD_POWER + "#" + str(battery_voltage[0]) + "#" + str(battery_voltage[1]) +
  "\n"` (`Code/Server/server.py`). New command handling should follow this same
  `CMD_NAME#arg1#arg2\n` shape and add the constant to both
  `Code/Server/command.py` and `Code/Client/Command.py` (kept in sync manually — there
  is no shared/generated source of truth).
- Command dispatch in `Code/Server/server.py::receive_commands` and
  `Code/Server/control.py::condition_monitor` uses `if cmd.CMD_X in command_parts:`
  membership checks against a small list, not a dict-based dispatch table. Follow this
  pattern for new commands rather than introducing a dispatch dict, to stay consistent
  with the rest of the chain.

---

*Convention analysis: 2026-08-06*
