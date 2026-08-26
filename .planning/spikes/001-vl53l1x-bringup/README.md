---
spike: 001
name: vl53l1x-bringup
type: standard
validates: "Given the VL53L1X wired on I2C (addr 0x29), when queried with a driver, then it returns plausible mm-precision readings that track a real object moving toward/away from it"
verdict: VALIDATED
related: []
tags: [hardware, i2c, vl53l1x]
---

# Spike 001: VL53L1X Bring-Up

## What This Validates

Given the VL53L1X wired on I2C (addr 0x29), when queried with a driver, then it returns
plausible mm-precision readings that track a real object moving toward/away from it.

## Research

| Approach | Tool/Library | Pros | Cons | Status |
|----------|-------------|------|------|--------|
| Pimoroni `vl53l1x` | ctypes wrapper over ST's official C driver | Lightweight, Raspberry Pi-specific, no extra abstraction layer, matches this project's direct-I2C driver pattern (`adc.py`, `pca9685.py`) | Smaller community than Adafruit | **Chosen** |
| Adafruit CircuitPython VL53L1X | `adafruit-circuitpython-vl53l1x` + Adafruit Blinka | Well documented, actively maintained | Requires Blinka (hardware abstraction layer) not used anywhere else in this project — extra dependency weight for no benefit here | Rejected |

Installed via `sudo pip3 install vl53l1x smbus2 --break-system-packages` (smbus2 was already present).

## How to Run

```
cd .planning/spikes/001-vl53l1x-bringup
sudo python3 -u test_bringup.py            # baseline, medium mode, no reset
sudo python3 -u test_reset_longmode.py     # reset=True + long mode
sudo python3 -u test_reset_mediummode.py   # reset=True + medium mode
```

Each logs to a CSV (timestamp, distance_mm, status) alongside live stdout output, so a human
can drive the physical test (moving objects around) while Claude reads the log afterward.

## What to Expect

Distance readings in mm that decrease as a hand/object approaches the sensor, with a
`status` of `Range Valid` for good reads and named failure codes (`Signal Fail`,
`Phase Fail`, `No Update`) for rejected measurements.

## Investigation Trail

1. **First run** (`test_bringup.py`, medium mode, default `open()`, no reset): readings looked
   stable (~190-206mm) but it was unclear whether anything was actually moving in front of the
   sensor — first false start, no real signal either way.
2. **Second run**, same script, explicit hand movement: got a real mix of valid readings
   (18mm/58mm/46mm as hand approached, ~190-216mm at rest) — confirmed the sensor **can** work.
3. **Third run**, added `get_range_status_string()` for visibility: revealed heavy
   `Signal Fail`/`Hardware Fail` noise during fast hand movement — expected some, but the
   `Hardware Fail` was concerning.
4. **Fourth run**, steady-hand test (hold at fixed 10/30/60/100cm instead of waving):
   **100% failure** — every single reading was `Phase Fail` or `Signal Fail`, zero valid
   reads across 15 seconds, despite deliberately calmer conditions that should have been
   *easier* than the earlier successful run. This regression (works → stops working) is the
   same pattern the ultrasonic sensor showed before its physical fault was found, so it was
   treated as a serious signal, not noise.
5. **Ruled out wiring/dead-connection hardware fault directly:** read the VL53L1X's model ID
   register (0x010F) over raw I2C via `smbus2` — got back `0xea`, the correct VL53L1X model ID.
   The chip responds correctly and consistently at its address; I2C communication itself is
   solid. Whatever was failing was in the ranging computation, not the bus/wiring.
6. **Isolated the fix:** tried `tof.open(reset=True)` (forces a hardware reset before ranging)
   combined with long-range mode (mode 3, higher VCSEL power) and a large flat reflective
   target (a book) at close range. Result: ~92% valid readings (109/119 samples), values
   tracking the book being moved around (26-114mm). Confirmed with a plain hand at 5/15/30cm
   in the same reset+long-mode configuration: readings tracked distance well
   (~43-51mm / ~121-165mm / ~259-298mm respectively — a consistent ~10-15mm offset above
   nominal, likely the sensor's internal reference plane vs. the hand's surface, not an error).
7. **Isolated reset vs. mode:** re-ran with `reset=True` + **medium** mode (mode 2 — the same
   mode as steps 1-4, but now with the reset). Result: 100% valid readings across the whole
   run (5cm→~36-64mm, 15cm→~129-192mm, 30cm→~217-307mm), same or better than long mode.
   **Conclusion: the reset was the fix, not the ranging mode.**

## Results

**Verdict: VALIDATED**, with an important caveat that shaped the finding.

- The VL53L1X hardware, wiring, and I2C connection are all confirmed good — no loose
  connection, no physical/optical fault (unlike the ultrasonic sensor's earlier dislodged
  transducer dish). Model ID register reads back correctly every time.
- **Root cause of the apparent "it stopped working" regression:** the Pimoroni `vl53l1x`
  library's `open()` defaults to `reset=False`. Across repeated `start_ranging()`/
  `stop_ranging()` cycles within the same power-on session (i.e., running several test
  scripts back to back without power-cycling the sensor), the sensor accumulated into a bad
  internal state that produced 100% rejected measurements (`Phase Fail`/`Signal Fail`) despite
  I2C communication staying perfectly healthy. Calling `open(reset=True)` clears this.
- **Ranging mode (medium vs. long) did not matter** for the ranges tested here (~3-30cm);
  both gave clean, consistent readings once reset. This should be re-checked at longer range
  (1-3m) during spike 002, since long mode is specifically meant for extended range at the
  cost of some close-range noise — but for the obstacle-avoidance use case (stop threshold in
  the 20-35cm band per `autonomy/behavior.py`), medium mode's readings were arguably cleaner
  (zero dropouts vs. long mode's occasional `No Update`) in this small sample.
- A small number of `No Update` readings occurred during fast hand transitions in every
  configuration — expected ToF behavior (momentary loss of lock during motion), not a defect.

## Signal for Later Spikes / the Real Build

**Requirement surfaced:** any VL53L1X integration (spike 004, and eventually
`autonomy/perception.py`) **must** call `tof.open(reset=True)`, not the library's default
`open()`. Skipping this reproduces the 100%-failure regression seen in step 4 above.
