# 123 — which frame the stop contour is in: it depends on n_comp

**Asked**: the open point from `analysis/029`'s aftermath - *"Settle which frame
`build_stop_contour_gcode` emits before trusting either answer"* - which is what
left the coverage sweep an untrustworthy instrument.

## The answer

**Control-point frame when the polyline compensates, contact frame when it does
not.** There is no single answer, which is why applying one assumption at both
ends of a cut gave contradictory results.

The chain, read and then measured:

- `build_stop_contour_gcode` calls `entry_contour(pts, stop_x, rough_dir, _nr,
  _or, stop_z)` with `_nr, _or = _comp_nose(...)`.
- `_comp_nose` returns `(0, 0)` unless `param_n_comp` is 1 or 2 - "with Tool
  nose comp off they must come out exactly as before".
- `entry_contour` puts `dist + nose_r` on the normal and subtracts the
  orientation term once at the end. With `nose_r = 0` both vanish and the
  table is the plain offset of the profile - contact frame. With `nose_r > 0`
  the table is where the CONTROL POINT goes.

## Measured, not just read

`testing_15_2`, same project, `param_n_comp` overridden 0 against 1:

```
stop contour points: 66 both
identical points:    0 of 66

  n_comp 0  Z   1.0000 R 20.7620   n_comp 1  Z   1.1657 R 20.7620   d +0.1657  0.0000
  n_comp 0  Z -19.2707 R 20.7620   n_comp 1  Z -19.2879 R 20.7620   d -0.0172  0.0000
  n_comp 0  Z -19.3008 R 21.4452   n_comp 1  Z -19.3011 R 21.0628   d -0.0004 -0.3824
```

Every point moves. And the pattern is exactly what `entry_contour`'s own
docstring claims: on the axis-parallel stretches the RADIUS is unchanged to the
digit - 20.7620 in both - because "a level cut runs parallel to Z, and there the
two terms cancel"; only Z moves. Where the contour is sloped, the radius moves
by the nose terms as well.

## What that means for the coverage sweep

- **Radial measurements against the stop contour are frame-independent** on the
  axis-parallel stretches, which is where a level's own diameter is decided.
  That is the part of the sweep that was always safe.
- **Axial ones are not.** Z moves in both cases, by the orientation term, and
  the sign depends on the insert.
- Today the question is moot in practice: **all 40 projects that carry the
  parameter have `n_comp = 0`**, so every shipped stop-contour table is in the
  contact frame. It stops being moot the moment anyone turns nose comp on.

The "contact = control + oz" assumption the sweep was built on is therefore
right only for `n_comp` 1 or 2, and is a no-op for the projects it was actually
run against - which is consistent with it matching a floor crossing to 0.0002 at
one end and reporting an impossible 0.40 uncut at the other.

## Not fixed here

Settling the frame is what the open point asked for; rebuilding the sweep on top
of it is separate work. Cut-to-cut measurements remain frame-independent and
remain the safe instrument in the meantime.
