# 118 — the window re-layout, part A: capacity and honest fallbacks

**Asked**: greatEndian, 2026-09-09 — *"plan the window re-layout"*, then *"go a"*.
Commit A of the two the plan split out: the capacity fix and the fallback
repairs, with the coverage fix (commit B) to follow.

## What was actually wrong

`analysis/117` left the coverage gap blocked on two windows. Auditing them found
the blockage was already causing damage, and that three fallback paths did not
fall back.

**ERAMP was overflowing today, on four shipped projects.** Verified in the
committed tree: `testing_13_arc_first` generated `#<_pl_entry_n> = 60` and
`#<_pl_eramp_n> = 0`, the zero being only the defaults block. The table costs
4 slots per ENTRY-contour segment - 59 x 4 + 3 = **239 against a capacity of
180** - so `build_entry_ramp_gcode` returned `''` and said nothing. Same on
`_0`, `_1` and `testing_13_arcs`. On every project that fits,
`eramp_n == entry_n - 1` exactly; those four were the only exceptions.

**Correcting my own account of it**: this did NOT mean those projects cut
without ramps. `testing_13_arc_first` has **339 shallow roughing ramps both
before and after** the fix. What it lacked was the ramp-DIRECTION table, so
every one of those ramps used the fallback - the segment the pass happens to
start on - instead of the dominant surface ahead, which is the whole reason
`entry_ramp_dirs` exists (greatEndian: a 2.9656 ramp where every neighbour runs
2.2004). The first framing, that they "ran with no profile-angle ramps", is true
of the table and overstates the motion.

**ERAMP's demand scales with the ENTRY contour, not the finish contour**, and
the entry contour is about twice as long: `fc_n 31 -> entry_n 60`. An earlier
sizing estimate of +320 slots was made against the finish contour and was too
low; the real figure is roughly double.

**Three fallbacks that did not fall back**, all pre-existing:

- `floor_contour_data` returned a WARNING **string** on overflow while both
  callers test `is None` and then unpack three names. A string is not `None`, so
  `env, renv, rough_dir = got` ran on it and raised `ValueError: too many values
  to unpack`. The one table meant to degrade with a comment was the one that
  killed generation.
- `build_sect_floor_gcode` **raised** `ValueError` outright.
- `build_level_split_gcode` returned a bare `''`, silently, like the ramp table.

And two ceiling expressions still named a neighbouring window instead of their
own top - `SECT_FLOOR` capped itself with `SECT_BASE`, with no `SECT_FLOOR_TOP`
existing - plus two test files (`test_through_cut.py`, `test_rough_overlay.py`)
that retyped window bounds instead of importing them. That is the same class as
the `FLANK_BASE` bug fixed in `ce50241`; it survived in four more places.

## What was done

**Phase 1, moving nothing.** `SECT_FLOOR_TOP = 3400` (the value the old
expression produced). `_pl_eramp_base` emitted, defaulted in `create_defaults()`
and read by `lathe_level_pass.ngc` in place of its two `3200` literals, so ERAMP
is addressed like every other table; `ERAMP_BASE` dropped from `cam_map`'s
`LITERAL_WINDOWS`. Every fallback now emits a `(WARNING - ...)` comment;
`floor_contour_data` returns a `FLOORC_OVERFLOW` sentinel so its two callers can
tell an overflow from "nothing to say" - the emitter owes a comment for one and
silence for the other, and the planner must fall back for both or it would
reason from a contour the runtime never received. The two tests take their
bounds from the module.

**Phase 2, the move.**

```
LVL    1000..1800   800 slots  (was 1600; measured peak 180, design worst case 595)
ERAMP  1800..2400   600 slots  (was 180 -> 45 segments; now 149)
FLANK  2400..2600   200 slots  (was 100 -> 50 points; now 100, matching FC/ENTRY/STOP)
```

`3200..3380` and `3600..3700` are released. `LVL_BASE` does **not** move:
`poly_lathe_mill`'s directory read is a bare `#[1000 + ...]`, absent from
`LITERAL_WINDOWS` and below `ngc_literals`' 3160 regex floor, so a base move
there is the one thing no static check would catch. It is now listed in
`LITERAL_WINDOWS` so that is no longer true.

## Verification

- **Motion fingerprint, all 46 projects: identical, twice** - after phase 1 and
  after phase 2. I had expected the four repaired projects to change; they do
  not, because their table's directions agree with the fallback everywhere. The
  fix is real (`eramp_n` 0 -> 59/60, measured) and latent at today's settings.
- No `WARNING` in any generated program; `test_project_sweep` 45 clean of 46.
- Whole suite exit 0: flake8, cam_map, test_cam_map, test_lathe_validation,
  test_sections, test_ramps, test_ladder, test_ladder_account,
  test_level_intervals, test_level_blocked, test_sub_spans,
  test_roughing_windows, test_ladder_python, test_leftover, test_x_continuity,
  test_bidir_warn, test_through_cut, test_rough_overlay, test_resume_envelope,
  test_surface_equality.

## Guardrails added, and a false positive in one of them

`test_project_sweep` now fails when a table's count global sits at 0 while the
table it indexes is non-empty - the `eramp_n == entry_n - 1` signature that
exposed this bug. `cam_map`'s `LITERAL_WINDOWS` gained `LVL_BASE`.
`test_sections`' layout regions now list every window, not six of them.

**The first version of the sweep check was wrong and the negative control found
it.** Thresholded at `entry_n > 1`, it flagged `testing_12_1`, whose entry
contour has 2 points - `build_entry_ramp_gcode` declines those by its own
`len(points) < 3` guard, correctly. Threshold matched to the builder. Worth
recording because the check had never been run on the fixed tree at that point:
the earlier passing sweep predated it, so "the suite is green" would have been
said over a check that had only ever run once, in the control.

Control, with `ERAMP_TOP` put back to 180 slots: exit 1, flagging exactly the
four projects, `testing_12_1` no longer among them. Restored: exit 0.

`test_motion_fingerprint.py` is committed as a tool - `--write` to record,
`--baseline` to compare. Deliberately not in the suite: it takes ~10 minutes and
needs a baseline recorded from the tree being compared against, which is a
decision rather than a constant. A stale one produced a false "all 36 differ"
earlier in this work.

## Still open

Commit B - the coverage fix itself. Sizing for it must be measured, not
extrapolated: at 66 finish-contour points the entry contour is ~128, needing
~511 ERAMP slots (600 available) and ~256 ENTRY slots against ENTRY's 200. STOP
and FLOORC scale with the same contour and are unchecked at that resolution.
