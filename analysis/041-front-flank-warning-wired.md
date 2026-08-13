# 041 — The leading flank, warned about

2026-08-13, branch `liveTooling`, from `054206a`. Gap **1** of
`POLYLINE-GAPS.md`, the warning half.

## What unblocked it

`054206a` built the detection and deliberately left it unwired: it reported
spans as large as **14.42 mm of radius** on `testing_15_5`, a part greatEndian
had been machining and verifying all session. Either the limitation was real and
had never been warned about, or the angle convention was inverted, or the side
mirror was wrong — and no amount of code can separate those.

greatEndian, 2026-08-13, answered both halves:

> *"yes the limitation is real"* … *"angle convention is right .. same path
> generation I see in the CAM software"*

So the numbers describe the part, and the reference package leaves the same
regions. That is what let the maths leave `lathe_front_flank.py` and come into
`lathe_sections.py` beside the function it mirrors.

## What it is

An insert's **trailing** flank limits surfaces that RISE as the tool travels —
drive past a boss and the sections behind it are the ones the back of the insert
can no longer get into. That is `flank_envelope`, and every roughing scan is
built from it.

The **leading** flank has its own clearance and limits the opposite thing:
surfaces that FALL AWAY in front of the tool — a steep face, the near wall of a
groove, an undercut on the approach side.

**Almost no new maths, on purpose.** The dilation is the same dilation; only the
angle and the shadowed side differ, and `flank_sides` already turns a roughing
direction into a side. `front_flank_envelope` is `flank_envelope` with
`mirror_dir` and the front angle. Re-deriving the wedge would have meant a
second, untested copy of geometry that took five stacked faults to get right the
first time (`analysis/032`).

`spans_between` was lifted out of `unreachable_spans` so both flanks share one
walk — the same 400 steps, the same halving of the diameter difference into a
radius gap. Two copies would have been two things to keep in step, and the two
readings have to be comparable to be reported together.

## What the operator now sees

The existing reachable-contour warning, in two distinguishable halves. The back
message now says **BACK** and names the trailing flank; the new one says
**FRONT**, names the leading flank, and states plainly that nothing is moved for
it — the toolpath is the same as it was, and the message says only that those
regions will not come out to the drawn shape.

`polyline.cfg` → **1.56**.

## A false alarm found and killed on the way

The first survey after the fold reported spans on `testing_3` and `testing_4` —
**1.32 mm and 1.10 mm** — on tools whose table carries **no angles at all**:

```
testing_3.xml   front 0.0  back 0.0   1.32 mm
testing_4.xml   front 0.0  back 0.0   1.10 mm
```

`get_tool_front_angle` answers `0.0` for a missing `I` column, and 0 degrees is
not a tool — it is the absence of a measurement. Worse, with the default back
clearance of 2° the ramp becomes `tan(88°)`, which dilates enormously and invents
metres of nothing.

`finish_profile` already refuses the trailing flank the same way
(`if back_deg is None or back_deg <= 0: return points, False`), so the two now
agree. Both projects report **none**, and the validated numbers are unchanged.

## The survey, with the guard in

```
project                   front  back   FRONT span              BACK span
testing_15_5 / _6          15     75    14.42 mm Z-20.4..-65.8  10.09 mm
testing_15_2               15     75     9.42 mm Z-20.4..-67.4  10.09 mm
testing_15_3               15     75     9.46 mm                10.09 mm
testing_15_0 / _1          15     75     9.35 mm                 4.95 mm
testing_14_inside          15     75    none                     4.98 mm
testing_13_arcs, arc_first 15     75     1.48 mm                none
testing_12_2 / _3          15     75     2.59 mm                none
testing_12_1               15     75    none                    none
testing_9_*                15     75     7.16–9.66 mm           none / 0.42
testing_5 / _6 / _7 / _8   15     75     3.91–7.39 mm           none
testing_2 / _3 / _4         0      0    none                    none
```

## Byte-identical

The warning tells; it does not move. Move lists hashed before the work and
after, unchanged through both the fold and the guard:

```
testing_15_2   361 moves   448820963c2a
testing_15_5   484 moves   a902e8e9eb08
testing_15_6   472 moves   31c81f1b61c3
```

`test_front_flank` also asserts it **structurally**: the front functions may be
reached from `[VALIDATION]` and from nowhere else in `polyline.cfg`, and no
`front_` appears in `[AFTER]`, `[CALL]` or `[DEFINITIONS]`. A numeric comparison
cannot hold that property for ever — somebody wires the same function into a
builder later and every number still matches until the day it does not. Where
the function may be *called from* is what actually has to stay true.

## Verified

`test_front_flank`, `test_leftover`, `test_x_continuity`,
`test_behind_boss_ladder`, `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_rough_overlay`, `test_all_projects`, `test_ladder`,
`test_floor_ladder`, `test_ramps`, `test_section_length`,
`test_resume_envelope`, `test_end_z`, `test_z_datum`, `test_extension`,
`test_peck`, `test_below_inner_radius`, `test_pane_layout`,
`test_lathe_validation`, `cam_map`, flake8 both lists.
