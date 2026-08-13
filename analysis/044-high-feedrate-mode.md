# 044 — High feedrate mode, and a dogleg that cannot happen here

2026-08-13, branch `liveTooling`. Gap **23** of `POLYLINE-GAPS.md`.

## What was asked for

*"Specifies when rapid movements should be output as true rapids (G0) and when
they should be output as high feedrate movements (G1)"* — six choices, and
*"usually set to avoid collisions at rapids on machines which perform 'dogleg'
movements at rapid."*

## The stated reason does not apply, and it was measured before building

A G0 with two axes moving is not a straight line on every control. That is the
whole case for the feature elsewhere. On this output it cannot arise:

```
positioning moves on testing_15_5 : 148
  radial, X only                  :  99
  axial, Z only                   :  49
  BOTH axes                       :   0
```

Every rapid the polyline emits names **one axis**, and a single-axis G0 is
straight on any control — not merely on LinuxCNC, where a G0 is coordinated
anyway. So the safety argument is doubly inapplicable, and three of the six
choices — *preserve all*, *preserve axial and radial*, *preserve single-axis* —
are the same thing here. They are offered so a setting carries its meaning
across from the package it was copied from, and the parameter's own tooltip says
so rather than implying a benefit it cannot deliver.

What does earn its place: posting positioning as G1 where G0 moves faster or
harder than wanted near a fixture — *preserve axial only*, *preserve radial
only*, *always high feed*.

## The real risk was the modal feed, not the geometry

`F` is modal. A `G1 F<high>` leaves it set, and `lathe_level_pass` has a path
where the level cut takes whatever `F` was last set — with the profile-angle
approach off, nothing names a feed between the positioning move and the cut. A
leak there runs a **cut at positioning speed**, which is a broken tool.

So the conversion lives in one subroutine, `lib/lathe/hf_move.ngc`, which puts
the caller's feed back before returning; every call site passes the feed that
should be in force afterwards. Centralising it is the point — the alternative
was the same restore hand-written at 21 sites.

Two guards in the same place: a rate of 0 falls back to a true rapid, because
`G1 F0` stops the machine; and the axis is a call argument rather than something
sniffed at runtime, since every site is statically one axis or the other.

`hf_move` is a NEW subroutine called only from `lib/`, never from a stored cfg
template, so giving it arguments is safe — the rule against new CALL arguments
is about subroutines a saved project calls.

## Measured

**Default byte-identical**, move list hashed with the work stashed and restored:

```
testing_15_2   347 moves   be18c9df96c4   identical
testing_15_5   470 moves   85d0094b62ab   identical
testing_15_6   458 moves   136c8589c74d   identical
```

**Each mode converts what it names, and only that** — 21 sites across
`lathe_level_pass`, `poly_lathe_mill` and `lathe_poly_pass`:

```
mode                     rapids left   radial   axial
preserve all                    148       99      49
preserve axial and radial       148       99      49
preserve single-axis            148       99      49
preserve axial only              49        0      49
preserve radial only             99       99       0
always high feed                  0        0       0
```

The move count stays 470 in every mode: the tool goes to the same places, only
the word changes.

**And the feed does not leak.** Counting interpreted moves running at the high
rate against the number converted — equal means every high-feed move is a
converted positioning move and no cut inherited the rate:

```
preserve axial only    99 converted   99 at the high feed   no leak
preserve radial only   49 converted   49 at the high feed   no leak
always high feed      148 converted  148 at the high feed   no leak
```

## Note on the contour passes

The first pass covered `lathe_level_pass` and `poly_lathe_mill` only, and
*always high feed* still left **6** rapids — from `lathe_poly_pass`, the
pre-finish and finish contour passes. Found by asserting zero rather than
assuming it. Those 8 sites are converted too, so the mode means the whole
operation.

## Verified

`test_high_feed` (new), `test_all_projects`, `test_leftover`, `test_x_continuity`,
`test_rough_comp`, `test_stock_to_leave`, `test_rough_ends` (the test that
reasons about retreats), `test_behind_boss_ladder`, `test_rough_overlay`,
`test_ladder`, `test_floor_ladder`, `test_ramps`, `test_section_length`,
`test_resume_envelope`, `test_end_z`, `test_z_datum`, `test_extension`,
`test_peck`, `test_below_inner_radius`, `test_front_flank`,
`test_front_flank_path`, `test_pane_layout`, `test_lathe_validation`, `cam_map`,
flake8 both lists.
