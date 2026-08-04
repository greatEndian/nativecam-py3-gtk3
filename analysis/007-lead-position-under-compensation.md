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

---

## 2026-08-04, second half: greatEndian's clarification, and the bump located

*"lead in and lead out can not end in the part or stock... also radius start can
not go first inside the part and then outside at prefinish contour... it has to
be exact line with no bump till radius start rising"*

That is a fault, not an appearance, and the bump is **measured**.

### The measurement

Offsetting testing_15_2's profile (23 points, Z +1.71 to −69.69):

    offset_contour  0.508   38 pts   1 Z reversal
    entry_contour   0.508   42 pts   4 Z reversals

The reversals, from `entry_contour`:

    0.641 -> 1.000        -20.000 -> -19.492
    -70.514 -> -69.892    -70.041 -> -69.334

**−20.000 → −19.492 is the corner where the wall meets the taper**, and 0.492
is the offset. A reversal *is* the bump: the path runs back the way it came and
then forward again, so the tool dips in and comes out.

Cause: offsetting segment by segment and joining consecutive offset ends with a
straight connector puts that connector *behind* the corner on an inside turn.
`build_finish_contour_gcode`'s own comment has flagged it since it was written —
*"that offset came out non-monotone in Z, so it needs its self-intersections
resolved first"*. It was written down and never resolved; this is it surfacing
on the part.

### An attempted fix, reverted

Dropping points that double back in Z took both counts to **0 reversals** — but
also 42 → 32 points, and broke `test_sections` ("every segment contributes both
its offset ends"), `test_rough_comp`, `test_comp_overlay` and `test_skip_short`.
It was discarding real geometry, not just connectors: on a RADIAL wall the
offset segment's two ends share a Z, so a monotone test cannot tell that pair
from a reversal. Reverted rather than committed.

**To finish**: resolve the self-intersection properly rather than filtering by
Z. The offset segments are already built with their endpoints in
`offset_contour` (`cur['a']`, `cur['b']`, `nxt['a']`); an inside corner is
already detected there by the sign of the cross product and trimmed with
`_isect`. `entry_contour` has no such trim at all — it just emits both ends of
every segment. **Giving `entry_contour` the same corner treatment
`offset_contour` already has is the likely fix**, and it can be checked without
rs274: reversals to zero AND `test_sections` still passing are both required,
and the reverted attempt failed the second.

### The leads

Still not established, and it needs the same care. The lead numbers in the first
half of this file are all exactly the nose radius and consistent with a correct
corner roll — but greatEndian's constraint is explicit: **a lead may not end in
the part or the stock**. That is a testable statement and it has not been
tested. Sweep the nose along the lead moves against the stock field, the way
`test_rough_comp.py` does for roughing, and see whether any lead move's swept
volume intersects material. That measurement does not exist yet.
