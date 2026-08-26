---
spike: 003
name: problem-surface-failure-modes
type: standard
validates: "Given each sensor's own proven-reliable operating zone (ultrasonic: full range 10-100cm+; VL53L1X: near-field <=60cm), when tested against real household surfaces (soft/angled/low-profile for ultrasonic; glossy/dark/glass for VL53L1X), then characterize failure modes within-zone rather than a symmetric full-range comparison"
verdict: PARTIAL
related: [001, 002]
tags: [hardware, reliability]
---

# Spike 003: Problem-Surface Failure Modes

## What This Validates

Given each sensor's own proven-reliable zone (established by spike 002: ultrasonic
full-range 10-100cm+, VL53L1X near-field only <=60cm), when tested against real household
surfaces that are known problem cases for each sensing technology, then characterize what
actually happens -- not whether the sensor works in ideal conditions (already proven), but
how it fails when it fails.

## Research

No new libraries -- reuses the exact `Ultrasonic` (`Code/Server/ultrasonic.py`) and
`VL53L1X` (Pimoroni library) wrappers established in spikes 001-002, with the same
`open(reset=True)` + medium-mode + 140ms-timing-budget configuration spike 001/002 already
validated as correct. No context7/web research needed.

**One relevant finding surfaced while re-reading `ultrasonic.py` for this spike:**
`Ultrasonic.__init__` calls `warnings.filterwarnings("ignore", category=DistanceSensorNoEcho)`,
which suppresses gpiozero's no-echo warning entirely rather than raising it. That means
`get_distance()`'s `except RuntimeWarning` branch is effectively dead code in this
codebase's actual runtime configuration -- a true no-echo condition doesn't return `None`,
it silently returns `max_distance` (300cm, i.e. reads as "clearly nothing there"). This is
exactly the mechanism the `soft_fabric_*` segments below are designed to probe: if a soft
surface absorbs the ping instead of reflecting it, the sensor may report the same 300cm
"all clear" as truly open space, at any distance -- including well inside the stop
threshold.

## How to Run

```
cd .planning/spikes/003-problem-surface-failure-modes
sudo python3 -u test_ultrasonic_surfaces.py    # 7 segments, ~70s + positioning time
sudo python3 -u test_vl53l1x_surfaces.py       # 7 segments, ~70s + positioning time
```

Each script walks through segments interactively: it names the surface/distance to set up,
you position the real object and press Enter, it logs ~10s of readings, then moves to the
next segment. `Ctrl+C` at any point saves the partial log and exits cleanly.

## What to Expect

**Ultrasonic** (`ultrasonic_surfaces_log.csv`): baseline hard-flat segment should match
spike 002's known-good accuracy. The two `soft_fabric_*` segments are the key risk --
watch for readings clamped at/near 300cm while a real obstacle is present. `angled_hard_*`
and `low_profile_*` segments test specular deflection and narrow-target detection.

**VL53L1X** (`vl53l1x_surfaces_log.csv`): baseline matte-hard segment should match spike
002. `glossy_reflective_*` and `glass_mirror_*` segments risk either `Signal Fail`/
`Phase Fail` status strings or (more dangerous) a confidently-wrong `Range Valid` reading,
per spike 002's phase-wrap-around finding. `dark_absorptive_*` segments risk weak-signal
failure from low IR return.

## Observability

Both scripts print live readings to stdout as they run and write the same data to CSV
(`timestamp, segment, distance_desc, distance_[cm|mm], [status]`) for post-hoc analysis --
no separate forensic log layer needed given the low data volume (7 segments x ~50 samples
each, human-paced).

## Investigation Trail

Both scripts were run to completion (7 segments each, ~10s/segment). Analyzed via the raw
CSVs (`ultrasonic_surfaces_log.csv`, `vl53l1x_surfaces_log.csv`) rather than relying on the
live printed summaries, since segment-by-segment stats and the raw sample-to-sample sequence
turned out to matter more than the aggregate numbers.

**Methodology caveat surfaced immediately:** unlike spike 002, these segments were
hand-positioned against a description ("~30cm") rather than tape-measured. Several segments
show a smooth, continuous drift across their full 10s window (e.g. `baseline_hard_flat_30cm`
drifting 36.6cm -> 31.8cm; `baseline_matte_hard_30cm` settling at ~93mm/9.3cm, nowhere near
the intended 30cm) consistent with a held object not staying perfectly still, or an
initial distance that didn't match the label. This means the *specific* target distances in
each segment name shouldn't be trusted as ground truth -- but it doesn't undermine the
sensor-behavior comparisons below, since both smooth-drift (real repositioning) and
sharp/chaotic jumps (sensor instability) are clearly distinguishable in the raw data, and
that distinction is what this spike actually cares about.

**1. Ultrasonic: no catastrophic failures on any tested surface.** Across all 7 segments
(`baseline_hard_flat_30cm`, `soft_fabric_15cm`, `soft_fabric_30cm`, `angled_hard_30cm`,
`angled_hard_50cm`, `low_profile_20cm`, `low_profile_40cm`) there was not one instance of the
feared "silent 300cm clear" (the `DistanceSensorNoEcho`-suppression risk flagged in Research)
-- every soft-fabric reading tracked a real, changing, plausible distance the whole time,
including 8.8cm at its closest. The soft surfaces did **not** absorb the ping into silence.
`angled_hard_30cm` was the noisiest segment (stdev 5.6cm vs. 0.8-2.9cm elsewhere) but even
that traces to a smooth downward drift (30.0 -> 26.4cm over ~3s) rather than erratic jitter --
more likely hand movement than a sensor artifact. Every value across every ultrasonic
segment was a plausible, continuously-tracking number; none were clamped, `None`, or wildly
discontinuous.

**2. VL53L1X: near-field segments (~20cm) were clean; ~45cm segments were not -- for every
surface type tested.** This is the spike's real finding, and it cuts across surface material
rather than being specific to one:

- `glossy_reflective_20cm`, `glass_mirror_20cm`: zero failure-status frames across 47 samples
  each (all `Range Valid`), values track smoothly even as the target visibly moved
  (`glass_mirror_20cm` settles tightly around 190-210mm after an initial approach).
- `glossy_reflective_45cm`, `glass_mirror_45cm`, `dark_absorptive_45cm`: all three show
  explicit `Signal Fail` / `No Update` frames (1-5 per 47-sample segment) AND, more
  tellingly, **multi-modal jumping between distinct stable plateaus within the same
  segment** rather than smooth tracking. `glossy_reflective_45cm` sits at ~119-193mm for 6
  samples, jumps to ~457-495mm for 9 samples, drops through a `No Update`, then resettles at
  ~390-414mm -- three separate "stable" plateaus in one 10s window with no smooth
  interpolation between them, which is a materially different signature from the smooth
  single-slope drift seen in the ultrasonic segments and in `baseline_matte_hard_30cm`.
  `glass_mirror_45cm` was the worst case: 5 explicit failure frames out of 47 (~11%) and
  continuous plateau-jumping (298mm / 371mm / ~450-500mm / 421mm) for the entire segment --
  it never fully settled.
- `dark_absorptive_45cm` additionally produced one genuinely alarming reading: a `Range
  Valid`-status frame reporting **0mm**, sandwiched between a `No Update` and a `Signal
  Fail`, during a ~1s burst where consecutive "valid" readings swung 55 -> 86 -> 38 -> 36 ->
  105 -> 115mm before settling. A status of `Range Valid` is supposed to mean "trust this
  number"; here it didn't.
- `dark_absorptive_20cm` sits in between: mostly clean (a tight ~74-82mm plateau for the
  first 2/3 of the segment) but with one `Signal Fail` at the very start and a second
  turbulent stretch near the end (64 -> 40 -> 33 -> 44mm, then a `Signal Fail`, then
  resettling at ~118mm) -- less severe than the 45cm segments but not perfectly clean either.

**3. The failure direction stayed safety-conservative, consistent with spike 002.** Every
unstable VL53L1X reading observed here -- the 0mm frame, the plateau jumps, the explicit
failure codes -- either under-reported distance (looks closer than reality) or was flagged as
a failure. None of the instability produced a falsely *far*/clear reading that would mask a
real close obstacle. That property held in spike 002 and holds again here.

## Results

**Verdict: PARTIAL.** Real, useful findings came out of this, but the segment-distance
labels aren't reliable ground truth (see methodology caveat), so treat the *qualitative*
comparisons here as solid and the specific mm/cm numbers as approximate.

- **Ultrasonic showed no surface-specific failure mode in this test** -- not for soft/
  absorptive, not for angled, not for low-profile targets. The one hypothesis this spike was
  specifically designed to probe (soft surfaces silently absorbing the ping into a false
  300cm "clear" reading, since `ultrasonic.py` suppresses the no-echo warning) did not occur.
  This is reassuring but not a full clearance: 15cm and 30cm against pillow/blanket at a
  ~90deg incidence angle were tested; a soft surface at a sharper angle, or a genuinely
  echo-dead material (heavy acoustic foam), was not.
- **VL53L1X's instability is range-triggered, not surface-triggered** -- the ~20cm segments
  were clean for every surface type including glass and dark cloth (the two "hardest"
  surfaces), while the ~45cm segments were unstable for every surface type including plain
  glossy material. This generalizes spike 002's phase-wrap/SNR finding: it isn't "avoid
  glossy/dark/glass," it's "the closer you are to the ~50-60cm reliability ceiling, the more
  any surface's SNR margin gets eaten, and difficult surfaces just make that happen sooner/
  worse than a matte-hard target would." The practical implication for the near-field
  cross-check role from spike 002 is to keep VL53L1X's effective working band well clear of
  its ceiling -- e.g. limited to the existing 20-35cm stop/resume band, not stretched out
  toward 45-60cm, if difficult surfaces are in play.
- **The one genuinely new safety-relevant finding**: a `Range Valid`-status reading of 0mm
  occurred once (`dark_absorptive_45cm`). If VL53L1X is ever wired into production
  arbitration logic, a raw `status == "Range Valid"` check is not sufficient on its own --
  worth sanity-bounding the distance value itself (e.g. reject implausible near-zero jumps
  inconsistent with the previous reading) rather than trusting the status string alone. This
  is a candidate item for spike 004's arbitration sketch.

## Signal for Later Spikes / the Real Build

- Ultrasonic needs no special-casing for soft/angled/low-profile surfaces based on what was
  tested here -- it stayed within the behavior already characterized in spike 002.
- If VL53L1X is integrated as a near-field cross-check (per spike 002's inverted framing),
  keep it constrained well inside its proven-clean zone (this spike suggests <=20-30cm is
  safest, not the full <=60cm range spike 002 called "reliable") and never trust a `Range
  Valid` status alone -- add a plausibility/continuity check on the value itself. Feed this
  into spike 004's arbitration design.
