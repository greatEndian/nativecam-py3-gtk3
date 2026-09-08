# 116 — the native-comp coverage gap, and the dropped corners found under it

**Asked**: greatEndian, 2026-09-08 — *"go on with the coverage gap"*, the open
point `analysis/115` left: `prove_cam_comp --mode 1` reporting 21–23 uncovered
segments across the whole `testing_13_*` family.

Two separate things came out of it. The coverage gap is **diagnosed and is a
known trade-off, still open**. Underneath it was **a real defect that is fixed**:
roughing stopping up to 8.96 mm past a corner and gouging 0.49 mm.

## What "uncovered" means, and validating the probe

`prove_region` calls a profile segment covered when some compensated path point
comes within `tol` of tangency to it. Before trusting any of it, the probe was
checked against a number already known: on `testing_13_arc_first` **mode 2** it
reproduced the passing run exactly - 0 uncovered, 95 tangent points.

## The coverage gap: arcs are walked as chords, thinned by `_min_segment`

Mode 1's 21 uncovered segments fall in two clusters, and both are the same
thing.

- **The opening R4 nose arc** - segments 1, 4, 7, 10, 13, i.e. every third.
- **An R6 concave fillet** at Z −45.5..−50.8 - 16 contiguous segments, nearest
  tangent rising to 3.63 in the middle and falling symmetrically.

The finish pass walks **30 records, every one `dir = 1`**. Not one arc survives
into it. Across that R6 fillet:

| | points across the fillet | distance to profile |
|---|---|---|
| mode 2, In CAM | 20 | 0.4000 exactly, all |
| mode 1, native | 7 (= 6 chords) | 0.4024–0.4025 at the vertices |

The vertices sit 0.4028 from the TRUE arc and the chord midpoints leave
**0.0416 mm of stock**, uniformly. So it is neither an uncut region nor purely a
tolerance artifact: the native path discretises arcs far more coarsely than the
In CAM path, and the 0.0025 excess at the vertices is what pushes them out of
the tangency window.

The cause is not the mesher - `poly_mesh_lathe` is never called on this path (0
calls, measured; the `_pl_env_count > 0` branch replaces it). It is
`_min_segment(env, 2.4 * nose_r)` thinning the finishing contour, and its own
docstring already measured it on this very family:

    R4   16 x 5.625 deg densified, kept every 3rd, remainder 0.3925 mm
    R6   20 x 4.500 deg densified, kept every 3rd, remainder 0.9423 mm

against a limit of 2.4 x 0.4 = 0.960 mm. `_densify_arc` and `poly_mesh_lathe`
agree with each other at MESH_MAX_SAG 0.005 - 20 chords on the R6 - and then the
thinning throws two thirds of them away.

### Why it is not simply relaxed

`_min_segment` exists because compensation shrinks a segment by `R*tan(deficit/2)`
at each end and a segment shorter than that reverses, which aborts the pass. The
limit is a blanket `2.4 * nose_r`; the per-corner requirement for an arc chord
turning 4.5 degrees is `0.4 * tan(2.25 deg) = 0.0157` - two orders of magnitude
smaller. So a per-corner rule would keep the resolution.

**It is blocked on a parameter window.** The thinned surface is emitted to BOTH
`FLANK_BASE 3600..3700` and `FC_BASE 4000..4200`, and the two must stay the same
surface (below). FC holds 100 points; **FLANK holds 50**. Un-thinned the contour
is 66 points - fits FC, overflows FLANK. Enlarging FLANK means moving FLOORC at
3700 and its O-code readers, which is its own change with its own blast radius.

A second, better route: the table is points only, so an arc must be chorded at
all. Carrying `dir` and the centre per record would let `g123_lathe` - which
already emits `G2`/`G3` for `dir` 2/3 - trace the true arc, exactly, in ONE
record instead of 20. Also its own change.

Measured, bounded, and left open.

## The defect found underneath: `protect` missing at one of two call sites

`_min_segment(pts, limit, protect=())` takes `protect` so the profile's real
corners survive whatever their spacing. Its docstring is emphatic about why -
a densified arc's last chord is the remainder of the sweep, routinely shorter
than the limit, so dropping it runs the path from the last chord vertex to the
NEXT ITEM'S far end and cuts the corner off.

**It was passed at the finishing call site (5275) and not at the flank one
(3957)** - directly under a comment saying *"Cleaned exactly as the finishing
contour is ... One surface, both users."* They were not.

Measured on `testing_13_arc_first`, the finishing contour held three corners the
flank envelope did not:

```
Z  -4.0000 R 12.0000   0.0186 mm    end of the R4 nose arc
Z -25.0000 R 22.0000   0.6270 mm
Z -51.0000 R 28.0000   0.9338 mm    end of the R6 fillet
```

which is the docstring's own worked example arriving in the shipped table. The
envelope read back out of the generated program:

```
OLD   Z -50.9261 R 27.0614  ->  Z -69.9998 R 28.0000     a 19 mm ramp
NEW   Z -50.9261 R 27.0614  ->  Z -51.0000 R 28.0000  ->  Z -69.9998 R 28.0000
```

Not a widening - the two tables are otherwise identical point for point, so the
corner was dropped, not moved.

### What it cost

Roughing stops against this surface (`poly_lathe_mill` fills `m_pds` from the
env table when `_pl_env_count > 0`). With the pre-finish and finish offsets at
0, so the roughing floor sits on the finished shape:

```
level R 27.5031   old stops Z -59.5079   new stops Z -50.5468   corner at Z -51
level R 21.5105   old stops Z -29.0102   new stops Z -24.5704   corner at Z -25
```

The phantom ramps carried roughing **8.96 mm and 4.44 mm past the corner**,
cutting at R27.50 where the part is R28.00 and at R21.51 where it is R22.00 -
**0.49 mm into a finished surface**, twice. That is the "roughing eats into the
pre-finish allowance" the comment above the unfixed call site predicted.

### The fix

`corners` is collected and passed at 3957 exactly as at 5219/5275.

## Verification

- The two surfaces now agree: env 31 = fc 31, **0 finish-contour points missing
  from the flank envelope** (was 3).
- Resource, measured on the real projects, not assumed: **no WARNING in any of
  the 46**, max env 32 against the FLANK cap of 50.
- Motion fingerprint of all 46 at their own settings: **46 identical, 0
  changed.** The defect is LATENT there - the truncated corners lie either
  outside the stock (R28 against an R25 blank) or below the roughing floor. It
  had to be forced into view with the offsets zeroed, and that is the
  demonstration above.
- Gates: flake8, cam_map, test_lathe_validation, test_ladder,
  test_ladder_account, test_level_intervals, test_level_blocked,
  test_sub_spans, test_roughing_windows, test_ladder_python, test_leftover,
  test_x_continuity, test_ramps, test_sections, test_bidir_warn - all exit 0.
  test_project_sweep 45 clean of 46, the one being the empty template.
- Coverage is UNCHANGED by this fix, as expected: still 21 uncovered, gouge
  0.0000. The thinning is what causes it and the thinning is still there.

## Why it was not caught earlier

Nothing compares the two surfaces. Both are emitted, both are walked, and no
gate asserts they are equal - the invariant lives only in a comment. A check
that `_pl_env_*` contains every `_pl_fc_*` point would have caught it the day
`protect` was added to one call site.

## Still unknown

- The coverage gap itself, above - blocked on the FLANK window.
- Whether any real part has been cut with a truncated corner inside the stock.
  Nothing here has touched metal.

## Addendum, same day — the gate

greatEndian: *"add the surface-equality gate"*, following "no gate asserts the
two surfaces are equal" above. `test_surface_equality.py`.

**Three candidate invariants were measured and two were thrown away**, which is
the useful part of the record:

1. *The stop surface never lies inside the finished profile.* False. It flags
   4.94 mm on the ID projects and 0.43 on testing_15_7, because `profile_bound`
   takes the OUTERMOST radius on a multi-valued profile, so a legitimately
   shadowed boss reads as buried.
2. *If an env segment's endpoints both lie on the profile, a corner between them
   must lie on that segment.* False. The reachable envelope deliberately BRIDGES
   unreachable pockets, and a bridge has both ends on the profile - 15 projects
   flagged, worst 9.84 mm, all legitimate. Adding a sign test and a
   single-valued test still left 15.
3. *Every finishing-contour point is a vertex of the flank envelope.* **True** -
   38 of 38 projects that carry both tables, no exceptions.

Three rounds of patching an invariant against fresh counterexamples is the
signal that it is not an invariant. A gate with false positives fails the suite
for everyone, so it is worth more to measure a candidate across the catalogue
before shipping it than to reason about whether it should hold.

The gate reads the SHIPPED TABLES back out of each generated program rather than
testing the builders: the bug was a missing argument at one call site while both
functions were correct, so a unit test on either would have passed.

**Negative control, and a false one first.** `git stash push lathe_sections.py`
reported success and stashed nothing - the fix was already committed - so the
first control re-tested the fixed code and "passed". That is the same shape as
the patch earlier in this branch whose assert fired before any write while the
gate reported MOTION IDENTICAL. Redone with `git checkout f8c5fdd^ --` and the
revert VERIFIED by grep before measuring:

    protected call sites 1 (pre-fix)  ->  exit 1, 4 projects, 3 points each
    protected call sites 2 (fixed)    ->  exit 0, 38 of 38

It also carries a comparator self-check that does not need the code reverted,
and fails on a zero project count - this project has shipped a vacuous pass
twice.

Not covered: the stop contour `_pl_stop_*` (4400) is a third table and a
different surface. And the two envelopes are not built from identical inputs -
the finishing one also takes a front-flank angle and `fin_dir` where the flank
one uses `rough_dir` - so containment is asserted as the documented intent
rather than proved from construction. It holds across the whole catalogue today.
