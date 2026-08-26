import csv
import statistics
import sys
import threading
import time

sys.path.insert(0, "/home/pi/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/Code/Server")

import VL53L1X
from ultrasonic import Ultrasonic

LOG_PATH = "contention_log.csv"
PHASE_SECONDS = 15


class UltrasonicCapture:
    """Replicates the worktree's SensorHub._install_capture pattern (commit 12a7fda,
    Code/Server/autonomy/perception.py): piggyback on gpiozero's OWN background polling
    thread instead of running a second independent poller against the same GPIO pins --
    that second-poller pattern is exactly what caused the original dual-poller bug this
    spike is re-testing for, now with a second I2C sensor in the mix instead of a second
    GPIO poller."""

    def __init__(self, ultrasonic):
        self._ultrasonic = ultrasonic
        self._latest = (None, 0.0)
        self._count = 0
        self._original_read = None

    def install(self):
        original_read = self._ultrasonic.sensor._read

        def _captured_read():
            value = original_read()
            ts = time.monotonic()
            cm = None if value is None else round(value * self._ultrasonic.max_distance * 100, 1)
            self._latest = (cm, ts)
            self._count += 1
            return value

        self._original_read = original_read
        self._ultrasonic.sensor._read = _captured_read

    def uninstall(self):
        if self._original_read is not None:
            del self._ultrasonic.sensor._read
            self._original_read = None

    def latest(self):
        return self._latest


def run_phase(name, capture, writer, f):
    print(f"\n--- Phase: {name} ---")
    input("Aim both sensors at the SAME fixed target (don't move it between phases) and press Enter...")
    start_count = capture._count
    samples = []
    t_end = time.time() + PHASE_SECONDS
    while time.time() < t_end:
        cm, ts = capture.latest()
        samples.append(cm)
        writer.writerow([f"{ts:.3f}", name, cm])
        f.flush()
        time.sleep(0.1)
    end_count = capture._count
    reads_in_phase = end_count - start_count
    rate = reads_in_phase / PHASE_SECONDS
    nums = [s for s in samples if s is not None]
    if nums:
        print(f"  ultrasonic gpiozero-thread: internal_reads/sec={rate:.1f} "
              f"observed_n={len(nums)} min={min(nums)} max={max(nums)} "
              f"mean={statistics.mean(nums):.1f} stdev={statistics.pstdev(nums):.2f}")
    else:
        print(f"  ultrasonic gpiozero-thread: internal_reads/sec={rate:.1f} observed_n=0 (all None)")
    return rate, nums


def tof_poll_loop(tof, stop_event, results):
    while not stop_event.is_set():
        d = tof.get_distance()
        status = tof.get_range_status_string()
        results.append((time.monotonic(), d, status))
        time.sleep(0.05)


def main():
    ultrasonic = Ultrasonic()
    capture = UltrasonicCapture(ultrasonic)
    capture.install()

    tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
    tof.open(reset=True)  # required -- spike 001
    tof.start_ranging(2)  # medium mode -- spike 001/002
    tof.set_timing(140000, 150)  # 140ms budget -- spike 002

    print("Dual-sensor contention test: A/B compare ultrasonic's own background-thread")
    print("read rate/stability with vs. without a concurrent VL53L1X polling thread.")
    print(f"Logging ultrasonic readings to {LOG_PATH}.\n")

    try:
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "phase", "ultrasonic_cm"])

            rate_a, nums_a = run_phase("A_ultrasonic_alone", capture, writer, f)

            stop_event = threading.Event()
            tof_results = []
            t = threading.Thread(target=tof_poll_loop, args=(tof, stop_event, tof_results), daemon=True)
            t.start()
            rate_b, nums_b = run_phase("B_ultrasonic_plus_vl53l1x", capture, writer, f)
            stop_event.set()
            t.join(timeout=2)

            tof_valid = [r for r in tof_results if r[1] is not None and r[1] >= 0]
            print(f"\n  VL53L1X during phase B: total_reads={len(tof_results)} "
                  f"valid={len(tof_valid)} reads/sec={len(tof_results) / PHASE_SECONDS:.1f}")

            print(f"\n  Comparison: ultrasonic reads/sec A={rate_a:.1f} vs B={rate_b:.1f} "
                  f"(delta={rate_b - rate_a:+.1f})")
            if nums_a and nums_b:
                print(f"  Comparison: ultrasonic stdev A={statistics.pstdev(nums_a):.2f}cm vs "
                      f"B={statistics.pstdev(nums_b):.2f}cm")
    except KeyboardInterrupt:
        print("\nAborted early.")
    finally:
        capture.uninstall()
        ultrasonic.close()
        tof.stop_ranging()
        tof.close()
        print(f"\nDone. Review {LOG_PATH} for full data.")


if __name__ == "__main__":
    main()
