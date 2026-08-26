# Spike Conventions

Patterns and stack choices established across spike sessions (001-004, VL53L1X/ultrasonic
sensor evaluation track). New spikes follow these unless the question requires otherwise.

## Stack

- Python 3 stdlib only for spike scripts (`csv`, `statistics`, `threading`, `time`) — no new
  dependencies introduced beyond what the project already vendors.
- `sys.path.insert(0, ".../Code/Server")` at the top of each script to import the project's
  own hardware wrappers (`from ultrasonic import Ultrasonic`) directly, rather than
  reimplementing sensor access.
- All hardware spike scripts run as `sudo python3 -u <script>.py` (unbuffered stdout, sudo
  for GPIO/I2C access) directly on the robot's own Pi — this project has no CI/mocking layer,
  live hardware is the only way to validate.

## Structure

- One `.py` script per distinct test/question within a spike, not one monolithic script —
  e.g. spike 002 split `test_compare.py` / `test_longmode_farrange.py` /
  `test_longmode_longbudget.py` rather than parameterizing one script three ways.
- CSV log per script, named descriptively (`compare_log.csv`, `contention_log.csv`), written
  incrementally with `f.flush()` after every row so a `Ctrl+C` mid-run still leaves usable
  partial data.
- Analyze the raw CSV after a live run, not just the live-printed summary stats — several
  real findings in spikes 003/004 (multi-modal plateau-jumping, a `Range Valid`-status 0mm
  reading, confirming phase A/B weren't accidentally identical data) only showed up by
  grep-ing/parsing the actual CSV rows, not the aggregate min/max/mean printed at segment end.

## Patterns

- **Interactive segmented testing:** for anything requiring a human to position a real
  physical object (surface-failure-mode spikes, accuracy spikes), structure as a list of
  `(label, description, what_to_check_for)` tuples, loop through them with `input()` gating
  each segment, log every sample with its segment label, print a live per-segment summary.
  Spikes 002 and 003 both used this shape.
- **A/B phase comparison for contention/regression questions:** when the question is "does
  adding X change Y's behavior," don't just run with X present — capture a baseline without
  X first, then the same measurement with X, and diff the two (spike 004). A single-phase
  "does it work" run has a blind spot: a degraded-but-still-plausible-looking reading (like
  the original dual-poller bug produced) won't visibly stand out without a same-target
  baseline to compare against.
- **Distances should be tape-measured, not estimated/labeled-only.** Spike 002 tape-measured
  every distance and got clean, trustworthy absolute numbers. Spikes 003/004 used
  description-only labels (`"~30cm"`) without a tape measure, and several segments drifted
  far from their labeled distance (one `~30cm` segment settled at ~9cm) — this didn't
  invalidate the *qualitative* findings (smooth drift vs. chaotic jumping is still clearly
  distinguishable) but did undermine using the specific label distances as ground truth.
  **Tape-measure every distance in future spikes**, even ones that feel like "just eyeball
  it" setup steps.

## Tools & Libraries

- `VL53L1X` (Pimoroni Python wrapper, `/usr/local/lib/python3.13/dist-packages/VL53L1X.py`):
  always `tof.open(reset=True)` (spike 001 — plain `open()` degrades to 100% failure after
  repeated start/stop cycles). `start_ranging(2)` (medium mode) plus
  `tof.set_timing(140000, 150)` (140ms budget) is the validated-good near-field
  configuration (spikes 001-003). Note `get_distance()` is a synchronous/blocking call with
  no background thread of its own — a ~290ms real cycle time at this timing budget, well
  under whatever poll rate you request (spike 004).
- `Ultrasonic` (`Code/Server/ultrasonic.py`): straightforward, no gotchas found across 4
  spikes. Note for future reference (not yet spike-tested in production code): its
  constructor suppresses `DistanceSensorNoEcho` warnings, so a true no-echo condition returns
  `max_distance` (300cm) rather than `None` — the class's own `except RuntimeWarning` branch
  is effectively unreachable in this configuration.
