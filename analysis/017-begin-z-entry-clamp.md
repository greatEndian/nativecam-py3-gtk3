# 017 — Every pass starts at the polyline's own Begin Z

2026-08-06, branch `liveTooling`. greatEndian: *"it hit the contour right in the
theoretical compensated position but in reality this creates small bump at part
start .. we have to create exception that at the very first polyline segment we
have to start from the Z begin at cutting X level"*, and then *"it has to be
everywhere .. I am not definitely sure that every time will be Z0.0 .. we need
to take temporary from first line segment or polyline definition"*.

## What was actually happening

Not a compensation fault. `testing_15_2`'s **first item runs forward of the
origin**:

```
origin   Z  0.0000  X 60.0000 dia
item 1   Z +1.0000  X 40.0000 dia      <- forward, past the reference
item 2   Z -20.0000 X 40.0000
```

So the profile itself starts 1 mm in front of Begin Z, and every pass followed
it there - Off at Z+1.0000, compensated at Z+0.6000 with the nose contact back
at exactly Z+1.0000. Geometrically correct against the contour, and the source
of the bump on the real part: the nose rides onto that forward-going segment.

## The rule

No pass may begin in front of the definition's own Begin Z. Applied to
**roughing levels, the pre-finish pass and the finish pass**, in all three
compensation modes.

```
              before                       after
Off           +1.0000 / +1.0000 / +1.0000  +0.0000 in all three
Native        +0.6000 / +0.6000 / +0.6000  +0.0000
In CAM        +0.6000 / +0.6000 / +0.6000  +0.0000
              (roughing / pre-finish / finish)
```

## Two wrong reference points on the way

- **Record 1 of the lathe array is NOT the origin.** The obvious source,
  `#[#<pds> + 1]`, reads **Z+1.0000** - the first ITEM's endpoint. The clamp
  compiled, ran 29 times and did nothing, and only instrumenting it showed why:
  `orgz=1.000000` against a `zstart` of 0.6. `poly_add_item CALL [-1]` does add
  the origin, but the lathe copy handed to these subs does not carry it.
  The reference now comes from a new global `#<_pl_begin_z> = #param_b_z`.
- **The contour clamp was inside the `comp_r` gate.** That block is skipped
  whenever `comp_r` is 0 - In CAM always, and any pass with no allowance - so
  it reached only Off's pre-finish and left the other five starting in front of
  the reference. Moved outside it.

Both were caught by measuring the result rather than by reading the change.

## Known consequence, not hidden

`test_rough_comp`'s compensated overcut moved **0.0394 -> 0.0503 mm**, worst
point now Z+0.3, Off unchanged at 0.1116. The compensated passes now cut the
Z0…+0.3 span they previously skipped. There is no stock there - the workpiece
is `_wp_z = 0.000`, material only at Z <= 0 - so this is the pre-finish target
extending past the stock, not metal being removed. Worth knowing before anyone
reads the number as a regression.

## Coverage

`test_ladder.py`: no pass starts in front of Begin Z, all three modes, with the
reference read from the project's own `param_b_z` rather than assumed to be 0.

Negative control, both clamps disabled:

```
mode 0  roughing +1.0000, pre-finish +1.0000, finish +1.0000
mode 1  roughing +0.6000, pre-finish +0.6000, finish +0.6000
mode 2  roughing +0.6000, pre-finish +0.6000, finish +0.6000
```

## Limitation, stated

Front-to-back only (`z_dir > 0`). With a back-to-front pass the first segment
is at the far end of the travel and this bound does not describe it. Untested
there, and guarded so it cannot fire.
