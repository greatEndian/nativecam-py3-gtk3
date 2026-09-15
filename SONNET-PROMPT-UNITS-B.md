# Task: unit-cover 12 pure functions in `lathe_sections.py` — batch B

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules.

Write your tests to a **new file**: `test_window_units.py`
Your analysis-file range is **`analysis/160`–`analysis/169`**. Never use a
number outside it — two sessions already collided on 130 and it cost two
cleanup commits.

## The functions (batch B — windows, call planning, offsets)

| function | line |
|---|---|
| `protected_flags` | 3087 |
| `level_floors` | 3115 |
| `window_calls` | 3315 |
| `rough_nose_terms` | 3390 |
| `roughing_call_plan` | 3403 |
| `flat_sub_number` | 3525 |
| `wrong_way_dirs` | 3626 |
| `curve_offsets` | 4115 |
| `stock_at_normal` | 4186 |
| `facing_rough_offset` | 4898 |
| `unreachable_spans` | 5696 |
| `xw_settings` | 6011 |

Cover as many as are genuinely pure. Twelve is the list, not the quota —
skipping four with a stated reason beats faking four `Feature` objects.

`facing_rough_offset` is worth extra care: it was moved from O-code into Python
very recently, and the offset it returns is **radial, not axial** — a T3/Q3
insert cancels the axial term. A test asserting an axial shift there is wrong;
that mistake has already been made once in this project.

## Non-interference rules — read these first, they are why this prompt exists

**Two other Claude sessions are working in this same git working tree right
now.** One is fixing `detect_sections()` and will be rewriting geometry and
running whole-project motion gates. Your job is written so it cannot collide
with them. Obey these literally:

1. **Create NEW test files only.** Do not edit `lathe_sections.py`, do not edit
   any existing `test_*.py`, do not edit anything under `lib/` or `cfg/`. If
   your task seems to need a source edit, it does not — document it instead
   (rule 6).
2. **Never `git add -A`, `git add .`, or `git commit -a`.** Another session has
   uncommitted edits in this tree and those commands would sweep them into your
   commit. Stage your own files by explicit path only:
   `git add <your-new-file> analysis/<your-file>.md`
3. **Never run these** — they invoke `rs274` or generate all 46 projects, and
   another session owns that machine time:
   `test_project_sweep.py`, `test_motion_fingerprint.py`,
   `test_surface_equality.py`, `test_all_projects.py`, and anything under
   `.claude/skills/lathe-gcode-verify/scripts/`.
4. **Skip any function that reaches `detect_sections()` or `floor_regions()`**,
   directly or indirectly — another session is changing their behaviour, so a
   test you write against today's output may be asserting a bug. Check with
   grep before testing each function; list every one you skipped, and why, in
   your report.
5. **If a gate fails in a file you did not touch, re-run it once.** Another
   session may have been mid-edit. Do not "fix" a failure outside your own
   files — report it.
6. **Find a bug → document it, do NOT fix it.** A geometry fix moves cut motion
   and needs gates you are forbidden from running here. Write it up in your
   analysis file and leave the code alone. The last worker did exactly this and
   it was the most valuable thing it produced.

## What a good test looks like

Copy the shape of `test_geometry_primitives.py`: plain point lists and numbers
in, no `Feature` object, no GTK, no `ncam` import, no rs274. If a function
requires a `Feature` to call, **skip it** and say so — faking one is out of
scope and produces tests that assert the fake, not the code.

Import any window bound from `lathe_sections` — never retype a number like
`3600`. `cam_map.py` check C8 fails the build if you retype one, and that is
the exact class of bug that has cost this project four rounds.

Each check asserts a value you derived **by hand from the geometry**, not a
value you got by running the function and pasting the output. A test that
records current behaviour proves nothing; it just freezes a bug.

## Gates — cheap ones only, all must pass before committing

```bash
flake8 ncam_*.py lathe_sections.py <your-new-file> --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py
python3 test_cam_map.py
python3 test_lathe_validation.py
python3 test_coord_mapping.py
python3 test_geometry_primitives.py
python3 <your-new-file>
```

`test_rough_ends.py` is a known failure awaiting a ruling from greatEndian —
not yours, not a blocker.

## Hard limits

- **Do not push.** Local commits only; pushing is greatEndian's call.
- Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
  any `.var` file.
- ID (inside-diameter) work is **paused** by greatEndian's instruction.

## Deliverable

1. Your new test file, committed, with every check passing.
2. `analysis/<your range>-<slug>.md` — what each function actually does in your
   own words, every hand-derived expected value, every function you skipped and
   why, and any bug you found (documented, not fixed).
3. A closing report: how many functions covered, how many checks, how many
   skipped and why, any bug found, and every gate's actual exit code.
