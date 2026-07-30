---
name: lathe-gcode-verify
description: "Use after any change to lib/lathe/*.ngc or cfg/lathe/*.cfg, or before reporting a lathe G-code fix as done. Runs the project's static checks plus an actual rs274 motion trace (tangent-continuity and dropped-fillet detection), ending in a hard PASS/FAIL verdict. Never invoke rs274 directly against a live lathe.var when this skill's scripts can do it safely instead."
---

# /lathe-gcode-verify

Verify a change to NativeCAM's lathe G-code generation (`cfg/lathe/*.cfg`, `lib/lathe/*.ngc`, or `ncam.py`) actually produces correct, non-regressed machine motion — not just code that reads right.

## Usage

```
/lathe-gcode-verify                                   # verify against the live-generated ncam.ngc for the ncam_demo lathe config
/lathe-gcode-verify --ngc <path>                      # verify a specific .ngc file instead
/lathe-gcode-verify --marker "retreat lead-out"       # also assert every marker comment is followed by an arc (catch a silently-dropped fillet)
```

## Proving nose compensation

Three scripts, and picking the wrong one wastes a run:

- `prove_tip_comp.py` — the parametric ops (`taper`, `taper_id`, `boring`, `facing`, `radius_od`, `turning`). Their target wall is a formula it rebuilds from a few numbers. Needs the correct `--side` to PASS **and** the wrong `--freeside` to FAIL.
- `prove_cam_comp.py` — a **polyline**, in either compensation mode. Takes the target profile from `lathe_sections.resolve_points` instead of a retyped `--profile`, and runs its own negative control by offsetting to the opposite side and requiring that to fail.
  ```bash
  python3 .claude/skills/lathe-gcode-verify/scripts/prove_cam_comp.py \
      --ini configs/sim/axis/ncam_demo/lathe-mm.ini --project testing_15_0.xml
  # ID work: the lead-in/out geometry is a separate question - see below
  ... --project testing_14_inside.xml --lead-margin 2
  ```
- `check_flank_clearance.py` — the roughing flank shadow, a different question entirely (tool *body*, not tip).

Two things learned the hard way here:

- **`check_nose_tangent.prove()` is wrong for a polyline.** It measures each point against its nearest single segment's *infinite line* while calling the point interior within 2% of the segment's ends. A nose legitimately rolling `R√2` past a convex corner still falls inside that window, where the distance to the extended line reads as zero — a false gouge of the full nose radius at every convex corner, which no `--tol` can separate from a real one. `prove_cam_comp.prove_region()` judges against the material *region* instead, with distances clamped to the segments.
- **Lead-in/lead-out must be judged separately from the contour.** Their geometry comes from the lead parameters, not the compensation. On ID work the ends currently gouge — 0.2929 mm in CAM mode and **1.4929 mm under native compensation** on `testing_14_inside`, against 0.0000 on the contour itself in CAM mode. Folding that into the verdict reports a pre-existing lead problem as a compensation fault; `--lead-margin` reports it instead of judging it. That ID lead clearance is a real open bug, not an artifact.

## What this replaces

Before this skill existed, verifying a lathe G-code change meant hand-writing a throwaway Python script every time: shelling out to `rs274`, parsing `STRAIGHT_FEED`/`STRAIGHT_TRAVERSE`/`ARC_FEED` canon lines, computing tangent dot products, checking arc presence after a comment marker — and re-deriving the "never point rs274 at the live var file" rule from scratch each session. That work is now in `scripts/parse_rs274.py` and `scripts/check_tangent.py`.

## Steps

1. **Static checks first** (cheap, catch obvious breakage before spending an rs274 run):
   ```bash
   flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py --builtins="_" --select=E9,F63,F7,F82
   python3 test_lathe_validation.py
   python3 test_coord_mapping.py
   ```
   If either fails, stop and fix before proceeding — a motion trace over broken code is meaningless.

2. **Locate the .ngc to verify.** Default: `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` (the user's live GUI-regenerated project — read-only, never edit it directly; see CLAUDE.md). If testing a scenario the live project doesn't currently exercise (e.g. a specific `lo_rad`/`li_rad`/`nose_comp` combination), write a small standalone `.ngc` calling the subroutine directly instead of trying to coax the GUI into the right state.

3. **Run the motion check:**
   ```bash
   python3 .claude/skills/lathe-gcode-verify/scripts/check_tangent.py \
     --ini configs/sim/axis/ncam_demo/lathe-mm.ini \
     --ngc <path-to-ngc> \
     --marker "retreat lead-out"        # omit --marker if not checking for a specific dropped-fillet pattern
   ```
   This always runs `rs274` against an isolated **scratch copy** of the ini's real var file (`parse_rs274.run_rs274` copies it to a tmp dir before ever invoking `rs274 -v` on it) — the live `lathe.var`/`lathe_mm.var` is never touched, never at risk from a crashed/interrupted run.

4. **Read the verdict, don't just glance at it.** The script's last line is always exactly one of:
   - `[VERDICT: PASS]`
   - `[VERDICT: FAIL - <reason>]`

   A FAIL with "N of M marker(s) missing an arc" is not automatically a bug — check the relevant `li_rad`/`lo_rad` parameter in the `.ngc` first (0 genuinely means "no fillet, straight lead only" and the marker check should be skipped or expected to report all-missing in that case).

5. Report the verdict and the specific numbers (min tangent dot, arc/marker counts) to the user — not just "looks good."

## Gotchas & Edge Cases

- **Never run `rs274 -v` against a live `.var` file directly.** A crashed/interrupted run can permanently corrupt real machine coordinate offsets. This is why `run_rs274()` always copies to a scratch dir first — don't bypass it by calling `rs274` directly in a one-off shell command.
- **Relative `--ngc`/`--ini` paths must survive a `cwd` change.** `rs274` needs `cwd` = the ini's own directory (`SUBROUTINE_PATH` and other ini entries are relative to it). `run_rs274()` absolutizes both paths against the caller's cwd before switching — if you extend this script, keep that order or relative paths silently resolve against the wrong directory and you get a silent 0-line canon output (looks like "no error" but nothing was actually parsed — always sanity-check `move_count` before trusting a report).
- **G18 (lathe) canon axis order**: in `STRAIGHT_FEED`/`STRAIGHT_TRAVERSE`, first arg is X, third is Z (not X/Y/Z as in a mill's G17 plane). `ARC_FEED`'s args are `(line, first_end, second_end, first_axis_center, second_axis_center, rotation, ...)` = `(z_end, x_end, zc, xc, rot, ...)` for a lathe. Getting this order wrong silently produces a "successful" but numerically meaningless tangent check.
- **`li_rad`/`lo_rad` = 0 is a valid, common configuration**, not a bug — it means a straight lead with no tangent fillet arc. The marker-arc check will (correctly) report every marker as "missing an arc" in that case. Check the actual parameter value in the `.ngc` (`grep -n "#15[4-5] ="` for the lathe roughing pass) before treating a marker-check FAIL as a regression.
- **`-b` (block-delete) is required** when running `rs274` against `ncam.ngc` — the generated file has a `/  o<safety_9999> repeat [1000] / M123 / M0` guard block for interactive safety that will otherwise make the interpreter hang waiting on stdin in batch mode.
- **The live-project `ncam.ngc` changes between sessions** as the user edits parameters and rebuilds in the GUI — before treating a run's arc count or parameter values as "the current state," re-`grep` the actual file; don't trust a prior session's memory of what it contained.

## Verification of this skill itself

Both scripts were validated against the real project before being written up here:
- `check_tangent.py` correctly reported `[VERDICT: PASS]` against a scratch test file with `lo_rad=0.5` (19/19 markers followed by a tangent arc, min dot 1.0).
- It correctly reported `[VERDICT: FAIL - 18 of 19 ... missing an arc]` against the live `ncam.ngc`, which turned out to be an accurate reflection of `lo_rad=0` in that file's current parameters, not a script defect.
- The scratch-var isolation was confirmed by `md5sum`-ing the real `lathe.var` before and after multiple runs — unchanged.
