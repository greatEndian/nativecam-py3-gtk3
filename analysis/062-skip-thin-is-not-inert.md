# 062 — `_pl_skip_thin` is not inert; it is blind at window boundaries

2026-08-24. `liveTooling`, on top of the uncommitted 061 work.

## What was asked

Pick up the open point recorded by `analysis/061`: *"`_pl_skip_thin` IS INERT —
the shipped 'Skip thin roughing passes' setting drops nothing"*, measured there
as **18 levels with the threshold against 18 without** on `testing_15_2`. The
suspected mechanism, recorded as a hypothesis and explicitly not shown, was the
`#<_pl_prev_lvl> = #<stock_r>` reset at `poly_lathe_mill.ngc:649`.

## What was measured

`testing_15_2`, `param_pass_from=1` (Final contour), `param_n_comp=1`,
Sectioning on. Stock radius **30.0000**, doc `#<_rough_cut>` = 0.5080.

| threshold | levels | stock → first gap | min in-ladder gap | max gap |
|---|---|---|---|---|
| 0.000 (off) | 18 | 0.3480 | 0.5080 | 0.5080 |
| 0.254 (`doc/2`) | 18 | 0.3480 | 0.5080 | 0.5080 |
| **0.400** | **17** | 0.8560 | 0.5080 | 0.5080 |
| 0.450 | 17 | 0.8560 | 0.5080 | 0.5080 |
| 0.600 | 13 | 0.8560 | 0.5080 | **1.0160** |

**The setting works.** At 0.400 the 29.6520 envelope level is dropped and every
surviving gap is still a whole depth of cut. The threshold reaches the `.ngc`
correctly — `#<_pl_skip_thin> = 0.254000` is in the generated file.

**It dropped nothing at `doc/2` because nothing was eligible.** Every gap in
that ladder is exactly 0.5080, and the only gap smaller than a whole step is the
stock → first level handover at **0.3480**, which is *above* 0.2540. Removing
nothing was the correct answer to the question asked.

So the recorded finding was wrong, and the test that produced it was asserting
a drop the geometry never warranted.

## But the hypothesis was right, on a different project

`testing_15_6`, defaults, Sectioning on. Thinnest gap **0.2591** — the phase-2
ceiling pass of `analysis/061`, the one at 0.51 × doc.

| threshold | levels | min gap |
|---|---|---|
| 0.000 | 29 | 0.2591 |
| 0.254 | 29 | 0.2591 |
| **0.300** | **29** | **0.2591** |
| **0.350** | **29** | **0.2591** |

A 0.350 threshold against a 0.2591 gap and the level survives. That is the
`:649` reset, confirmed by measurement rather than by reading: the ceiling pass
is the FIRST level of its phase-2 window, `_pl_prev_lvl` has just been reset to
`stock_r`, and the level is judged 4.6 mm thick instead of 0.2591 mm.

**The precise fault is not "inert" but "blind exactly where thin passes come
from".** Within a window every step is a whole doc and nothing is ever eligible;
the thin passes this project actually produces are window handovers, and those
are the ones the check cannot see. The setting fires only on the stock envelope,
where the reset happens to be telling the truth.

## Why this matters less than it did

greatEndian ruled **SPREAD, not drop**, on 2026-08-24. The uncommitted 061
change removes the ceiling thin pass structurally by dividing the phase-2 span
evenly, so the blindness no longer has a live symptom on these projects. It is
still a real gap in a shipped user setting, and it is now measured rather than
suspected.

Repairing it is still not free, for the reason 061 recorded:
`lathe_level_pass.ngc:999` computes the retract from `_pl_prev_lvl`, so carrying
the true previous level across a window boundary lowers the retract into a band
that may still hold uncut stock. The fix is to **separate the two uses** — a
per-region thickness reference for the thin check, and a safe-radius reference
for the retract — not to change what `:649` assigns.

## A second fault found on the way

**A threshold larger than the depth of cut halves the ladder.** At 0.600 with
doc 0.508: 13 levels and a **1.0160** gap, two whole depths of cut. The check
measures against the last level actually cut, so level N is thin and skipped,
prev stays put, level N+1 is 1.0160 away and is kept — it alternates. Gaps past
the doc against a part surface is the failure `test_x_continuity` exists to
prevent.

`cfg/lathe/polyline.cfg:76` sets `minimum_value = 0.0` and no maximum, so a user
can type it. Not fixed here; recorded in `openPoints.md`.

## Why it was not caught earlier

`test_ladder`'s control was `len(tl) < len(base)` at a hard-coded `doc/2` — an
uncalibrated threshold on a ladder whose thinnest gap is above it. It could only
ever pass by luck, and when it went red it produced a wrong diagnosis rather
than a wrong-test signal. Replaced with a control calibrated off the ladder it
runs on: read the thinnest real gap including the invisible stock handover,
assert nothing drops below it, then assert the right level and only the right
level drops just above it, capped under a whole depth of cut so the alternating
mode above cannot be mistaken for success.

## What is still unknown

- **Whether any project produces a thin pass at a window boundary that spread
  does not already fix.** Not seen on 15_2 or 15_6 after the 061 change.
- The retract separation above is designed but not built.
