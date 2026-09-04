# 106 — the bore gouge is in the INPUT to offset_contour, not the side

**Asked**: greatEndian, 2026-09-04 — *"go with 1"*, the ID compensation fix.

## Narrowed, not fixed

The obvious suspect was the compensation side. It is not:

```
testing_14_inside     -> side=-1  orient=2  nose_r=0.4
testing_14_inside_bar -> side=-1  orient=3  nose_r=0.4
```

Both derive `side = -1` correctly from `param_side = 1`, measured by probing
`build_cam_comp_gcode` itself rather than reading the code.

And `offset_contour` handles Q3 correctly when it is given the drawn profile:

```
Q2 side-1 : first ctrl r16.2   [10 pts]      <- matches T2's emitted path
Q3 side-1 : first ctrl r17.0   [10 pts]      <- CORRECT: centre 16.6 = wall - R
Q3 side+1 : first ctrl r17.8   [15 pts]      <- matches T14's emitted path
```

So the function computes the right answer for a boring bar, and the caller
passes the right side - yet the emitted path is the `side+1` one.

**Therefore the wrong thing is the INPUT.** `build_cam_comp_gcode` does not
offset the drawn profile; it offsets `finish_profile`'s REACHABLE contour, and
for a Q3 boring bar on a bore that contour is evidently not what the drawn
profile is. That is where the next session starts.

## What is solid

- The 0.8000 gouge is real and reproducible on `testing_14_inside_bar`.
- Nose centres sit at `wall + R` where a bore needs `wall - R`.
- The wrong-side control is sound; it gouges 2R because that is what the
  wrong side does, and the emitted path coincides with it.
- The side derivation and `offset_contour` itself are both exonerated by
  measurement.

## Three readings of one failure, two of them wrong

1. *"the project has n_comp = 0, the reproduction is invalid"* - wrong, the
   prover overrides it.
2. *"identical results across three projects, the instrument cannot
   discriminate"* - wrong, same cause.
3. *"the side is inverted for ID"* - wrong, the side is correct.

Each was settled by measuring the thing itself rather than reasoning about it,
and each wrong reading cost a round. The pattern in all three: I explained a
surprising number with a story instead of instrumenting the code that produced
it.

## Not touched

No fix attempted. `offset_contour`'s input is motion, ID and compensation at
once, and `openPoints` says that class of change does not get made without a
word first - which it now has, but not blind. The gate it needs is unchanged:
correct side PASS and wrong side FAIL on `testing_14_inside_bar`, plus an OD
project to show nothing moved.
