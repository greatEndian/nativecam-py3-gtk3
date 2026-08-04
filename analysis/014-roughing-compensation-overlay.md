# 014 — How compensation works for roughing, and the dashed overlay for it

2026-08-04, branch `liveTooling`. greatEndian: *"investigate and verify how
compensation works for roughing ... also create there dashed lines to find out
if it is right same as in the finishing example"*.

## How it works

Roughing is a **ladder of straight cuts**, so it has no single compensated path
the way a contour pass does — there is nothing to draw a `G41.1` offset of. The
nose enters roughing through the two tables the levels walk, both built by
`lathe_sections` and both gated by `_comp_nose`:

| | carries the nose via |
|---|---|
| level start Z | `_pl_rgh_oz`, gated in Python (`bfa2fa2`) |
| where a level may BEGIN | the ENTRY contour, `#4200` |
| the profile-angle ramp | the entry contour's own segment direction |
| where a level must STOP | the STOP contour, `#4400` |
| lead-in | inherits from the entry crossing |
| lead-out | inherits from the stop |

There is no interpreter compensation anywhere in roughing, in any mode — the
tables carry it, which is why `_comp_nose` returns (0, 0) with compensation off
and the same code then produces the uncompensated ladder unchanged.

## Verified

`test_rough_comp`, all three modes:

```
Off      overcut past the pre-finish contour  0.1116 mm at Z-64.4
Native                                        0.0394 mm at Z-19.6
In CAM                                        0.0394 mm at Z-19.6
every roughing level reaches the pre-finish wall     Off / Native / In CAM
every pass behind the boss ramps in, none plunges    Off / Native / In CAM
```

Leads measured separately: the lead-in start moves `dz -0.4456` Off→Native, and
each lead-out end moves by **exactly** the amount its stop moves (-0.2459,
-0.2197, -0.2194 …). Behind the boss those deltas read 0.0000 because the stop
there is limited by the wall, identically in both modes.

## The overlay

`COL['rgh_entry']` yellow-green and `COL['rgh_stop']` red-orange, both dashed
`[3.0, 3.0]` — a **shorter** dash than the finish overlay's `[6.0, 3.0]`,
because on a busy plot the eye reads dash length before hue. Gated on the
existing Contour toggle; the pane is already tight and another switch costs
more than it gives.

**At the current settings the two curves coincide** — the entry stands off by
the roughing depth of cut and the stop by `param_f_off`, both 0.508 here, so
one dashed line appears rather than two. That is correct, not a fault.

## Three wrong things caught on the way

- **The supplier passed `0.0` to `finish_profile`** where both builders pass
  `nose_r`. It would have drawn a different reachable contour from the one the
  program walks.
- **The supplier added the pre-finish offset to the stop**, where
  `build_stop_contour_gcode` uses `param_f_off` alone — one allowance out from
  where the levels really stop.
- **The pane was constructed positionally**, so inserting `rough_cb` into the
  signature silently handed `_preview_comp_mode` to the wrong parameter. Now
  keyword-named from `comp_cb` on.

All three were plausible on screen and none would have failed a lint.

## And one measurement thrown away

A first attempt swept the nose along the roughing moves and compared the
surface against the stop contour over the whole field: **3.1663 mm on Off**,
3.1657 compensated. A metric that fires on the baseline is not a metric — it
was taking `max()` over a multi-valued Z at the end wall. Discarded rather than
reported; `test_rough_comp`'s one-sided overcut measure is the one that holds.

That is the **fifth** baseline-firing metric this session (5.0452 "gouge",
17.83 "error", 0.3902 "jerk", 0.2168 "jerk", now 3.1663 "overcut"), plus a
sixth in the new test itself — an assertion that entry and stop must DIFFER,
which fails on exactly the valid configuration where they coincide.
