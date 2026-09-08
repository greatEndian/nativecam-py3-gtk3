# 114 — arc-first profiles: the pre-finish offset makes a corner LinuxCNC refuses

**Asked**: greatEndian, 2026-09-08 — *"chase the arc_first failure"*, the three
dead projects `analysis/113` found.

## The error is real compensation, even though nose comp is OFF

All three projects carry `n_comp = 0`, which made the cutter-compensation error
look impossible. It is not. `tip_comp_dia.ngc`, in its `nose_on = 0` branch:

```
#<_tip_comp_d> = [2 * #<extra_r>]
#<_tip_comp_l> = 0
```

**With the nose comp switched off, D is still non-zero** - it is twice the
pass's radial allowance - and `tip_comp_on` emits `G41.1 D... L0` whenever
D > 0.0001. That is deliberate and documented: `L0` is a pure geometric offset,
and it is how the pre-finish pass holds its stock. `CLAUDE.md` states it -
*"G41.1/G42.1 D 2x offset, L0 for pure geometric offset, L#5413 only when Tool
nose comp is on"*.

So the interpreter is compensating, correctly, and refusing the geometry it is
given.

## The geometry it refuses

The program gets 2832 moves in - through facing and the whole roughing ladder -
and aborts during the **pre-finish** pass at the arc-first end:

```
(11.1160, Z 0.1191) -> (11.4621, Z 0.0000) -> (11.1168, Z -0.5353)
```

Out and straight back: a cusp, where the offset path doubles over itself. That
is the "concave corner cannot be reached without gouging" the interpreter
reports.

`testing_13_arcs` - same family, same mode - runs clean, so it is specific to a
profile that BEGINS with an arc.

## Why the roughing passes survive it

Roughing is uncompensated and walks a table; the pre-finish pass is the first
one to hand the interpreter an offset contour. The cusp exists in the geometry
either way - it only becomes fatal when something has to offset around it.

## Not caused by this session

`analysis/113` established that: rolled back to `dad4f7e` and both reproduce
identically.

## What a fix has to decide

Whether the cusp is in the emitted contour or in what the interpreter makes of
it. Two candidates, and they need separating by measurement before either is
touched:

- the pre-finish contour genuinely doubles back at an arc-first start, in which
  case the contour builder should trim the overlap - the same class of join
  `offset_contour` already handles for internal corners;
- or the contour is fine and the entry handling for `arc_entry` puts the pass
  start inside the arc, making the first two moves fold.

The `arc_entry` branch in `lathe_poly_pass` already exists because an arc
cannot establish compensation, so the arc-first case is known to be special
here - which makes the second candidate worth testing first.
