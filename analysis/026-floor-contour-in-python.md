# 026 — The floor contour moves to Python

2026-08-09, branch `liveTooling`, from `e70721c`. Fixes the defect greatEndian
reported in `photo/separateOffsetZ_0.png`.

## The defect

With *Separate Z offset* on, X 0.508 and Z 2.000, measured against
testing_15_2's Z−70.4 end wall:

```
                     before    after
stop contour         2.0000    2.0000
pre-finish           2.0000    2.0000
finish               0.0000    0.0000
roughing             0.7620    2.0000
```

0.7620 is `fin_off + prefin_off` — the single scalar `lathe_level_pass` offset
every profile segment by, at runtime. Two allowances cannot be expressed that
way, and the stop table could not rescue it: that one is bounded to
**extending** a cut and never pulls one back.

## The fix

`build_floor_contour_gcode` emits the floor as a table — the profile offset by
`fin_off + prefin_off` radially and `fin_off_z + prefin_off` axially, blended by
each surface's own normal. The scan walks it. Two things came free:

- the allowance is anisotropic;
- **the corners are already joined**, so the walk needs neither the offset
  arithmetic nor the gap-connector the old scan carries to paper over the gaps
  independently-offset segments leave at a corner.

The pre-finish allowance stays isotropic: it is a depth of cut for the pass
that follows, not a face-versus-diameter choice.

## Three things that went wrong on the way

**1. Fixing the scan alone changed nothing.** With multi-crossing on — which it
is by default — a second walk, `o<mcross>`, replays every crossing to set the
cut target, and it does its own offsetting. It wins. Both walks had to move to
the table, and they must share it or they disagree about where the level stops.

**2. Building it from `finish_profile` cost nine levels.** That is the
*reachable* contour; the scan walks the record array, which is the polyline as
drawn. testing_15_2 went from 29 roughing levels to 20 and still generated
cleanly. The back-angle shadow is a separate table the level pass consults on
its own — **the only thing that may change here is the allowance**, so the
builder uses `resolve_points`.

**3. It needed 226 slots and 200 were free — and said nothing.** Built from the
raw profile the contour has more points than the tables built from the
simplified reachable one, so it emitted a WARNING comment and fell back to the
old scan. Everything still ran; the measurement was simply unchanged. The flank
envelope has never used more than 58 of its 400 slots across four projects, so
it keeps 100 and the floor contour takes 3700–4000.

## The assertion that was missing

`test_stock_to_leave` measured a **45° chamfer** — 0.3008 against an expected
0.3 — and I read it as proof that roughing honoured the blend. It was not. On a
slope the scan stops on the scalar and the stop table then extends it forward
onto the anisotropic contour: **the right number for the wrong reason.** A wall
with an axial value far larger than the radial one needs the stop pulled back,
which the stop table can never do.

greatEndian's check — set the axial value to 2.000 against a radial 0.508,
where the two cannot be confused — is the one that could not be fooled. It is
now in the test, on a wall, alongside the isotropic control.

## Verified

```
isotropic     341 moves, 29 levels, deepest 0.5080 from the wall
X 0.508 Z 2.0 341 moves, 29 levels, deepest 2.0000 from the wall
```

`test_rough_comp` Off 0.1115 / Native 0.0503 / In CAM 0.0503, `test_ladder`,
`test_floor_ladder`, `test_ramps`, `test_leads`, `test_rough_ends`,
`test_end_z`, `test_stock_to_leave`, `test_all_projects`, `test_skip_short`,
`test_sections`, flake8 both lists.

## Still open

- The old scans remain as the fallback for a program generated before the
  table existed, and for the case where the contour will not fit. Both are
  reachable and neither is exercised by a test.
- `_pl_flc_n` is capped at 150 points. A profile richer than testing_13_arcs
  could still overflow and fall back **silently** — the WARNING is a comment in
  the file, which nobody reads. It should refuse or degrade loudly.
