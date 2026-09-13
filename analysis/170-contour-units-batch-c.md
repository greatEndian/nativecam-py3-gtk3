# 170 — batch C: 0 of the 17 named functions were coverable without faking a Feature

**Asked**: `SONNET-PROMPT-UNITS-C.md` — direct unit coverage for the
remaining non-`build_` public functions in `lathe_sections.py`, following
batches A (`37c1952`) and B (`9230065`) as models, now that the
`detect_sections()` rewrite (`f610fbd`) has landed and is verified.

## Count correction, first

The prompt says "Nineteen non-`build_` public functions still have no
direct unit test" but its own table lists 17 distinct names (9 in the left
column, 8 in the right — `floor_stages` has no right-column partner). Both
`test_contour_units.py` and this file work from the 17 actually named; the
discrepancy is recorded rather than silently resolved one way or the other.

## Result

```
0 of 17 covered directly - EVERY named function needs a Feature object.
39 checks in test_contour_units.py: a permanent, automated purity census,
not behavioural coverage - see "What the test file actually is" below.
0 bugs found (none were reachable to test).
```

## Path

1. Read all 17 functions in full, in the current working tree (the
   `detect_sections` fix, `f610fbd`, is committed and the tree is otherwise
   clean of anyone else's in-flight edit to `lathe_sections.py` as of this
   session).
2. For each, checked by eye whether its own signature takes
   `polyline_feature`/`feature` and calls `.get_param`/`.get_attr` on it, or
   calls another helper (`resolve_points`, `x_limit_abs`, `_comp_nose`, ...)
   that does.
3. Cross-checked eye-reading with an AST call-graph walker (the same
   technique batch B used for the detect_sections/floor_regions question,
   here extended to also answer the Feature question): for every
   module-level function, walk its own AST subtree (which includes its
   nested closures, so the many differently-scoped local `_p(name,
   default=0.0)` helpers are picked up without needing to be named
   separately), collect every name it calls, and recurse into any called
   name that is itself a module-level function. A function "needs a
   Feature" here if `get_param` or `get_attr` appears anywhere in that
   transitive closure.
4. Validated the walker itself before trusting its verdict on anything: ran
   it against four functions ALREADY known Feature-free because they were
   directly unit-tested without one in earlier batches (`ceiling`,
   `boundary_height`, `ramp_facing`, `apply_merge_radii` — all currently in
   `test_geometry_primitives.py`/`test_ramp_direction.py`) and confirmed all
   four read `False`. A walker that answered `True` for everything would
   have made every skip verdict below worthless without this check.
5. Also confirmed the walker follows INDIRECT reach, not just a function's
   own literal calls: `profile_problem` never calls `get_param` itself, only
   `resolve_points(polyline_feature)`, and the walker correctly reads `True`
   for it by recursing into `resolve_points`.

Every one of the 17 read `True` on the Feature question. Read every
function's actual body to confirm the specific call, listed per-function
below and asserted with that reason as a comment in `test_contour_units.py`.

## What each function needs a Feature for

| function | the call that needs it |
|---|---|
| `resolve_points_untrimmed` | `resolve_points(polyline_feature, trim=False)` |
| `z_limit_band` | `z_limit_abs(polyline_feature, 'front'/'end')` |
| `profile_problem` | `resolve_points(polyline_feature)` (indirect) |
| `level_allowance` | `polyline_feature.get_param('param_pf_on')`, `stock_pair(polyline_feature)` |
| `rough_radius_bounds` | `polyline_feature.get_param(...)`, `x_limit_abs(polyline_feature, ...)` |
| `ext_dz` | `resolve_points(polyline_feature, extend=...)` (twice) |
| `rough_emit_reversed` | `polyline_feature.get_param('param_dir')` |
| `rough_nose_terms` | `_comp_nose(polyline_feature, ...)` → `polyline_feature.get_param('param_n_comp')` |
| `flat_sub_number` | `polyline_feature.get_attr('id')` |
| `facing_rough_offset` | `feature.get_param(...)` × 6 (plus module globals `WORKPIECE_OD`/`ID`) |
| `finish_profile` | `polyline_feature.get_param('param_flank'/'param_f_dir'/'param_front_flank')` |
| `unreachable_spans` | `resolve_points`/`finish_profile`, both above |
| `xw_settings` | `polyline_feature.get_param(...)` × 4 |
| `section_windows` | `polyline_feature.get_param(...)` × 4, `x_stock_ref(polyline_feature, ...)` |
| `split_peaks` | `polyline_feature.get_param('param_dir')`, `level_allowance(polyline_feature)` |
| `floor_stages` | `polyline_feature.get_param(...)` × 2, `x_limit_abs(polyline_feature, ...)` |
| `roughing_call_plan` | a dozen `polyline_feature.get_param(...)` calls |

## "Newly unblocked" was true, and was not enough

The prompt is right that `section_windows`/`split_peaks` (and, by the same
AST walk, `floor_stages` and `roughing_call_plan`) are no longer blocked by
the `detect_sections()`/`floor_regions()` rewrite — `f610fbd` landed, and the
walker confirms all four still transitively reach one or both, but that
reach is no longer a reason to refuse: the rewrite is done and merged.

**It does not change the verdict, because each of the four has an
INDEPENDENT, unrelated reason to skip** — they all take `polyline_feature`
directly and call `.get_param` on it themselves (see table above), which has
nothing to do with `detect_sections`. Lifting one blocker does not lift the
other one sitting behind it. The standing rule the prompt itself repeats one
paragraph later — *"Batch B skipped six functions because they need a
Feature object. That skip still stands — do not fake a Feature"* — applies
to these four exactly as it applies to the other thirteen; nothing in the
prompt exempts `section_windows`/`split_peaks` from it, and reading their
code confirms they need one just as much as, say, `xw_settings` does.

This is worth stating plainly rather than silently complying with the
"most valuable entries" framing: the honest technical reading of the code
does not support treating these two differently from the rest of the batch.

## What the test file actually is

`test_contour_units.py` is **not** behavioural coverage — there is no
function in this batch to compute an expected value for, because none can
be called without a `Feature`. What it is instead: the evidence above, made
permanent and machine-checked rather than left as this session's prose.

It ships the AST walker as real code (not a scratch script), asserts the
Feature-dependency verdict for all 17 functions with the specific call named
in a comment, asserts the detect_sections/floor_regions reach status for the
four that have it (and asserts its ABSENCE, as a negative control, for the
other thirteen — proving the per-function reasons given are not
interchangeable), and opens with the four known-pure sanity controls that
would fail loudly if the walker itself were broken.

The practical payoff: if a future refactor drops the `Feature` dependency
from any of these 17 (for instance, if `section_windows` is ever split the
way `floor_regions`/`region_floor` were, separating the parameter reads from
the geometry), **this test fails** — not silently stays green — which is
the signal that function should move from this file into direct behavioural
coverage. That is a more durable deliverable than a paragraph saying "still
needs a Feature," which nobody re-checks until the next worker reads the
function again from scratch.

## Bugs found

None. There was nothing to run: every function in the batch requires
exactly the fixture the brief forbids building. The purity census itself
found no discrepancy between the eye-reading and the AST walk's answer for
any of the 17, nor between the walk on the sanity controls and their known
(already-tested) purity.

## Verification

```
flake8 ncam_*.py lathe_sections.py test_contour_units.py --builtins="_" --select=E9,F63,F7,F82   exit 0
python3 cam_map.py                                                                                exit 0
python3 test_cam_map.py                                                                            exit 0
python3 test_lathe_validation.py                                                                   exit 0
python3 test_profile_units.py                                                                       exit 0
python3 test_window_units.py                                                                        exit 0
python3 test_geometry_primitives.py                                                                 exit 0
python3 test_contour_units.py                                                                       exit 0 (39/39 checks)
```

No rs274-backed gate run. `lathe_sections.py` not edited by this worker.

## What is still unknown

- Whether greatEndian wants a real (not faked) `Feature`/`Parameter` harness
  built deliberately for `section_windows`/`split_peaks` specifically, given
  the prompt's framing of them as high-value — that is a scope decision this
  worker's brief explicitly does not authorize on its own.
- Whether `floor_regions`'s own direct unit tests (`test_sectioning_windows.py`,
  from before the `detect_sections` fix landed) should be revisited now that
  the underlying rising-section `min_x` bug (`analysis/130`) is fixed — those
  tests were deliberately restricted to falling/flat profiles to route around
  the (then-present) bug, and could now be extended to rising sections too.
  Out of scope for this batch's own function list, noted for whoever picks
  that file up next.
