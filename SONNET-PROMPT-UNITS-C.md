# Task: unit-cover the remaining pure functions in `lathe_sections.py` — batch C

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules.

New file: **`test_contour_units.py`**. Analysis range: **`analysis/170`–`179`**.

Batches A and B (`test_profile_units.py`, `test_window_units.py`, committed as
`37c1952` and `9230065`) are your models — read both before starting. Nineteen
non-`build_` public functions still have no direct unit test:

```
resolve_points_untrimmed :52     rough_emit_reversed  :2458
z_limit_band             :264    rough_nose_terms     :3395
profile_problem          :1234   roughing_call_plan   :3408
section_windows          :1269   flat_sub_number      :3530
level_allowance          :1464   facing_rough_offset  :4903
split_peaks              :1623   finish_profile       :5382
rough_radius_bounds      :2030   unreachable_spans    :5701
ext_dz                   :2076   xw_settings          :6016
floor_stages             :2127
```

**`section_windows` and `split_peaks` are newly unblocked.** Batch A and B were
told to skip anything reaching `detect_sections()` because it was being fixed
concurrently. That fix landed (`f610fbd`) and is verified — 30 of 46 projects
byte-identical, 16 changed with the deepest floor identical in every one. Those
two are now fair game and are the most valuable entries on the list.

`facing_rough_offset` returns a **radial** offset, not an axial one — a T3/Q3
insert cancels the axial term. A test asserting an axial shift is wrong; that
mistake has already been made once here.

Batch B skipped six functions because they need a `Feature` object. **That
skip still stands** — do not fake a `Feature`; a faked fixture tests the fake.
Skip and say so.

## What a good test looks like

Plain point lists and numbers in; no `Feature`, no GTK, no `ncam` import, no
rs274. Import any window bound from `lathe_sections` — never retype a number
like `3600`; `cam_map.py` check C8 fails the build if you do.

Every expected value must be **derived by hand from the geometry**, never
pasted from the function's own output. A test that records current behaviour
proves nothing — it freezes whatever bug is there.

**Find a bug → document it in your analysis file, do NOT fix it.** A geometry
fix moves cut motion and needs gates you are forbidden to run here. The batch-B
worker found none and said so plainly; the worker before it found a real one
and left it alone. Both were right.

## Gates

```bash
flake8 ncam_*.py lathe_sections.py test_contour_units.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py && python3 test_lathe_validation.py
python3 test_profile_units.py && python3 test_window_units.py
python3 test_geometry_primitives.py && python3 test_contour_units.py
```

`test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
ruling — not yours, not a blocker.

## Deliverable

Your test file committed; `analysis/17N-...md` with each function described in
your own words, every hand-derived value, every skip and its reason, and any
bug found but not fixed; then a report with counts and every gate's exit code.

## Non-interference rules

Other Claude sessions may be working in this same git working tree.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage your own files
   by explicit path only. Another session's uncommitted edits live here.
2. **Never run** `test_project_sweep.py`, `test_motion_fingerprint.py`,
   `test_surface_equality.py`, `test_all_projects.py`, or anything under
   `.claude/skills/lathe-gcode-verify/scripts/` — they drive `rs274` and
   generate all 46 projects. `analysis/134` records that this suite returns
   **false FAILs under load**; two drivers looked broken that way today and
   both passed alone.
3. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. Do not fix a failure outside your own files.
4. **Do not push.** Local commits only — pushing is greatEndian's call.
5. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID (inside-diameter) work is **paused** by instruction.
