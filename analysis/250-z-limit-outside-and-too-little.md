# 250 - the Z limits' two silent gaps: outside the profile, too little to machine

Asked: openPoints.md's "VALIDATION - the Z limits are only half validated" -
the crossed-limits check in `polyline.cfg`'s `[VALIDATION]` catches Front Z <=
End Z, but nothing catches (1) a limit that falls outside the profile
entirely, which `trim_to_front_z`/`trim_to_end_z` silently no-op on by their
own docstrings ("ACTIVE ONLY WHEN THE LIMIT FALLS INSIDE THE PROFILE... At or
beyond either end it does nothing"), or (2) limits that leave too little of
the profile to actually machine.

## Why this could not go in [VALIDATION]

Traced `Feature.validate()`'s call site: `ncam_project_io.py:251`, inside
`recursive()`, called BEFORE that function resets and populates
`f.child_features` (line 261-287) and before `[AFTER]` runs (line 289). A
lathe polyline's profile only exists once `resolve_points()` can walk
`child_features`, and the datum globals `lathe_sections.WORKPIECE_FACE_Z` /
`OD` / `ID` are only set as `to_gcode()`'s own walk visits the Workpiece
feature (`ncam_project_io.py` ~143-186), in document order, before the
polyline is reached. `[VALIDATION]` runs first in the SAME feature's own
processing step - too early for either. `[AFTER]` runs last, after
`child_features` is populated - confirmed by every existing
`build_*_gcode` call already living there (`build_z_limit_bounds_gcode`,
`build_sections_gcode`, etc.).

## What was built

`z_limit_span.py` - new module, no GTK, no `ncam` import (same standalone
contract as `lathe_sections.py`), per-lane rule that `lathe_sections.py` has
exactly one writer at a time and this task does not need to be it:

- `outside_profile_problems(polyline_feature)` - mirrors `resolve_points`'s
  own trim order (front, then end) using `lathe_sections.z_limit_abs`,
  `trim_to_front_z`, `trim_to_end_z` directly, so a limit only pushed outside
  by the OTHER limit's own trim is caught too, not just the simple raw-profile
  case (see CASE 3 below).
- `min_machinable_span(rough_cut, nose_r)` = `2*nose_r + rough_cut`.
- `too_little_problem(polyline_feature, rough_cut, nose_r)` - only fires when
  a limit actually trimmed the profile (an untrimmed short profile is not
  this check's business - `PARAM_MIN_PASS`/`PARAM_SKIP_THIN` and
  `profile_problem` already own that).
- `build_z_limit_span_gcode` - both checks as `(WARNING ...)` G-code comments,
  called from `[AFTER]` via `<exec>print(...)</exec>`, same convention as
  every other `build_*_gcode` in `lathe_sections.py`. No `msg_inv` / GTK
  dialog: openPoints.md records "No test may exercise a severity-1
  validation" and severity 2 already has a headless-safe precedent in the
  SAME `[AFTER]` block (`profile_problem`'s WARNING-comment-plus-best-effort
  `mess_dlg`, guarded in `try/except`) - a plain comment is simpler, fully
  testable with `python3`, and sufficient for "detect it and say so".

Wired: `cfg/lathe/polyline.cfg` `version` 1.76 -> 1.77, one new `<exec>` line
in `[AFTER]` right after `build_z_limit_bounds_gcode` (same data, same place).
`ncam.py` gained `import z_limit_span` alongside its existing
`import lathe_sections`, so the module is a bare name in the cfg's `<exec>`
namespace (same mechanism the DEFINITIONS-block comment documents for
`ncam.py`'s own imports).

## The threshold - not a magic number

`2 * nose_r + rough_cut`, both read the same way `TOOL_TABLE.get_rough_cut()`
/ `tip_comp_inputs()[0]` are already read elsewhere in this same `[AFTER]`
block:

- **2 * nose_r** - the tool nose is round, radius `nose_r`. CLAUDE.md's own
  comp-entry rule is "a straight feed of at least the nose radius, in free
  air" to establish contact without gouging - that is ONE wall. A Z-limited
  span is walled at BOTH ends, so it needs that clearance twice: once to
  enter clear of the near wall, once to leave clear of the far one.
- **rough_cut** - one roughing depth of cut. A span that cannot take even a
  single roughing level is not the "thin roughing" `PARAM_SKIP_THIN` /
  `PARAM_MIN_PASS` already have their own threshold for (their tooltips: "Half
  the roughing depth of cut" / "About 2.5 times the tool nose diameter" are
  sensible STARTING values for SKIPPING a level that is mostly redundant with
  the finish pass) - it is a span roughing cannot enter at all.

Either being unknown (0.0 - no tool change yet) drops its own term to 0 rather
than refusing the check, so a project with no tool data is never flagged for
a tool it has not chosen. `min_machinable_span(0.0, 0.0) == 0.0`, proved in
`test_z_limit_span.py`.

## The three cases, proved with numbers

Real project: `testing_15_5.xml` (same one `test_z_limits.py` already uses).
Raw profile Z range measured directly with `resolve_points(pf, trim=False)`
after a real `to_gcode()` walk: **Z-70.400 to Z0.000**, 61 points. Tool
numbers from that project's own Tool Change: `rough_cut = 0.508`,
`nose_r = 0.4` -> threshold `2*0.4 + 0.508 = 1.308`.

Generated via `gen_project.py --config-copy` (no rs274 needed - grepped the
`.ngc` text directly):

| case | override | result |
|---|---|---|
| fine (known-good, `test_z_limits.py`'s own case) | `param_e_z_on=1 param_e_z=-40` | **no WARNING line** |
| baseline, no limits | (none) | **no WARNING line** |
| outside the profile | `param_e_z_on=1 param_e_z=-80` | `(WARNING - Lathe Polyline Z limits: the End Z limit you typed, -80.000, is outside the profile here - it runs from Z-70.400 to Z0.000. The limit does nothing. Move it inside that range, or turn it off)` |
| too little to machine | `param_e_z_on=1 param_e_z=-1` | `(WARNING - Lathe Polyline Z limits: the Z limits leave only 1.000 to machine here, from Z-1.000 to Z0.000 - trimmed by End Z. That is less than 1.308, twice this tool nose radius 0.400 plus one roughing depth of cut 0.508. Loosen a limit, use a smaller nose radius, or a lighter depth of cut)` |

Exact `.ngc` line numbers and grep output captured during the session; all
four generations are reproducible with the commands above.

## Migration proof

`testing_15_5.xml`'s stored polyline `version` attribute (checked directly
against the XML on disk): **1.43** - 34 versions behind the new 1.77. The
WARNING only appears in output generated through `gen_project.py`, which
calls `app.update_features(...)` before `treestore_from_xml` - exactly
NativeCAM's own migration path (`ncam_project_io.py:539`,
`f_B.get_version() > f_A.get_version()` triggers a full template replace).
Since the stored 1.43 template has no `z_limit_span` call at all, the WARNING
appearing on this project's own output IS the migration proof, not a
separate check - it can only have come from the freshly-migrated 1.77
template.

## Fingerprint - the validation-only requirement

Baseline captured on `HEAD` (edits reverted to a clean working tree first -
`--config-copy` preserves symlinks back into the live repo, so any live edit
mid-sweep would have contaminated the "before" run):

```
flock /tmp/ncam-rs274.lock python3 test_motion_fingerprint.py --write fp_before.txt
```

Edits restored, then:

```
flock /tmp/ncam-rs274.lock python3 test_motion_fingerprint.py --baseline fp_before.txt
```

**Result: 46 identical, 0 changed, 0 not in the baseline, of 46.** No motion
diff anywhere - this change is a WARNING-comment emitter and nothing else, as
required (`(WARNING ...)` lines are pure comments; `test_motion_fingerprint.py`
explicitly does not cover comments, by its own docstring).

## Gates - every exit code, this session

```
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py --builtins="_" --select=E9,F63,F7,F82   -> 0
flake8 ncam_*.py lathe_sections.py z_limit_span.py test_z_limit_span.py --builtins="_" --select=E9,F63,F7,F82           -> 0
python3 cam_map.py                                                       -> 0 (all 9 checks PASS)
python3 run_tests.py test_lathe_validation.py test_cam_map.py test_vkb.py test_z_limit_span.py  -> 0 (4 run, 4 passed)
flock /tmp/ncam-rs274.lock python3 test_surface_equality.py              -> 0 (46 generated, 38 compared, one surface)
flock /tmp/ncam-rs274.lock python3 test_project_sweep.py                 -> 0 (45 clean, 1 broken - default_template.xml, pre-existing/expected, unrelated to this change)
flock /tmp/ncam-rs274.lock python3 test_motion_fingerprint.py --baseline fp_before.txt  -> 46 identical, 0 changed, 0 missing
```

`test_rough_ends.py` not run - unrelated known failure per SONNET-LANES.md,
not exercised by this change.

## What is unknown / left

- The threshold is a first cut, same status as `PARAM_MIN_PASS`'s own
  tooltip ("a sensible starting value") - not tuned against a wide range of
  tool geometries beyond the one real project measured here.
- Both messages are unconditional WARNING comments, not gated behind a
  parameter (unlike `WARN_UNREACHABLE`) - if this turns out noisy on a real
  project with intentionally tight limits, a follow-up may want an
  off-switch. Left for greatEndian to judge from real use.
