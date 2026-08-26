import time

from . import settings


def clamp_pan(angle):
    """Clamp a pan angle into the unattended-safe window [PAN_SAFE_MIN, PAN_SAFE_MAX]."""
    if angle < settings.PAN_SAFE_MIN:
        return settings.PAN_SAFE_MIN                      # below the safe window, clamp up
    if angle > settings.PAN_SAFE_MAX:
        return settings.PAN_SAFE_MAX                      # above the safe window, clamp down
    return angle                                           # already inside the safe window


class SensorHub:
    def __init__(self, ultrasonic_sensor, head_servo):
        """Wrap the Server's existing Ultrasonic/Servo singletons for no-echo-honest sensing."""
        self._ultrasonic = ultrasonic_sensor                # Server.ultrasonic_sensor — never construct a new sensor instance here
        self._servo = head_servo                            # Server.servo_controller — never construct a new servo instance here
        self._latest = (None, time.monotonic())            # (distance_cm_or_None, monotonic_timestamp), atomic tuple rebind
        self._original_read = None                          # set while the capture wrapper is installed, for restore in stop()

    def _to_cm(self, raw):
        """Convert gpiozero's raw [0.0, 1.0] echo fraction to centimeters; None stays None."""
        if raw is None:
            return None                                     # genuine unknown — never invent a value
        return round(raw * self._ultrasonic.max_distance * 100, 1)

    def _install_capture(self):
        """Idempotently splice into gpiozero's OWN polling thread instead of running a second one.

        gpiozero.DistanceSensor already runs a background GPIOQueue thread calling _read()
        continuously for the entire process lifetime (it backs the smoothed .distance property
        that CMD_SONIC/get_distance() rely on). A second thread calling _read() independently
        (the previous _poll_loop) fired the same trigger/echo pins on an uncoordinated schedule
        and corrupted nearly every reading. Wrapping the existing bound method lets gpiozero's
        thread remain the sole caller of real hardware _read() while we passively observe every
        result it already produces.
        """
        if self._original_read is not None:
            return                                          # already installed, do not double-wrap
        original_read = self._ultrasonic.sensor._read

        def _captured_read():
            value = original_read()
            try:
                self._latest = (self._to_cm(value), time.monotonic())
            except Exception as e:
                print(f"SensorHub: capture failed: {e}")
            return value                                     # unchanged, so gpiozero's own smoothing sees no difference

        self._original_read = original_read
        self._ultrasonic.sensor._read = _captured_read

    def _uninstall_capture(self):
        """Remove the instance-level override, so the wrapper never outlives this SensorHub
        and lookups fall back to gpiozero's own class-bound _read, exactly as before we wrapped."""
        if self._original_read is None:
            return                                          # not installed, nothing to restore
        del self._ultrasonic.sensor._read
        self._original_read = None

    def read_first_distance_cm(self, timeout=settings.FIRST_READ_TIMEOUT_SECONDS):
        """Bounded first read — waits for gpiozero's own thread to produce a fresh sample
        rather than calling _read() again ourselves (that would recreate the dual-poller bug)."""
        self._install_capture()
        started_at = time.monotonic()
        deadline = started_at + timeout
        while time.monotonic() < deadline:
            distance, timestamp = self._latest
            if timestamp >= started_at:
                return distance                             # fresh sample captured since we started waiting
            time.sleep(0.01)
        print("SensorHub: first distance read timed out")
        return None                                          # sensor never produced a first reading in time

    def center_head(self):
        """Center the pan servo, clamped into the unattended-safe window."""
        try:
            clamped = clamp_pan(settings.PAN_CENTER)
            self._servo.set_servo_angle(settings.PAN_CHANNEL, clamped)
        except Exception as e:
            print(f"SensorHub: center_head failed: {e}")

    def start(self):
        """Install the read-capture wrapper. No dedicated thread — gpiozero's own thread drives it."""
        self._install_capture()

    def stop(self):
        """Remove the read-capture wrapper, restoring gpiozero's untouched original _read."""
        self._uninstall_capture()

    def latest(self):
        """Return (distance_cm, age_seconds); distance is None if unknown or stale."""
        distance, timestamp = self._latest
        age = time.monotonic() - timestamp
        if distance is None or age > settings.SENSOR_STALE_SECONDS:
            return None, age                                # stale or never-known — never fall back to a stale value
        return distance, age


if __name__ == '__main__':
    from ultrasonic import Ultrasonic
    from servo import Servo

    ultrasonic_sensor = Ultrasonic()
    head_servo = Servo()
    hub = SensorHub(ultrasonic_sensor, head_servo)
    hub.start()
    try:
        while True:
            distance, age = hub.latest()
            print(f"distance={distance} age={age:.2f}s")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEnd of program")
    finally:
        hub.stop()
