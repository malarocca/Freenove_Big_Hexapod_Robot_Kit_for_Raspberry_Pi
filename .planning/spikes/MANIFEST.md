# Spike Manifest

## Idea

Determine whether the newly-installed VL53L1X Time-of-Flight sensor should become the
primary obstacle-sensing input for Phase 01's autonomy work, with the just-replaced
ultrasonic sensor demoted to a fallback/cross-check (per SEED-001,
`.planning/seeds/SEED-001-vl53l1x-tof-sensor.md`). This is a live-hardware decision:
both sensors are physically installed on the robot right now. The outcome directly
affects CLAUDE.md's stated v1 hardware constraint ("ultrasonic sensor + camera only, no
new sensors planned for v1"), which will need an explicit update if VL53L1X is adopted.

## Requirements

- Any VL53L1X integration must call `tof.open(reset=True)`, not the library default
  `open()` — skipping the reset causes measurements to degrade to 100% failure
  (`Phase Fail`/`Signal Fail`) across repeated ranging start/stop cycles within the same
  power-on session, even though I2C communication with the chip stays fully healthy.
  (Spike 001)
- VL53L1X's genuinely reliable range in this physical setup is only ~50-60cm — beyond that
  it reports confidently-wrong short distances (safe-biased direction, but would make
  autonomous walking see phantom obstacles everywhere past ~60cm). Ultrasonic reliably
  covers the full tested range (10-100cm+). **Ultrasonic must stay the primary/long-range
  sensor; VL53L1X is a candidate near-field (<=60cm) precision cross-check only** — this
  inverts SEED-001's original "VL53L1X primary" framing. Any production use should default
  to a ~100-150ms timing budget, not the ~33ms library default. (Spike 002)
- VL53L1X instability is range-triggered, not surface-triggered: ~20cm readings were clean
  for every surface tested (including glass/dark, the "hardest" cases), while ~45cm readings
  were unstable for every surface including plain glossy material. **If VL53L1X is used as a
  near-field cross-check, keep it well inside its clean zone (<=20-30cm), not stretched
  toward the ~60cm ceiling.** Also: a `Range Valid` status alone is not sufficient to trust a
  VL53L1X reading — one instance of a `Range Valid`-status 0mm reading was observed; any
  production use needs a plausibility/continuity check on the value itself, not just the
  status string. (Spike 003)
- Running VL53L1X on its own polling thread concurrently with ultrasonic's gpiozero
  background thread introduces **no measurable contention** (identical read rate, near-
  identical value distribution vs. ultrasonic-alone) — the original dual-poller bug
  (`12a7fda`) was two threads racing on the *same* sensor's GPIO pins, and VL53L1X's I2C
  polling doesn't touch those pins, so that failure class cannot recur through this path.
  Practical gotcha: `get_distance()` blocks for ~290ms at the 140ms/150ms timing settings
  spikes 002/003 established, so a requested 20Hz poll rate only achieves ~9.3Hz in
  practice — budget for the real rate, not the requested one. (Spike 004)
- **Arbitration recommendation (spike 004 sketch):** ultrasonic stays authoritative for the
  full STOP/RESUME range; VL53L1X is only ever consulted inside the existing 20-35cm
  ambiguous band, only trusted to <=30cm of its own reading (per spike 003), only trusted on
  an explicit `Range Valid` status AND a plausibility/continuity check on the value itself
  (per spike 003's 0mm finding), and even then only ever agrees with or defers to
  ultrasonic's STOP — it cannot relax a stop decision ultrasonic already made. Its likely
  real value is as a precision input for a *future* directional decision (e.g. plan
  01-03's sweep/pick-open-side logic), not the binary stop/clear decision itself. This is an
  open question for whoever plans 01-03: is the integration complexity worth it for a
  directional-precision assist alone? (Spike 004)

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | vl53l1x-bringup | standard | VL53L1X returns plausible readings over I2C | ✓ VALIDATED | hardware, i2c, vl53l1x |
| 002 | vl53l1x-vs-ultrasonic-accuracy | comparison | Accuracy/noise/range vs ultrasonic | ⚠ PARTIAL | hardware, comparison |
| 003 | problem-surface-failure-modes | standard | Real failure modes on household surfaces | ⚠ PARTIAL | hardware, reliability |
| 004 | dual-sensor-sensorhub-integration | standard | Both sensors readable without contention; arbitration sketch | ✓ VALIDATED | integration, architecture |
