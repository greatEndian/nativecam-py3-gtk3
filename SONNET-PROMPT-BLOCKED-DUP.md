# Task: the front interval of the first blocked level is emitted twice

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules — especially **plan the
whole blast radius first** and **self-verify**.

Analysis range: **`analysis/210`–`219`**.

## Run alone

This changes cut motion. Do **not** start while another session is running
`rs274` or generating projects, and do not run this concurrently with a sweep —
`analysis/134` records that concurrency produces false FAILs here, and it has
corrupted measurements in this project four times.

## The bug

From `openPoints.md` (search: *"front interval of the first blocked level"*):

> the front interval of the first blocked level is emitted **twice** —
> identical moves, `34.0636 0.0000 -> -31.2092`. Pre-existing, follows
> whichever level is first blocked, costs an air-cutting repeat rather than
> any wrong metal.

So: a duplicated pass, always on the **first blocked** level, whichever that
is. It cuts no wrong metal — it wastes a pass in air. That makes it a clean
target: the fix should **remove** moves and change nothing else.

Read the whole surrounding section of `openPoints.md` before starting. It ends
with a recorded lesson that applies directly to this task:

> Three checks in a row looked at the passes that EXIST and found them regular.
> A missing pass is only visible if you ask which levels are ABSENT — dumping
> the whole ladder sorted by X, front and behind intervals side by side, showed
> it in one line. **Prefer a measurement that enumerates what should be there
> over one that inspects what is.**

Build that enumerating instrument first, and check it against a number you
already know before trusting it.

## Method

1. **Reproduce** the duplicate and name the project and level it appears on.
2. **Find every consumer** of the blocked-level interval path by grep, not
   memory — `_split_level_intervals`, `lathe_level_pass.ngc`, and whatever else
   emits interval calls. State which one duplicates, and why.
3. **Baseline the motion first**: `python3 test_motion_fingerprint.py` writes a
   per-project hash table. Capture it **before any edit** — it is unrecoverable
   afterwards.
4. **Fix it in Python** if the duplication is decided at generation time. The
   standing rule is Python first, O-code last; if the duplicate is emitted by
   the `.ngc`, check whether the decision behind it belongs in Python.
5. **Re-fingerprint.** Expected shape of a correct result: the projects that
   change should **lose** moves, never gain them, and the finished surface must
   be untouched. Justify **every** changed project individually. A project that
   gains moves, or a changed finished depth, means the fix is wrong — stop and
   report rather than commit.
6. Add a regression test that fails on the old code.

## Gates

```bash
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py && python3 test_lathe_validation.py
python3 test_level_intervals.py && python3 test_level_blocked.py
python3 test_sub_spans.py && python3 test_ladder.py && python3 test_x_continuity.py
python3 test_surface_equality.py
python3 test_project_sweep.py
python3 test_motion_fingerprint.py
```

## Deliverable

The fix committed with its regression test; `analysis/21N-...md` with the
reproduction, the consumer table, the before/after move counts per changed
project and why each is right, and what is still unknown; then a report naming
how many of the 46 projects changed and every gate's exit code.

**Finding no safe fix is an acceptable outcome.** An analysis proving the
duplication cannot be removed without moving metal is worth more than a change
nobody can account for.

## Non-interference rules

Other Claude sessions work in this same git tree.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only — another session has uncommitted edits here.
2. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. `analysis/134` records that this suite returns **false FAILs under
   load**; two drivers looked broken that way today and both passed alone.
   Never "fix" a failure outside your own files.
3. **Do not push.** Local commits only — greatEndian's call.
4. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID (inside-diameter) work is **paused** by instruction.
5. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
