# Domain Pitfalls

**Domain:** Reactive obstacle avoidance + boundary/wall-follow patrol, added to an existing teleoperated hexapod robot (single pannable ultrasonic sensor + co-mounted camera, Raspberry Pi, threaded Python control loop, no SLAM/odometry, no dedicated e-stop, operating near pets/kids)
**Researched:** 2026-08-05
**Overall confidence:** MEDIUM — general reactive-avoidance and concurrency failure modes are well documented (HIGH confidence); several findings are grounded directly in this repo's own code (`ultrasonic.py`, `control.py`, `server.py` — HIGH confidence for those); gpiozero `DistanceSensor` no-echo semantics verified against source (MEDIUM-HIGH); household-pet-safety-specific literature is thin, so those recommendations lean on general reactive-robotics and safety-engineering principles (MEDIUM).

## Critical Pitfalls

Mistakes that cause rewrites, hardware damage, or (given this milestone) real risk to a pet, child, or the robot itself.

### Pitfall 1: Treating "no echo" as "path is clear" (ultrasonic false negative on soft/angled/absorptive surfaces)

**What goes wrong:** The robot ignores an obstacle it actually could have detected — a couch cushion, a pet's fur, a curtain, or a shin at a steep angle to the beam — because the ultrasonic sensor never received a return pulse, and the avoidance logic (or the sensor wrapper itself) interprets "no reading" as "nothing there" rather than "unknown / uncertain."

**Why it happens:** Ultrasonic works by specular reflection: soft, fibrous, or foam materials (carpet, pet fur, upholstery, curtains) absorb rather than reflect the pulse, and hard surfaces angled more than ~15-30° off the sensor's boresight bounce the pulse away from the receiver instead of back to it. Both produce the same symptom — no echo — which is indistinguishable at the sensor level from "genuinely nothing within range." In this codebase specifically: `Code/Server/ultrasonic.py` wraps `gpiozero.DistanceSensor`, whose `_read()` returns `None` and raises a `DistanceSensorNoEcho` warning on a failed echo — and the module already does `warnings.filterwarnings("ignore", category=DistanceSensorNoEcho)`, so that warning is silently discarded. `get_distance()`'s own `except RuntimeWarning` is dead code (Python warnings don't raise exceptions unless explicitly configured to), so a no-echo condition surfaces to the caller only as a `None` return — which is easy to write avoidance logic that treats as "not close" rather than "sensor failed to confirm clearance."
**Consequences:** The robot drives into a soft obstacle (a sleeping pet, a child's leg at an angle, a couch) because the closest thing to a "detection" it got was silence, and silence was coded as safe.
**Prevention:**
- Treat `get_distance() is None` (or any read that returns exactly `max_distance`/`None` more than once in a row) as **"unknown," never as "clear."** Unknown readings must not be used to justify increasing speed or committing to a "path ahead is open" decision — only confirmed-clear consecutive readings should.
- Require **N consecutive valid, clear readings** (e.g. 2-3) below a "safe to proceed" distance threshold before treating a direction as clear; require only **one** close reading to trigger a stop/avoid response (asymmetric confidence: fast to distrust, slow to trust).
- Combine with the camera where possible for corroboration on soft/low-reflectivity obstacles the ultrasonic is likely to miss — even simple frame-difference/motion or a coarse "something large fills the lower-center frame" heuristic catches cases ultrasonic structurally cannot.
- Empirically characterize this specific sensor/firmware combo against a pillow, a rug edge, and a person's leg at 30-45° before trusting any threshold in production — do not assume textbook HC-SR04 specs transfer directly.
**Detection (warning signs):** Logging shows intermittent `None`/max-distance readings clustering when the robot is near known soft furnishings; the robot's near-miss/bump events correlate with pets or soft objects rather than furniture edges.
**Phase mapping:** Address in the **sensing/perception phase** (before any avoidance behavior is built on top of raw distance readings) — this is a foundational data-quality issue, not a tuning issue to fix later.

### Pitfall 2: Oscillation/thrashing near obstacles (no hysteresis on the avoidance threshold)

**What goes wrong:** The robot approaches an obstacle, detects "too close," turns away; the new heading now reads "clear," so it turns back toward its original heading, re-detects "too close" a step later, and repeats — visibly juddering/bouncing in place instead of smoothly routing around the obstacle. In corners or between two obstacles it can thrash indefinitely.
**Why it happens:** A single distance threshold used symmetrically for both "trigger avoidance" and "resume normal path" creates a decision boundary the robot's own motion keeps crossing. This is a textbook failure of naive reactive/potential-field avoidance — well documented as force-field oscillation when repulsion and drive forces sit on the same line with no damping.
**Consequences:** Beyond looking broken, thrashing near a pet or child is exactly the "erratic, unpredictable" behavior this milestone explicitly wants to avoid ("behaves cautiously... rather than aggressively"); rapid direction reversals on a hexapod also stress a gait that may not be mid-stride-stable for sudden reversals (see Pitfall 8).
**Prevention:**
- Use **two thresholds with hysteresis**: e.g. trigger avoidance at 25cm, only resume "clear ahead" behavior once distance reads above 40cm (or requires several consecutive higher readings) — never the same number for both directions of the decision.
- On avoidance, commit to a **turn direction and a minimum turn duration/angle** rather than re-evaluating every control tick; re-evaluate only after the committed maneuver completes.
- Add a **stuck/thrash detector**: if the robot has reversed avoidance direction more than N times within a short window, escalate to a different behavior (stop, back up, or turn a larger fixed angle) rather than repeating the same reactive rule.
**Detection:** Watch for rapid alternating turn commands in the command log within a short time window at roughly the same position; visually, robot "vibrates" or shuffles without net displacement.
**Phase mapping:** **Reactive avoidance behavior phase** — this is core algorithm design, not a later tuning pass.

### Pitfall 3: Race condition between manual (TCP) and autonomous command sources writing to `Control.command_queue`

**What goes wrong:** Auto mode and manual teleoperation both need to be able to drive the robot, and per this milestone's requirement, manual control must remain available *at all times*, including during auto mode (it's the safety net in lieu of a dedicated e-stop). If autonomous decision logic and the existing TCP `receive_commands` thread both write into `Control.command_queue` without synchronization, a manual command arriving mid-cycle can interleave with a partially-written autonomous command, producing a queue state neither source intended — e.g. a movement direction from one source paired with a speed/angle field from the other, or a torn read mid-write by `condition_monitor`.
**Why it happens:** This is a **pre-existing, documented condition in this codebase**, not a hypothetical: `Code/Server/control.py`'s `command_queue` is a plain shared list read/written from both the network thread and the always-on `condition_monitor` polling thread with zero locks, relying entirely on GIL atomicity of single attribute writes — which does not make multi-field, multi-statement updates atomic (see `.planning/codebase/ARCHITECTURE.md` "Shared mutable state across threads without locks" and `.planning/codebase/CONCERNS.md`). Adding a *third* writer (the autonomous decision loop) on top of an already-unsynchronized two-writer design compounds an existing hazard rather than introducing a new pattern to guard against from scratch.
**Consequences:** Best case, a glitchy/jerky motion. Worst case: a manual "stop"/override command a human sends because the robot is about to hit a pet gets silently lost, overwritten, or interleaved with an in-flight autonomous "move forward" command — precisely the safety-net path this milestone depends on, since there's no dedicated e-stop.
**Prevention:**
- Do **not** add the autonomous decision loop as a second unsynchronized writer to the existing pattern. Introduce a single **arbitration point**: one lock-protected (or `queue.Queue`-based) command source that both manual and auto write into, with an explicit priority rule — **manual commands always preempt/cancel in-flight autonomous commands**, never the reverse.
- Treat any manual command arriving during auto mode as an implicit "pause/cancel auto-mode's current maneuver" signal, not just a queued next-step.
- This is a good forcing function to fix the underlying `command_queue` locking gap generally (per CONCERNS.md's own recommended fix: `threading.Lock` or `queue.Queue`), since autonomy is the first feature to make the existing hazard load-bearing for safety rather than just a jerkiness bug.
**Detection:** Stress-test by sending manual commands via the desktop client while auto mode is actively issuing avoidance commands; watch for dropped/ignored manual stops, or legs receiving self-inconsistent target angles (visible as a stumble/jerk).
**Phase mapping:** **Concurrency/command-arbitration phase**, ideally sequenced *before* or *alongside* first building the autonomous decision loop — retrofitting locking after auto-mode behavior already exists is riskier than designing the arbitration point up front.

### Pitfall 4: No graceful stop — auto-mode cancellation via unsafe thread-kill can freeze the robot mid-stride in an unstable pose

**What goes wrong:** When auto mode needs to stop (bounded runtime expiry, manual override, error), if the shutdown mechanism abruptly kills the thread driving the gait mid-cycle, the hexapod can be left with some legs mid-swing and others planted — an unstable stance — right at the moment stability matters most (i.e., right when something triggered the stop).
**Why it happens:** This codebase's existing pattern for stopping long-running threads is `Code/Server/Thread.py`'s `stop_thread()`, which uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to asynchronously inject `SystemExit` into a running thread — already flagged in `.planning/codebase/CONCERNS.md`/`ARCHITECTURE.md` as unsafe: it can fire mid-operation, leaving hardware/state inconsistent, and is explicitly called out as "not to be used as a template for new cancellable-thread code." Reusing this pattern for auto-mode shutdown (e.g. to enforce the bounded runtime) would apply an already-known-fragile mechanism to the one scenario where atomicity matters most for physical safety.
**Consequences:** A hard-killed gait mid-stride can tip the hexapod over, potentially near a pet or child, or leave it splayed in a position that stresses servos under load indefinitely (since nothing tells the servos to relax afterward).
**Prevention:**
- Auto-mode's stop signal (whether from bounded-runtime timeout, obstacle-triggered halt, or manual override) must be a **cooperative flag** (`threading.Event`) checked at safe boundaries — ideally at the start/end of each gait step, not injected asynchronously mid-motion.
- Define an explicit "reach a stable stance, then stop" sequence as the normal shutdown path, distinct from "stop immediately regardless of stance" only for genuinely urgent cases (e.g. imminent collision) — and even then, prefer commanding all legs to their nearest stable ground contact rather than freezing mid-air.
- Do not extend `stop_thread()`/`Thread.py`'s SystemExit-injection pattern to the autonomy loop; this is exactly the kind of new cross-thread state CONCERNS.md already warns against building on top of that mechanism.
**Detection:** Manually trigger auto-mode stop (timeout, override) repeatedly during different points of the gait cycle and watch for the robot ending in a visibly unstable/asymmetric stance rather than a settled position.
**Phase mapping:** **Auto-mode lifecycle/safety phase** — needs to be designed alongside the bounded-runtime mechanism itself, not bolted on after.

### Pitfall 5: Bounded-runtime and "safety net = physical access" assumptions break down if the command channel silently dies

**What goes wrong:** This milestone's safety model explicitly relies on "manual control remains available at all times" plus a time-boxed auto-mode runtime, in lieu of a dedicated e-stop. But the existing TCP command channel has a **known, already-documented bug** where it cannot recover from a dropped connection.
**Why it happens:** `Code/Server/main.py` sets `self.server.tcp_flag`, but `Server` only ever reads `self.is_tcp_active` (never set to `True` anywhere) — so the auto-reconnect path in `receive_commands()` is permanently dead code (per CONCERNS.md). Any TCP hiccup during auto mode (Wi-Fi drop, client crash, phone screen lock) causes the command-receiving thread to `break` and stop entirely, requiring a full server restart to regain remote manual control — exactly when a human might urgently want to send a stop/override command.
**Consequences:** If a household Wi-Fi blip happens to coincide with auto mode approaching a pet, the human's expected recourse (manual override from the client) is unavailable, and they're forced to rely purely on physical intervention (picking up the robot) — which is still the documented fallback, but the bounded-runtime timer becomes the *only* automated safety net in that window, and it may not fire soon enough.
**Prevention:**
- Fix (or at minimum, explicitly acknowledge and design around) the `tcp_flag`/`is_tcp_active` bug as part of this milestone if auto mode is going to lean on "manual override always available" as a stated safety property — an autonomy feature that structurally assumes a working reconnect path should not ship on top of a known-broken one without a deliberate decision to accept the risk.
- Independent of the TCP fix: the bounded auto-mode runtime should be enforced **on the server side, locally, independent of any client connection** (a local timer/watchdog inside the auto-mode loop itself, not something that requires the client to send a "stop auto mode" command) — so a dead command channel doesn't also disable the one automated safety net.
- Consider making loss of the command connection during auto mode itself a trigger to stop auto mode (fail-safe on disconnect), rather than continuing to run autonomously with no path for override.
**Detection:** Kill/drop the client connection mid-auto-mode during testing and verify the robot still stops within the bounded time and that manual reconnection is possible without a full server restart.
**Phase mapping:** **Auto-mode lifecycle/safety phase**; the TCP reconnect fix itself may be a small, separate prerequisite phase/step given it's a one-line-diagnosis bug with outsized safety relevance here.

### Pitfall 6: Silent failure via bare `except:` in the new autonomy decision loop

**What goes wrong:** An exception in obstacle-avoidance decision logic (a malformed sensor reading, a `None` distance mishandled in arithmetic, a servo write failure) gets swallowed, and the robot either freezes silently, continues acting on stale data, or — worse — continues issuing whatever the last successfully-computed command was, on a loop, oblivious that its own sensing/decision path has broken.
**Why it happens:** This is the dominant existing error-handling style in the codebase: 16+ bare `except:` blocks across `server.py`/`main.py`/`control.py` that print and continue rather than propagate or log meaningfully (CONCERNS.md). It's the path of least resistance to copy when writing new code in this style, especially for a background polling loop like `condition_monitor`, which today has **no top-level try/except at all** — an uncaught exception there currently kills the entire movement/balance thread outright, silently, requiring app restart.
**Consequences:** For manual teleop this is an annoyance. For an autonomous loop making obstacle-avoidance decisions near pets/kids, a silently-dead or silently-degraded decision loop is a safety issue: the robot may keep walking on the last command it had, or a "detect obstacle → stop" code path may throw before ever issuing the stop.
**Prevention:**
- The autonomy decision loop must have **its own explicit, narrow exception handling** — catch specific expected failure types (e.g. a `None` sensor reading, an out-of-range servo command) and handle them with an explicit "treat as unknown/unsafe" fallback, not a bare `except: pass`.
- Any *unexpected* exception in the autonomy loop should trigger a **fail-safe stop**, not a silent continue — the default behavior on "I don't know what just happened" must be "stop moving," never "keep doing whatever I was doing."
- Add actual logging (even just structured `print` with timestamps, given no logging framework exists yet) specifically around the autonomy loop, since debugging a field failure after the fact is otherwise impossible in this codebase (no test suite, no logs).
**Detection:** Code review flag: any `except:`/`except Exception:` in new autonomy code without an explicit fail-safe action and a log line. Inject a fault (e.g. temporarily disconnect the ultrasonic sensor) during testing and confirm the robot stops rather than continuing blind.
**Phase mapping:** **Reactive avoidance behavior phase** and **patrol phase** both — apply as a standing code-review rule for all new autonomy code, not a one-time fix.

## Moderate Pitfalls

### Pitfall 7: Shared pan/tilt head means the camera and ultrasonic sensor cannot independently aim — "scanning" trades off against "looking where you're walking"

**What goes wrong:** Because the ultrasonic sensor and camera are both rigidly co-mounted on the same 2-axis head (servos 0/1), any behavior that pans the head to scan for a clear direction (e.g. sweeping wall-follow, "look before turning") simultaneously points the camera away from the direction of travel. A design copied from projects that scan independently, or that assume the camera always faces forward, will silently create a real forward blind spot during every scan.
**Why it happens:** Easy to overlook if avoidance logic is designed sensor-first ("sweep the ultrasonic across N angles to find the clearest heading") without accounting for the fact that the camera — the only other sensing modality available for corroboration (Pitfall 1) — goes blind to the front exactly during that sweep.
**Prevention:** Design scanning behavior as brief, bounded sweeps (not continuous), return the head to forward-facing as the default resting state between decisions, and treat "currently mid-sweep" as a state where forward speed should be reduced/held rather than assuming continued forward progress is safe just because the last forward-facing reading was clear.
**Phase mapping:** **Reactive avoidance / patrol phase**, when head-scanning behavior is first designed.

### Pitfall 8: Sensor-to-actuation latency makes avoidance decisions act on stale distance data

**What goes wrong:** `Ultrasonic.get_distance()` is a blocking, synchronous read; if it's called from inside a busy-poll style loop (matching this codebase's existing `condition_monitor` pattern — see CONCERNS.md's "busy-wait polling" performance note) alongside head-pan servo motion and gait stepping, the distance value driving a given decision may be tens to hundreds of milliseconds old by the time a movement command actually executes. For anything moving toward the robot (a pet, a child) rather than static, this gap matters far more than for static-obstacle avoidance the algorithm may have been implicitly designed around.
**Prevention:** Keep the sense→decide→act loop as tight and consistently-timed as practical; bias safety margins to account for a fast-moving target covering real distance within the loop's worst-case latency, not just its average; avoid adding unrelated blocking work (e.g. long head sweeps, slow gait phases) between a sensor read and the corresponding movement command.
**Phase mapping:** **Reactive avoidance behavior phase.**

### Pitfall 9: Aggressive in-place turning or reversal during avoidance stresses hexapod gait stability

**What goes wrong:** A hexapod's static/dynamic stability depends on which legs are in stance vs. swing phase at a given moment; a reactive avoidance rule that issues an abrupt direction reversal or sharp turn without regard to gait phase can command a transition while too few legs are grounded for it to be stable, risking a stumble or tip — worse on carpet/uneven flooring than the hard flat surfaces gait tuning is typically validated on.
**Why it happens:** `Control`'s gait/kinematics layer (per ARCHITECTURE.md) has no explicit state machine gating "is it currently safe to change direction" — `condition_monitor` just polls `command_queue` and reacts. An avoidance rule bolted on without awareness of gait phase inherits this gap.
**Prevention:** Route avoidance-triggered direction changes through the same command path normal teleop turns use (so existing gait-phase handling, if any, applies uniformly) rather than a shortcut path; avoid designing avoidance logic that assumes instantaneous direction reversal is safe at any point in the stride.
**Phase mapping:** **Reactive avoidance behavior phase.**

### Pitfall 10: Over-trusting a single ultrasonic ping leads to lurching, not smooth motion

**What goes wrong:** A momentary specular dropout (Pitfall 1's mechanism, but transient rather than persistent) produces one "clear" reading sandwiched between two "obstacle" readings; if the avoidance/patrol logic reacts to every individual reading rather than a smoothed/debounced signal, the robot can visibly lurch forward for one control tick before re-detecting the same obstacle.
**Prevention:** Apply a short rolling median/average (not just gpiozero's built-in queue smoothing, which already discards `None`s but still averages noisy real readings) before feeding distance into the decision layer; require the "safe to proceed" signal to be stable across a short window, not a single sample.
**Phase mapping:** **Sensing/perception phase.**

### Pitfall 11: Reactive obstacle avoidance has no model of moving targets — pets and kids don't behave like walls

**What goes wrong:** Wall-follow/bug-style reactive algorithms are designed around the assumption that obstacles are static; a pet or child walking *toward* the robot invalidates that assumption. The robot will only react once the moving obstacle is already inside the detection threshold, with no anticipation, and — because avoidance logic is typically tuned for "route around a stationary object" — it may attempt a sideways skirting maneuver that walks it *toward* a target that has since moved into the new path, rather than simply stopping.
**Prevention:** For this specific safety context (pets/kids, no e-stop), bias the default reaction to "stop and wait" rather than "immediately maneuver around" when an obstacle is detected at close range and there's no strong signal it's stationary (e.g. it wasn't there on the previous scan). Reserve active maneuvering-around behavior for patrol/wall-follow against known-static boundaries (walls, furniture) where the assumption actually holds; keep the reactive-avoidance-of-unknown-obstacles behavior conservative by default.
**Phase mapping:** **Reactive avoidance behavior phase** — this should shape the core avoidance policy, not just a parameter tweak.

## Minor Pitfalls

### Pitfall 12: Demo-clean-room testing doesn't surface real-home failure modes

**What goes wrong:** Avoidance/patrol tuned and validated in an open, obstacle-sparse test area (typical for quick iteration) looks solid, then fails against real household clutter it was never exposed to: low coffee-table legs below the ultrasonic's mounting height, thin cords/cables the beam passes over, rug edges that change gait dynamics underfoot, pet food bowls, or a sleeping pet lower than the sensor's beam.
**Prevention:** Include low-profile and beam-height-relevant obstacles in test scenarios explicitly, not just "put a box in front of the robot"; test at the actual pan/tilt head height the sensor will run at during patrol, since a fixed head angle chosen for open-floor testing may aim over low obstacles entirely.
**Phase mapping:** **Field-testing/tuning phase**, but the *test plan* for it should be written during the reactive-avoidance design phase so blind spots aren't discovered only after the behavior ships.

### Pitfall 13: Unvalidated `CMD_HEAD` values reused by autonomy code could exceed safe servo range

**What goes wrong:** If autonomous scanning logic computes pan/tilt angles programmatically (e.g. sweeping through a range) and reuses the existing `CMD_HEAD` handling path, it inherits a known gap: `Code/Server/server.py`'s `CMD_HEAD` handler passes angle values straight to `Servo.set_servo_angle()` with no clamping (unlike `CMD_CAMERA`, which does clamp via `restrict_value`). A logic bug in the sweep bounds (off-by-one, wrong sign) could command an out-of-range angle and risk mechanical/servo damage.
**Prevention:** Clamp any programmatically-generated head angles in the new autonomy code itself before dispatch, rather than relying on the existing `CMD_HEAD` path to reject bad values — it currently doesn't.
**Phase mapping:** **Sensing/perception phase**, when head-sweep logic is implemented.

### Pitfall 14: No automated tests means avoidance-threshold regressions ship silently

**What goes wrong:** The avoidance decision logic (distance thresholds, hysteresis bounds, state transitions) is exactly the kind of pure logic that's easy to accidentally regress (e.g. loosen a threshold while refactoring) with no test suite to catch it, given this codebase has zero automated tests today.
**Prevention:** Even without hardware-in-the-loop testing, the avoidance *decision function* (given a distance reading and current state, what command results) can and should be written as pure, hardware-independent logic with unit tests that mock sensor input — this is explicitly called out as feasible and high-priority in `.planning/codebase/CONCERNS.md` for the existing kinematics code, and the same argument applies even more strongly to new safety-relevant decision logic.
**Phase mapping:** **Reactive avoidance behavior phase**, as the logic is first written — not retrofitted later.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Sensing/perception (ultrasonic + camera integration) | Ultrasonic false negatives on soft/angled surfaces (P1); single-ping lurching (P10); unclamped head-sweep angles (P13) | Treat no-echo/None as "unknown," require consecutive confirmations, clamp servo angles locally |
| Concurrency / command arbitration | Manual vs. auto race on `command_queue` (P3) | Single lock-protected or `Queue`-based arbitration point; manual always preempts auto |
| Reactive avoidance behavior design | Oscillation/thrashing (P2); gait-phase-unaware turning (P9); no moving-target model (P11); silent exception swallowing (P6); untested decision logic (P14) | Hysteresis + committed maneuvers; route through existing turn/gait path; default to stop over maneuver-around for unknown/close obstacles; explicit fail-safe exception handling; unit-testable pure decision function |
| Patrol / wall-follow | Shared-head scan-vs-look tradeoff (P7); sensor latency (P8) | Bounded sweeps with forward-resting default; tight sense-decide-act loop |
| Auto-mode lifecycle & safety (bounded runtime, no e-stop) | Unsafe thread-kill on stop (P4); dead TCP reconnect breaking the "manual override always available" safety property (P5) | Cooperative `threading.Event`-based stop reaching a stable stance; local server-side bounded-runtime enforcement independent of client connection; consider fixing/acknowledging the `tcp_flag`/`is_tcp_active` bug as a prerequisite |
| Field testing / tuning | Clean-room testing missing real-home clutter (P12) | Explicit low-profile/beam-height obstacle test plan written during design, not after |

## Sources

- [Obstacle Avoiding Robot with Arduino & Ultrasonic Sensor — Zbotic](https://zbotic.in/obstacle-avoiding-robot-with-arduino-ultrasonic-sensor/) — soft-material absorption / angled-surface specular miss, MEDIUM confidence (single hobbyist source, consistent with general acoustic reflection physics)
- [Obstacle Avoiding Robot Using Arduino and Ultrasonic Sensor — IJFMR](https://www.ijfmr.com/papers/2026/3/79205.pdf) — general ultrasonic obstacle-avoidance robot design patterns, MEDIUM confidence
- [Obstacle detection using ultrasonic sensor for a mobile robot — IOPscience](https://iopscience.iop.org/article/10.1088/1757-899X/707/1/012012) — ultrasonic detection limitations, MEDIUM confidence
- [gpiozero DistanceSensor source (`input_devices.py`)](https://gpiozero.readthedocs.io/en/stable/_modules/gpiozero/input_devices.html) — verified no-echo returns `None`, `SmoothedInputDevice` ignores `None` in averaging, HIGH confidence (primary source, matches this project's actual dependency)
- [gpiozero/gpiozero GitHub issue #903 — "Distance sensor script hangs when sensor is disconnected"](https://github.com/gpiozero/gpiozero/issues/903) — corroborates no-echo/disconnected-sensor edge cases, MEDIUM confidence
- Force-field/potential-field oscillation near obstacles — general reactive-robotics literature (ScienceDirect: "An obstacle avoidance algorithm for robot manipulators based on decision-making force"; multiple corroborating academic sources on repulsion/drive-force oscillation), MEDIUM-HIGH confidence (well-established, multi-source)
- Bug algorithm / wall-following reactive navigation fundamentals — general robotics literature (arXiv: "Intelligent Bug Algorithm (IBA)"; ScienceDirect comparative bug-algorithm study), MEDIUM confidence
- `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md` — direct codebase analysis of this repo's threading model, error handling, and known bugs (`command_queue` race, `tcp_flag`/`is_tcp_active` dead reconnect, `stop_thread()` unsafe cancellation, bare `except:` prevalence, unclamped `CMD_HEAD`), HIGH confidence (primary source, this exact codebase)
- `Code/Server/ultrasonic.py`, `Code/Server/control.py`, `Code/Server/server.py` — direct code reading, HIGH confidence
- Household-robot/pet-safety-specific literature (e.g. arXiv "Designing Multispecies Worlds for Robots, Cats, and Humans," "Field Notes on Deploying Research Robots in Public Spaces") — general safety posture context, LOW-MEDIUM confidence (directionally relevant, not hexapod/ultrasonic-specific)
