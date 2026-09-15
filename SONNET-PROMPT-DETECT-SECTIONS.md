# Task: fix the `detect_sections()` wrong `min_x` on rising sections

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules — especially
**plan the whole blast radius first**, **research → show the path → fix →
self-verify**, and **Python first**.

## Run alone

This task **changes cut motion**. Do not run it while another terminal is
running `rs274`, `test_project_sweep.py`, or any gate — concurrent runs have
corrupted measurements in this project three separate times. If you are told
another session is active, wait.

Your analysis-file range is **`analysis/140`–`analysis/149`**. Do not use any
number below 140; two sessions already collided on 130 and it cost two cleanup
commits.

## The bug

`detect_sections(points)` returns `(z_from, z_to, min_x)` per section. For a
**rising** (monotonic non-decreasing) section it reports the wrong `min_x` —
it reports a value from inside the section rather than the section's true
minimum, which for a rising region is at its own start.

Verified reproduction:

```python
import lathe_sections as ls
ls.detect_sections([(0,20), (-10,20), (-20,40), (-30,60)])
#   section 1  Z-10.0..-30.0  min_x = 40.0     <-- true minimum over that span is 20.0
```

`analysis/130-detect-sections-rising-min-x.md` is the existing write-up —
**read it before touching anything**. It has the worked example, the docstring
contradiction, and the tie to `analysis/057`.

## What already exists, and must be studied first

`analysis/057` hit this same flaw and **worked around it locally** rather than
fixing it: `_side_min()` inside `_boundary_list()` (`lathe_sections.py:~1500`)
recomputes the minimum itself instead of trusting `detect_sections`. That
workaround was never applied to the other consumers. Understand why 057 chose a
local workaround before you decide to fix the root.

## Blast radius — three consumers, found by grep, not memory

| caller | line | what it does with `min_x` |
|---|---|---|
| `section_windows()` | `lathe_sections.py:1327` | ? |
| `split_peaks()` | `lathe_sections.py:1640` | ? |
| `floor_regions()` | `lathe_sections.py:1793` | ? |
| `_boundary_list()` | `~1500` | bypasses it via `_side_min` (the 057 workaround) |

Tests that call it directly: `test_sections.py:346,611`, and
`test_sectioning_windows.py` (which calls it indirectly through
`floor_regions`, and whose test profiles were deliberately confined to
falling/flat shapes to avoid this bug).

**Fill in that table yourself before editing.** The real design question this
task must answer is *where the fix belongs*:

- **(a)** fix `detect_sections` at the root — correct for all consumers, but
  changes three call sites' inputs at once; or
- **(b)** fix only the consumer(s) that assume `min_x` means "deepest material
  in this region", the way `_side_min` did — smaller blast radius, but leaves
  the trap in place for the next caller.

Pick one, and **state the reason in the analysis file**. Do not pick (a) just
because it is tidier, and do not pick (b) just because it is smaller.

## Method — measure before you decide

1. **Reproduce** the wrong number and write it down.
2. **Answer the table**: for each of the three consumers, does a wrong rising
   `min_x` actually reach cut motion, or is it discarded/overwritten downstream?
   This is the crux. A consumer that never uses it is not part of the fix.
3. **Baseline the motion** across all 46 projects with
   `python3 test_motion_fingerprint.py` (record the fingerprints *before* any
   edit — you cannot recover this afterwards).
4. **Fix it.**
5. **Re-fingerprint.** Then:
   - **Zero projects changed** → the fix is provably safe. Commit it with a
     regression test that fails on the old code.
   - **Some projects changed** → that is expected for a real geometry fix, but
     **each changed project must be justified individually** in the analysis
     file: which section, why the old path was wrong, why the new one is right.
     A fingerprint diff you cannot explain is a bug you introduced, not the fix
     landing. If you cannot explain one, **stop and report** rather than commit.
6. **Add the regression test** — a rising profile asserting the true minimum,
   in the style of `test_geometry_primitives.py`. Import window bounds from
   `lathe_sections`, never retype them (`cam_map` check C8 enforces this).

## Gates — all must pass before you commit

```bash
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
  --builtins="_" --select=E9,F63,F7,F82
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py
python3 test_cam_map.py
python3 test_lathe_validation.py
python3 test_sections.py
python3 test_sectioning_windows.py
python3 test_geometry_primitives.py
python3 test_surface_equality.py
python3 test_project_sweep.py      # 46 projects must still generate AND run
python3 test_motion_fingerprint.py # the primary gate for this task
```

`test_rough_ends.py` is a **known failure** awaiting a ruling from greatEndian
on tip-vs-cut semantics — it is not yours to fix and not a blocker.

## Hard limits

- **Do not push.** Commit locally only; pushing is greatEndian's call.
- **Do not touch** the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc`
  or any live `.var` file. Never run `rs274 -v` against a live `.var` — always
  the scratch copy that `parse_rs274.run_rs274()` makes.
- **ID (inside-diameter) work is PAUSED** by greatEndian's instruction. If the
  fix reaches ID geometry, stop and report.
- If a `cfg/` file is edited, its `version` **must** be bumped or the change
  never reaches a saved project.

## Deliverable

1. The fix, committed, with its regression test.
2. `analysis/14N-...md`: what was measured with real numbers, which option
   (a or b) you chose and why, the per-project justification for every
   fingerprint change, and what is still unknown.
3. A closing report stating: the option chosen, how many of the 46 projects
   changed motion, and every gate's actual exit code.

**Not finding a safe fix is an acceptable outcome.** Writing the analysis that
proves the blast radius is too large, and committing no code, is worth more
than a fix that moves motion you cannot explain.
