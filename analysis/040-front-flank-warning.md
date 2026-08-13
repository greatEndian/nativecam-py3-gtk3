# 040 — The leading flank: detection built, numbers not yet trusted

2026-08-13, branch `liveTooling`. Gap **1** of `POLYLINE-GAPS.md`, the WARNING
half only. greatEndian asked to look at it now rather than later, and to do the
warning before any toolpath change so the toolpath question could be decided on
a measurement.

## What the gap actually is

An insert's **trailing** flank limits surfaces that RISE as the tool travels —
drive past a boss and the sections behind it are the ones the back of the insert
can no longer get into. Modelled already: `flank_slope`, `flank_envelope`,
`finish_profile`, `unreachable_spans`, and the validation warning that names the
span in millimetres.

The **leading** flank has its own clearance and limits the opposite thing:
surfaces that FALL AWAY in front of the tool — a steep face, the near wall of a
groove, an undercut on the approach side. Nothing checked it.

## The spec's premise was already known false

`POLYLINE-GAPS.md` had claimed the reachable-contour maths "already takes a
front angle". It does not: `flank_slope`, `flank_envelope`, `finish_profile`
and `unreachable_spans` take `back_deg` only. Corrected before this work began.

What **does** exist is the tool table accessor — `get_tool_front_angle(tn)`
reads `tool[6]`, the I token, mirroring `tool[7]` for back. So the input is
there; the constraint was not.

## The implementation is a mirror, not new geometry

`flank_sides` already turns the roughing direction into a shadowed side —
`0 -> (1,)`, `1 -> (-1,)`, `2 -> (1, -1)`. The leading flank is shadowed by
whatever the trailing flank is not, so the front envelope is the **same**
`flank_envelope` call with the direction mirrored and the front angle in place
of the back one:

```python
front_envelope(pts, front_deg, d, ...) = flank_envelope(pts, front_deg,
                                                        mirror_dir(d), ...)
```

Deliberately no second copy of the wedge maths. This project spent five stacked
faults getting that dilation right (`analysis/032`); a parallel implementation
would have been a second thing to get wrong.

## The angle convention — the one assumption

The tool table's I and J are **absolute edge directions**, not clearances. The
sim tools carry `T2 I15 J75`, and `flank_slope(75)` is `tan(15°)` — exactly what
`flank_slope`'s own docstring says a J75 insert ramps at. So the front edge is
read the same way, `90 - I - clearance`.

If that reading is wrong, every number below is wrong with it. `front_spans_both_ways`
therefore reports the complement reading alongside it.

## The survey — every demo project

Run after `to_gcode()`, which matters: `get_back_angle()` reads `saved_tool`,
and that is only set when the Tool Change feature actually **runs**. A first
pass without generating reported front 0.0 / back 0.0 and "none" everywhere —
a clean, wrong answer. It was caught because testing_15_2 is known to have back
clearance moving 198 of 323 moves, so a back angle of 0 could not be true.

| project | front | back | FRONT span (mirror) | BACK span (existing) |
|---|---|---|---|---|
| current_work | 15 | 75 | Z−70.2..−19.5, 9.42 mm | Z−70.2..−35.8, 10.09 mm |
| testing_10 | 15 | 75 | Z−49.9..−12.5, 9.56 mm | Z−49.9..−15.9, 0.42 mm |
| testing_11 | 15 | 75 | Z−79.8..−12.6, 11.77 mm | Z−79.8..−16.0, 4.05 mm |
| testing_12_0 | 15 | 75 | none | Z−29.1..−18.6, 8.16 mm |
| testing_12_1 | 15 | 75 | none | none |
| testing_12_2 / _3 | 15 | 75 | Z−40.4..−39.7, 2.59 mm | none |
| testing_13_arcs & arc_first ×3 | 15 | 75 | Z−69.8..−0.0, 1.48 mm | none |
| testing_14_inside | 15 | 75 | none | Z−40.0..−20.1, 4.98 mm |
| testing_15_0 / _1 | 15 | 75 | Z−79.8..−18.6, 9.35 mm | Z−71.6..−50.2, 4.95 mm |
| testing_15_2 | 15 | 75 | Z−70.2..−19.5, 9.42 mm | Z−70.2..−35.8, 10.09 mm |
| testing_15_3 | 15 | 75 | Z−64.8..−19.5, 9.46 mm | Z−64.8..−35.8, 10.09 mm |
| testing_15_4 | 15 | 75 | Z−70.2..−19.5, 9.42 mm | Z−70.2..−35.7, 10.09 mm |
| **testing_15_5 / _6** | 15 | 75 | **Z−70.2..−19.5, 14.42 mm** | Z−70.2..−35.7, 10.09 mm |
| testing_5 / _6 / _7 | 15 | 75 | 4.83 / 6.38 / 7.39 mm | none |
| testing_0,1,2 | 0 | 0 | none | none |

Projects with no Tool Change report angle 0, `flank_slope` returns `None`, and
nothing is claimed — which is the right degradation.

## Why these numbers are NOT acted on

**testing_15_5 reports 14.42 mm of radius unreachable, on a part greatEndian has
been machining and verifying all session.** If that were literally true the part
would not come out, and it does. So one of three things is so:

1. the limitation is real and nobody has ever been warned about it;
2. the angle convention is inverted;
3. the side mirror is wrong.

Code cannot separate these. What was ruled out: it is **not** a blanket artifact
of parts that grow toward the chuck — a plain rising taper reports **none** in
every direction, as do a plain cylinder and an unusable angle. The detector
discriminates; whether it discriminates *correctly* is a question about a real
insert.

So `lathe_front_flank` is committed **inert**. Nothing imports it — asserted by
the test, which greps the tree — so no toolpath can have moved, and the
byte-identical requirement is met by construction rather than by comparison.

## The one check that settles it

Take `testing_15_5` and the tool that cuts it (orient 2, `I15 J75`) and ask
whether the leading edge can physically get into **Z−70.2 to −19.5**. That is a
question for someone holding the insert, and it decides all three possibilities
at once:

- if it can → the convention or the mirror is wrong, fix it and re-survey;
- if it cannot → the limitation is real, the warning should be wired, and the
  toolpath half becomes worth its risk.

Until then, wiring this to `polyline.cfg`'s `[VALIDATION]` block would fire on
most projects, and a warning that fires on most parts trains the operator to
ignore it.

## Note on where the code lives

`lathe_front_flank.py`, not inside `lathe_sections.py`. Partly because that file
had another agent's uncommitted Z-datum work in it while this was written —
committing it would have swept up a half-finished feature — but it stays outside
now for a better reason: unvalidated geometry should not sit in the module every
builder imports, where it can be reached by accident. Fold it in once the check
above has been made.

## Verified

`test_front_flank` (mirror, fires on a steep front wall, silent on a rising
taper in all three directions, silent on a cylinder, silent on an unusable
angle, and nothing imports it), `test_all_projects`, `test_below_inner_radius`,
flake8.
