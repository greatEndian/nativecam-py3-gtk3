# 150 — batch A: 4 of 12 functions were genuinely pure

**Asked**: `SONNET-PROMPT-UNITS-A.md` - direct unit coverage for a named list
of 12 functions in `lathe_sections.py`, skipping any that need a `Feature`/
`NCam`, or that reach `detect_sections()`/`floor_regions()` (both under active
rewrite by a parallel session).

## Result

```
4 of 12 covered directly: boundary_height, set_insert_orient, ladder_consts, ladder_phases
8 of 12 skipped, with reason (below)
27 checks, 6 explicit negative controls
0 bugs found
```

## What each covered function actually does

- **`boundary_height(points, z_b)`** - the highest X any segment crossing
  `z_b` reaches. A vertical wall (constant Z, the "step" case) contributes
  both its endpoints; a sloped segment contributes its one interpolated X.
  For a step this is the top of the wall; for a peak formed by two sloped
  segments it is the peak's own X - both confirmed by hand-picked profiles,
  not just read from the docstring.

- **`set_insert_orient(orient)`** - not a computation, a remembered fact.
  Sets the module global `INSERT_ORIENT = int(orient or 0)` and returns `''`
  (it exists to be called from a cfg `<exec>` tag, which prints whatever it
  returns into the G-code - the empty string is deliberately a no-op there).
  Tested as the state change it is, with the prior value restored afterward
  so this file leaves no residue for any other test run in the same process.

- **`ladder_consts(start_r, final_r, fin_off, prefin_off, doc, pass_from,
  floors)`** - the roughing ladder's head scalars. `rough_target`/
  `step_target` are the finish/pre-finish targets offset by direction
  (`dirsign`); `lad_tgt` is `step_target` unless more than one floor stage
  exists, in which case it takes the shallowest floor (`floors[0]`) instead;
  `rough_passes` is LinuxCNC's own FUP (round-away-from-zero) of the span
  over `doc`. `pass_from=True` (anchored) is the subtle branch the docstring
  itself flags: it reassigns `cut_step` to a **whole** `+-doc` rather than an
  even division, then re-anchors `step_target`/`lad_tgt` outward from
  `rough_target` by whole multiples of `doc` - confirmed by hand-tracing the
  branch line by line (a single-floor input does NOT trigger the
  multi-floor override; `len(floors) > 1` is a real gate, not `>= 1`).

- **`ladder_phases(start_r, lad_tgt, step_target, cut_step, first_step, doc,
  dirsign, sect_on, sect_count, sect_top_r)`** - with Sectioning off, a pure
  5-tuple passthrough of `(step_target, cut_step, first_step, cut_step,
  first_step)`. With Sectioning on, confirmed the docstring's own claim that
  "the two gates are not the same gate": `sect_count == 0` still recomputes
  both phase step sizes (just around `top = step_target`, since the
  `sect_top_r` override itself needs `sect_count > 0`) - a passthrough would
  have been the easy, wrong assumption to test for. `top` is clamped twice:
  never past the floor (`step_target`) and never above the stock the ladder
  starts from (`start_r`) - both clamps exercised directly, the second one
  with a `p1_step`/`p1_first` chosen to be distinguishable from any
  recomputed value, so the resulting no-op p1 (`abs(top-start_r)<=EPS`
  skips the whole branch) is provably the untouched passthrough and not a
  coincidence.

## What was skipped, and why

**Needs a `Feature` object** (calls `.get_param` or `resolve_points(...)`
directly on the argument named `polyline_feature`) - faking one would test
the fake, not the code:

- `resolve_points_untrimmed` - calls `resolve_points(polyline_feature,
  trim=False)`
- `z_limit_band` - calls `z_limit_abs(polyline_feature, ...)`
- `profile_problem` - calls `resolve_points(polyline_feature)`
- `level_allowance` - calls `polyline_feature.get_param(...)`
- `rough_radius_bounds` - calls `polyline_feature.get_param(...)` and
  `x_limit_abs(polyline_feature, ...)`
- `ext_dz` - calls `resolve_points(polyline_feature, extend=...)`
- `rough_emit_reversed` - calls `polyline_feature.get_param('param_dir')`

**Needs a `Feature` object AND reaches the functions under rewrite** -
double reason to skip:

- `floor_stages` - takes `polyline_feature` directly, and its own body calls
  `floor_ladder(points, ...)` which (grep-verified, line 1848 of the file on
  disk at the time of this session) calls `floor_regions(...)`, which calls
  `detect_sections(...)` - exactly the two functions the parallel session is
  rewriting. Testing this now would assert today's output of code known to
  be changing under it.

No function in the list reaches `detect_sections`/`floor_regions` WITHOUT
also needing a `Feature` - the two exclusion reasons happened to fully
overlap in this batch (`floor_stages` is the only one hitting the second
rule, and it already fails the first).

## Bugs found

None. All hand-derived expected values (independently worked out from each
function's own formula/docstring before running anything) matched the
function's actual output on first check except one - a mistake in my OWN
arithmetic on the "single floor does not override lad_tgt" case for
`ladder_consts` (I copied `rough_passes: 1` from the unrelated "already at
target" boundary case instead of computing `FUP(10/2)=5` for this one).
Caught by re-deriving by hand rather than trusting the first number, fixed
in the test before committing - not a code defect, recorded here per the
brief's instruction to log the actual arithmetic, not just the final answer.

## Verification

```
flake8 ncam_*.py lathe_sections.py test_profile_units.py --builtins="_" --select=E9,F63,F7,F82   exit 0
python3 cam_map.py                                                                                exit 0
python3 test_cam_map.py                                                                            exit 0
python3 test_lathe_validation.py                                                                   exit 0
python3 test_coord_mapping.py                                                                       exit 0
python3 test_geometry_primitives.py                                                                exit 0
python3 test_profile_units.py                                                                       exit 0 (27/27 checks)
```

No rs274-backed gate run. `lathe_sections.py` not edited - it is currently
modified in the working tree by the parallel `detect_sections` session; this
worker only ever imported it as-is.
