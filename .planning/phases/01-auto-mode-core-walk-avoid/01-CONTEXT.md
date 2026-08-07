# Phase 1: Auto-Mode Core — Walk & Avoid - Context

**Gathered:** 2026-08-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Robot can be toggled into/out of auto mode from the desktop client and, while active, walks forward and reactively avoids obstacles using the head-mounted ultrasonic sensor — the smallest possible end-to-end slice of the core value ("moves around without crashing into things"), safe by construction (instant manual override, bounded runtime, unknown-readings never treated as clear). Requirements: AUTO-01, AUTO-02, AUTO-03, AUTO-04, SENSE-01, SENSE-02, AVOID-01, CAUTION-01.

</domain>

<decisions>
## Implementation Decisions

### Manual override & reconnect resilience
- **D-01:** Fix the `tcp_flag`/`is_tcp_active` dead-code reconnect bug as in-scope work for this phase (`Code/Server/server.py:128,133`, `Code/Server/main.py`) — auto mode's "manual override always available" safety claim structurally depends on the command channel being able to reconnect.
- **D-02:** The bounded-runtime auto-stop timer is enforced server-side, independent of client connection state — the robot self-stops on schedule even if no client is connected at all, not just on reconnect.
- **D-03:** Auto mode keeps running by default even if the client disconnects entirely (bounded-runtime timer remains the safety net during the disconnect window). Add a flag/setting to instead stop auto mode on disconnect. When that setting is enabled, reconnecting always drops to manual/idle and requires the user to explicitly re-toggle auto mode — no silent auto-resume in that configuration.

### Obstacle stop/turn parameters
- **D-04:** Close-range "stop and reassess" threshold: ~20cm. Never treated as "nudge past" — always stop.
- **D-05:** Head-sweep on stop samples 3 bearings: left / center / right.
- **D-06:** Hysteresis gap between stop and resume: stop-trigger stays at ~20cm, but forward motion only resumes once the chosen heading reads clear past ~35cm. Prevents oscillation/thrashing at a single shared threshold (research Pitfall 2).
- **D-07:** Evasive turn uses a fixed angle (~45°) toward the more-open side for this phase — not scaled by clearance difference. Scaled/varied turn angles are explicitly Phase 2 scope (AVOID-02/AVOID-03).
- A no-echo/missing ultrasonic reading is never treated as "clear" (locked by ROADMAP success criterion #3 — not re-litigated here).

### Bounded runtime & auto-halt behavior
- **D-08:** Auto mode runs unattended for 5 minutes before automatically halting. (Expected to become client-tunable in Phase 4 — CONFIG-01.)
- **D-09:** On bounded-runtime timeout or an obstacle-triggered stop, the robot finishes its current gait step/cycle at the next safe boundary, then commands a stable standing posture — a cooperative, `threading.Event`-style stop checked at step boundaries, not an asynchronous mid-motion cut (avoids research Pitfall 4's unsafe-thread-kill failure mode).
- **D-10:** Manual override is the one exception that cuts in immediately, with no wait for the current autonomous action to finish (per ROADMAP success criterion #2, which is stricter than D-09's boundary-checked stop). Timeout and obstacle stops use the boundary-checked stop from D-09; manual override does not.

### Auto-mode toggle & status UX
- **D-11:** Add a new dedicated "Auto Mode" toggle button/switch to the desktop client control panel (`Code/Client/ui_client.py` / `Main.py`) rather than repurposing an existing control.
- **D-12:** Auto-mode-active indicator is an always-visible status label/badge near the toggle (not just a pressed-button visual state, not a fading toast).
- **D-13:** The Phase 1 indicator is binary (on/off) only — it does not surface sub-state (walking vs. avoiding vs. stopped). Distinct-state status signaling (LED/buzzer, richer indicators) is explicitly Phase 3 scope (AUTO-05, CONFIG-02); don't pull that forward.

### Claude's Discretion
- Exact wire-protocol command names/fields for the auto-mode toggle and reconnect-fix implementation.
- Internal cooperative-stop mechanism details (e.g. exact `threading.Event` usage, where `command_queue` reads happen) beyond the D-09/D-10 behavioral contract.
- Exact styling/placement of the toggle button and status badge within the existing PyQt5 layout.
- Specific gait/servo calls used to reach the "stable standing posture" in D-09.

</decisions>

<specifics>
## Specific Ideas

No specific product references beyond the decisions above — behavior described in concrete numeric/behavioral terms rather than by analogy.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Codebase concerns & architecture (this repo)
- `.planning/codebase/CONCERNS.md` — TCP reconnect dead-code bug (`tcp_flag`/`is_tcp_active`), single-client design, `command_queue` race
- `.planning/codebase/ARCHITECTURE.md` — Command dispatch flow (`Server.receive_commands` → `command_queue` → `Control.condition_monitor`), threading model, God-object `Control` class
- `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md` — File/naming conventions for new server- and client-side code

### Research (this milestone)
- `.planning/research/PITFALLS.md` — Pitfall 1 (no-echo ≠ clear), Pitfall 2 (oscillation/hysteresis), Pitfall 3 (`command_queue` race), Pitfall 4 (unsafe thread-kill / cooperative stop), Pitfall 5 (dead TCP reconnect), Pitfall 9 (camera blind during head sweep), Pitfall 13 (unclamped `CMD_HEAD` angles)
- `.planning/research/SUMMARY.md` — Overall risk framing and recommended build sequencing
- `.planning/research/ARCHITECTURE.md`, `.planning/research/STACK.md`, `.planning/research/FEATURES.md` — Supporting research

### Project-level
- `.planning/REQUIREMENTS.md` — AUTO-01–04, SENSE-01/02, AVOID-01, CAUTION-01 acceptance criteria
- `.planning/ROADMAP.md` §Phase 1 — Success criteria this phase must satisfy
- `CLAUDE.md` — Safety constraint ("err toward slowing/stopping"), no-new-hardware constraint

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Code/Server/ultrasonic.py` — Existing `Ultrasonic`/`gpiozero.DistanceSensor` wrapper; already suppresses `DistanceSensorNoEcho` warnings, returns `None` on no-echo (must be handled explicitly, never treated as clear)
- `Code/Server/servo.py` (head pan/tilt via `CMD_HEAD` path) — existing head-sweep mechanism, but reused sweep angles must be clamped in new code (Pitfall 13 — `CMD_HEAD` doesn't clamp like `CMD_CAMERA` does)
- `Control.command_queue` / `Control.condition_monitor` (`Code/Server/control.py`) — existing gait/posture state machine auto mode must integrate with, not replace

### Established Patterns
- Command dispatch is a large `if/elif` chain in `Server.receive_commands()` keyed on `command_parts` substrings — new auto-mode commands should follow this existing pattern rather than introducing a new dispatch mechanism
- `Code/Server/Thread.py`'s `stop_thread()` (SystemExit injection) is explicitly NOT to be reused for auto-mode's stop mechanism (D-09) — use a cooperative flag instead

### Integration Points
- `Server.receive_commands()` — where the auto-mode toggle command and manual-override detection both plug in
- `Control.condition_monitor()` — where auto-mode's walk/sense/avoid loop must coexist with the existing gait/posture state machine and `command_queue` reads
- `Code/Server/main.py` / `Code/Server/server.py` — where the `tcp_flag`/`is_tcp_active` reconnect fix applies (D-01)

</code_context>

<deferred>
## Deferred Ideas

- Variable/scaled evasive turn angle by clearance difference — explicitly Phase 2 scope (AVOID-02/AVOID-03)
- Sub-state status indicator (walking/avoiding/stopped) in client UI, and LED/buzzer physical status signaling — explicitly Phase 3 scope (AUTO-05, CONFIG-02)
- Client-side tuning of the 5-minute duration, stop/resume thresholds, and turn angle — explicitly Phase 4 scope (CONFIG-01)

</deferred>

---

*Phase: 01-auto-mode-core-walk-avoid*
*Context gathered: 2026-08-07*
