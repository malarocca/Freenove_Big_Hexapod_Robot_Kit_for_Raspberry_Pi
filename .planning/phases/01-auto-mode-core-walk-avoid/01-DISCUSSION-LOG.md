# Phase 1: Auto-Mode Core — Walk & Avoid - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-07
**Phase:** 01-auto-mode-core-walk-avoid
**Areas discussed:** Manual override & reconnect resilience, Obstacle stop/turn parameters, Bounded runtime & auto-halt behavior, Auto-mode toggle & status UX

---

## Manual override & reconnect resilience

| Option | Description | Selected |
|--------|-------------|----------|
| Fix it now | Small, diagnosed bug with outsized safety relevance; fold into this phase's scope | ✓ |
| Accept the risk explicitly | Defer the fix, document the risk, rely on bounded-runtime timer as the net | |
| Not sure — explain more | Walk through the worst case before deciding | |

**User's choice:** Fix it now.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, server-side independent timer | Pi enforces its own auto-stop regardless of connection state | ✓ |
| No, timer only matters while connected | Simpler; disconnect treated as a separate failure mode | |

**User's choice:** Yes, server-side independent timer.

| Option | Description | Selected |
|--------|-------------|----------|
| Always drop to manual/idle | Disconnect is an implicit "stop and reassess"; user must re-toggle | |
| Auto-resume where it left off | Reconnecting picks auto mode back up automatically | |

**User's choice (free text, neither option as-is):** Auto mode stays ON by default even if the client disconnects — bounded-runtime timer still caps it. A flag/setting exists to instead stop auto mode on disconnect; when that setting is enabled, reconnecting always requires a manual re-toggle back to auto.
**Notes:** User explicitly rejected both preset options in favor of "stay on by default, with an opt-in stricter setting."

---

## Obstacle stop/turn parameters

| Option | Description | Selected |
|--------|-------------|----------|
| ~20cm | Conservative default balancing stride margin and false-stop rate | ✓ |
| ~30cm | More cautious buffer, more false stops in clutter | |
| ~10cm | Tighter buffer, higher risk given soft-surface false negatives | |

**User's choice:** ~20cm.

| Option | Description | Selected |
|--------|-------------|----------|
| 3 bearings: left/center/right | Simple, fast, re-confirms trigger via center | ✓ |
| 5 bearings | Finer resolution, longer camera blind-spot window (Pitfall 9) | |
| Just left vs. right | Fastest, skips trigger re-confirmation | |

**User's choice:** 3 bearings: left/center/right.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add a gap — resume past ~35cm | Prevents oscillation at a shared threshold (Pitfall 2) | ✓ |
| No, same threshold | Simpler tuning, carries oscillation risk | |

**User's choice:** Yes, add a gap — resume only past ~35cm.

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed turn angle (~45°) | Simple, predictable for the thinnest working slice | ✓ |
| Scale turn angle by clearance difference | More nuanced, adds tuning complexity — explicitly Phase 2 scope | |

**User's choice:** Fixed turn angle (~45°).

---

## Bounded runtime & auto-halt behavior

| Option | Description | Selected |
|--------|-------------|----------|
| 5 minutes | Meaningful run length without long unattended wandering if something's wrong | ✓ |
| 2 minutes | More conservative for early pet/kid-adjacent testing | |
| 10 minutes | Longer runway for patrol-style testing | |

**User's choice:** 5 minutes.

| Option | Description | Selected |
|--------|-------------|----------|
| Finish current step, then settle to stand | Cooperative stop at gait-cycle boundary (avoids Pitfall 4's unsafe thread-kill) | ✓ |
| Immediately command a stable stance from wherever it is | Faster but more abrupt, unverified mechanical safety | |

**User's choice:** Finish current step, then settle to stand.

| Option | Description | Selected |
|--------|-------------|----------|
| Manual override cuts in immediately, timeout/obstacle stops wait for step boundary | Matches ROADMAP's locked instant-override requirement while keeping other stops cooperative | ✓ |
| All stop conditions wait for the step boundary, including manual override | More uniform, but relaxes the locked "no wait" override requirement | |

**User's choice:** Manual override cuts in immediately; timeout/obstacle stops wait for step boundary.

---

## Auto-mode toggle & status UX

| Option | Description | Selected |
|--------|-------------|----------|
| New dedicated toggle button | Unambiguous, doesn't overload an existing control | ✓ |
| Repurpose existing button/keybind | Saves layout space, risks confusion | |

**User's choice:** New dedicated toggle button.

| Option | Description | Selected |
|--------|-------------|----------|
| Always-visible status label/badge | Persistent, unambiguous at a glance | ✓ |
| Highlighted/pressed toggle button state only | Simpler to build, less visible | |

**User's choice:** Always-visible status label/badge.

| Option | Description | Selected |
|--------|-------------|----------|
| Binary on/off only | Matches Phase 1 scope, avoids pulling forward Phase 3's status signaling | ✓ |
| Show sub-state too (walking/avoiding/stopped) | More informative now, but scope creep into Phase 3 | |

**User's choice:** Binary on/off only.

---

## Claude's Discretion

- Exact wire-protocol command names/fields for the auto-mode toggle and reconnect fix
- Internal cooperative-stop mechanism implementation details beyond the behavioral contract
- Exact styling/placement of the toggle button and status badge in the PyQt5 layout
- Specific gait/servo calls used to reach the stable standing posture

## Deferred Ideas

- Variable/scaled evasive turn angle by clearance difference — Phase 2 (AVOID-02/AVOID-03)
- Sub-state status indicator and LED/buzzer physical status signaling — Phase 3 (AUTO-05, CONFIG-02)
- Client-side tuning of duration/thresholds/turn angle — Phase 4 (CONFIG-01)
