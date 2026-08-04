# 011 — The top roughing level missed the wall, compensated only

2026-08-04, branch `liveTooling`. greatEndian, `photo/leadOutIssue_1.png`:
*"the first roughing pass behind boss segment ends too early and does not
touch the prefinish pass.. it stops at same point as second roughing pass lead
out finished and go rapid"*.

## Measured

```
Off      level r29.6520 cuts to Z-69.8920   ON the pre-finish wall
Native   level r29.6520 cuts to Z-69.3840   SHORT by 0.5080
         every other back-end level         ON the wall, both modes
```

One level, and only with compensation on.

## Root cause

A roughing level stops at the first crossing of the STOP contour. That contour
carries the nose, and the orientation term shifts **the whole contour,
including its open ends**.

The profile's last segment is the back wall, running r24.2381 → **r30.0000**,
the stock. Shifted by the orientation term the stop contour's wall tops out at
**r29.6000** — and the highest roughing level sits at **r29.6520**, 0.052 above
it. That level therefore never crosses the wall at all. It stopped on the
previous segment, 0.5080 short, never touched the pre-finish, and rapided away.

Same 0.4 shortfall as the drawn-contour fix in `analysis/009`'s addendum, in
the stop table instead of the pass. The shift is correct where it places the
tool; at an open END it silently removes coverage instead.

## The fix

`entry_contour` — used by both the entry and the stop tables — now extends
both terminal segments back along their own direction by the shift, restoring
the span the contour had before it moved.

Over-extending slightly is harmless: this is a stop/entry reference and a
level above the stock has nothing to cut. Under-extending drops a whole pass,
silently.

## After

```
Off / Native / In CAM   level r29.6520 -> Z-69.8920, on the wall
```

`check_tangent` PASS min |dot| 1.00000; `test_leads` 24/24, `test_sections`,
`test_comp_overlay`, `test_lathe_validation`, `test_coord_mapping`, `test_vkb`
all pass; `test_rough_comp`'s overcut numbers unchanged.

## Why nothing caught it

`test_rough_comp` measures how far roughing cuts **PAST** the pre-finish. A
level that stops early cuts *less*, which reads as an improvement — the metric
is one-sided by design, for a good reason recorded in that file, and this is
the failure mode that one-sidedness cannot see.

**Under-cutting needed its own assertion**, and now has one: every roughing
level in the wall region must reach the pre-finish wall. Negative control run
— with the extension disabled, Native and In CAM fail with
`r29.6520 stops at Z-69.3840, 0.5080 short` and Off passes.

## Still unknown

- The entry contour gets the same extension, which is right by symmetry, but
  no measurement demonstrates an entry-side case that needed it.
- Roughing's lead-out still has no reference for where its 1 mm should end -
  the open item from `openPoints.md`, untouched here.
