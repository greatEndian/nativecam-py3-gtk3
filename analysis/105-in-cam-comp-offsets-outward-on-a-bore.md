# 105 — In-CAM compensation offsets the wrong way on a bore

**Asked**: greatEndian, 2026-09-04 — *"chase the wrong-side control"*.

## The control is sound. The emitted path is wrong.

The wrong-side control is `offset_contour(..., side=-side)`. On a bore that
offsets in the OD sense, putting the path at `wall + R` instead of `wall - R` -
so gouging exactly 2R is the control working, not failing.

The emitted path gouges the same 2R because **the emitted path IS the
wrong-side offset**. Nose centres, from the program, with the prover's own
calibrated Q3 offset applied:

```
centre Z  0.0000  r 17.4000     wall r17    0.4 INTO the material
centre Z-20.0000  r 17.4000     wall r17    0.4 into
centre Z-20.4000  r 12.4000     wall r12    0.4 into
centre Z-40.4000  r 10.0000     wall r10    on the wall
```

A bore needs the nose centre at **wall MINUS R** - 16.6, 11.6, 9.6. It is at
**wall PLUS R**. The whole 0.8000 gouge is that one sign.

## It is orientation-dependent

Same part, same profile, In-CAM finishing:

```
Q2 (OD tool)     control r16.2  + offset (+0.4, +0.4)  ->  centre 16.6  = wall - R   CORRECT
Q3 (boring bar)  control r17.8  + offset (+0.4, -0.4)  ->  centre 17.4  = wall + R   WRONG
```

Mirrored about the wall. So `offset_contour` gets inside work right for one
orientation and wrong for the other - the orientation term and the `side`
argument are not composing correctly for a bore.

That also explains why this stayed hidden: the only ID test project used T2, an
OD turning tool, whose orientation happens to give the right answer, and whose
unreachable contour masked the coverage with three uncovered segments.

## Not fixed here, deliberately

The fix is in `offset_contour`'s composition of orientation and side - motion,
ID, and compensation at once. `openPoints` already says a change of that class
does not get made without a word first, and it needs its own gate: the correct
side must PASS and the wrong side must FAIL, on `testing_14_inside_bar` and on
an OD project to prove nothing moved there.

## What this closes

The recorded **0.2929 mm** and **1.4929 mm** ID gouges now have a mechanism and
a reproducer. They are not lead-geometry faults as the notes assumed - the
proposed fix there was to widen the entry by `_tip_lead_w`, mirroring
`boring.ngc`. That would have treated a symptom: the whole contour is on the
wrong side of the wall, not just its ends.

## Reproducer

`testing_14_inside_bar.xml` - the stepped bore with T14, a right-hand boring
bar. It is the first ID project in the repo whose tool can actually reach the
profile.
