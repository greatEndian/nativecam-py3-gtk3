# 022 — One roughing floor per region of the profile

2026-08-08, branch `liveTooling`, from `b08ac38`.

## What was asked

greatEndian: *"fix it, floor has to follow the profile per region"* — the
`openPoints` item that several of the previous session's fixes were working
around.

## The bug, in one line of arithmetic

A roughing level is **one radius held across its whole sweep**, and the ladder
of levels is anchored on a floor. That floor came from `final_radius`, the
polyline's Final Diameter — the deepest point of the WHOLE part — so every
region that is not the deepest had its levels positioned by somebody else's
floor.

On `testing_15_4` (`_rough_cut` 0.508, f_off 0.508, pf_off 0.254, anchored):

| region | Z span | own deepest | own floor |
|---|---|---|---|
| chamfer | 0 … −1 | r19 | **20.016** |
| cylinder | −1 … −20 | r20 | **21.016** |
| boss | −20 … −32.5 | r20.707 | **21.7227** |
| far cylinder | −32.5 … −70.4 | r20 | **21.016** |

21.016 − 20.016 = **1.000**, and 0.508 does not divide 1.000. **No single grid
can land on both**, so whichever floor the ladder is anchored on, the other is
missed — the cylinder's deepest level came out at 21.032, 0.016 above where it
was entitled to stop.

That single fact is the whole bug, and it is why the symptoms looked unrelated:
a chamfer pass that only grazes, a cylinder level a hair off its own contour.

## What was tried first, and why it was wrong

**Per-region WINDOWS.** Split the profile into floor regions and give each its
own Z window and ladder — a full-length phase down to the shallowest floor,
then region-by-region below it. Built, and abandoned: `testing_15_4` has
Sectioning **on**, and the window that actually cuts (`Z0…−32.5`, band
r20…r32.659) spans the chamfer AND the cylinder, so a per-window floor cannot
separate them. Splitting that window instead would have turned one sweep per
level into two with a retract between — a traversal change greatEndian did not
ask for.

**Per-window floors on the sectioned path.** Same dead end for the same reason,
plus it would have re-introduced the failure the existing code already warns
about: *"a ladder PER WINDOW is worse still - the seven section windows start
at different radii, so their levels miss each other by 0.006."*

## What it actually needed

**The ladder does not need to know WHERE each floor applies.** A level that
drops past a region's floor cannot reach that region any more — the stop
contour holds it off — so the Z span narrows by itself. What the ladder must do
is **land on each floor**, and it can do that by re-anchoring as it descends.

So: Python emits the list of floors the profile is entitled to, shallowest
first (`floor_ladder`, `#3300+i`), and the level loop re-anchors at each in
turn. **No windowing change, no traversal change** — the sweep order is exactly
what it was.

`region_floor` reproduces `poly_lathe_mill`'s own arithmetic deliberately
(`rough_target` → `step_target` → the anchored grid), because a floor the
ladder cannot land on would be worse than no table at all.

**The first stage keeps the window's own ladder and only retargets it.** Every
later stage is anchored on the floor above, which is a global number, so every
window walks an identical grid. Anchoring the first stage on the window's own
start radius was tried and is wrong: the windows start at different radii, and
the levels came out **0.0118 apart** — pairs of passes where the part should
have had one. That is the same failure the old comment warned about, reproduced
by hand and then removed.

## Measured, with the gate as the control

The comparison is the same generated program with `#<_pl_floor_n>` forced to 0,
which is the runtime gate — so "before" is this exact file with the feature off,
not a remembered number from another commit.

| project | floors | old ladder lands on | new ladder lands on |
|---|---|---|---|
| testing_15_4 | 3 | **0** | **2** |
| testing_15_2 | 2 | 1 | **2** |
| testing_13_arcs | 7 | 1 | **7** |
| testing_11 | 2 | 0 | 1 |

`testing_15_4`'s cylinder now stops at **21.016** where it stopped at 21.032 —
the reported 0.016.

**Not every floor is reachable, and the test does not pretend otherwise.**
testing_15_4's chamfer bottoms at r19 at a SINGLE POINT, the tip at Z0; the
surface at radius 20.016 lies at Z−1.016, which is the cylinder. No level can
cut at that floor and the pass is correctly blocked. A floor derived from a
point rather than an area is entitled to nothing, so the assertion is that the
new ladder lands on strictly *more* floors, not on all of them.

## A regression it caused, and the fix

`test_rough_comp` failed in all three modes: *"1 of 11 plunge - first at
r25.2788, Z−68.1460"*. The new ladder moved the levels behind the boss, so the
last one entered a **1.3003 mm** cut where it had entered 2.6397 mm, and the
profile-angle ramp — capped at "never longer than the cut it enters" — was
dropped entirely, leaving a 45° plunge.

The cap now **shortens the ramp to fit instead of dropping it**, to half the
cut. How long the approach is was never the point; arriving *parallel* to the
surface is, and a short ramp at the contour's own angle does that. This also
removes the coupling that made the failure possible: whether the full ramp fits
depends on where the levels happen to fall against the slope, so **any** change
to the ladder could turn a ramped pass into a plunging one.

Off's overcut moved 0.1115 → 0.1113 mm; Native and In CAM unchanged at 0.0503.

## `test_ladder.py` asserted the old design

Three of its checks were written for one ladder with one remainder, and the
change supersedes them rather than breaking them. Generalised, keeping teeth:

- *at most one gap is not a whole step* → **at most `stages + 1`**: one
  remainder per re-anchoring, plus the window ladder's own first-step remainder
  at the stock end.
- *every gap is the same* (Stock) → **evenly spaced within each stage**,
  distinct gaps ≤ `stages + 1`.
- *every remaining gap is a whole depth of cut* (skip-thin) → **every remaining
  thin gap lands on a floor.** That is the stronger statement: a floor level is
  the surface roughing must leave for the pre-finish pass and is never
  skippable, whatever the threshold, and any *other* thin gap is a sliver that
  got through.

Its own `import re` inside `main()` shadowed the module-level one and raised
`UnboundLocalError` as soon as `re` was used earlier in the function — removed.

## Still unknown

- **ID work is declined outright.** `build_floor_ladder_gcode` returns '' when
  the pass starts inside the part; on a bore the floors run the other way and
  every comparison inverts. ID is paused (`openPoints`), and a wrong guess there
  would rough INTO the wall rather than leave a sliver.
- `testing_11` lands on 1 of its 2 floors. Not chased — the same
  point-versus-area question as testing_15_4's chamfer, but not confirmed.
- The ramp is now capped at **half** the cut. Half is a choice, not a
  measurement: it guarantees the ramp never eats the whole pass, but nothing
  says half is the best fraction.
