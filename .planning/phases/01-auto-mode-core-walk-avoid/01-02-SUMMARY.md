---
phase: 01-auto-mode-core-walk-avoid
plan: 02
subsystem: ui
tags: [pyqt5, desktop-client, tcp-protocol, cmd-auto]

# Dependency graph
requires:
  - phase: 01-auto-mode-core-walk-avoid (plan 01-01)
    provides: "CMD_AUTO#1/#0 server-side wire protocol, unsolicited status pushes on toggle-off/preempt/timeout/connect-sync"
provides:
  - "Button_Auto toggle and label_Auto_Status badge widgets in Code/Client/ui_client.py, matching the UI-SPEC geometry/color contract"
  - "auto_mode_toggle()/set_auto_status() in Code/Client/Main.py, badge driven exclusively by the server's CMD_AUTO ack, never by the click"
  - "CMD_AUTO client-side protocol constant, kept in sync with Code/Server/command.py"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Badge/status widgets driven only from server acks (receive_instruction) and the disconnect branch, never optimistically from the triggering click -- keeps the UI honest when auto mode ends for reasons the client didn't initiate"
    - "QToolTip.showText anchored to a button for a non-modal, non-widget inline error, matching the fixed 1000x800 absolute-pixel layout's constraint against QMessageBox/statusBar()"

key-files:
  created: []
  modified:
    - Code/Client/Command.py
    - Code/Client/ui_client.py
    - Code/Client/Main.py

key-decisions:
  - "Task 3 (on-device walkthrough) is a blocking checkpoint requiring physical robot access and human observation of badge colors -- cannot be automated or approved by this agent. Executor stops here per standard (non-auto) checkpoint protocol; AUTO_CFG/auto_advance both resolved false at start of this session."

patterns-established:
  - "Auto Mode badge text/color is written from exactly one method (set_auto_status); every other call site only ever passes True/False into it, never touches the widgets directly"

requirements-completed: []  # AUTO-01/AUTO-04 remain unverified pending Task 3's live hardware checkpoint

# Metrics
duration: ~10min (Tasks 1-2 only; Task 3 checkpoint pending)
completed: 2026-08-30
---

# Phase 01, Plan 01-02: Auto Mode Client UI Summary

**Auto Mode toggle button and always-visible status badge wired into the PyQt5 desktop client, driven exclusively by the server's CMD_AUTO ack rather than the click -- Tasks 1-2 complete and committed, Task 3's live hardware walkthrough is a blocking checkpoint awaiting the operator.**

## Performance

- **Duration:** ~10 min (Tasks 1-2)
- **Started:** 2026-08-30T01:49:00Z (approx, first file read)
- **Completed:** Tasks 1-2 complete 2026-08-30T01:56:00Z; plan not yet fully complete (Task 3 pending)
- **Tasks:** 2 of 3 complete (Task 3 is a blocking checkpoint, not yet executed)
- **Files modified:** 3

## Accomplishments

- `Button_Auto` and `label_Auto_Status` added to `Code/Client/ui_client.py` at the exact contracted geometry (`QRect(150,510,110,30)` / `QRect(270,510,160,30)`), idle text/colors, generator-pattern-compliant (additions only, zero deletions).
- `CMD_AUTO` added to `Code/Client/Command.py`; `CMD_*` token set is byte-for-byte identical to `Code/Server/command.py` (verified via sorted-set diff).
- `auto_mode_toggle()` sends `CMD_AUTO#1`/`CMD_AUTO#0` only when connected; shows the exact contracted inline error via `QToolTip.showText` (no dialog, no third widget) when clicked while disconnected, and never flips the button/badge itself.
- `set_auto_status()` is the single writer of both widgets' text/style; it is called from exactly three places: the not-connected guard, the inbound `CMD_AUTO` branch in `receive_instruction` (covers explicit toggle-off, manual-command preemption, and bounded-runtime halt in one branch, since the server pushes `CMD_AUTO#0` in all three cases), and the disconnect branch in `connect()`.
- Inbound `CMD_AUTO` parsing guards `len(data) >= 2` and compares `data[1] == "1"` as a string (never `int()`), per the plan's T-01-07 mitigation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the CMD_AUTO client constant and the two new widgets to the generated Qt layout** - `6e2c6aa` (feat)
2. **Task 2: Wire the toggle, the connection guard, and server-driven badge updates in Main.py** - `d2550db` (feat)
3. **Task 3: On-device walkthrough** - NOT YET EXECUTED (blocking checkpoint, requires human operator with physical access to the robot)

**Plan metadata:** this commit (docs: pause plan 01-02 at checkpoint)

## Files Created/Modified

- `Code/Client/Command.py` - `CMD_AUTO = "CMD_AUTO"` constant added, kept in sync with the server copy
- `Code/Client/ui_client.py` - `Button_Auto` (toggle) and `label_Auto_Status` (badge) widgets added to `setupUi()`, `retranslateUi()`, and the z-order `raise_()` block; no other widget touched
- `Code/Client/Main.py` - `Button_Auto.clicked` wiring, `auto_mode_toggle()`, `set_auto_status()`, inbound `CMD_AUTO` branch in `receive_instruction`, and a `set_auto_status(False)` call in `connect()`'s disconnect branch

## Decisions Made

- Followed the plan's exact widget-insertion points (immediately after `Button_Face_ID`) and QFont/style-sheet blocks verbatim, per `ui_client.py`'s "do not hand-edit" generator-pattern constraint.
- Placed the two new `Main.py` methods immediately after `buzzer()`, matching that method's dynamic-label toggle shape as the plan directed.
- Did not add a fourth `set_auto_status` call site beyond the three the action text explicitly enumerates (not-connected guard, `CMD_AUTO` inbound branch, disconnect branch) even though the plan's own acceptance-criteria line claims the grep count should be 5 (`def` + "four call sites") -- the action prose explicitly says "and no others" after naming exactly three sites, and inventing an unrequested fourth call would violate "the single place that renders auto-mode state" intent. Actual grep count is 4 (1 `def` + 3 calls). Documented here rather than silently forcing the plan's numeric hint.

## Deviations from Plan

None requiring a fix — plan executed as written. Two pre-existing, out-of-scope conditions worth flagging (both predate this plan's diff, confirmed via `git diff --numstat` showing zero deletions on every file this plan touched):

- The plan's acceptance criteria for Task 2 state `grep -nE '^\s*except\s*:' Code/Client/Main.py` should return no matches, and the overall plan-level `<verification>` states no `QMessageBox` should appear anywhere in `Main.py`. Both are already present in `Main.py` before this plan (3 bare `except:` in `receive_instruction`/`connect`'s existing thread-stop cleanup at lines ~490/545/549; `QMessageBox.information(...)` calls already used by the pre-existing `faceWindow`/`calibrationWindow` classes). Per the deviation rules' scope boundary ("only auto-fix issues directly caused by the current task's changes"), these were left untouched — fixing them would be out-of-scope legacy cleanup unrelated to Auto Mode. This plan's own diff introduces zero new bare `except:` and zero new `QMessageBox`/`statusBar()` calls (verified via `git diff` hunk inspection — additions only).
- Task 2's acceptance criteria expects `grep -c "set_auto_status"` to return 5; actual is 4 (see Decisions Made above).

## Issues Encountered

- **Worktree branch mis-based at agent start:** on spawn, `HEAD` (`worktree-agent-a30ab368de8f31ca7`) pointed at an ancient commit (`b7d228c`, an original-repo commit far behind `autonomy`'s tip) instead of branching from `autonomy`'s current tip (`d39f6e5`, which includes plan 01-01's merged work and this plan's own PLAN.md). The working tree was clean and the branch's own history was a strict subset of `autonomy` (merge-base == branch HEAD, zero divergent commits), so `git reset --hard d39f6e5` was used to align the branch with `autonomy`'s tip before any work began, per the `worktree_branch_check`/destructive_git_prohibition allowance for branch-alignment resets at agent startup. No work was lost; this was a pre-existing worktree-creation issue, not something introduced by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Tasks 1-2 are complete, committed, and self-verified against every automated check in the plan (compile, protocol-sync, geometry, colors, wiring, connection guard, no-optimistic-badge). **Task 3 is a blocking `checkpoint:human-verify` gate** requiring an operator with physical access to the real hexapod (2m clear floor or stand, hand near power switch) to run the 8-step walkthrough in `01-02-PLAN.md` (layout check, not-connected guard, happy path, explicit stop, manual-preemption badge flip, timeout badge flip, reconnect state sync, binary-only check). This session cannot execute Task 3 — it requires a human to physically observe the robot and the client's screen. Once Task 3 is approved live, the plan is complete and Phase 01 Wave 3 (plan 01-03, real avoidance sweep/turn) can begin.

---
*Phase: 01-auto-mode-core-walk-avoid*
*Completed: Tasks 1-2 only; plan not yet complete (Task 3 checkpoint pending)*
