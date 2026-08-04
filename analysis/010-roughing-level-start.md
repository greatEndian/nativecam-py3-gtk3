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

## Addendum REVERTED, 2026-08-04

greatEndian: *"roughing return to status before last edit, last time it was
good and now it is wrong"*. The stock clamp above is reverted — roughing is
back to 27 retreats, min end radius r21.7231.

**Why it was wrong**: the clamp was invented rather than taken from anything.
The reference is the PINK contour, which ends at
**Z−70.4000 r30.0000 — the stock envelope, in the polyline's own segment
coordinates**. A blanket `G1 X#<_wp_dia_od>` after every level ignores that: it
adds a full-radius move to every level regardless of where the profile
actually meets the stock, which is 25 extra moves on testing_15_2 and not what
the geometry says.

Left open: the retreat height is still whatever `lo_len * sin[lo_ang]` gives
above each level, so most levels do finish inside the bar. The fix has to come
from pink's own ending, not from a clamp.
