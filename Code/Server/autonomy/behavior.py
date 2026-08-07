import threading
import time

from . import settings

BLOCKED = "BLOCKED"
CLEAR = "CLEAR"


def decide(distance_cm):
    """Pure walk/stop decision: unknown or close-range readings are always BLOCKED."""
    if distance_cm is None or distance_cm < settings.STOP_THRESHOLD_CM:
        return BLOCKED                                      # unknown/close is never treated as clear
    return CLEAR


class AutoModeController:
    def __init__(self, control_system, sensor_hub, status_callback=None):
        """Own the auto_mode_active arbitration gate and the walk/stop decision loop."""
        self._control_system = control_system                # existing Control singleton, reused as-is
        self._sensor_hub = sensor_hub                         # SensorHub wrapping the existing Ultrasonic/Servo
        self._status_callback = status_callback               # fired with True/False on every state change
        self.auto_mode_active = threading.Event()            # the single arbitration gate manual preempt clears
        self._worker_thread = None
        self._deadline = 0.0
        self._settle_on_exit = True
        self._last_intent = None                             # cached last-emitted intent, avoids twitchy rebinds
        self._last_queue_ref = None                          # tracks whether condition_monitor reset the queue

    def start(self):
        """Arm the bounded-runtime deadline and spawn the decision loop. No-op if already running."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return False                                      # already running, nothing to do
        self._sensor_hub.center_head()
        first_reading = self._sensor_hub.read_first_distance_cm()
        print(f"AutoModeController: first distance reading = {first_reading}")
        self._sensor_hub.start()
        self._deadline = time.monotonic() + settings.AUTO_RUN_SECONDS  # server-side, never reset by client traffic (D-02)
        self._settle_on_exit = True
        self._last_intent = None
        self._last_queue_ref = None
        self.auto_mode_active.set()
        self._worker_thread = threading.Thread(target=self._run, daemon=True)
        self._worker_thread.start()
        if self._status_callback is not None:
            self._status_callback(True)
        return True

    def stop(self, settle=True):
        """Explicit stop path (CMD_AUTO#0) — cooperative, joins the worker before returning."""
        self._settle_on_exit = settle
        self.auto_mode_active.clear()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
        self._sensor_hub.stop()

    def preempt(self):
        """Manual-override path (D-10) — clears the gate and returns immediately, never blocks."""
        self._settle_on_exit = False                         # a human command is now authoritative, no settle write
        self.auto_mode_active.clear()

    def is_active(self):
        """True while the decision loop is running and permitted to write commands."""
        return self.auto_mode_active.is_set()

    def _forward_intent(self):
        return ['CMD_MOVE', settings.WALK_GAIT, '0', str(settings.WALK_STEP_Y), str(settings.WALK_SPEED), '0']

    def _halt_intent(self):
        # x=0,y=0 makes run_gait short-circuit to transform_coordinates + set_leg_angles — a stable stance, not a freeze.
        return ['CMD_MOVE', settings.WALK_GAIT, '0', '0', str(settings.WALK_SPEED), '0']

    def _run(self):
        """The decision loop: sense, decide, emit, at LOOP_HZ, until the gate clears or the deadline hits."""
        while self.auto_mode_active.is_set():
            try:
                if time.monotonic() >= self._deadline:
                    self._settle_on_exit = True               # bounded-runtime halt still settles (D-09)
                    self.auto_mode_active.clear()
                    break
                distance_cm, _age_seconds = self._sensor_hub.latest()
                state = decide(distance_cm)
                if state == BLOCKED:
                    self._emit(self._halt_intent())
                else:
                    self._emit(self._forward_intent())
                time.sleep(1.0 / settings.LOOP_HZ)
            except Exception as e:
                print(f"AutoModeController: decision loop error, stopping: {e}")
                self._settle_on_exit = True                   # fail safe: stop and settle, never keep walking blind
                self.auto_mode_active.clear()
                break
        if self._settle_on_exit:
            self._write_intent_unconditional(self._halt_intent())  # gate is clear by definition here
        self._sensor_hub.stop()
        self._sensor_hub.center_head()
        if self._status_callback is not None:
            self._status_callback(False)

    def _emit(self, intent_list):
        """Write an intent, gated by auto_mode_active, without restarting the gait animation needlessly."""
        if not self.auto_mode_active.is_set():
            return                                            # gate cleared between decide() and here — do not write
        same_content = self._last_intent == intent_list
        same_queue_object = self._control_system.command_queue is self._last_queue_ref
        if not (same_content and same_queue_object):
            self._control_system.command_queue = intent_list
            self._last_intent = intent_list
            self._last_queue_ref = self._control_system.command_queue
        self._control_system.timeout = time.time()             # keep condition_monitor's 10s idle-relax from firing

    def _write_intent_unconditional(self, intent_list):
        """Write the settle-on-exit intent once, bypassing the gate (already clear by the time this runs)."""
        self._control_system.command_queue = intent_list
        self._control_system.timeout = time.time()


if __name__ == '__main__':
    test_cases = [
        (None, BLOCKED),
        (19.9, BLOCKED),
        (21.0, CLEAR),
        (0.0, BLOCKED),
    ]
    all_passed = True
    for distance_cm, expected in test_cases:
        actual = decide(distance_cm)
        passed = actual == expected
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"{status}: decide({distance_cm}) -> {actual} (expected {expected})")
    if not all_passed:
        raise SystemExit(1)
