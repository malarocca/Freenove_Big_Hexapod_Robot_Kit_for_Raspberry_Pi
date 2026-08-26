import csv
import time
import VL53L1X

LOG_PATH = "longmode_farrange_log.csv"

tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
tof.open(reset=True)  # force a hardware reset before ranging
tof.start_ranging(3)  # 3 = Long range mode (higher VCSEL power)

print("Reset + Long mode, far-range test. In an open area, hold a target at 100cm")
print("(tape measure), then slowly bring it toward the sensor down to ~10cm and back out.")
print(f"Logging to {LOG_PATH}. Press Ctrl+C to stop.\n")

with open(LOG_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "distance_mm", "status"])
    try:
        while True:
            distance_mm = tof.get_distance()
            status = tof.get_range_status_string()
            ts = time.time()
            print(f"{time.strftime('%H:%M:%S')} distance={distance_mm}mm ({distance_mm / 10:.1f}cm) status={status}")
            writer.writerow([f"{ts:.3f}", distance_mm, status])
            f.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        tof.stop_ranging()
        tof.close()
