# Autonomous Hexapod

## What This Is

A Raspberry Pi-powered hexapod robot (Freenove Big Hexapod kit), currently controlled purely by manual teleoperation from a desktop client, being upgraded with real sensor-driven autonomy — obstacle avoidance and boundary-follow patrol — as the foundation for an eventual AI-piloted control loop and, further out, voice interaction.

## Core Value

The hexapod can move around on its own without crashing into things, pets, or kids. That's the non-negotiable foundation everything else (AI piloting, voice) gets built on top of.

## Requirements

### Validated

- ✓ Manual teleoperation of gait/posture/balance via desktop client — existing
- ✓ Live video streaming from robot camera to desktop client — existing
- ✓ Head pan/tilt control via servos 0/1 (camera and ultrasonic sensor are co-mounted on this head) — existing
- ✓ Battery voltage monitoring with low-battery buzzer alert — existing
- ✓ Per-leg calibration persisted to disk — existing

### Active

- [ ] Robot can enter/exit an autonomous "auto mode," triggered from the existing desktop client
- [ ] Auto mode senses obstacles ahead using the head-mounted camera + ultrasonic sensor and avoids them
- [ ] Auto mode performs boundary/wall-follow patrol behavior within a flat-floor area (no waypoint navigation)
- [ ] Auto mode behaves cautiously around unpredictable moving obstacles (pets/kids) rather than aggressively
- [ ] Auto mode runs for a bounded duration and stops on its own
- [ ] Manual control remains available at all times; no dedicated remote e-stop needed for v1 (physical/local access is the safety net)

### Out of Scope

- Waypoint / return-to-start navigation — no SLAM or odometry exists in the codebase; deferred until real navigation is actually needed
- Standalone/headless auto-mode boot (no desktop client involved) — user wants this "eventually," but v1 starts with client-triggered auto mode
- Real-time AI (Claude)-driven control loop piloting the robot directly from live camera/sensor telemetry — this is the explicit long-term vision, not v1. v1's sensor/data access should stay clean enough not to block it later.
- Voice/audio chat interaction with the robot — no microphone or speaker hardware exists today (only a piezo buzzer); deferred until that hardware question is resolved
- Authenticating/hardening the TCP command protocol — known issue (unauthenticated socket), but not the focus of this autonomy-focused milestone unless it becomes a safety blocker

## Context

- **Architecture today:** Raspberry Pi server (Python 3, PyQt5, picamera2, gpiozero/smbus/spidev) + separate PC desktop client (PyQt5/OpenCV), talking over a custom, unauthenticated TCP protocol (port 5002 commands, port 8002 video). No autonomy exists anywhere in the current code — the server only moves when the client tells it to.
- **Sensing hardware:** One ultrasonic distance sensor and the camera are both physically mounted on the same 2-axis pan/tilt head (servo channels 0 and 1), driven via `CMD_HEAD`/`CMD_CAMERA`. There is no other distance or vision sensor. IMU (accel/gyro) exists but is used for balance, not obstacle sensing.
- **No localization:** No SLAM, no odometry, no mapping anywhere in the codebase. "Patrol" is achievable only as reactive wall/boundary-following, not as memorized-map navigation.
- **Live hardware testing:** This Claude Code session runs directly on the Raspberry Pi that drives the physical robot — changes can be built and validated against the real hardware in real time during development, not just simulated.
- **Codebase quality is mixed:** some hardware driver modules are modernized (type hints, docstrings — e.g. `adc.py`, `camera.py`, `servo.py`), others are legacy-style with wildcard imports and bare `except:` blocks (`control.py`, `imu.py`, `server.py`, most of the desktop client). No automated test suite exists for first-party code — only manual hardware smoke-test scripts (`test.py`, per-module `__main__` blocks).
- **Long-term vision (explicitly beyond v1):** a real-time loop where Claude consumes live camera + sensor telemetry and directly pilots the robot for specific tasks, and — if audio hardware and "scripted audial interpretation" (speech I/O) prove feasible — a voice chat layer on top of that.

## Constraints

- **Hardware**: Obstacle sensing must work with what exists today — one ultrasonic sensor + camera, both on the pan/tilt head. No new sensors planned for v1.
- **Safety**: Real physical hardware operating near pets and kids — auto mode must err toward slowing/stopping rather than pushing through when something unexpected is nearby.
- **No localization**: Patrol/boundary behavior must be achievable via reactive sensing (wall-follow), not mapping — there is no SLAM/odometry to build on.
- **Testing**: No CI, no automated test framework for first-party code. Verification relies on live, on-device hardware testing (feasible here since the session runs on the robot's own Pi).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use existing head-mounted camera + ultrasonic for obstacle sensing; no new sensor hardware for v1 | Both already co-located on the pan/tilt head — confirmed against Tutorial.pdf and server.py's CMD_HEAD/CMD_CAMERA handling | — Pending |
| Patrol = reactive wall/boundary-follow, not waypoint navigation | No SLAM/odometry exists in the codebase; a reactive behavior is achievable now, a mapped one is not | — Pending |
| v1 relies on physical/local access for override; no dedicated remote e-stop command | User's explicit choice, paired with time-boxed auto-mode runtime as the safety net | — Pending |
| Real-time AI-piloted control loop and voice interaction are deferred to later milestones | User wants v1 to establish the sensor-autonomy foundation first; AI piloting + voice are the long-term "big picture" goal | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/bm:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/bm:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-06 after initialization*
