# 107 — every In-CAM bore with a right-hand boring bar was 0.8 mm oversize

**Asked**: greatEndian, 2026-09-04 — *"go on with the offset_contour input"*.

## The fault

`offset_contour` takes each segment's normal from that segment's DIRECTION:

```
nz, nr = ur * side, -uz * side
```

So the same profile handed to it backwards produces the opposite offset.
`finish_profile` returns its points in the FINISHING direction, and for a
right-hand boring bar that runs the other way round the profile than it does
for an OD tool. Probed at the call site rather than reasoned about:

```
testing_14_inside      side=-1 orient=2  npts=3   Z0 -> Z-40   forward
testing_14_inside_bar  side=-1 orient=3  npts=5   Z-40 -> Z0   REVERSED
```

Reversed input flips every normal, so `side = -1` behaves as `+1` and the path
offsets OUTWARD. On a bore that is the nose centre at `wall + R` instead of
`wall - R` - a gouge of exactly 2R, the whole nose diameter into the wall.

Confirmed by computing both orders directly:

```
forward   side=-1 Q3 -> mouth ctrl r17.0000  [10 pts]   correct
REVERSED  side=-1 Q3 -> mouth ctrl r17.8000  [15 pts]   matches the emitted program
```

The emitted program had exactly r17.8000 and 15 points.

## The fix

Offset in the DRAWN order and put the result back the way it came, so the cut
direction is preserved and only the geometry is corrected. The test is against
`resolve_points`' own order, so a project whose points already match is
untouched - which is what keeps OD bit-identical.

## Gates

```
testing_14_inside_bar   contour gouge 0.8000 -> 0.0000, 27 tangent points,
                        0 uncovered -> PASS
                        wrong-side control still FAILS at 0.8000
testing_15_0 (OD)       PASS, wrong-side control FAILS
36 OD configurations    byte-IDENTICAL
suite                   twelve gates, cam_map, lathe_validation, flake8
```

The negative control failing is the half that matters: a proof that cannot fail
is not a proof, and a single profile line is tangent to the nose circle from
either side.

## Why it hid

The only ID project in the repo used **T2, an OD turning tool**, on a bore. Its
orientation happens to give the right answer, and its unreachable contour
shortened the path to 3 points - so the prover reported three uncovered
segments and a 0.3542 gouge, which looked like a lead-geometry fault rather
than a reversed offset.

`testing_14_inside_bar.xml`, added yesterday, is the first ID project whose
tool can actually reach the profile. It exists because the recorded numbers
would not reproduce.

## What it corrects in the record

The notes proposed widening the entry by `_tip_lead_w`, mirroring `boring.ngc`,
on the theory that the ends gouge. **The whole contour was on the wrong side of
the wall**, not just its ends. That fix would have moved the entry and left the
bore 0.8 mm oversize.

## Still open

Whether the recorded **1.4929 mm** native-compensation figure is this same
fault seen through the interpreter rather than In-CAM. Native comp does not go
through `offset_contour`, so it needs its own measurement.
