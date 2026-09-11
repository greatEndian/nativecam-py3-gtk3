# 130 — detect_sections' min_x is wrong for every non-first rising section

**Asked**: worker session, 2026-09-11 — unit-test the pure functions in
`lathe_sections.py` that only slow rs274 sweeps cover. Found while deriving
independent expected values for `floor_regions`, one of the assigned
functions.

## The rule it breaks

`floor_regions`' own docstring: *"Regions come from `detect_sections`, which
already splits the profile wherever its trend changes, so each one is
monotonic and its `min_x` IS that region's deepest material."* A monotonic
RISING region's deepest material is at its own start — mathematically the
only place it can be, since every later point is >= the first by definition
of monotonic non-decreasing.

## The input, the output, the expected value

```
>>> import lathe_sections as ls
>>> pts = [(0.0, 20.0), (3.0, 10.0), (6.0, 20.0)]   # valley: falls to 10, rises back to 20
>>> ls.detect_sections(pts)
[(0.0, 3.0, 10.0), (3.0, 6.0, 20.0)]
```

The second section spans Z 3..6 and RISES from diameter 10 (at Z3, shared
with the first section's own end) to 20 (at Z6). Its true deepest material
over that span is 10, at its own start. `detect_sections` reports **20** —
the section's shallowest point (its far end), not its deepest.

The first (falling) section is unaffected: `(0.0, 3.0, 10.0)` correctly finds
its own minimum (10, at its end) because a falling run's minimum sits where
the loop's own per-point tracking naturally lands.

## Root cause

```python
if prev_category is not None and category != prev_category:
    if abs(pz - sec_z_from) > EPS:
        sections.append((sec_z_from, pz, sec_min_x))
    sec_z_from = pz
    sec_min_x = float('inf')        # <-- reset, pivot's own x never re-added
```

On a category change the pivot vertex `(pz, px)` becomes the START of the new
section, but only `sec_z_from` carries it forward — `sec_min_x` resets to
`float('inf')` and is next updated only by `cx` of the point **being
processed in this same iteration**, which is the far end of the new section,
not its start. For a FLAT run this is harmless (constant value, so far end ==
start). For a FALLING run it is harmless (the minimum is naturally at the far
end, which the very next iteration captures before any further reset). Only a
RISING run loses its own true minimum, because that minimum lives at the
point the reset just discarded.

The very first section is seeded correctly — `sec_min_x = e_x` before the
loop starts, from `points[0]` — so a profile that OPENS with a rise is fine.
Every rising section after the first loses its start value.

The module's own docstring calls the reset "carried over unchanged from the
original wall-only version" and frames it as deliberate, but gives no
rationale for discarding the pivot specifically — and the neighbouring
`floor_regions` docstring's contract ("min_x IS that region's deepest
material") is the thing it violates.

## Not a new class of bug — known once, fixed once, not here

`analysis/057` hit exactly this for a different consumer, the peak test in
`_boundary_list`: *"The peak test is not `detect_sections`' own `min_x`. That
is taken over the points a section RECEIVES, which on a straight rise is just
its far end — so a boss made of two plain tapers has the peak as its own
minimum and would be rejected."* The fix there was `_side_min`, a function
written specifically to avoid `detect_sections`' `min_x` and compute the
region's own minimum honestly, excluding the boundary vertex on purpose in
the OTHER direction (still not reusing the flawed value).

`floor_regions` was never given that treatment. It reads `detect_sections`'
`min_x` directly, so a profile with a rising region after its first section
gets a `region_floor` computed from that region's shallowest point instead of
its deepest. Per `region_floor`'s formula (`rough_target = min_dia/2 +
fin_off`), a too-large `min_dia` produces a too-large (too conservative)
`rough_target` for that region — not a gouge, but the ladder believes it is
protecting a bigger diameter than the region's own start actually allows,
which understates how deep that region may safely be roughed. On a rising
region that follows a proper falling neighbour the true minimum is at least
recorded correctly by that neighbour (shared vertex), so the practical
exposure is a per-region floor that is looser than the profile's own
docstring says it should be — not obviously caught by the project's own
demo catalogue, since `floor_regions`/`region_floor` are new (this session's
neighbour path per `analysis/126`) and have no unit coverage of their own
before this one.

## Verified purely in Python, no rs274

```
>>> ls.floor_regions([(0.0,30.0),(2.0,30.0),(2.0,20.0),(8.0,20.0)], 0.2, 0.1, 0.3, False)
[(0.0, 2.0, 15.3), (2.0, 8.0, 10.3)]         # falling-then-flat, unaffected — correct
```
vs a profile whose second region rises instead of staying flat: its `min_x`
(and so its floor) would be pinned to the region's far end rather than its
own start, the same 10-vs-20 gap shown above.

## What is still unknown

- Whether any shipped project's OD profile actually has a rising region that
  is not its own first section and is deep enough for the gap to matter in
  practice — not checked here, this is a pure-Python finding, no rs274 run.
- Whether the fix belongs in `detect_sections` itself (seed `sec_min_x` with
  the pivot's own x on reset, matching how the first section is seeded) or in
  a `floor_regions`-local re-derivation like `_side_min`'s. Not decided here —
  a geometry fix needs the fingerprint gate and is out of scope for this
  worker.

STOPPED HERE per instructions — not fixed, only measured and written up.
