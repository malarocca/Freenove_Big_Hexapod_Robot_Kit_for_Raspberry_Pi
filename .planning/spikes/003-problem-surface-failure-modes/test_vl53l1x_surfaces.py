import csv
import statistics
import time

import VL53L1X

LOG_PATH = "vl53l1x_surfaces_log.csv"
SEGMENT_SECONDS = 10
SAMPLE_INTERVAL = 0.2

# Near-field only (<=60cm) -- spike 002 found VL53L1X unreliable beyond ~50-60cm regardless
# of surface, so this spike stays inside its proven zone and varies surface type instead.
SEGMENTS = [
    ("baseline_matte_hard_30cm", "matte hard surface (book cover, wall) at ~30cm",
     "sanity re-baseline vs spike 002's known-good result"),
    ("glossy_reflective_20cm", "glossy surface (phone screen, glossy magazine) at ~20cm",
     "specular reflection -- does return signal miss the sensor or arrive distorted?"),
    ("glossy_reflective_45cm", "glossy surface at ~45cm (near this sensor's known ceiling)",
     "same risk, closer to the ~50-60cm reliability edge"),
    ("dark_absorptive_20cm", "black/dark matte surface (dark cloth, dark cardboard) at ~20cm",
     "low IR return -- Signal Fail risk from weak reflected signal"),
    ("dark_absorptive_45cm", "black/dark matte surface at ~45cm",
     "same risk, closer to the reliability edge"),
    ("glass_mirror_20cm", "glass or mirror surface at ~20cm",
     "multi-path/specular artifact -- confidently-wrong reading risk (spike 002's core finding)"),
    ("glass_mirror_45cm", "glass or mirror surface at ~45cm",
     "same risk, closer to the reliability edge"),
]


def run_segment(tof, label, distance_desc, checking_for):
    print(f"\n--- Segment: {label} ---")
    print(f"Position: {distance_desc}")
    print(f"Checking for: {checking_for}")
    input("Press Enter when positioned and holding steady...")

    readings_mm = []
    status_counts = {}
    t_end = time.time() + SEGMENT_SECONDS
    while time.time() < t_end:
        distance_mm = tof.get_distance()
        status = tof.get_range_status_string()
        ts = time.time()
        readings_mm.append(distance_mm)
        status_counts[status] = status_counts.get(status, 0) + 1
        print(f"{time.strftime('%H:%M:%S')} {distance_mm}mm ({distance_mm / 10:.1f}cm) status={status}")
        yield (ts, label, distance_desc, distance_mm, status)
        time.sleep(SAMPLE_INTERVAL)

    if readings_mm:
        print(f"  n={len(readings_mm)} min={min(readings_mm)}mm max={max(readings_mm)}mm "
              f"mean={statistics.mean(readings_mm):.0f}mm stdev={statistics.pstdev(readings_mm):.1f}mm")
        print(f"  status breakdown: {status_counts}")


def main():
    tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
    tof.open(reset=True)  # required -- spike 001, plain open() degrades to 100% failure
    tof.start_ranging(2)  # medium mode -- spike 001 found this as good as long mode near-field
    tof.set_timing(140000, 150)  # 140ms budget -- spike 002 found this improves SNR/predictability

    print("VL53L1X near-field (<=60cm) surface-failure-mode test.")
    print(f"{len(SEGMENTS)} segments, {SEGMENT_SECONDS}s each. Logging to {LOG_PATH}.")
    print("Ctrl+C at any point to abort early (partial log is still saved).\n")

    try:
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "segment", "distance_desc", "distance_mm", "status"])
            for label, distance_desc, checking_for in SEGMENTS:
                for row in run_segment(tof, label, distance_desc, checking_for):
                    writer.writerow([f"{row[0]:.3f}", row[1], row[2], row[3], row[4]])
                    f.flush()
    except KeyboardInterrupt:
        print("\nAborted early.")
    finally:
        tof.stop_ranging()
        tof.close()
        print("\nDone. Review vl53l1x_surfaces_log.csv for full data.")


if __name__ == "__main__":
    main()
