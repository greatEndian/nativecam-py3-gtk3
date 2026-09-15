# Task: a cfg must be able to CHANGE a parameter's minimum or maximum

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules.

Analysis range: **`analysis/220`–`229`**.

**You own the migration path** — `ncam.py` / `ncam_project_io.py`
(`update_features` and what it calls). Do **not** edit `ncam_preview.py`,
`lathe_sections.py`, `lib/`, or `cfg/` feature templates; other sessions own
those.

## The bug, as recorded in `openPoints.md`

> `update_features` copies the saved bounds back over the cfg's:
>
> ```
> cfg declares     min 0.01    max 10.0
> saved project    min -45.0   max 45.0
> after migration  min -45.0   max 45.0     the stale bound wins
> ```
>
> Found narrowing the back angle clearance (`analysis/043`).

Read that entry in full, and `analysis/043`, before touching anything.

So: a saved project embeds its parameters' bounds, and migration restores those
stale bounds instead of adopting the cfg's new ones. A cfg author therefore
cannot tighten or widen a range on any project that already exists — the change
silently does nothing, which is the same failure shape `CLAUDE.md` warns about
for `version` bumps.

## Why this is delicate, and what to plan before editing

This is the **migration path for every saved project**, so per the blast-radius
rule, find every consumer before you type:

- What else does `update_features` restore from the saved copy, and which of
  those *should* win over the cfg? A user's **value** must survive migration;
  its **bounds** are the cfg author's to change. Establish that distinction in
  the code, and say where the line is.
- What happens to a saved **value that falls outside the cfg's new bounds**
  after the change? That case is the whole risk of this fix: silently clamping
  a user's number is worse than the bug. Decide, state the decision, and make
  it visible to the user rather than silent.
- Does the `version` bump interact? A cfg edit only reaches a saved project
  through migration — check whether a bounds change needs a bump to take
  effect, and record the answer.

## Verify it yourself

The acceptance test is the worked example above, run for real: a project saved
with `min -45.0 / max 45.0`, a cfg declaring `min 0.01 / max 10.0`, migrated —
and the result must be the cfg's bounds, with the saved **value** untouched.

Also prove the reverse: **widening** a range must work too, not just narrowing.
And prove a value outside the new bounds behaves the way you decided, rather
than however it happens to fall out.

Write these as a standalone `test_*.py` in this repo's style (no pytest
harness, runs under plain `python3`, exits non-zero on failure).

## Gates

```bash
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
  --builtins="_" --select=E9,F63,F7,F82
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py
python3 test_lathe_validation.py && python3 test_coord_mapping.py && python3 test_vkb.py
python3 test_ui_panel.py && python3 test_menu_layout.py
python3 <your new test>
```

## Deliverable

The fix and its test committed; `analysis/22N-...md` recording the consumer
survey, the value-vs-bounds decision and its reason, what happens to an
out-of-range saved value, and the migration cases proved; then a report with
every gate's exit code.

**If the fix cannot be made safe for existing projects, say so and commit
nothing but the analysis.** A silent clamp of someone's saved number is a worse
outcome than the bug you were sent to fix.

## Non-interference rules

Other Claude sessions work in this same git tree right now.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only.
2. **Do not run** `test_project_sweep.py`, `test_motion_fingerprint.py`,
   `test_surface_equality.py`, `test_all_projects.py`, or anything under
   `.claude/skills/lathe-gcode-verify/scripts/` — they drive `rs274`, and
   another session may own that. `analysis/134` records that this suite returns
   **false FAILs under load**.
3. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. Never "fix" a failure outside your own files.
4. **Do not push.** Local commits only — greatEndian's call.
5. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID work is **paused** by instruction.
6. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
