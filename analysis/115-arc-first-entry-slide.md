# 115 — the arc-first abort: a near-radial entry made the Begin Z slide unbounded

**Asked**: greatEndian, 2026-09-08 — *"chase the arc_first failure"*.
`analysis/114` established the mechanism was real compensation and located the
abort at a cusp in the pre-finish entry. This is the root cause and the fix.

## The error was not what n_comp said

All three projects carry **`n_comp = 0`**, which made a cutter-compensation
error look impossible. `tip_comp_dia.ngc`'s `nose_on = 0` branch:

```
#<_tip_comp_d> = [2 * #<extra_r>]
#<_tip_comp_l> = 0
```

D is non-zero whenever the pass has a radial allowance, so `tip_comp_on` emits
`G41.1 D... L0` - a **pure geometric offset**, which is how the pre-finish pass
holds its stock. Measured on the run: `D 1.016000`, comp_r 0.508. The
interpreter was compensating correctly and refusing the geometry handed to it.

## The root cause, measured

Instrumented `lathe_poly_pass.ngc` at the entry and read the numbers out of the
actual run:

```
ENT  entry (Z 0.000000, R 8.000000)   uz -0.146730  ux 0.989177
     t -3.424658   Begin Z 0.000000   comp_r 0.508000
     -> comp entry (Z 0.000000, R 11.462130)
```

The `o<ext_bz>` block slides the entry point along the entry segment until Z
reaches Begin Z:

```
#<ex_t> = [[#<comp_ez> - #<_pl_begin_z>] / #<ex_uz>]
```

`comp_ez` is the entry **after** the comp normal and the orientation term were
added. Here `entry_z` was already 0 = Begin Z, so the whole 0.5025 the term had
to cancel was the comp contribution - and it can only buy Z along the entry
segment. A contour that starts on an arc arrives with the arc's first chord,
which climbs almost radially: `ex_uz = -0.1467`. Buying 0.5025 of Z cost
**3.39 in RADIUS**.

So the entry landed at **R11.4621** with the profile start at **R8.0000**,
`G42.1` came on 3.46 mm outside the part, and the first compensated move
plunged radially back into the corner: *"Straight feed in concave corner cannot
be reached by the tool without gouging"*, 2832 moves in.

The existing guard was `ABS[ex_uz] GT 0.001` - it names this exact fault
(*"dividing by its zero Z component would throw the entry to infinity"*) but
only catches the exactly-zero case. Nearly zero is the same fault with a finite,
still-ruinous number. It admits an entry up to 81.6 degrees steep.

## Two failed fixes, and why they failed

Recorded because each was plausible and each was wrong in an instructive way.

**1. Guard on the angle** - `ABS[ex_uz] GE 0.7071`. Fixed all three projects,
but the fingerprint sweep showed **7 other projects changed**, including
testing_15_7, the project the extension was built for.

**2. Guard on the radial excursion** - skip when `ABS[ex_t * ex_ux] GT comp_r`.
Same 7 projects changed. Measuring them showed why: **`comp_r = 0`** in all of
them. They are In CAM passes, where the extension is still legitimate and
`testing_15_blocked` needs a genuine 21.146 mm slide. Bounding by comp_r
deleted it.

**3. Measure the slide from `entry_z` instead of `comp_ez`.** This dropped the
collateral to 3 projects and was more nearly right - but `test_ladder` caught
it: *"mode 1: every contour pass starts AT Begin Z ... pre-finish at -0.4000,
finish at -0.4000"*. Under native comp the contour then began 0.4 mm past the
face. That equality is greatEndian's own requirement (*"when we are at 0.0 Z and
X at driven diameter we will be at cutting level already"*) and was written,
measured and argued in the test's own comments. It must hold.

## The fix

The slide does **two jobs** and only one of them is always affordable:

- `ex_pt = (entry_z - begin_z) / uz` carries the **profile point** to Begin Z.
  A real extension of the contour; whatever radius it costs is the radius the
  contour actually has there. Always paid. In CAM mode `comp_ez` IS `entry_z`,
  so this is the whole term - which is why every In CAM pass is unchanged.
- `ex_ct = (comp_ez - entry_z) / uz` cancels the Z the comp normal and the
  orientation term added, so the compensated entry still lands on Begin Z. A
  correction, not travel, and unbounded on a steep segment.

`ex_ct` is bounded by `comp_r`, the scale of the terms it is cancelling. An
axial entry - every case the extension was built for - has `ex_ux` near zero and
pays nothing, so it still lands exactly on Begin Z. A near-radial entry keeps
the plain comp point, which sits in free air in front of the face and is a valid
compensation entry.

## Verification

Motion fingerprint (sha1 of every move) of all 46 lathe projects, before and
after:

```
43 identical, 3 changed of 46
  testing_13_arc_first     2832 ERR:concave corner ...  ->  2920 ok
  testing_13_arc_first_0   2840 ERR:concave corner ...  ->  2928 ok
  testing_13_arc_first_1   2840 ERR:concave corner ...  ->  2884 ok
still broken: default_template.xml   (the empty template - expected)
```

**The only three projects that changed are the three that were broken.**

Gates: flake8, cam_map, test_lathe_validation, test_ladder_account,
test_level_intervals, test_level_blocked, test_sub_spans,
test_roughing_windows, test_ladder_python, test_ladder, test_leftover,
test_x_continuity, test_ramps, test_sections, test_bidir_warn,
test_project_sweep - all exit 0. `test_ladder` passes the Begin Z equality in
all three modes.

Geometry, `prove_cam_comp` on testing_13_arc_first:

| mode | contour gouge | coverage | verdict |
|---|---|---|---|
| 2, In CAM | 0.0000 | full, 95 tangent points | **PASS**, wrong-side control correctly FAILs |
| 1, native | 0.0000 | 21 segment(s) uncovered | FAIL on coverage only |

The mode 1 coverage FAIL is **pre-existing and not from this fix**. Control:
`testing_13_arcs`, which has always run and is byte-identical in the sweep,
reports the same failure with 23 uncovered segments and a **worse** gouge -
0.0358 against 0.0000. The fixed projects are strictly cleaner than the
control. Left open below.

## Why it was not caught earlier

Nothing ran the projects. Every other gate takes a hand-picked list - the
ladder tests all sweep the same six `testing_15_*`, `prove_cam_comp` takes one
project at a time - so three projects that aborted at load were invisible until
`test_project_sweep` (analysis/113) ran the catalogue. They have been dead since
before this branch: rolling `lathe_sections.py` and `lathe_poly_pass.ngc` back
to `dad4f7e` reproduces the abort identically.

## Still unknown

- The mode 1 coverage gap on the whole `testing_13_*` family - 21 to 23
  uncovered segments under native comp, gouge-free on the arc_first three.
  Measured, not diagnosed.
- No arc-first project has cut metal. The fix is proved in rs274 only.
- `ext_bz` is still runtime O-code deciding something largely generation-time.
  The entry-segment direction is direction-resolved from the record array at
  runtime, so moving it needs the direction resolution moved first - it belongs
  with the flat-roughing migration, not before it.
