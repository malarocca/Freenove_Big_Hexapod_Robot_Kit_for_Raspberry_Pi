---
id: SEED-001
status: dormant
planted: 2026-08-08
planted_during: v1.0 / Phase 01 (auto-mode-core-walk-avoid)
trigger_when: when the user reports the replacement ultrasonic sensor has arrived and been installed; also surface during any /bm:new-milestone scan for sensing/perception scope
scope: medium
---

# SEED-001: Add a VL53L1X Time-of-Flight sensor as a replacement/complement for the ultrasonic sensor

## Why This Matters

The existing ultrasonic sensor (HC-SR04-style, `Code/Server/ultrasonic.py`) failed physically
mid-Phase-01 (a transducer dish was dislodged) — user is buying a cheap replacement. While
shopping for parts, the user asked whether to also add a LiDAR sensor, since GPIO capacity
looks available.

Two software fixes this session (hysteresis `ff87cda`, dual-poller GPIO contention `12a7fda`)
already worked around real bugs in how the ultrasonic sensor is polled, but the sensor's
underlying physics still have a known weakness already flagged as an open concern in
STATE.md: real-world ultrasonic behavior against soft/angled/low-profile obstacles
(pillows, rugs, furniture edges) is unvalidated and likely unreliable — ultrasonic echoes
bounce away from angled/absorbent surfaces rather than returning, common in a home with
pets and kids.

A **360-degree spinning LiDAR** (e.g. RPLIDAR A1, ~$99) was considered and **rejected** as a
recommendation: it draws ~500mA continuous plus motor spin-up, and its main payoff — building
an occupancy map — is unused because CLAUDE.md's project constraints explicitly rule out
SLAM/localization (reactive sensing only, no mapping).

A **directional VL53L1X Time-of-Flight sensor** (ST, I2C, ~$10, ~20mA active, up to 50Hz,
mm-precision, ~4m range) was recommended instead: it's a drop-in fit for the existing
single-sensor-on-pan/tilt-head architecture (same physical mounting pattern as today's
ultrasonic), doesn't share ultrasonic's soft/angled-surface weakness, and its own known
failure modes (glass/mirrors, extremely IR-absorptive black surfaces) are less common in a
home environment than ultrasonic's failure modes.

**Open question to resolve when this seed is worked:** does the VL53L1X *replace* the
ultrasonic outright, or should both be fused (dual-sensor arbitration)? Working
recommendation captured here: **replace, don't fuse** — this is a single narrow-beam ranging
sensor on a panning head, same shape as today's setup, and simplification should be the
default unless a specific gap shows up in testing. Sensor fusion adds real complexity
(arbitration logic, disagreement handling) that the "no new sensors planned for v1" /
reactive-only constraints don't currently justify.

**Scope note:** Adding this sensor means updating CLAUDE.md's current stated hardware
constraint — "Obstacle sensing must work with what exists today — one ultrasonic sensor +
camera... No new sensors planned for v1." That's an explicit project-scope decision the user
has not yet made; this seed exists so it isn't forgotten, not to pre-decide it.

## When to Surface

**Trigger:** Ask the user about this the next time they report the replacement ultrasonic
sensor is installed (i.e., right when Phase 01 Plan 01-01 Task 3's hardware checkpoint is
about to resume) — don't wait for a full new-milestone cycle, this is timely while they're
already ordering hardware parts. Also surface normally during any `/bm:new-milestone` scan
touching sensing/perception scope, in case the near-term nudge is missed.

## Scope Estimate

**Medium** — not just a part swap. Likely touches:
- A new driver module (VL53L1X over I2C — no existing vendored library in `Code/Libs/`,
  would need e.g. `smbus`-based driver or a small vendored library, following the existing
  `Code/Server/adc.py`/`pca9685.py` I2C pattern).
- `Code/Server/autonomy/perception.py` (`SensorHub`) — swap or abstract the reading source.
- Possibly `Code/Server/ultrasonic.py` if keeping both sensors behind a shared interface.
- `CLAUDE.md` constraint update (explicit scope decision, not just code).
- Re-verification of the full Phase 01 Task 3 hardware checkpoint once wired in.

## Breadcrumbs

- `Code/Server/ultrasonic.py` — current `gpiozero.DistanceSensor` wrapper (trigger=GPIO27,
  echo=GPIO22) that would be replaced or paralleled.
- `Code/Server/autonomy/perception.py` — `SensorHub`, the consumer of ultrasonic readings for
  the autonomy decision loop; this session's dual-poller fix (commit `12a7fda`) lives here.
- `Code/Server/autonomy/behavior.py` — hysteresis decision logic (commit `ff87cda`,
  `RESUME_THRESHOLD_CM`/`STOP_THRESHOLD_CM`) that would carry over unchanged regardless of
  sensor swap, since it only consumes a distance value.
- `.planning/STATE.md` — "Real-world ultrasonic behavior against soft/angled/low-profile
  obstacles is unvalidated" (Blockers/Concerns), the concern this sensor swap would resolve.
- `CLAUDE.md` — "Hardware" constraint line to be updated if this is adopted.
- `.planning/HANDOFF.json` — session record of the physical sensor fault (transducer dish
  dislodged) that triggered this conversation.

## Notes

Captured live during a `/bm:resume-work` session (2026-08-08) while the user was mid-way
through diagnosing a physically broken ultrasonic sensor for Phase 01. User explicitly asked
to be reminded of this "when I come back with the new ultrasonic sensor" — treat that as the
primary trigger, ahead of any milestone-scan surfacing.
