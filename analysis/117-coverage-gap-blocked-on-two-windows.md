# 117 — the coverage gap closes, and is blocked by two parameter windows

**Asked**: greatEndian, 2026-09-08 — *"go on with the coverage gap"*, the open
point from `analysis/116`.

**Result: the gap is closable and was closed in a working tree — native
compensation went from 21 uncovered segments to 0 and PASSED — but shipping it
needs a parameter-window re-layout, so the geometry change was reverted and only
the safe findings are committed.** What is committed changes no motion on any of
the 46 projects.

## The gap does close

Keeping the drawn profile's arc points instead of thinning them, `prove_cam_comp
--mode 1` on testing_13_arc_first:

| | before | after |
|---|---|---|
| segments uncovered | 21 | **0** |
| tangent points | 1407 | 3469 |
| contour gouge | 0.0000 | 0.0000 |
| verdict | FAIL | **PASS**, wrong-side control correctly FAILs |

`testing_13_arcs` went 23 uncovered to 2 - and those 2 are segments 0 and 1 at
the front face, where the pass never reaches past Z-2.6788. That is a reach
question, not arc chording, and is logged separately.

## Why it cannot ship yet: two windows overflow, one of them silently

**FLANK, 3600-3700, 100 slots = 50 points.** The contour needs 66. It overflows
with a WARNING and roughing loses its stop surface entirely - measured, 4
projects emitted `env0 fc66 WARNING`.

**ERAMP, 3200-3380, 180 slots.** `build_entry_ramp_gcode` needs
`len(dirs) * 4 + 3`; at 66 points that is **263**. And it does not warn:

```python
if ERAMP_BASE + len(dirs) * 4 + 3 >= ERAMP_TOP:
    return ''
```

This is what actually removed the back-angle entry ramps - testing_15_2/4/5 went
from 9 shallow roughing feeds to **0**, and `test_ramps` reported "0 ramps
checked". It looked for a long time like a geometric coupling between contour
resolution and the ramps. It is not. The ramp table simply did not fit and was
dropped with no message anywhere.

That silent `return ''` is worth fixing on its own merits, whatever happens to
the resolution: every other table here emits a `(WARNING - ...)` comment when it
falls back.

## Three attempts, and what each one taught

1. **Per-corner `_min_segment` limit** - replace the blanket `2.4 * nose_r` with
   the `R*tan(deficit/2)` the docstring derives. Correct in principle: an arc
   chord turning 4.5 degrees needs 0.0157 mm against a 0.960 limit. It closed
   the gap and killed the ramps.
2. **Protect the on-profile points instead**, leaving ramp stretches thinned as
   before. Also closed the gap, also killed the ramps - which is what showed the
   cause was not the thinning rule.
3. **Refine only the finishing contour, leave roughing's envelope coarse.**
   Coverage PASSED, ramps still gone. That isolated it to ERAMP, since the
   flank envelope was untouched in this variant.

## A latent bug found on the way, and fixed

`section_windows` capped its own table with the NEXT window's base:

```python
if SECT_BASE + 4 * len(out) > FLANK_BASE:
```

correct only while the windows happen to be contiguous. Moving FLANK to 2600 put
a smaller number there than SECT_BASE, so every profile "overflowed" and
`section_windows` fell back to a single full-span window - silently, exactly the
way its own comment says a truncated table would. `test_sections`' interval-
window case caught it.

Now `SECT_TOP`, its own constant, **set to 3600 - the same value the old
expression produced** - so nothing about the table changes today and the next
window move is not a landmine.

## And one in the gate written yesterday

`test_surface_equality.py` hardcoded `ENV_BASE, FC_BASE = 3600, 4000`. With
FLANK at 2600 it read an empty region, called 42 of 46 projects "without both
tables" and would have passed on nothing. It now takes both from
`lathe_sections`. A window moved in Python with its readers naming it separately
is the bug `cam_map.py` exists to catch, and a gate is not exempt from it.

`test_sections`' layout check had the same shape - it gave the sections table
`FLANK_BASE` as its top - and now names every region's own top, sorts them, and
sizes the overflow-guard case from `SECT_TOP - SECT_BASE` rather than from the
20 copies that stopped testing anything once the window grew.

## What the re-layout needs

Measured, not assumed:

- FLANK needs 132 slots against 100.
- ERAMP needs 263 against 180.
- FC already holds it: 66 points is 132 of its 200.
- The only free block is **1600 slots inside LVL**: it is allocated 1000-2600
  and reaches slot **1179** across all 46 projects - 179 used of 1600. Every
  other window is contiguous from 3380 up.

So the space exists, in one place, and taking it means moving windows past
consumers that may name each other's bounds - one of which has already been
found doing exactly that. That is a plan-mode job, not a patch.

## Verification of what IS committed

46 of 46 projects byte-identical in motion. flake8, cam_map,
test_lathe_validation, test_sections, test_ramps, test_ladder, test_leftover,
test_x_continuity, test_bidir_warn, test_ladder_account, test_level_intervals,
test_level_blocked, test_sub_spans, test_roughing_windows, test_ladder_python,
test_surface_equality - all exit 0.
