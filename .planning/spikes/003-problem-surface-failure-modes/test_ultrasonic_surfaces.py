import csv
import statistics
import sys
import time

sys.path.insert(0, "/home/pi/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/Code/Server")

from ultrasonic import Ultrasonic

LOG_PATH = "ultrasonic_surfaces_log.csv"
SEGMENT_SECONDS = 10
SAMPLE_INTERVAL = 0.2

# Each segment: (label, distance description, what we're checking for)
SEGMENTS = [
    ("baseline_hard_flat_30cm", "hard flat surface (book/wall) at ~30cm",
     "sanity re-baseline vs spike 002's known-good result"),
    ("soft_fabric_15cm", "pillow or folded blanket at ~15cm (inside STOP_THRESHOLD_CM=20)",
     "echo absorption -- could a soft obstacle silently read as 300cm 'clear'?"),
    ("soft_fabric_30cm", "pillow or folded blanket at ~30cm (inside RESUME_THRESHOLD_CM=35)",
     "same risk, at the resume-hysteresis distance"),
    ("angled_hard_30cm", "hard flat surface tilted ~30-45deg off perpendicular at ~30cm",
     "specular deflection -- does the echo bounce away instead of back?"),
    ("angled_hard_50cm", "hard flat surface tilted ~30-45deg off perpendicular at ~50cm",
     "same risk, longer range where deflection has more effect"),
    ("low_profile_20cm", "low object (book spine, low shelf edge) below main beam axis at ~20cm",
     "narrow/low target -- does the sensor pick it up at all?"),
    ("low_profile_40cm", "low object below main beam axis at ~40cm",
     "same risk, longer range"),
]

FAILURE_CLAMP_CM = 300.0  # gpiozero DistanceSensor's max_distance -- see README Research section


def run_segment(sensor, label, distance_desc, checking_for):
    print(f"\n--- Segment: {label} ---")
    print(f"Position: {distance_desc}")
    print(f"Checking for: {checking_for}")
    input("Press Enter when positioned and holding steady...")

    readings = []
    clamp_count = 0
    none_count = 0
    t_end = time.time() + SEGMENT_SECONDS
    while time.time() < t_end:
        d = sensor.get_distance()
        ts = time.time()
        if d is None:
            none_count += 1
            print(f"{time.strftime('%H:%M:%S')} None (RuntimeWarning path)")
        else:
            if d >= FAILURE_CLAMP_CM - 0.5:
                clamp_count += 1
            readings.append(d)
            print(f"{time.strftime('%H:%M:%S')} {d}cm")
        yield (ts, label, distance_desc, d)
        time.sleep(SAMPLE_INTERVAL)

    if readings:
        print(f"  n={len(readings)} min={min(readings)} max={max(readings)} "
              f"mean={statistics.mean(readings):.1f} "
              f"stdev={statistics.pstdev(readings):.2f} "
              f"clamped_to_300cm={clamp_count} none={none_count}")
    else:
        print(f"  n=0 (all {none_count} reads were None)")


def main():
    ultrasonic = Ultrasonic()
    print("Ultrasonic full-range surface-failure-mode test.")
    print(f"{len(SEGMENTS)} segments, {SEGMENT_SECONDS}s each. Logging to {LOG_PATH}.")
    print("Ctrl+C at any point to abort early (partial log is still saved).\n")

    try:
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "segment", "distance_desc", "distance_cm"])
            for label, distance_desc, checking_for in SEGMENTS:
                for row in run_segment(ultrasonic, label, distance_desc, checking_for):
                    writer.writerow([f"{row[0]:.3f}", row[1], row[2], row[3]])
                    f.flush()
    except KeyboardInterrupt:
        print("\nAborted early.")
    finally:
        ultrasonic.close()
        print("\nDone. Review ultrasonic_surfaces_log.csv for full data.")


if __name__ == "__main__":
    main()
