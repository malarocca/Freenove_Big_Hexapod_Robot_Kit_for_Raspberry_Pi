# Technology Stack

**Analysis Date:** 2026-08-06

## Languages

**Primary:**
- Python 3 (developed/run against Python 3.13.5 on the target Raspberry Pi OS install) - all robot server code (`Code/Server/*.py`), desktop client code (`Code/Client/*.py`), and bundled hardware libraries (`Code/Libs/`)

**Secondary:**
- C - native extension source for the WS281x LED driver, compiled via a Python C extension (`Code/Libs/rpi-ws281x-python/library/*.c`, `Code/Libs/rpi-ws281x-python/library/lib/`)
- Shell/Bash - install helper invoked via `subprocess`/`os.system` calls in `Code/setup.py`

There is no JavaScript/TypeScript, no web frontend, and no build-tool-managed frontend stack. Desktop UIs are native PyQt5 apps; `Application/windows/windows.exe` and `Application/mac/mac` are pre-built (compiled) client binaries checked into the repo, not built from source in this repository.

## Runtime

**Environment:**
- Raspberry Pi OS (Debian-based; observed dev environment is Debian 13 "trixie") running on Raspberry Pi hardware (Pi 3, Pi 4/generic, and Pi 5 are all explicitly detected/handled — see `Code/Server/parameter.py:get_raspberry_pi_version` and `Code/setup.py:get_raspberry_pi_version`)
- Python 3.13.5 observed on the dev/target machine; `Code/Libs/mpu6050/setup.py` still declares Python 2.7 classifier compatibility (legacy metadata, not enforced) while `Code/Libs/rpi-ws281x-python/library/setup.py` declares `python_requires >= 3.6`
- Client-side desktop app (`Code/Client/`) is intended to run on a separate PC (Windows/macOS/Linux) with PyQt5, connecting to the robot over TCP/Wi-Fi

**Package Manager:**
- pip3 (invoked via `sudo pip3 install {package}` in `Code/setup.py:check_and_install`)
- apt / apt-get for system packages (`Code/setup.py:apt_install`, e.g. `libqt5gui5 python3-dev python3-pyqt5`)
- No lockfile present (no `requirements.txt`, `Pipfile.lock`, or `poetry.lock`); dependencies are installed ad hoc by `Code/setup.py` and via manual `setup.py install` of vendored libraries

## Frameworks

**Core:**
- PyQt5 - desktop GUI framework for both the on-robot control panel (`Code/Server/ui_server.py`, `Code/Server/main.py`) and the remote control client (`Code/Client/ui_client.py`, `Code/Client/ui_face.py`, `Code/Client/ui_led.py`). UI modules are Qt Designer-generated (`# Created by: PyQt5 UI code generator 5.11.3`) and must not be hand-edited per their own header warnings.
- picamera2 - Raspberry Pi camera stack (`Code/Server/camera.py`), used with `libcamera.Transform`, `H264Encoder`/`JpegEncoder`, `FileOutput`
- gpiozero - GPIO abstraction for ultrasonic sensor and servo-power output (`Code/Server/ultrasonic.py`, `Code/Server/control.py`)
- OpenCV (`cv2`) - video frame decoding on the client and face detection/recognition (`Code/Client/Client.py`, `Code/Client/Face.py` uses `cv2.face.LBPHFaceRecognizer_create()` and `cv2.CascadeClassifier`, requiring `opencv-contrib-python`)

**Testing:**
- No automated test framework (no pytest/unittest suite found). `Code/Server/test.py` is a manual, interactive hardware smoke-test script (`test_Led`, `test_Ultrasonic`, etc.), not an automated test suite.

**Build/Dev:**
- `setuptools` - used to build/install the two vendored native/Python libraries: `Code/Libs/mpu6050/setup.py` (pure Python, MIT) and `Code/Libs/rpi-ws281x-python/library/setup.py` (C extension `_rpi_ws281x`, compiled per-target as seen in `Code/Libs/rpi-ws281x-python/library/build/lib.linux-aarch64-cpython-313/`)
- `Code/setup.py` - top-level install orchestrator: runs `apt-get update`, installs vendored libs via `python3 setup.py install`, installs `libqt5gui5 python3-dev python3-pyqt5` via apt, and edits `/boot/firmware/config.txt` (enables SPI, configures camera overlay, disables audio on Pi 3) — this is provisioning/bootstrap code, not a Python packaging build for this project itself.

## Key Dependencies

**Critical:**
- `smbus` - I2C bus communication with the PCA9685 PWM driver (`Code/Server/pca9685.py`) and ADS7830 ADC (`Code/Server/adc.py`)
- `spidev` - SPI communication for LED strips on newer PCB/Pi versions (`Code/Server/spi_ledpixel.py`)
- `numpy` - vector/array math for LED color buffers, IMU math, and image frame handling (`Code/Server/spi_ledpixel.py`, `Code/Server/control.py`, `Code/Client/Client.py`)
- `mpu6050` (vendored, `Code/Libs/mpu6050`) - accelerometer/gyroscope driver used by `Code/Server/imu.py` alongside a custom `Kalman_filter` (`Code/Server/kalman.py`) for orientation fusion
- `rpi_ws281x` (vendored, `Code/Libs/rpi-ws281x-python`) - low-level WS281x/NeoPixel LED strip driver used by `Code/Server/rpi_ledpixel.py`

**Infrastructure:**
- `PIL` (Pillow) - image handling on the client (`Code/Client/Client.py`, `Code/Client/Face.py`)
- `multiprocessing`, `threading`, `queue` (stdlib) - concurrency for video streaming, command handling, and LED animation threads (`Code/Server/server.py`, `Code/Server/tcp_server.py`, `Code/Client/Client.py`)
- `ctypes`, `inspect` (stdlib) - used by the custom thread-kill utility (`Code/Server/Thread.py`, `Code/Client/Thread.py`) to forcibly terminate long-running threads

## Configuration

**Environment:**
- No `.env`/environment-variable-based configuration. Hardware/runtime configuration is file-based:
  - `Code/Server/params.json` - stores `Pcb_Version` and `Pi_Version`, read/written by `Code/Server/parameter.py:ParameterManager` (interactive prompt on first run/mismatch)
  - `Code/Server/point.txt` / `Code/Client/point.txt` - calibration leg-position offsets, read by `Control.read_from_txt` in `Code/Server/control.py`
  - `Code/Client/IP.txt` (and `Application/*/IP.txt`) - plain-text robot IP address the desktop client connects to
- `/boot/firmware/config.txt` on the Pi is modified directly by `Code/setup.py` (`config_file()`) to enable SPI (`dtparam=spi=on`), select the camera overlay (`ov5647`/`imx219`), and (on Pi 3) disable onboard audio

**Build:**
- `Code/Libs/mpu6050/setup.py`, `Code/Libs/rpi-ws281x-python/library/setup.py` - `setuptools`-based build/install scripts for vendored dependencies
- No `pyproject.toml`, no `tsconfig.json`/`package.json` (not applicable — pure Python/embedded project)

## Platform Requirements

**Development:**
- Any machine with Python 3 + PyQt5 to run/edit the Client desktop app (`Code/Client/`); no Pi hardware required for pure UI/protocol work, but hardware-dependent server code (I2C/SPI/GPIO/camera) can only run on a Raspberry Pi
- OpenCV with the `cv2.face` contrib module (`opencv-contrib-python`) is required for face recognition features on the client

**Production:**
- Raspberry Pi (3, 4, or 5) running Raspberry Pi OS / Debian, with camera module, PCA9685 servo driver, ADS7830 ADC, MPU6050 IMU, ultrasonic sensor, and WS281x/SPI LED strip attached via I2C/SPI/GPIO as wired per the hexapod hardware kit
- Server process (`Code/Server/main.py`) launched on the Pi; opens two TCP sockets on the Pi's `wlan0` IP — port `8002` for video streaming and `5002` for command/telemetry (`Code/Server/server.py`)
- Remote client (`Code/Client/Main.py`) run on a separate PC/laptop on the same network, connecting to the robot's IP (from `IP.txt`) on those same ports

---

*Stack analysis: 2026-08-06*
