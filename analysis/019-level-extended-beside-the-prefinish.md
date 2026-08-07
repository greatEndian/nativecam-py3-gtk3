# 019 — The stop extension carried a level 19.4 mm beside the pre-finish

2026-08-06, branch `liveTooling`. greatEndian, `testing_15_4` (front chamfer):
*"last roughing pass is at all long length same as prefinishing passing ..
passing must not be repeated in the same spot"*.

## Measured

```
deepest level     r20.5240
pre-finish contour r20.5080 on the cylinder      -> 0.0160 apart
the level ran Z-0.0882 .. -19.5318, 18.5 mm of it within 0.10 mm of the contour
```

## Why it happened

The ladder's floor is anchored on the polyline's **Final Diameter, 38 (r19)** -
the chamfer's small end - so the grid is `19.508 + k*0.508` = …20.016,
**20.524**, 21.032… The cylinder's own roughing floor is `20 + 0.762 = 20.762`,
so level 20.524 sits **below** it and the floor scan correctly stops that level
at Z-0.0882, on the chamfer.

The **stop table then extended it**. That extension exists to carry a level
from the floor allowance it stops on to the pre-finish allowance the table
holds, and it was unbounded:

```
legitimate extensions, both projects, every level:  0.90 .. 1.0034 mm
this one:                                          19.4436 mm
```

It jumped the entire cylinder - a region where the level is below the local
roughing floor and has no business cutting - and left it running the length of
the part 0.0160 mm from the pre-finish contour.

## The fix

Bound the extension by the band it crosses: at most one depth of cut of
RADIUS, which costs `doc/|slope|` of Z on the crossing segment, with a floor of
`3 x doc`.

The floor is not decoration. A slope-only bound collapses to nearly zero on a
near-vertical segment and rejects a good extension: the end wall of
`testing_15_2` needs 0.5080 and was cut off, which left **every** level 0.508
short of the pre-finish wall and made one pass behind the boss plunge. That was
measured, not predicted - the first version of this bound shipped it and five
assertions failed.

```
after   testing_15_4  deepest level 19.132 mm -> 0.088 mm, 28 cuts, longest 22.898
        testing_15_2  29 cuts, 0 under 2 mm, longest 23.139
        test_rough_comp Off 0.1116 | compensated 0.0503, unchanged
```

## The wrong fix, and why it was wrong

`224c0b9` truncated the level instead, and was reverted. It measured "what a
level removes" as `level - stop_contour`, which is what is left **below** the
level rather than what it takes - a level removes down to itself from the
PREVIOUS level above it. On the far taper those cuts were taking a full 0.508
step and were truncated anyway: **10 honest passes cut to 1.299 mm**, which is
`photo/spaceBehindIssue_9.png`.

Treating it at the level's length was the wrong end. The level should never
have been carried across the cylinder in the first place.

## Two process notes

- **The first bisect was invalid.** `lib/*.ngc` are read at rs274 RUNTIME, so
  checking out an old lib and parsing a file generated separately measures
  nothing: six commits gave byte-identical output, and the md5s matching is
  what gave it away. The parse has to run with that lib on disk.
- A script named `bisect.py` shadows the stdlib module and breaks
  `import random` -> `tempfile` -> `ncam_preview`.

## Coverage

`test_ladder.py`: no level may run more than 2 mm within 0.10 mm of the
pre-finish contour. Negative control, bound removed:
`r20.5240 runs 18.5 mm of its 19.5 within 0.10 mm of it`.

---

## Addendum — the leads, not the length

greatEndian, after the extension bound landed: *"the short roughing segment
which roughs the existing chamfer is missing and instead there is a small lead
in lead out bump which will produce vibrations .. fix the root cause, no tells
me how to bypass them"*.

Fair, and the workaround offered first - `Skip short roughing passes` - was
one. The root cause is in the SHAPE, not the length.

### The 0.088 length is correct

```
SCAN lvl=20.524000 found=1 zc=-0.088159 zstart=0.000000 doff=1.016000
```

`doff` is **1.016**, not the 0.762 assumed from the parameters:
`pass_from = Final contour` reassigns `step_target = anch_floor`, rounding the
roughing floor outward by a whole depth of cut, and `lvl_d = step_target -
final_radius = 20.016 - 19.000`. With a 1.016 allowance the chamfer's offset
profile crosses r20.525 at exactly Z-0.0882. The scan is right.

### The shape was not

A 1.000 mm lead-in and a 1.000 mm lead-out around a 0.088 mm cut is not a
pass. Both leads are now bounded by the cut they serve:

```
before   lead-in 1.000 | cut 0.088 | lead-out 1.000
after    lead-in 0.088 | cut 0.088 | lead-out 0.088
```

Bounded by the cut and not a fraction of it: a lead equal to the cut still
reads as a lead and keeps its angle, and there is no honest number between
"as long as the cut" and "arbitrary".

### What "the right shape from earlier commits" turned out to be

There isn't one. The deepest level across the history:

```
7404a9d  r20.7454  Z+0.0000 -> -19.5415  19.541   r20.524 did not cut at all
91e8cf9  r20.5240  Z-0.4000 -> -19.5318  19.132   full length beside the pre-finish
224c0b9  r20.5240  Z-0.4000 ->  -0.7409   0.341   the reverted truncation
f98f329  r20.5240  Z+0.0000 -> -19.5318  19.532
cf29e14  r20.5240  Z+0.0000 ->  -0.0882   0.088   correct length, wrong leads
```

It was never a good short chamfer pass - either the full length beside the
pre-finish, or a stub. Saying so was worth more than restoring one of them.

Coverage: `test_ladder` asserts no lead exceeds the cut it serves. Negative
control: `r20.5240 has a 0.088 mm cut with a 0.125 mm lead`.

---

## Addendum 2 — the lead cap was the wrong call, reverted

greatEndian: *"I am sure that lead in/out have to be 1mm as is from property
taken value, then your yesterday last change is right opposite what I thought"*.

Reverted. A lead takes its property value; it is not scaled to the cut.

### And the leads were not 1 mm for a different reason

With the cap gone they came out **0.125**, not 1.000. A pre-existing Z-room cap
was doing it: `room = |z_end - w_from| = 0.0882`, `0.0882 / cos 45 = 0.125`.

That cap exists so a **continuation** interval's retreat cannot run back over
its own start, where the boss that blocked the sweep is sitting. The **first**
interval has no obstruction behind it - it begins at the polyline's Begin Z and
everything in front of that is air - so the cap there only takes away the lead
the operator asked for. It is now skipped on the first interval:

```
before   lead-in 0.125 | cut 0.088 | lead-out 0.125
after    lead-in 1.000 | cut 0.088 | lead-out 1.000
```

Both leads run out into air past Z0.

### The distances, which greatEndian was right about

At Z0.0 on `testing_15_4`, for the level at r20.5240:

```
pre-finish contour        r19.7184     0.8056 mm of material above it
roughing floor (anchored) r20.4368     0.0872 mm
```

The 0.088 cut is the distance to the **anchored roughing floor**, not to the
pre-finish contour - greatEndian's *"distance between this segment start point
Z0.0 and prefinishing contour is not 0.088"* is exactly right.

`anch_floor` is 20.016, derived from **Final Diameter 38 (r19)** - the chamfer's
tip - and applied to the whole part, so `lvl_d` is 1.016 rather than the 0.762
the parameters suggest. The cylinder's own roughing floor would be 20.762.

**Still open**: one ladder floor taken from the deepest point of the profile
gives the chamfer region levels that can only graze it, and gives the cylinder
a level 0.016 from its pre-finish contour. A floor that follows the profile -
per region rather than per part - is what would fix both, and it is a larger
change than anything in this file.

---

## Addendum 3 — the scan was holding 1.016 off the profile, not 0.762

greatEndian: *"the length of the last rough segment is wrong .. it has to be
more than 1mm .. there is a huge gap between the last passing and the
contour"*, `photo/leadInPresent_1.png`.

### A real bug, found and fixed

```
#<lvl_d> = [#<dirsign> * [#<step_target> - #<final_radius>]]
```

`step_target` is REASSIGNED to `anch_floor` by
*Space passes from = Final contour* - the ladder's floor rounded outward by a
whole depth of cut. So the scan's stock allowance became
`20.016 - 19.000 = 1.016` where **0.762** (`fin_off + prefin_off`) was
configured. The anchoring decides where the LEVELS are, not how much stock is
left, and conflating the two shortened every level's reach.

It is now `fin_off + prefin_off` directly. With Stock anchoring
`step_target - final_radius` already equals that, so nothing changes there.

```
last rough segment on testing_15_4:   0.088 -> 0.447 mm
```

### The remaining gap is the option, not a fault

```
Final contour (as saved)  deepest cut r20.5240 len 0.447  gap at Z0  0.8056
Stock                     deepest cut r20.2684 len 0.791  gap at Z0  0.5500
```

*Final contour* rounds the roughing floor outward by a whole depth of cut on
purpose - its own comment says so: *"The pre-finish pass then carries one whole
depth of cut down to its own contour instead of the configured allowance, which
is the point of anchoring on the part rather than on the stock."* So it leaves
`doc + prefin_off = 0.762` rather than `0.254`, and 0.8056 is that plus the
staircase a 45 degree chamfer gets from horizontal levels.

Switching to Stock closes it to 0.5500 and lengthens the last segment to 0.791.

### Why it cannot reach "more than 1 mm" at this level

The chamfer is 1.000 mm of Z. With a 0.762 allowance its offset curve runs
(0.539, 19.539) -> (-0.461, 20.539), and the level at r20.5240 meets that at
Z-0.4474. No level can cut more of a 1 mm chamfer than the offset curve
exposes; a longer cut needs a LOWER level, which needs a lower floor - the
per-region floor still recorded as open above.

---

## Addendum 4 — the chamfer level did not finish on the contour

greatEndian: *"why is this last small pass not tangent to the prefinish
profile?"*.

### Measured, and it was the odd one out

How far each cut ends from the pre-finish contour, perpendicular:

```
r20.5240   0.4190 mm off      <- the chamfer level
r21.0320   0.0001
r21.5400   0.0002
r22.0480   0.0001
r22.5560   0.0002
r23.0640   0.0003
```

Every level with a crossing in the stop table is carried onto that contour and
ends on it. The chamfer level has **no** crossing - it sits above the whole
offset chamfer - so it stops on the floor scan instead and finishes in air.

### The fix

The cut is carried down to the nearest point on the stop contour. On a level
that already ends there the move is zero length and nothing is emitted, so the
guard is the distance itself rather than a special case for chamfers. Bounded
by one depth of cut, like every other reach in this file.

```
r20.5240  cut ends Z-0.4474  ->  finishes at Z-0.7436 r20.2277   0.0000 mm off
```

### What it cost to get right

The first version moved the tool but left the lead-out blending from
`(z_end_cut, level)` - a point the tool no longer occupied. The interpreter
rejected the arc outright on `testing_13_arcs`:

```
Radius to end of arc differs from radius to start:
start=(Z-2.7666,X9.1815) center=(Z-2.7666,X9.5957) end=(Z-3.0595,X9.9503)
r1=0.4142 r2=0.4599 rel_err=9.9433%
```

`test_leads` caught it as all three modes failing to parse. The lead-out now
blends from `_end_x`, where the tool actually is.

Coverage: `test_ladder` asserts every level finishes on the contour. Negative
control: `r20.5240 finishes 0.4190 mm off it, hanging in air`.

---

## Addendum 5 — the chamfer pass is extended, not stopped

greatEndian, after four wrong readings on my part, chose from three concrete
options: **let the pass run past the floor stop and cut nearer the contour than
`fin_off + prefin_off` allows**, rather than following the chamfer diagonally
or dropping the descent.

That is one change to the stop extension: a crossing beyond the reach is now
**clamped to the reach** instead of rejected. The reach becomes the LENGTH of
the extension rather than a test on it.

```
testing_15_4  chamfer level  Z+0.0000 -> -1.9714   1.971 mm   was 0.447
testing_15_2  deepest level  Z+0.0000 -> -19.5534  19.553 mm  unchanged
              29 cuts, longest 24.143             unchanged
```

Every level whose crossing already lies inside the reach - all of them on both
projects, 0.90 to 1.0034 mm - is untouched, so this only affects a level that
would otherwise stop on the floor allowance with a long way still to go.

### What the four wrong readings were

Worth listing, because the pattern is the lesson and not the individual errors:

1. **Truncate the level** where it stops removing material - built on
   `level - stop_contour`, which is what is left BELOW the level rather than
   what it takes. Cut 10 honest passes to 1.299 mm. Reverted.
2. **Cap the leads** to the cut they serve - greatEndian: *"lead in/out have to
   be 1mm as is from property taken value, your change is right opposite"*.
   Reverted.
3. **Finish on the contour** by descending onto it - correct in itself and kept,
   but it was not what "the last pass is too short" meant.
4. **Read "tangent" as touching** rather than as running parallel.

The fifth attempt was not a guess: three options were put with their geometry
written out, and greatEndian picked one. That should have happened after the
second miss, not the fourth.
