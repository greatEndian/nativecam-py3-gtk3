# Task: finish the preview pane — wire collision detection, and three small toggles

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules.

Analysis range: **`analysis/200`–`209`**.

**You own `ncam_preview.py`.** No other session may edit it while you work.
In exchange, do not edit `lathe_sections.py`, `lib/`, `cfg/`, or any
`test_*.py` that another worker is creating.

## Why this is safe to run in parallel

This is preview/GTK work. It must not change generated G-code at all. If a
change of yours alters any produced toolpath, you have gone out of scope —
stop and report rather than continue.

## The work — four entries, all listed as open and unblocked in `openPoints.md`

Read each entry in `openPoints.md` in full before starting; each carries prior
measurements you should not re-derive.

1. **Collision detection is built and tested but not wired to the pane.** The
   detection exists (`ncam_preview.py`, `test_collisions.py`,
   `test_tool_silhouette.py` all pass today) but nothing surfaces it to the
   user. Wire it.
2. **Timeline marks for collisions, and a Verification line in Stats.** The
   natural companion to 1 — where a collision is found, mark it on the
   timeline and state the verdict in Stats.
3. **`Accuracy` slider → `StockField.columns_for`** (`ncam_preview.py:1617`).
   Small; the slider should drive the column count that already exists.
4. **Programmed Point toggle** and **Regenerate on rewind as an option** — both
   marked tiny in the index.

Do 1 and 2 first: they are the substance, and 3/4 are small enough to finish
after. **Landing 1 and 2 properly is worth more than landing all four
hurriedly.** If you run out of room, commit what is complete and say what is
left — do not half-wire the collision pane.

## Verify it yourself

`ncam_preview.py` has existing tests — `test_collisions.py`,
`test_tool_silhouette.py`, `test_leads.py`, `test_rough_comp.py` all import it.
They must still pass. Add a test for what you wire: a collision the pane is
told about, and one it is not.

There is a real trap recorded in that file at line ~1197: an earlier check
*"reported the SAME 50 collisions for a 12 m program and for a program with
none"* — a detector that always fires is indistinguishable from one that works
until you feed it a clean program. **Your test must include a clean case that
reports zero.**

## Gates

```bash
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
  --builtins="_" --select=E9,F63,F7,F82
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py
python3 test_collisions.py && python3 test_tool_silhouette.py
python3 test_leads.py && python3 test_ui_panel.py && python3 test_menu_layout.py
```

## Deliverable

The wiring committed, with its test; `analysis/20N-...md` recording what each
entry needed, what you measured, and anything you left; then a report with each
entry's state and every gate's exit code.

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
