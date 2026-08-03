# 006 — The polyline's roughing carries the nose

2026-08-03, under the all-or-nothing rule. **Implemented; the acceptance
measurement is NOT yet in place** — see "Still unknown", which is the honest
state of it.

## Before

Roughing was byte-identical across all three modes — 99 feeds, **0 of 99 moved**
between Off, Native and In CAM. `lathe_level_pass.ngc` has no `tip_comp_*` call
of any kind, so there was nothing for the mode to change.

## Where the offset belongs

A roughing level is a straight cut at a fixed diameter, and **a level's own
diameter needs no compensation**: the cut is parallel to Z, and there the normal
and orientation terms cancel exactly — the same reason a Z wall gets no radial
shift on an orientation-2 tool. What needs compensating is where a level
**starts** and **stops** against the contour.

Both come from walking Python-emitted tables — `_pl_entry_base` and
`_pl_stop_base`, at `lathe_level_pass.ngc:277` and `:341` — and both tables are
built by the same function, `entry_contour`. So this is a pure Python change
with no `.ngc` edit at all, which is the standing rule's shape.

`entry_contour` gained `nose_r` and `orient`: the normal carries
`dist + nose_r`, and the orientation term is subtracted once at the end scaled
by the **bare** nose radius. Folding the nose into `dist` would scale both and
cancel on any axis-parallel surface — precisely how the pre-finish pass
collapsed twice in `analysis/004`. Verified on a wall at r 20:

    nose 0.0 -> (1.0000, 20.5080)  (-20.0000, 20.5080)
    nose 0.4 -> (0.6000, 20.5080)  (-20.4000, 20.5080)

The radius is untouched and Z shifts by the nose. Correct.

`_comp_nose()` gates it on the polyline's own `param_n_comp`, so nothing moves
with compensation off.

## After

    Off      18 level cuts   (baseline)
    Native   18 level cuts   start shift +0.0000   stop shift -0.1300 .. +0.5080
    In CAM   18 level cuts   start shift +0.0000   stop shift -0.1300 .. +0.5080

No level appears or disappears, and Native and In CAM shift **identically** -
correct, since the tables are built once and do not depend on which compensated
mode is in use.

Starts are unchanged because on this project every level begins at the stock
face, not on the entry contour; only levels entering behind the peak take their
start from the entry table, and their radii are not among the 18 measured here.

**Off is byte-identical to before the change** — 247 polyline moves, same hash,
checked against `git stash`. Every saved project in the repo has
`Tool nose comp = 0`, so this is inert for all of them.

## Still unknown — the honest part

**There is no trustworthy acceptance measurement that the compensated roughing
is CORRECT**, only that it moves and that it is inert when off.

A gouge check was written and rejected: it reported 5.0452 mm on **Off**, the
known-good baseline, because it was measuring the uncut region behind the boss
that `openPoints` already records (up to 9.73 mm, Z−70.22 to Z−36.31) rather
than a gouge. A metric that fails the baseline is not a metric.

What is needed: the surface roughing leaves, compared against the **pre-finish**
contour rather than the final profile, restricted to the reachable stretch. That
is the shape of `comp_investigate`'s measurement but on the roughing phase, and
it does not exist yet.

Also not established: whether the roughing tables should carry the roughing
ALLOWANCE through the same route now, as the pre-finish contour does since
`8e50db1`.

---

## The acceptance measurement — added, and it proves it

`test_rough_comp.py`. Sweep the real nose circle along the roughing moves only,
and ask how far past the **pre-finish** contour the surface ends up.

    Off      overcut 0.1116 mm at Z-64.4   (707 samples)
    Native   overcut 0.0503 mm at Z 1.3
    In CAM   overcut 0.0503 mm at Z 1.3

**Uncompensated roughing cuts 0.1116 mm past the stock the pre-finish needs;
compensated it cuts 0.0503 — 55% of it removed — and the two compensated modes
agree to four decimals.** That is the claim, and it is now a test.

The claim it rests on: roughing levels stop against the stop table.
Uncompensated that table stops the imaginary TIP on the pre-finish contour, so
the nose trails past it. Compensated the table carries the nose, so the NOSE
stops there.

### Two metrics were rejected before this one worked

Both are worth keeping, because each failed in a way that looked like a result.

1. **Against the FINAL profile**: reported 5.0452 mm on Off, the known-good
   baseline. It was measuring the region behind the boss that the back angle
   cannot reach and that roughing correctly leaves standing. Fixed by counting
   only OVERCUT — surface *below* the target — so an unreachable stretch leaves
   material above it and contributes exactly zero. No exclusion window has to
   be guessed at.
2. **Still confounded at vertical walls**: reported 4.7405 mm at Z−64.4… in
   *every* mode including Off. At a near-vertical segment there is no single
   radius at that Z, and comparing a swept surface against the outer one
   reports the whole height of the wall. Fixed by returning the (min, max) span
   and skipping any Z where it exceeds 0.5 mm.

**A metric that fails the baseline is not a metric** — twice over.

### And the threshold was wrong too

The first assertion demanded Off exceed half the nose radius. That was a guess,
not a bound: the overcut an uncompensated stop leaves is R·(1−cos) of the local
surface angle, which on a 13° ramp is 0.0102 mm; only a steep wall approaches R.
The real figure, 0.1116, is well above the field's quantisation and below the
guessed threshold — **the assertion was wrong, not the code**. It now tests the
margin between the modes, which is the actual claim.

## Verified

- the measurement above, three modes in one run
- Off still byte-identical, 247 polyline moves, same hash
- flake8 clean; `test_sections`, `test_arc_endpoint`, `test_offset_contour`,
  `test_lathe_comp`, `test_flank_envelope`, `test_skip_short` green
