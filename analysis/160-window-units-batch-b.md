# 160 - unit coverage for `lathe_sections.py` batch B (windows, call planning, offsets)

## What was asked

Cover 12 named functions in `lathe_sections.py` with hand-derived unit tests
in a new file, `test_window_units.py`, without touching `lathe_sections.py`,
any existing `test_*.py`, or anything under `lib/`/`cfg/` - two other Claude
sessions are concurrently editing this tree, one of them rewriting
`detect_sections()`/`floor_regions()` and running whole-project motion gates.

The 12: `protected_flags`, `level_floors`, `window_calls`, `rough_nose_terms`,
`roughing_call_plan`, `flat_sub_number`, `wrong_way_dirs`, `curve_offsets`,
`stock_at_normal`, `facing_rough_offset`, `unreachable_spans`, `xw_settings`.

## Path

1. Read every one of the 12 functions in the current working tree (line
   numbers had already drifted a few lines from the prompt's, because another
   session has an uncommitted edit to `lathe_sections.py` sitting in the same
   file - confirmed with `git status`/`git diff --stat` before touching
   anything).
2. For each, checked whether it needs a `Feature` object (`.get_param`,
   `.get_attr`) to run at all, and separately ran a small AST call-graph walk
   over the whole module to check whether it reaches `detect_sections()` or
   `floor_regions()`, directly or through any callee - grep alone would miss
   an indirect reach through two or three levels of helper, so this walked
   every `ast.Call` in every function transitively.
3. For the six left over, derived every expected value by hand: either
   directly from the docstring's stated rule (`protected_flags`,
   `level_floors`, `wrong_way_dirs`, `stock_at_normal`), by hand-tracing the
   algorithm against a deliberately simple, physically-legible geometry
   (`window_calls`), or by independently re-implementing the documented
   formula as a standalone calculator script and cross-checking the
   arithmetic before writing it into the test (`curve_offsets`, whose joint
   maths is not mental-arithmetic-sized) - never by calling the function
   under test first and pasting what came back.
4. Wrote `test_window_units.py`, ran it, ran the six gates the prompt lists.

## Functions covered (6 of 12) and what each actually does

**`protected_flags(levels, floors, step_target, staged)`** - one flag per
roughing level saying whether it IS the floor stage currently being aimed at
(`fl_prot` in the O-code it replaces). Unstaged (or a single floor), the flag
only ever matches `step_target`. Staged with several floor stages, the walk
starts pinned on stage 0 and advances to the next stage the level *after* one
lands on the current stage; the last stage never advances further no matter
how many more levels hit it.

Hand-derived: with `floors=[6,3,1]`, `step_target=1`, `staged=True`, and
`levels=[10,8,6,5,3,2,1,0.5]`, tracing the loop by hand gives
`[0,0,1,0,1,0,1,0]` - the tool verified this exactly.

**`level_floors(levels, floors, window_floor)`** - the floor each level is
itself aiming at (`lvl_floor`). Re-anchors on stage 0 only when
`window_floor` equals the *last* floor stage (analysis/095, 096 already
established this asymmetry is load-bearing: writing at the window start
instead of the advance broke testing_15_5). The value is written **at the
advance, not at the hit** - the level that lands exactly on a floor still
reports the OLD floor; the next level reports the new one.

Same input geometry as above gives `[6,6,6,3,3,1,1,1]` - hand-traced and
verified. A second check confirms the negative control: `window_floor` NOT
equal to the last stage never re-anchors, and every level reports the
window's own floor unchanged.

**`window_calls(...)`** - simulates one whole window: for every level, which
of band/thin/stock skips it (or neither), and if neither, every
`lathe_level_pass` call that level makes with `first`/`blocked` markers. Fully
pure - all its arguments are lists and scalars, and none of its callees
(`level_calls`, `level_stop_z`, `_level_scan`, `resume_z`, `sub_spans`) reach
`detect_sections`/`floor_regions` (confirmed by the AST walk in step 2).

Covered with six hand-traced scenarios, each choosing the simplest possible
`floor_contour`/`resume_env` that makes the arithmetic legible instead of
building anything resembling a real profile:

- an unobstructed level (`floor_contour` flat at r=0) → one call spanning the
  window, `blocked=False`;
- a level blocked from the window's own start (`floor_contour` flat at r=10,
  above the level) → the call is still recorded, `blocked=True`, and **`why`
  stays `''`** - the docstring's point that `why` only reports the
  band/thin/stock gate, never whether the walk actually cut anything;
- a level outside `[w_rlo, w_rhi]` → `'band'`, no calls;
- a level at `stock_r` in the travel direction → `'stock'`, no calls;
- two levels both within `skip_thin` of `prev_thin` and leaving the next
  level within one depth of cut → both `'thin'`;
- the same thin-shaped geometry but with `protected[0]=1` → the thin branch
  is refused outright and the level runs normally - "A PROTECTED FLOOR IS
  NEVER DROPPED whatever the threshold" is exercised, not just quoted.

**`wrong_way_dirs(orient, rough_dir)`** - True when the requested roughing
direction opposes the insert's own cutting face. Derives entirely from
`NOSE_OFFSET[orient]`'s Z component via `ramp_facing`: orientation 2 (raw
vector `(1,1)`) faces -Z (front-to-back, `param_dir=0`); orientation 1
(`(1,-1)`) faces +Z (back-to-front, `param_dir=1`). `rough_dir=2` ("Both
directions") is always wrong for a directional insert; neutral orientations
6/8/9 (no Z term) are never wrong. All seven cases hand-derived straight from
`NOSE_OFFSET`'s table values in `lathe_comp.py` (`(1,-1),(1,1),(-1,1),(-1,-1),
(0,-1),(1,0),(0,1),(-1,0),(0,0)` for orientations 1-9).

**`stock_at_normal(nz, nr, off_x, off_z)`** - the allowance formula itself:
`d = nz^2*off_z + nr^2*off_x`, i.e. `off_x` on a pure diameter, `off_z` on a
pure wall, their mean at 45 degrees, and (via the documented `EPS` shortcut)
exactly `off_x` for ANY normal, including a degenerate one, whenever
`off_x == off_z`. All four checks are the formula evaluated by hand.

**`curve_offsets(pts, side, nose_r, off_x, off_z)`** - per-segment offset
endpoints plus the allowance rolled into each. The isotropic case
(`off_x==off_z`) short-circuits to the plain per-segment offset with no joint
maths at all. The anisotropic case only blends two segments to a shared joint
point when the turn between them is under `CURVE_TURN_DEG` (20 degrees) -
i.e. only where the vertex is interior to a smooth curve; a sharp corner
(90 degrees here) keeps each segment's own normal and its own allowance with
no shared point at all, which is the exact "allowance belongs to the surface"
rule the docstring states. Four scenarios: isotropic corner (round numbers,
mental arithmetic), one anisotropic diameter segment, an anisotropic sharp
corner (diameter keeps `off_x`, wall keeps `off_z` - roll 1.008 vs 2.5), and
an anisotropic smooth vertex built from 3-4-5 direction vectors (turn ≈16.26°,
inside the 20° cut) so the dot product, the bisector, and the joint
projection are all exact rationals. The smooth-vertex arithmetic was
cross-checked with an independent 30-line re-implementation of
`_unit`/`stock_at_normal` run as a calculator, not with `curve_offsets`
itself - see the script output captured below.

```
seg cyl: normal 0.0 -1.0 roll 1.008
a,b: (0.0, 8.992) (10.0, 8.992)

seg (0.0, 10.0) (5.0, 10.0) normal (0.0, -1.0) roll 1.008
seg (5.0, 10.0) (5.0, 5.0) normal (-1.0, -0.0) roll 2.5
plain 0 (0.0, 8.992) (5.0, 8.992)
plain 1 (2.5, 10.0) (2.5, 5.0)

dir (0.6, 0.8) normal (0.8, -0.6) roll 1.9628800000000002
dir (0.8, 0.6) normal (0.6, -0.8) roll 1.54512
dot 0.96 cut 0.9396926207859084 True
joint normal (0.7071067811865476, -0.7071067811865476) d 1.7540000000000002 joint pt (4.240265294201205, 2.7597347057987953)
plain 0 (1.5703040000000001, -1.177728) (4.570304, 2.822272) roll 1.9628800000000002
plain 1 (3.927072, 2.763904) (7.927072, 5.763904) roll 1.54512
```

(The two `plain` rows for the smooth-vertex case are the UN-joined endpoints;
`curve_offsets` itself replaces the shared vertex ends - `b` of segment 0 and
`a` of segment 1 - with the joint point, which is what the test asserts.)

All 26 checks passed on the first run of `test_window_units.py` - no
derivation had to be corrected against the tool's own output.

## Functions skipped (6 of 12) and why

All six need a `Feature`-like object (`.get_param(name)` returning something
with `.get_ngc_value()`, or `.get_attr('id')`), which the worker brief rules
out building: *"If a function requires a Feature to call, skip it... faking
one is out of scope and produces tests that assert the fake, not the code."*

- **`rough_nose_terms(polyline_feature, nose_r, orient)`** - calls
  `_comp_nose(polyline_feature, nose_r, orient)`, which does
  `polyline_feature.get_param('param_n_comp')`.
- **`roughing_call_plan(polyline_feature, ...)`** - needs a `Feature` for a
  dozen params AND, confirmed by the AST call-graph walk, reaches
  `floor_contour_data` → `finish_profile` → ... → `detect_sections`/
  `floor_regions` (the walk reported `roughing_call_plan -> True`, the only
  one of the 12 that does). Doubly out of scope: the other session owns that
  code right now, and even if it did not, this needs a Feature.
- **`flat_sub_number(polyline_feature)`** - `polyline_feature.get_attr('id')`.
  Trivial in isolation, but still a `Feature` call, and the function's own
  docstring says it is `UNUSED, kept for the record` (the whole
  numbered-vs-named-subroutine approach it served was abandoned - see the
  docstring's "NUMBERED SUBS ARE FILE-LOCAL" explanation), so there is also no
  live behaviour at stake.
- **`facing_rough_offset(feature, nose_r, orient)`** - six `feature.get_param`
  calls plus the module-level `WORKPIECE_OD`/`WORKPIECE_ID` globals.
- **`unreachable_spans(polyline_feature, ...)`** - `resolve_points` and
  `finish_profile` both need the Feature to read the polyline's own points.
- **`xw_settings(polyline_feature)`** - four `polyline_feature.get_param`
  reads, nothing else.

None of the six reach `detect_sections`/`floor_regions` on their own (the AST
walk says `False` for all of them except `roughing_call_plan`), so the Feature
requirement is the only reason for the skip in five of the six cases.

## `facing_rough_offset`'s extra-care note (documented, not tested)

The prompt calls this one out by name: the offset it returns is **radial, not
axial**, because a T3/Q3-style insert cancels the axial term. Reading the
function confirms why, without needing a Feature to prove it: the cut this
computes runs radially at constant Z (`"The cut runs radially at constant Z,
so only the SIGN of the radial travel matters"`), and it calls
`lathe_comp.offset_vector(side, 0.0, (ex - bx) / DIAMETER_MODE, nose_r,
orient)` with `dz` **hard-coded to `0.0`** - i.e. the travel-direction term
handed to the shared primitive has no Z component by construction, so
whatever axial contribution the orientation vector would otherwise produce is
never picked up. A test that expected an axial (`off_z`, the first tuple
element) shift from a facing pass would be asserting a shape the function
cannot produce - which the prompt says has already happened once in this
project. This is recorded here per the "worth extra care" instruction; it is
not exercised by `test_window_units.py` because doing so needs a `Feature`.

## Bugs found

None. Every hand-derived expected value matched the function's own output on
the first run - no derivation had to be corrected, and no discrepancy between
the docstring's stated rule and the code's actual behaviour turned up in the
six functions covered.

## What is still unknown

- The six skipped functions have no unit coverage at all yet; they would need
  either a real `Feature`/`Parameter` pair from the existing project-loading
  path, or a deliberate, reviewed decision to build a minimal fake exempted
  from this prompt's "faking is out of scope" rule - not this worker's call.
- `roughing_call_plan`'s current behaviour cannot be trusted as a baseline for
  a future test in any case, since `detect_sections()`/`floor_regions()` are
  being actively rewritten by another session as of this writing.
