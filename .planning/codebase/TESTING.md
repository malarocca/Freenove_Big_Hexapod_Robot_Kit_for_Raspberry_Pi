# Testing Patterns

**Analysis Date:** 2026-08-06

## Test Framework

**Runner:** None. There is no `pytest`, `unittest`, `nose`, or any other test runner
configured or installed for the first-party code (`Code/Server/`, `Code/Client/`).
`python3 -c "import pytest"` fails on this machine, and no `pytest.ini`, `tox.ini`,
`conftest.py`, `pyproject.toml`, or `setup.cfg` exists at the project root or under
`Code/`.

**Assertion library:** None used in first-party code — no `assert` statements appear
in `Code/Server/` or `Code/Client/` outside of vendored third-party libraries.

**Run commands:** There is no automated "run all tests" command for this project.
The closest equivalent is running individual hardware modules directly, e.g.:
```bash
cd Code/Server
python3 test.py Led          # manually observe LED strip behavior
python3 test.py Ultrasonic   # manually read printed distance values
python3 test.py Servo        # manually watch servos sweep
python3 test.py ADC          # manually read printed battery voltage
python3 test.py Buzzer       # manually listen for buzzer beeps
```
or running any module's own `if __name__ == '__main__':` block directly, e.g.
`python3 camera.py`, `python3 led.py`, `python3 adc.py`.

**Important distinction — vendored test suite exists but is out of scope:**
`Code/Libs/rpi-ws281x-python/library/tests/` contains a real `pytest`-based suite
(`test_setup.py`, `conftest.py`) for the vendored `rpi-ws281x-python` dependency. This
is third-party library code checked into `Code/Libs/`, not project test infrastructure
— it should not be treated as a pattern to extend for `Code/Server/`/`Code/Client/`
code, and it does not exercise any of this project's own modules.

## Why there is no automated test suite

This project is hardware-integration code for a Raspberry Pi driving physical
actuators (18 servos), sensors (IMU/MPU6050, ultrasonic, ADC/battery), and
peripherals (WS281x LEDs, buzzer, camera) over I2C/SPI/GPIO. Nearly every class
(`Code/Server/servo.py::Servo`, `Code/Server/adc.py::ADC`,
`Code/Server/imu.py::IMU`, `Code/Server/camera.py::Camera`, etc.) instantiates a
hardware driver directly in `__init__` (e.g. `smbus.SMBus(1)`, `mpu6050(address=0x68,
bus=1)`, `Picamera2()`, `gpiozero.OutputDevice(4)`), so importing/instantiating these
classes on non-Pi hardware, or without the physical device attached, raises at
construction time. None of the classes accept an injectable driver/interface, so there
is currently no seam for mocking hardware access in unit tests.

## Existing "Test" Pattern: Manual Hardware Verification Scripts

**Location:** `Code/Server/test.py`

**Structure:** A flat script with one `test_<Device>()` function per peripheral,
selected via a CLI argument, not via a test runner or `assert`. Verification is done
by the human operator watching/listening to the hardware, not by a pass/fail
assertion. Example (`Code/Server/test.py`):
```python
def test_Led():
    from led import Led
    led = Led()
    try:
        print ("\nRed wipe")
        led.color_wipe([255, 0, 0])
        time.sleep(1)
        ...
        led.color_wipe([0, 0, 0])   #turn off the light
        print ("\nEnd of program")
    except KeyboardInterrupt:
        led.color_wipe([0, 0, 0])   #turn off the light
        print ("\nEnd of program")

if __name__ == '__main__':
    print ('Program is starting ... ')
    import sys
    if len(sys.argv) < 2:
        print ("Parameter error: Please assign the device")
        exit()
    if sys.argv[1] == 'Led':
        test_Led()
    elif sys.argv[1] == 'Ultrasonic':
        test_Ultrasonic()
    ...
```

**Naming:** `test_<PascalCaseDeviceName>()` — note this does not match `pytest`
discovery conventions in a way that would let `pytest` collect/run these usefully
(each function performs an infinite loop or `time.sleep`-gated hardware sequence and
never asserts anything), so this file cannot simply be pointed at `pytest`.

**Cleanup pattern:** Every `test_*` function wraps its body in
`try: ... except KeyboardInterrupt: <cleanup>` so Ctrl-C leaves hardware in a safe
state (LEDs off, buzzer off, servos relaxed). Any new manual verification script
should follow this same shape.

## Per-Module Smoke Tests (`if __name__ == '__main__':`)

**Location:** Nearly every file in `Code/Server/` and several in `Code/Client/`.

**Pattern:** Each module is independently runnable and exercises its own class
end-to-end against real hardware, printing results for manual inspection. This is the
dominant "testing" convention in the codebase — treat it as the pattern to follow when
adding a new hardware-facing module. Example (`Code/Server/adc.py`):
```python
if __name__ == '__main__':
    print("start .. \n")
    adc = ADC()
    try:
        while True:
            power = adc.read_battery_voltage()
            print ("The battery voltage is "+str(power)+'\n')
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEnd of program")
        adc.close_i2c()
```
Similar blocks exist in `Code/Server/servo.py`, `Code/Server/led.py`,
`Code/Server/camera.py`, `Code/Server/imu.py`, `Code/Server/tcp_server.py` (starts a
real TCP echo server on port 12345), `Code/Server/ultrasonic.py`,
`Code/Server/buzzer.py`, `Code/Server/parameter.py`.

## Mocking

**Framework:** None (`unittest.mock` / `pytest-mock` not used anywhere in first-party
code).

**What would need to be mocked to unit test this code:** `smbus.SMBus`, `mpu6050`,
`gpiozero.OutputDevice`, `Picamera2`, PWM chip access in
`Code/Server/pca9685.py`, and the WS281x drivers
(`Code/Server/rpi_ledpixel.py`, `Code/Server/spi_ledpixel.py`) — all instantiated
directly inside constructors with no dependency-injection seam. Introducing real unit
tests would first require refactoring these classes to accept an injectable driver
(e.g. pass an `smbus`-like object into `ADC.__init__` instead of constructing it
internally).

## Fixtures and Factories

Not applicable — no fixture/factory infrastructure exists for first-party code.

## Coverage

**Requirements:** None enforced. No coverage tool (`coverage.py`, `pytest-cov`)
referenced anywhere in the repo.

## Test Types

**Unit tests:** None.

**Integration tests:** None in the automated sense. The `Code/Server/test.py` script
and per-module `__main__` blocks function as manual integration checks against real
attached hardware.

**E2E tests:** None. End-to-end verification is done manually by running the full
`Code/Server/main.py` server on the robot and the `Code/Client/Main.py` PyQt desktop
client, then visually/physically confirming the robot responds (documented in
`README.md`, not automated).

## Guidance for Adding New Code

When a future phase adds testable pure-logic code (e.g. math in
`Code/Server/control.py`'s `coordinate_to_angle`/`angle_to_coordinate`, or protocol
parsing in `Code/Server/server.py`/`Code/Client/Client.py`), there is no existing
convention to match — introducing `pytest` with `assert`-based unit tests for such
pure functions (which do not touch hardware) would be a reasonable, additive first
step, since `coordinate_to_angle`, `angle_to_coordinate`, `restrict_value`,
`map_value`, and `calculate_posture_balance` in `Code/Server/control.py` are pure
functions with no hardware I/O and are natural candidates for the first real unit
tests in this repo. Any such addition should be called out explicitly since it
establishes a new pattern rather than following an existing one.

---

*Testing analysis: 2026-08-06*
