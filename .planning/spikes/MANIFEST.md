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

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | vl53l1x-bringup | standard | VL53L1X returns plausible readings over I2C | ✓ VALIDATED | hardware, i2c, vl53l1x |
| 002 | vl53l1x-vs-ultrasonic-accuracy | comparison | Accuracy/noise/range vs ultrasonic | ⚠ PARTIAL | hardware, comparison |
| 003 | problem-surface-failure-modes | standard | Real failure modes on household surfaces | PENDING | hardware, reliability |
| 004 | dual-sensor-sensorhub-integration | standard | Both sensors readable without contention; arbitration sketch | PENDING | integration, architecture |
