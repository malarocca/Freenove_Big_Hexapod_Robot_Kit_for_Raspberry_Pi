import csv
import sys
import time

sys.path.insert(0, "/home/pi/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/Code/Server")

import VL53L1X
from ultrasonic import Ultrasonic

LOG_PATH = "compare_log.csv"

ultrasonic = Ultrasonic()

tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
tof.open(reset=True)  # required -- see spike 001, plain open() degrades to 100% failure
tof.start_ranging(2)  # medium mode -- spike 001 found this as good as long mode at close range

print("Reading both sensors every ~0.3s. Aim both at the SAME target (they're on the same")
print("pan/tilt head so this should already be true) at known distances from a tape measure")
print("or ruler if you have one: e.g. 10cm, 20cm, 30cm, 50cm, 100cm, ~3-5s each, in order.")
print(f"Logging to {LOG_PATH}. Press Ctrl+C to stop.\n")

with open(LOG_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "ultrasonic_cm", "vl53l1x_mm", "vl53l1x_status"])
    try:
        while True:
            us_cm = ultrasonic.get_distance()
            tof_mm = tof.get_distance()
            tof_status = tof.get_range_status_string()
            ts = time.time()
            print(f"{time.strftime('%H:%M:%S')} ultrasonic={us_cm}cm  vl53l1x={tof_mm}mm ({tof_mm / 10:.1f}cm) status={tof_status}")
            writer.writerow([f"{ts:.3f}", us_cm, tof_mm, tof_status])
            f.flush()
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        tof.stop_ranging()
        tof.close()
        ultrasonic.close()
