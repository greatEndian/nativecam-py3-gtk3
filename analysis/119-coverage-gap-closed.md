# 119 — the coverage gap closed

**Asked**: greatEndian, 2026-09-09 — *"go b"*. Commit B of the plan: the
coverage fix itself, on the capacity commit A provided.

## Result

`prove_cam_comp --mode 1`, native compensation:

| project | before | after |
|---|---|---|
| `testing_13_arc_first` | 21 uncovered, gouge 0.0000, FAIL | **0 uncovered, gouge 0.0000, PASS** |
| `testing_13_arcs` | 23 uncovered, gouge **0.0358**, FAIL | 2 uncovered, gouge **0.0183**, FAIL |

The wrong-side control still correctly fails on both. `testing_13_arcs`'
remaining 2 are segments 0 and 1 at the front face - its finish pass never
reaches past Z-2.6788 - which is the separate front-face reach bug, not
chording.

## The fix

`_min_segment`'s limit was a blanket `2.4 * nose_r`, roughly **sixty times**
what an arc chord needs to survive compensation. The docstring already derives
the real rule - the interpreter shrinks a segment by `R*tan(deficit/2)` at each
end - and a densified R6 chord turns 4.5 degrees, needing 0.0157 mm against a
limit of 0.960. So two thirds of every arc was thrown away, the finish pass
walked 6 chords across a fillet where the In CAM path walks 20, and 21 profile
segments never had the nose tangent to them.

The limit is now computed per corner, from the actual turn at each end of each
segment, with `SHRINK_MARGIN` 2.0 over the derived requirement, a 0.02 mm floor
and the deficit clamped at 160 degrees so `tan` cannot run away. Genuinely sharp
corners now ask for MORE than the blanket did and are still dropped, which is
what the limit was introduced for on testing_15_2's back-angle ramp.

## The route that looked right and had to be abandoned

Protecting every point that lies ON the drawn profile - keeping the operator's
own geometry whole and leaving ramp stretches thinned - gave a BETTER coverage
result: `testing_13_arcs` reached 0 uncovered and gouge 0.0000 rather than 2 and
0.0183.

**It aborts the real project.** `test_project_sweep` caught
`testing_13_arcs` dying at runtime with "Straight feed in concave corner cannot
be reached by the tool without gouging" - the same error `analysis/115` fixed a
different instance of. Keeping every on-profile point reintroduces exactly the
short segments `_min_segment` exists to prevent.

Worth recording: **`prove_cam_comp` PASSED that variant.** It overrides the
project (`n_comp 2, op 2, f_pass 1, pf_on 0`) and so tests a program the
operator never runs. The sweep tests the project as saved. A green prover is not
a green project.

## Why this works now and did not in analysis/117

The per-corner rule was tried in `analysis/117` and rejected because it took
testing_15_2's shallow entry ramps from 9 to 0. That was never the rule's fault:
the finer contour overran ERAMP's 180 slots and `build_entry_ramp_gcode`
returned `''` silently. Commit A (`analysis/118`) gave ERAMP 600 slots. With
that in place the same rule keeps every ramp - `test_ramps` reports **68 ramps
checked**, exit 0.

Three attempts read as a geometric coupling between contour resolution and the
ramps. It was a parameter window the whole time.

## The windows this pushed, and the repack

Measured across all 46 at the new resolution, before repacking:

```
ENTRY   200 slots, peak 200   100%   testing_13_arc_first   entry_n = 100
STOP    200 slots, peak 192    96%
```

ENTRY landed exactly on its ceiling - `4200 + 2*100 = 4400 = ENTRY_TOP`, and the
guard is `>`, so it fit by one slot. It sat at 61% before this change. Checked
for a clamp at 100 rather than assuming the coincidence: `entry_contour` has
none, so that is the natural count.

Shipping a window at 100% that this change pushed there is not defensible, so
the 3600..4600 region is repacked. All four windows read their base from a
global the O-code never hardcodes, so it is Python-only:

```
FLOORC  3600..3850   250   peak 192   76%   (was 3700..4000, 300)
FC      3850..4050   200   peak 132   66%
ENTRY   4050..4330   280   peak 200   71%   (was 100%)
STOP    4330..4600   270   peak 192   71%   (was 96%)
CAM     4600..4984   384   peak 306   79%   untouched - the tightest of the rest
```

3600..3700 came free when the flank envelope moved out in commit A. No window is
now above 80%, and no project emits a WARNING.

## Verification

- Coverage above; `test_ramps` 68 ramps, exit 0; `test_project_sweep` 45 clean
  of 46; `test_surface_equality` passes, so the two surfaces still agree.
- Whole suite exit 0: flake8, cam_map, test_cam_map, test_lathe_validation,
  test_sections, test_ramps, test_ladder, test_ladder_account,
  test_level_intervals, test_level_blocked, test_sub_spans,
  test_roughing_windows, test_ladder_python, test_leftover, test_x_continuity,
  test_bidir_warn, test_through_cut, test_rough_overlay, test_resume_envelope,
  test_surface_equality.
- Motion changed on 15 of 46 - this is a geometry change, and most keep their
  move count with the coordinates moving as the arcs densify. Checked for
  regression rather than assumed: `testing_9_1`, which PASSED before, still
  passes with **identical** numbers (gouge 0.0000, 203 tangent points);
  `testing_15_3`'s pre-existing failure is unchanged from its `analysis/116`
  baseline (gouge 0.0110, 26 uncovered), with only the sample count rising as
  the path densified.

## Still open

- The front-face reach on `testing_13_arcs` - 2 uncovered segments because the
  finish pass stops at Z-2.6788. Separate bug.
- Nothing here has cut metal. Proved in rs274 only.
