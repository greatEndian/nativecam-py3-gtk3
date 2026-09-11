# 129 — the coverage sweep is not rebuilt: it is superseded, not just blocked

**Asked**: openPoints "THE COVERAGE SWEEP STILL NEEDS REBUILDING ON THE SETTLED
FRAME" (analysis/123 settled which frame `build_stop_contour_gcode` emits).
Explicit condition on doing this work at all: read `test_leftover.py` and
`test_x_continuity.py` first, and if this instrument can't be stated as
measuring something they don't, say so and stop rather than build a third
overlapping one.

## What the classic coverage sweep did

Per the historical uses recorded in openPoints (2026-08-30, the false 9-gap
alarm; the boss-front-gaps close, 18→16 on `testing_15_9`): sample Z, and for
each roughing **level** ask whether the recorded floor position (read back
from the `_pl_stop_*`/flank tables `build_stop_contour_gcode` emits) is
actually **reached** by some generated cut. It never existed as a committed
`test_*.py` — every use of it was ad hoc, and the false alarm it produced is
exactly what left it untrusted (comparing a control-point table against a
contact-frame assumption, or vice versa, reports a phantom gap of exactly the
nose term, `_pl_rgh_oz`).

## What the two existing gates already do, read in full

- **`test_leftover.py`**: builds a physical `StockField`, sweeps the REAL
  nose along every real roughing move on it, and samples Z from
  `min(target_z)` to `max(target_z)` in fixed `STEP` asking whether the
  remaining outer radius exceeds the true target by more than one depth of
  cut. The target is the programmed contour from an **Off-mode run** — nose
  comp forced off — which is deliberate and sidesteps the frame question
  entirely rather than resolving it: there is no control-vs-contact ambiguity
  because there is no comp on the comparison side at all. Its own docstring
  states the one thing it cannot see: a single missing pass, on most
  geometry, because a shallow redundant pass leaves no trace and a genuinely
  narrow gap is thinner than `MIN_RUN`.
- **`test_x_continuity.py`**: for every real generated level, finds the next
  level down that overlaps it in Z over the SAME disjoint region and asserts
  the step between them is at most one depth of cut. This is exactly the gate
  the file's own docstring says exists **because** of `test_leftover`'s blind
  spot — it is what actually caught the missing pass behind the boss on
  `testing_15_6`, not `test_leftover`.

Both are already Z-sampled coverage checks. Both are already gated in CI on
every commit. Both are already proven against the specific historical bugs
the classic coverage sweep was invented to find — the boss-front gaps are
closed and `test_leftover` control sits at 24/24 since that fix.

## The honest comparison

A rebuilt coverage sweep, done correctly on the settled frame, would sample Z
and ask "does the real cut reach the stop-contour table's floor here" —
which is a weaker question than `test_leftover`'s, not a different one:

- It compares against an **intermediate per-level table**, itself built by
  Python from the same profile the real target is built from. `test_leftover`
  compares against the **real final target** directly, with the real nose
  physically swept, which is what actually removing too little metal means.
  Anything a floor-table comparison could catch that survives to become a
  real problem shows up as real leftover metal — which is exactly what
  `test_leftover` samples for, at finer resolution (`STEP`) and without ever
  needing to resolve which frame a table is in, because sweeping real tool
  moves against a real target has no frame question to resolve.
- Its per-level framing (does THIS level reach) is not more precise than
  `test_x_continuity`'s adjacent-level step check for the failure mode it
  actually exists to catch — a level silently missing from the ladder. A
  missing level is exactly an oversized step to whatever ended up below it,
  which `test_x_continuity` already asserts against, matched by overlap in Z
  the same way region-splitting makes necessary for a rebuilt sweep too.

I cannot state a concrete failure that would pass both `test_leftover` and
`test_x_continuity` and be caught by a stop-contour-table coverage sweep. Every
route to "roughing didn't reach far enough" that the classic sweep watched for
either shows up as real leftover metal (caught by `test_leftover`) or as an
oversized step to the next real level (caught by `test_x_continuity`) — and
both catch it without the frame question the classic sweep could not get past
in the first place. Rebuilding it on the settled frame would reintroduce a
strictly weaker, frame-fragile signal for a question two more robust, already
-gated instruments already answer.

## Stopping here, per the standing instruction

This is the explicitly pre-authorized outcome, not a shortfall: "if it can't
articulate what the sweep measures that test_leftover and test_x_continuity
don't, building it is motion rather than progress." No file was written, no
generated output touched. `openPoints.md` records this as reasoned-and-
declined rather than leaving the open point either "done" (nothing was built)
or silently dropped.

## One adjacent, genuinely open gap — noted, not built

Reading `test_surface_equality.py` in full for this comparison surfaced a real
gap it names itself: it checks the flank table (`_pl_env_*`, 3600) contains
the finishing contour (`_pl_fc_*`, 4000), and its own "WHAT IS NOT COVERED"
section says the stop contour (`_pl_stop_*`, 4400) — a third surface, the
pre-finish contour — "is not compared here." That table is exactly the one
whose frame analysis/123 settled. Whether the stop contour ever sits INWARD of
the finish contour (i.e. roughing eating into the pre-finish allowance, an
over-cut rather than an under-cut) is not asserted by any committed test today.
This is a different question from "the coverage sweep" as asked — over-cut
containment, not under-cut coverage — and building it was out of scope for
this task without it being asked for. Recorded here so it is not
rediscovered from nothing; not written to openPoints.md as a new open point
since that is greatEndian's call on whether it is worth doing at all, not a
gap this task was asked to close.
