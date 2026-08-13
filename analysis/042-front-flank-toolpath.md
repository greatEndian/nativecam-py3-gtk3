# 042 — The leading flank, machined around

2026-08-13, branch `liveTooling`, from `eab37b1`. Gap **1**, the toolpath half.
`analysis/041` is the warning half.

## The one place

`finish_profile` — the choke point. Every contour, section window, ladder and
table in the operation derives from it, which is why the trailing-flank version
of this cost five stacked faults (`analysis/032`). Nothing else was touched.

Inside it, `flank_envelope` gained an optional second flank. The dilation loop
already walked a list of `(side, slope)` pairs, so the leading flank is another
pair with the mirrored side and the front angle. `reach` became per-pair: two
angles project different distances along Z, and one shared value would give the
shallower flank the steeper one's range.

## Why not merge two finished envelopes — measured, not assumed

The first attempt built the back envelope and the front envelope separately and
merged them by resampling onto the union of their breakpoints. It generated, and
the interpreter refused it:

```
Straight feed in concave corner cannot be reached by the tool without gouging
```

Resampling two piecewise-linear curves manufactures corners tighter than the
nose. `finish_profile`'s existing `_clean_ramp` / `_min_segment` treatment could
not rescue it, because the damage was already in the shape it was handed.

Built as one envelope, the candidate-Z generation, the outer bound and the
collinearity pruning all see both flanks at once, and the result is a contour
the interpreter accepts. The crude merge also exaggerated the effect wildly —
361 → 275 moves against the correct 361 → 340 — which is worth remembering: a
broken implementation of a change is not a measurement of that change.

## Off by default, deliberately

`Respect tool front angle`, `polyline.cfg` **1.57**, default **0**.

Switching it on changes the part: the path stops attempting shapes the insert
cannot make. That is the honest part, and it is also a different part from the
one every saved project has been producing, so it cannot arrive unasked.
`Respect tool back angle` has had its own switch since it was built, for exactly
this reason.

The front angle reaches `finish_profile` as a module-level value published by
`to_gcode`'s walk, the same route and the same reasoning as `WORKPIECE_FACE_Z`
in `14e50e3`: `lathe_sections` imports nothing from `ncam`, and a `Feature` has
no back-reference to its tree. Cleared per build, so a tool left over from the
last generation cannot silently shape this one.

## Measured

Default untouched — move lists hashed against the pre-work baseline:

```
testing_15_2   361 moves   448820963c2a
testing_15_5   484 moves   a902e8e9eb08
testing_15_6   472 moves   31c81f1b61c3
```

Switched on:

```
testing_15_2   361 -> 340 moves
testing_15_5   484 -> 463 moves
testing_13_arcs 3731 -> 3721 moves
```

And the direction is the one greatEndian's answer predicts — the contour stands
FURTHER OFF the drawn shape inside the front-unreachable region, rather than
diving into it. At the worst-gap Z of each project's front span:

```
                    drawn      contour OFF   contour ON   stand-off OFF -> ON
testing_15_5  Z-68.02  r20.000   r24.787      r27.228      4.787 -> 7.228 mm
testing_15_2  Z-68.79  r20.000   r24.609      r24.808      4.609 -> 4.808 mm
```

## Every project, switched on

Swept all demo projects with the switch forced on. Three fail, and all three
fail identically with it **off** — confirmed by running both ways:

- `default_template.xml` — has no polyline feature at all; produces no motion
  either way.
- `testing_12_0.xml`, `testing_12_3.xml` — the interpreter does not finish
  within 120 s, with the switch off as well. Pre-existing, and worth its own
  look some day.

Every project that works with the switch off also works with it on.

## Verified

`test_front_flank_path` (new), `test_front_flank`, `test_leftover`,
`test_x_continuity`, `test_behind_boss_ladder`, `test_rough_comp`,
`test_stock_to_leave`, `test_rough_ends`, `test_rough_overlay`,
`test_all_projects`, `test_ladder`, `test_floor_ladder`, `test_ramps`,
`test_section_length`, `test_resume_envelope`, `test_end_z`, `test_z_datum`,
`test_extension`, `test_peck`, `test_below_inner_radius`, `test_pane_layout`,
`test_lathe_validation`, `cam_map`, flake8 both lists.

## Still open

The switch has never been run on a real part. The warning says which regions the
leading flank cannot make; this says the path will stop trying. Whether the
resulting part is the one greatEndian wants — rather than one that leaves more
stock than he expected — is a question for a machine, not a test suite.
