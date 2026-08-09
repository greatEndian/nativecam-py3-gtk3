# 025 — An End Z, and the sentinel that would have eaten the part

2026-08-09, branch `liveTooling`, from `d4a1e37`. Gap **8** of
`POLYLINE-GAPS.md`.

## What was asked

The reference package puts a **Front** and a **Back** limit on the Geometry
tab, each with a mode, a datum and an offset. We had *Start Z* and nothing at
the back at all: an operation always ran to the end of the drawn profile.

Only the **back limit** was built. The datum machinery — *Stock front, Chuck
front, Model back, Selection* — points at solid geometry we do not have, and
`POLYLINE-GAPS.md` already records why copying it would leave parameters that
can never resolve. The number is the useful half.

## Where it belongs

`resolve_points` — once, to the profile every builder reads. The contours, the
section windows, the floor ladder and the entry and stop tables are all derived
from those points, so trimming there is what keeps them agreeing with each
other. It is also why the reference puts its limits on the *geometry* tab
rather than on the passes.

`trim_to_end_z` clips the polyline and **interpolates** the last point, so the
profile ends exactly on the limit rather than at the last vertex before it.

## The defect this nearly shipped with

The first version used **0.0 as "no limit"**, on the reasoning that a profile
starting at Z0 and running negative is untouched by a limit of 0.

`testing_15_2`'s profile **starts at Z+1.0**.

So 0.0 fell inside it, the trim fired on a project that had asked for nothing,
and kept only the first millimetre of the part:

```
                     moves   level cuts   reaches
before the change      341           29    Z-70.400
with the 0.0 sentinel  137            2    Z-69.638
```

**It still generated. It still ran. `rs274` reported nothing.** The only signal
was the move count, and the only reason it was looked at was that the *trimmed*
run had gone UP to 265 moves — an oddity that turned out to be the trimmed part
generating more passes around its new open end, while the supposedly untouched
run had quietly collapsed to two levels.

No Z value is safe as a sentinel, because a profile may begin at a positive Z.
The parameter is now gated on an explicit switch, `param_e_z_on`, off by
default.

## Measured

```
switch OFF                     341 moves, 29 levels, reaches Z-70.400
switch OFF, End Z set to -40   identical, move for move
switch ON at -40               265 moves, 20 levels, reaches Z-40.604
```

The 0.604 past the limit is the lead-out and retreat, which are entitled to go
there.

## `test_end_z.py`

The unit cases — outside the profile, inside it, exactly on a wall, and a limit
that would leave a single point — plus three at the machine. The one that
matters is **"the switch OFF is identical whatever End Z holds"**, and beside it
**"the untrimmed run still machines the whole part"**: a bare off-equals-off
comparison would have passed happily while both runs were equally wrong, which
is exactly the shape of the bug above.

`test_all_projects`, `test_rough_comp` (Off 0.1115 / Native 0.0503 / In CAM
0.0503), `test_ladder`, `test_floor_ladder`, `test_ramps`,
`test_stock_to_leave`, `test_leads`, `test_rough_ends`, `test_sections`,
`test_offset_contour`, `test_comp_overlay`, `test_skip_short`, flake8 both
lists.

## Still open

- **A front limit** is not built. `param_b_z` is the profile's origin, not a
  trim: items are resolved relative to it, so it cannot double as one. A front
  trim would be the same `trim_to_end_z` with the sense reversed, and nobody
  has asked for it yet.
- **The reference's datums and offsets** — measuring a limit from the stock
  face or the chuck rather than in absolute Z. The Workpiece feature carries a
  face Z, so pointing at *that* is the version of this idea that could work
  here, and it is recorded as gap 14's useful half.
- The trim is applied to the **profile**, so the reachable-contour warning and
  the preview both follow it. That is right, but it means an End Z also changes
  what the warning reports — worth knowing before reading a warning on a
  trimmed part.
