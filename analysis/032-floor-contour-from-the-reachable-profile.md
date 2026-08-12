# 032 — The roughing floor was built from the RAW polyline

2026-08-12, branch `liveTooling`, from `27c7535`. Closes the fifth and last
fault on *"the first pass behind the boss segment is missing"*.

## What was asked

Wire the resume-envelope walker and the flag split — three of the four faults on
that bug were already fixed — without the 7.6 mm pre-finish overcut that
appeared the moment the walker was live:

```
Off      overcut past the pre-finish contour  7.6277 mm at Z-51.7
Native   7.4133 mm at Z-54.5
In CAM   7.4133 mm at Z-54.5          bound 0.0800
```

## What was measured

The worst point is at **Z−51.7**, not the end wall, and `test_rough_comp`'s
`radius_span` already excludes vertical-segment artefacts — so the number is
sound. Two dumps settled it.

**The pre-finish target there is real.** The programmed finish contour has a
**35.096 mm gap**, Z−35.3038 → Z−70.3998, with no points between: the finish
pass crosses that span as one straight taper. So the interpolated target of
r29.0766 at Z−51.7 *is* the surface, and roughing reaching r21.5 there is a
genuine 7.6 mm gouge.

**The floor contour disagrees with it completely:**

```
Z -45.2761  X 23.7179
Z -45.6937  X 21.5096
Z -45.7490  X 20.7617
Z -45.7502  X 20.7620      <- Z non-monotonic, a self-intersection signature
Z -69.6380  X 20.7620      <- 24 mm FLAT at r20.762
Z -69.6380  X 30.0000
```

It plunges from r23.7 to r20.76 across 0.47 mm and then runs **flat for 24 mm**,
where the machined surface tapers from about r33 down to r24.24.

## Root cause

`build_floor_contour_gcode` was built from **`resolve_points` — the raw polyline
as drawn** — while `build_stop_contour_gcode` and `build_entry_contour_gcode`
beside it both use `finish_profile`, the **reachable** contour. The floor was
the only one of the three reading the raw shape.

testing_15_2's polyline contains an undercut behind the boss that the tool's
back angle cannot reach. The finish pass correctly skips it — that is the 35 mm
straight move. The floor contour followed it, so every consumer of the floor
believed the floor was at r20.76 across 24 mm of the part, and roughing dived
into material it must not enter.

**This is one cause behind three separate reports:** the 7.6 mm overcut here,
greatEndian's *"sectioning does not take care about the back tool angle"*, and
the sectioning over-cut in `openPoints`.

## The fix

One line: the floor contour is built from the reachable profile, like its two
neighbours.

```python
pts, _soft = finish_profile(polyline_feature, back_deg, nose_r,
                            flank_len, clearance)
```

The docstring carried a warning that building it from `finish_profile` "cost
testing_15_2 nine of its 29 levels". **That is no longer true** — measured now,
the level count is healthy (49 level cuts on testing_15_5, 51 with sectioning)
and every roughing test passes. Whatever caused the lost levels was fixed by
intervening work; the warning outlived the fault and would have blocked this fix
for anyone who trusted it without re-measuring.

## Measured, before and after

```
                                       before        after
test_rough_comp overcut, Off          7.6277 mm     0.0503 mm
                        Native        7.4133        0.0503
                        In CAM        7.4133        0.0503
topmost behind-boss level, sect off   32.1920       33.2080
                          sect on     32.1522       33.1273
```

The missing pass is restored and the overcut is back to the no-walker baseline.

## A pre-existing failure fixed on the way

`test_rough_overlay` was already red before this work — `3df0a4c` gave the stop
contour `fin + prefin` and did not move the drawn twin, leaving the overlay
0.2540 (exactly `pf_off`) inside the line the levels stop on. The overlay now
takes the pre-finish allowance the same way the table does. A drawing that
disagrees with the table is worse than none: several rounds of this
investigation chased faults that existed only on screen.

## Still open

`test_section_length` still fails, but far less: the sectioning discrepancy went
from **23.1% / 20.1%** to **7.0% / 5.7%**, and the sign flipped — a sliced
program now cuts slightly *less* than an unsliced one rather than 23% more. So
the raw-profile floor was most of that fault too, and what remains is a smaller,
separate one.

## The lesson

Instrument before theorising, and re-measure a warning before obeying it. The
docstring that said "do not build this from `finish_profile`" was the single
thing standing between this bug and its one-line fix, and it had been true once.
