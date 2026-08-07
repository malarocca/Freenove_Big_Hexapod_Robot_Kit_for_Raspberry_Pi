---
phase: 1
slug: auto-mode-core-walk-avoid
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-07
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Adapted per CLAUDE.md's explicit constraint: "No CI, no automated test framework for
> first-party code. Verification relies on live, on-device hardware testing." This
> project-level directive takes precedence over the default pytest-oriented template —
> this document describes how verification actually works for this phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (project constraint) — live, on-device hardware verification, matching the existing convention of `Code/Server/test.py` (interactive hardware smoke test) and `Code/Server/myCode.py` (standalone `Control` exercise script) |
| **Config file** | none |
| **Quick run command** | Manual: run the new autonomy module's standalone entry point directly on the Pi (e.g. `python3 Code/Server/autonomy/behavior.py`'s `if __name__ == '__main__':` self-test block, matching `servo.py`/`led.py`/`ultrasonic.py` convention) |
| **Full suite command** | Manual: full `CMD_AUTO` toggle from the desktop client with a real obstacle placed in the robot's path, observing all four ROADMAP success criteria live |
| **Estimated runtime** | ~5-10 min per full walkthrough (includes the 5-minute unattended-timeout check) |

---

## Sampling Rate

- **Per task:** Manual smoke test of the specific behavior just implemented, on real hardware, following the existing `test.py`/`myCode.py` standalone-script convention
- **Phase gate (before `/bm:verify-work`):** Full live walkthrough of all four ROADMAP success criteria — no automated suite substitutes for this per CLAUDE.md
- **Max feedback latency:** Immediate (interactive, on-device)

---

## Per-Task Verification Map

| Req ID | Behavior | Verification Type | Method |
|--------|----------|-----------|-------------------|
| AUTO-01 | Toggle auto mode on/off from client | manual | Click new toggle button; observe robot starts/stops walking |
| AUTO-02 | Manual command instantly preempts auto | manual (timed) | Send arrow-key move while auto-walking; stopwatch/observe latency, cross-check against `run_gait` worst-case latency findings in RESEARCH.md |
| AUTO-03 | Bounded-duration auto-stop, stable stance | manual (timed) | Leave auto mode running unattended 5+ minutes; observe automatic halt into a settled stance |
| AUTO-04 | Visible auto-mode-active indicator | manual (visual) | Confirm status badge shows on toggle, updates on auto-stop |
| SENSE-01 | No-echo never treated as clear | manual + code-level self-check | Physically block/absorb the ultrasonic beam (soft object at an angle) during auto mode; confirm robot does not proceed. Additionally sanity-check the `_read()` bypass logic directly on the Pi via a short standalone script asserting `None` is returned when the sensor is covered |
| SENSE-02 | Head sweeps 3 bearings before deciding | manual (visual) | Observe head pan movement (left/center/right) on obstacle-triggered stop |
| AVOID-01 | Stop-and-turn with hysteresis, no thrashing | manual | Place obstacle at ~20-35cm boundary repeatedly; observe no rapid oscillation |
| CAUTION-01 | Close-range always stop, never nudge past | manual | Place obstacle well inside 20cm; confirm stop, never partial-approach |

*Status: ⬜ pending for all rows — populated during execution.*

---

## Wave 0 Requirements

- None in the pytest sense (no framework to install, per project constraint).
- Recommended (not required): a standalone `if __name__ == '__main__':` self-test block in the new `behavior.py` decision module that constructs hand-built sensor-snapshot inputs and asserts the expected stop/turn/walk decision — mirrors `servo.py`/`ultrasonic.py`'s existing self-test pattern, runnable directly on the Pi without pytest, and gives the one piece of this phase's logic that doesn't strictly require hardware (the pure decision function) a repeatable check.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Auto-mode walk + avoid end-to-end | AUTO-01..04, SENSE-01/02, AVOID-01, CAUTION-01 | Physical hardware behavior (servo motion, ultrasonic sensing, real obstacles) — no CI/automated test framework exists for first-party code per CLAUDE.md | See Per-Task Verification Map above; run full walkthrough on the robot with real obstacles before marking the phase verified |

---

## Validation Sign-Off

- [ ] All tasks have a manual on-device verification step mapped in the table above
- [ ] Phase gate walkthrough covers all 4 ROADMAP success criteria
- [ ] `SENSE-01` no-echo handling verified against the `gpiozero` `_read()` bypass (RESEARCH.md Pitfall 1), not just the smoothed public API
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
