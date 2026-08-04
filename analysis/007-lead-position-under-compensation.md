# 007 — Lead-in / lead-out position under compensation

2026-08-04. greatEndian reports the lead-in and lead-out misplaced whenever
compensation is on, absent with it off. **Measured, not yet diagnosed** — what
is measured is consistent with correct compensation, so the next step is to
establish whether the PART comes out wrong or only the picture looks different.

## Measured — testing_15_2, finish pass, last three moves

    Off      f(-70.400, 24.238) -> (-70.400, 30.000)   wall up to r30
             f(-70.400, 30.000) -> (-70.400, 30.000)   zero-length
             f(-70.400, 30.000) -> (-69.693, 30.707)   1 mm lead-out at 45

    Native   f(-70.400, 24.341) -> (-70.400, 29.600)   wall stops 0.400 short
             f(-70.400, 29.600) -> (-70.000, 30.000)   extra diagonal
             f(-70.000, 30.000) -> (-69.293, 30.707)   lead-out, +0.400 in Z

And at the other end, the approach rapid lands at Z 1.307 under Native against
Z 1.707 under Off — again 0.400, again the nose radius.

## Why this may not be a fault

0.400 is exactly the nose radius, and the extra diagonal is the **nose rolling
around the convex corner** at (Z−70.400, r30). That is what a correct
compensated path does at a 90° external corner: the control point cuts the
corner while the nose stays on the part. The wall "stopping short" at r 29.600
is the control point, not the cut surface — the nose is still on r30.

The same goes for the approach: with an orientation-2 tool the compensated
control point sits 0.400 back in Z on an axis-parallel surface, which is the
result `test_quadrants` proves to 1e-12 and the whole reason `c16df1f` exists.

So every number here is the nose radius appearing where the nose radius should
appear. **Different from Off is what compensation is for.**

## What would make it a fault

- the lead-out **cutting into** the finished face on its way out rather than
  retreating through air
- the lead-in **entering the material** before the contour starts
- the compensated surface, as opposed to the control point, not reaching r30

None of those has been measured. The first two are answerable by sweeping the
nose along the lead moves and testing against the stock field — the machinery
`test_rough_comp.py` already uses. The third by extending the surface
measurement past the contour ends, which it currently stops at.

## Open question for greatEndian

Which is it: does the finished PART come out wrong under compensation, or does
the toolpath merely look different from the Off case in the plot? The
distinction decides whether this is a bug in the lead placement or the expected
appearance of a compensated path, and guessing wrong costs a working
compensation path.
