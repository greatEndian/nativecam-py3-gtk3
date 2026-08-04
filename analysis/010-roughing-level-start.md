# 010 — Roughing's level start Z was never compensated

2026-08-04, branch `liveTooling`. greatEndian: *"roughing has to start from 1
too"*.

## The fault

A roughing level begins at `#<z_start>`, which falls back to the **window
start** (`lathe_level_pass.ngc:27`) whenever the entry contour never crosses
that level — every level above the part. The window is a raw profile Z, so the
TIP started where the SURFACE starts and the nose, which trails the tip by the
orientation vector, began cutting past it.

Measured on `testing_15_2`, drawn segment starting at Z+1.0000:

| | tip starts | nose first cuts |
|---|---|---|
| green roughing, ALL modes | Z+1.0000 | **Z+1.4000** |
| blue/magenta, Native / In CAM | Z+0.6000 | Z+1.0000 |

The level's STOP and re-entry have carried the nose since the stop and entry
tables were built (`_comp_nose`, `lathe_sections.py:1772`/`:1823`), so **one
end of every roughing pass was compensated and the other was not** — the same
asymmetry `analysis/009` found at the two ends of the contour pass.

## The fix

Python-first: `build_rough_nose_gcode()` emits `#<_pl_rgh_oz>`/`_ox`
**already gated** by the same `_comp_nose` question the tables ask — zero
unless the polyline compensates. `lathe_level_pass` then subtracts a number
and decides nothing:

```
#<z_start> = [#<w_from> - #<_pl_rgh_oz>]
```

Emitted unconditionally, unlike the entry contour which is skipped when the
roughing depth is 0 — a level starts somewhere regardless.

## Measured after

```
Off      roughing tip Z+1.0000  nose cuts from Z+1.4000   (unchanged - Off compensates nothing)
Native   roughing tip Z+0.6000  nose cuts from Z+1.0000   finish tip Z+0.6000
In CAM   roughing tip Z+0.6000  nose cuts from Z+1.0000   finish tip Z+0.6000
```

Green, blue and magenta now start together, and the cut begins exactly on the
drawn segment.

**It also made roughing more accurate**, which was not the goal and is worth
recording: `test_rough_comp`'s overcut past the pre-finish contour fell from
**0.0503 to 0.0394 mm** in both compensated modes, worst point moving to
Z-19.6. `check_tangent` PASS, min |dot| 1.00000 over 20555 events;
`test_leads` and `test_sections` unchanged.

## The trap that cost the most time here

The cfg edit did nothing at first. **A saved project embeds the whole `after=`
template, `<exec>` lines included**, so a `cfg/` change is invisible until the
`version` is bumped and NativeCAM migrates. `1.37 -> 1.38`. `lib/*.ngc` needs
no such thing — subroutines are read at runtime, which is why the
`lathe_poly_pass` fix of `analysis/009` took effect immediately and this one
did not.

## Still unknown

- Roughing's lead-OUT retreat geometry is still unmeasured; only the stop it
  retreats from is known to be compensated.
- No test asserts the roughing start. `test_rough_comp`'s number moved
  0.0503 -> 0.0394, so a regression would show up there, but indirectly.

---

## Addendum, same day — the roughing lead-out ended inside the stock

greatEndian: *"it is ending at first roughing pass level which is wrong.. it
has to end at level of stock at least"*.

The retreat starts at `#<phys_x> = #<level>` and rises `lo_len * sin[lo_ang]`
above **its own level**, so only the topmost level ever cleared the bar. On
testing_15_2, `lo_len` 1.0 at 45 deg gives 0.7071 of rise:

```
level r29.6520 -> r30.3591   clears the 30.0 bar
level r29.1440 -> r29.8511   0.1489 inside it
level r28.6360 -> r29.3431   0.6569 inside it        ... 25 of 27 levels
```

Fixed with a separate radial `G1 X#<_wp_dia_od>` after the angled retreat,
taken only when the angled move finished short. **Not** by lengthening
`_lo_leff`: that fights the Z-room cap directly above it, which exists to stop
a continuation interval retreating back over its own start. OD only - on a
bore the retreat travels the other way and clamping outward would drive it
into the wall.

After: **0 retreats of 52 finish below the stock.** `check_tangent` PASS,
min |dot| 1.00000; `test_rough_comp` and `test_lathe_validation` unchanged.
