# External Integrations

**Analysis Date:** 2026-08-06

## APIs & External Services

There are no third-party cloud APIs, SaaS services, or web APIs integrated in this codebase. All "external integrations" are local hardware peripherals and a custom point-to-point network protocol between the robot server and a desktop client. This is an embedded/robotics project, not a networked web application.

**Hardware Peripherals (I2C):**
- PCA9685 16-channel PWM servo driver - `Code/Server/pca9685.py`
  - Bus: I2C bus 1 via `smbus.SMBus(1)`, device address `0x40`
  - Used by: `Code/Server/servo.py` (leg/head servo angle control)
- ADS7830 8-channel ADC - `Code/Server/adc.py`
  - Bus: I2C bus 1, device address `0x48`
  - Used for: dual battery voltage monitoring (`read_battery_voltage`), reported to the client over the `CMD_POWER` command and used to trigger low-battery buzzer alerts (`Code/Server/server.py`)
- MPU6050 accelerometer/gyroscope - vendored driver `Code/Libs/mpu6050/mpu6050/mpu6050.py`
  - Integrated via `Code/Server/imu.py` (`IMU` class), combined with a custom `Kalman_filter` (`Code/Server/kalman.py`) for attitude estimation, consumed by `Code/Server/control.py` for balance/attitude commands (`CMD_BALANCE`, `CMD_ATTITUDE`)

**Hardware Peripherals (SPI):**
- SPI-based RGB LED strip driver - `Code/Server/spi_ledpixel.py` (`Freenove_SPI_LedPixel`), using `spidev`, selected for newer PCB versions (see `Code/Server/led.py` version-branching logic)

**Hardware Peripherals (GPIO / PWM):**
- WS281x/NeoPixel LED strip - `Code/Server/rpi_ledpixel.py` wraps vendored `rpi_ws281x` (`Code/Libs/rpi-ws281x-python/`), a compiled C extension talking to the Pi's PWM/PCM/SPI hardware for LED data, selected for older PCB/Pi combinations
- Ultrasonic distance sensor (HC-SR04-style) - `Code/Server/ultrasonic.py` via `gpiozero.DistanceSensor` (trigger pin 27, echo pin 22 by default)
- Servo power enable/disable line - `Code/Server/control.py` via `gpiozero.OutputDevice(4)`
- Buzzer - `Code/Server/buzzer.py` (GPIO-driven, toggled for low-battery alerts and the `CMD_BUZZER` command)

**Camera:**
- Raspberry Pi camera module - `Code/Server/camera.py` via `picamera2` (`Picamera2`, `libcamera.Transform`), streamed as MJPEG frames (`JpegEncoder`) or recorded as H264 (`H264Encoder`); supports `ov5647` and `imx219` sensor models, configured into `/boot/firmware/config.txt` by `Code/setup.py:config_camera_to_config_txt`

## Data Storage

**Databases:**
- None. No SQL/NoSQL database engine is used anywhere in the codebase.

**File Storage:**
- Local filesystem only:
  - `Code/Server/params.json` - PCB/Pi hardware version config (`Code/Server/parameter.py`)
  - `Code/Server/point.txt` / `Code/Client/point.txt` - leg calibration offsets (read/written in `Code/Server/control.py` and `Code/Client/Calibration.py`)
  - `Code/Client/IP.txt`, `Application/mac/IP.txt`, `Application/windows/IP.txt` - stored robot IP address for the desktop client
  - `Code/Client/Face/face.yml`, `Code/Client/Face/haarcascade_frontalface_default.xml`, `Code/Client/Face/name.txt` - face recognition model data and trained face labels loaded by `Code/Client/Face.py`

**Caching:**
- None.

## Authentication & Identity

**Auth Provider:**
- None. The TCP command/video sockets (`Code/Server/server.py`, `Code/Server/tcp_server.py`) accept any client that can reach the robot's IP/port on the local network — there is no authentication, pairing, or access-control mechanism. Security relies entirely on network isolation (same local Wi-Fi network).

## Monitoring & Observability

**Error Tracking:**
- None. Errors are handled with local `try/except` blocks and `print()` statements throughout (e.g. `Code/Server/server.py:send_data`, `Code/Server/camera.py:save_image`). No Sentry/Bugsnag/remote logging integration.

**Logs:**
- Console/stdout only via `print()`. No structured logging framework, no log files, no log shipping.

## CI/CD & Deployment

**Hosting:**
- Not applicable in the cloud-hosting sense — the "deployment target" is the Raspberry Pi itself, provisioned by running `Code/setup.py` directly on-device (installs system/vendored dependencies, edits `/boot/firmware/config.txt`, requires a manual reboot to finish).

**CI Pipeline:**
- None found. No `.github/workflows`, `.gitlab-ci.yml`, or other CI configuration in the repository.

## Environment Configuration

**Required "env vars":**
- None — this project does not use environment variables for configuration (see STACK.md Configuration section for the file-based config it uses instead: `params.json`, `point.txt`, `IP.txt`).

**Secrets location:**
- Not applicable. No API keys, tokens, or credentials are used anywhere in the codebase (no `.env`, credentials, or secret files were found or read).

## Webhooks & Callbacks

**Incoming:**
- None (no HTTP server/webhook receiver). The robot exposes two raw TCP sockets instead:
  - Video stream socket, port `8002` (`Code/Server/server.py:start_server`) - length-prefixed JPEG frames pushed to the connected client (`transmit_video`)
  - Command socket, port `5002` (`Code/Server/server.py:start_server`) - newline-delimited, `#`-separated text commands defined in `Code/Server/command.py` (`COMMAND` class: `CMD_MOVE`, `CMD_LED`, `CMD_LED_MOD`, `CMD_SONIC`, `CMD_BUZZER`, `CMD_HEAD`, `CMD_BALANCE`, `CMD_ATTITUDE`, `CMD_POSITION`, `CMD_RELAX`, `CMD_POWER`, `CMD_CALIBRATION`, `CMD_CAMERA`, `CMD_SERVOPOWER`), parsed and dispatched in `Code/Server/server.py:receive_commands`

**Outgoing:**
- The server pushes unsolicited responses back over the same command socket for `CMD_POWER` (battery voltage) and `CMD_SONIC` (ultrasonic distance) requests (`Code/Server/server.py:send_data`); this is a bespoke request/response protocol over a single TCP connection, not a webhook system.
- Client-to-server counterpart lives in `Code/Client/Client.py` (`turn_on_client`, `send_data`, `receive_data`, `receiving_video`), connecting to the robot's IP on the same two ports.

---

*Integration audit: 2026-08-06*
