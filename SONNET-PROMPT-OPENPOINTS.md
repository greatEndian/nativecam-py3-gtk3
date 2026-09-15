# Task: reconcile `openPoints.md` against the `analysis/` record

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first — in particular the standing rule that `openPoints.md`
records what is LEFT while `analysis/NNN` records the working behind a finding.

Analysis range: **`analysis/190`–`199`**. This task edits **`openPoints.md`
only** — no source, no tests, no `lib/`, no `cfg/`.

## Why this exists

`openPoints.md` has **69 unticked `- [ ]` entries**, and at least one of them is
already done. Today, item **"1. RESPECT TOOL FRONT ANGLE MEASURES THE ANGLE
FROM THE WRONG AXIS"** was recommended as the next piece of work — and its own
body says **"FIXED 2026-08-24, `analysis/064`"**, with the measured result
(both flanks ramping at 13.00 degrees). The checkbox was simply never ticked.

That stale entry came within one step of sending a worker at a solved problem.
A second entry, the `taper_id`/`boring`/`facing` compensation item, is
suspected stale in the same way — part of it may have been closed when facing's
roughing offset moved into Python.

The list is the project's own account of what is left. Right now it cannot be
trusted, and that is a defect in the record worth fixing on its own.

## What to do

Walk **every** `- [ ]` entry in `openPoints.md`. For each, classify it:

- **DONE** — the entry's own body, or a file in `analysis/`, states it was
  fixed, with a measurement. Tick it to `- [x]` and append the evidence inline:
  the analysis number and the measured result already recorded there.
- **BLOCKED ON greatEndian** — the body says NEEDS A CALL, or presents two
  variants for a decision. Leave unticked, but mark it clearly so it is
  visibly *not* available work. Item 2 (back-to-front lead-in) is one: both
  variants are built and measured, awaiting a choice.
- **PARTLY DONE** — some sub-points closed, others open. Say which, and make
  the remaining part the entry's headline so it reads as what is actually left.
- **GENUINELY OPEN** — leave exactly as it is.

Then, at the top of the file, add a short index: how many entries in each
class, and a list of every entry that is **genuinely open and needs nobody**.
That list is the answer to "what can a worker do next", which is currently
expensive to compute and was got wrong today.

## Rules of evidence

- **Never tick an entry on the strength of the body's own claim alone** if that
  claim has no analysis number and no measurement behind it. An entry asserting
  "fixed" with nothing to point at is a *finding*, not a closure — list it
  separately as unverified, and leave it unticked.
- Cross-check against `analysis/` by grep, not by memory.
- **Do not verify by running anything that generates projects or drives
  `rs274`** (see the non-interference rules). This is a documentation
  reconciliation, not a re-measurement. Where closing an entry would need a
  fresh measurement, say so and leave it open.
- Where the body and an analysis file **disagree**, that is the most valuable
  thing you can find. Do not resolve it silently — record both readings.

## Gates

```bash
python3 cam_map.py && python3 test_cam_map.py
git diff --stat          # must show openPoints.md and nothing else
```

## Deliverable

1. `openPoints.md` updated and committed (that file alone).
2. `analysis/19N-openpoints-reconciliation.md`: the counts per class, every
   entry reclassified with the evidence used, every body/analysis disagreement
   found, and every entry whose "fixed" claim has nothing behind it.
3. A report naming the genuinely-open-and-unblocked entries — that list is the
   point of the task.

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
