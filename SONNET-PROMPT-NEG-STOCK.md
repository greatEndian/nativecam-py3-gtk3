# Task: negative stock to leave fails SILENTLY past its bound

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first. Analysis range: **`analysis/260`–`269`**.

## Run alone

You edit `lathe_sections.py`, a single-writer file. Do not start while another
geometry session is active, and do not run `rs274` concurrently with one.

## The bug, as recorded in `openPoints.md`

> `offset_contour` already cuts past the model correctly down to
> `extra > -nose_r` — measured −0.10 → −0.1000 and −0.39 → −0.3900 with a 0.4
> nose. At −0.40 and −0.50 the guard returns the profile unchanged: **ask for
> 0.5 past the model and get 0.0, with no warning.**

`offset_contour` is at `lathe_sections.py:4220`. Read the entry in full first.

## Scope — the guard only

The entry names two halves. **You are doing the first one:**

- **IN SCOPE — make the silent failure loud.** Asking for more than the nose
  allows must produce a clear, visible refusal or warning naming the bound and
  the value asked for. Silently returning 0.0 is the defect.
- **OUT OF SCOPE — exposing the parameter.** The cfg minimum is 0.0, so a
  negative value is unreachable today. Exposing it needs *"a decision about
  roughing, which cannot hold a negative allowance without a nose"* — that is
  greatEndian's call, not yours. **Do not lower the cfg minimum.**

Because the parameter is unreachable from the UI, a correct fix should change
**no motion on any of the 46 projects**. That makes verification unusually
clean: it is a pure guard, and any motion change means you have gone out of
scope.

## Method

1. **Reproduce** both cases with real numbers: −0.39 with a 0.4 nose returning
   −0.3900, and −0.40/−0.50 returning the profile unchanged. Write them down.
2. **Find every caller** of `offset_contour` by grep, not memory — there is at
   least one in `ncam_preview_ui.py:1355` and several in
   `test_offset_contour.py`. A warning that only the CAM path sees is half a
   fix; decide where the message has to surface and say why.
3. **Decide refuse vs clamp-with-warning, and justify it.** The
   `param-bounds` work of 2026-09-13 settled a related principle: silently
   changing a user's number is worse than the bug. Apply the same reasoning
   and state it.
4. **Baseline the motion before editing**: `python3 test_motion_fingerprint.py`
   writes a per-project hash table and it is unrecoverable afterwards.
5. Fix it, then **re-fingerprint: 46 of 46 must be identical.** Anything else
   means the guard reached live geometry — stop and report.
6. Add regression tests to a **new** file (do not edit `test_offset_contour.py`
   if another session may own it): the last good value, the first refused
   value, and the boundary exactly at `-nose_r`.

## Gates

```bash
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
python3 run_tests.py test_offset_contour.py test_cam_map.py test_lathe_validation.py \
        test_geometry_primitives.py <your new test>
python3 cam_map.py
python3 test_surface_equality.py
python3 test_project_sweep.py
python3 test_motion_fingerprint.py
```

## Deliverable

The guard and its tests committed; `analysis/26N-...md` with the reproduced
numbers, the caller survey, the refuse-vs-clamp decision and its reason, and
the fingerprint result; then a report with every gate's exit code.

State explicitly in your report that the **exposure half remains open and needs
greatEndian's decision** — do not let it look finished.

## Non-interference rules

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only. On 2026-09-13 a worker's bulk `git add` swept three of another
   session's in-flight files into its commit (`8c38722`, undone by `1e08a93`).
2. **You are the single writer of `lathe_sections.py`.** Nearly every geometry
   task edits that file, so only one such session may run at a time. Confirm
   with greatEndian that no other geometry worker is active before you start.
3. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. `analysis/134`: this suite returns **false FAILs under load**. Prefer
   `python3 run_tests.py <drivers>` — it re-runs a failing driver once and
   reports "passed on retry" separately from "failed twice".
4. **Do not push.** Local commits only — greatEndian's call.
5. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID work is **paused** by instruction.
6. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
7. **Lane: GEOMETRY, main tree.** Read `/home/user/nativeCamDev/SONNET-LANES.md`
   first. Every `rs274`/generation/sweep/fingerprint command runs as
   `flock /tmp/ncam-rs274.lock <command>` — other terminals are running.
   `roughing_ladder`'s ceiling-dup fix (analysis/210) lands just before you
   start; record your fingerprint baseline AFTER `git log` shows it.
