import threading
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
        self._stop_event = threading.Event()
        self._poll_thread = None

    def read_raw_distance_cm(self):
        """Bypass Ultrasonic.get_distance()'s smoothing to get an honest no-echo signal."""
        try:
            # sensor._read() is a semi-private gpiozero method, verified against gpiozero 2.0.1:
            # it returns a float in [0.0, 1.0] on success or a genuine None on no-echo, bypassing
            # SmoothedInputDevice's ignore={None} filtering that silently swallows no-echo samples.
            raw = self._ultrasonic.sensor._read()
            if raw is None:
                return None                                 # genuine unknown — never invent a value
            return round(raw * self._ultrasonic.max_distance * 100, 1)
        except Exception as e:
            print(f"SensorHub: raw distance read failed: {e}")
            return None                                     # an errored read is unknown, not clear

    def read_first_distance_cm(self, timeout=settings.FIRST_READ_TIMEOUT_SECONDS):
        """Bounded first read — guards the boot-time case where gpiozero's queue never fills."""
        result = {}

        def _read():
            result['value'] = self.read_raw_distance_cm()

        reader_thread = threading.Thread(target=_read, daemon=True)
        reader_thread.start()
        reader_thread.join(timeout)
        if reader_thread.is_alive():
            print("SensorHub: first distance read timed out")
            return None                                     # sensor never produced a first reading in time
        return result.get('value')

    def center_head(self):
        """Center the pan servo, clamped into the unattended-safe window."""
        try:
            clamped = clamp_pan(settings.PAN_CENTER)
            self._servo.set_servo_angle(settings.PAN_CHANNEL, clamped)
        except Exception as e:
            print(f"SensorHub: center_head failed: {e}")

    def _poll_loop(self):
        """Background poller: refresh the latest (distance, timestamp) snapshot at SENSOR_POLL_HZ."""
        while not self._stop_event.is_set():
            distance = self.read_raw_distance_cm()
            self._latest = (distance, time.monotonic())     # atomic tuple rebind, matches command_queue's convention
            time.sleep(1.0 / settings.SENSOR_POLL_HZ)

    def start(self):
        """Start the background polling thread."""
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop(self):
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)

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
