# 015 — Compensated roughing overcuts the steep wall by 0.1643 mm

2026-08-05, branch `liveTooling`. Found while answering greatEndian's *"do it
for all.. there is no compromises"* — the search for what was still
uncompensated in roughing turned up the opposite: a place where compensation
makes it **worse**.

## Measured

Worst overcut past the pre-finish target, window Z −19.4 … −22.5 (the steep
wall at the base of the boss, local angle ~79 degrees):

```
Off       0.0000 mm
Native    0.1643 mm at Z-19.640
In CAM    0.1643 mm at Z-19.640
```

`0.1643 ~= R*sqrt(2) - R = 0.1657` — the orientation-vector signature, inside
the stock field's own quantisation. It is **not** staircase discretisation:
a 0.508 radial step on a 79.3 degree wall gives 0.0960 mm of Z between level
ends, and it would appear in all three modes, not only the compensated two.

Across the whole part compensation is still a net gain — `test_rough_comp`
reports 0.1116 mm of overcut on Off against 0.0394 compensated — so this is a
LOCAL regression that the global one-sided metric averages away.

## Mechanism, as far as it is established

The stop contour on that wall:

```
Off      Z-19.5545 r21.4341   Z-19.7812 r22.8870
Native   Z-19.5549 r21.0516   Z-19.7862 r22.5495
                   ^ 0.3825 lower      ^ 0.3375 lower
```

On a wall the surface normal is nearly axial, so `roll * normal` contributes
almost nothing in X while the orientation term subtracts its full 0.4 — the
compensated stop contour sits ~0.4 lower in radius than the uncompensated one.

**That is correct for a control point**: the tip is the lower-left corner of
the nose, and for the nose to touch the wall the tip must sit R below the
contact radius. What is not established is whether a roughing LEVEL may read
its stop from that contour. A level is a horizontal cut at a fixed tip radius,
and the nose it drags is a disc: at tip radius r the disc reaches its extreme
-Z at radius r + R, not at r. Looking the stop up at the level's own radius
therefore asks the contour a question about a different point of the tool than
the one that will actually touch the wall.

**Unproven.** This is the hypothesis the fix has to be built on, and it has not
been demonstrated — no measurement in this file distinguishes it from the
alternatives. Do not treat it as the cause.

## Not fixed

Deliberately left. This is a change to roughing motion at the end of a session
that has already produced two reverts from acting on a plausible mechanism
before proving it (`57eea44`, and the retreat rework). The evidence above is
solid; the explanation is not, and the two must not be shipped together.

### What the fix needs, in order

1. **Settle how a level's stop should be looked up when the tool is a disc.**
   Synthetic case: one horizontal level, one vertical wall, known nose - work
   out by hand where the tip must stop, then compare against what
   `lathe_level_pass` computes today. Five lines, and it decides everything
   after it.
2. Only then change the lookup - in Python if the answer belongs in the stop
   table, in the subroutine only if it genuinely depends on the level.
3. **Acceptance**: the steep-wall window measures ~0 on all three modes, and
   `test_rough_comp`'s whole-part number does not get worse than 0.0394.
4. A regression test for the window itself. `test_rough_comp`'s existing metric
   is one-sided and whole-part, and it **passed throughout** while this was
   live - it cannot see a local regression that is smaller than the worst
   global overcut.

## What this says about the metric

The whole-part overcut number (0.1116 -> 0.0394) is what has been quoted all
session as proof that roughing compensation works. It is true and it is not
enough: a mode can improve the worst point on the part while introducing a new
error somewhere else, and a single max() hides that completely. Windowed
comparison against the SAME target, per mode, is what surfaced this in one run.

---

## REFUTED, same day — there is no steep-wall defect

Both halves of the finding above are wrong, and both were settled by
measurement rather than argument.

### 1. The stop contour is exact

The synthetic case this file prescribed: a cylinder at r20 running into a wall
rising to r26 at 83 degrees, offset by 0.508. Hand-derived tip stop — nose
centre at `surface + (f_off + R) * n`, tip at `centre - (R, R)` — against what
`entry_contour` produces with the nose applied:

```
level    table stop Z (comp)    hand-derived tip Z    error
r21.00   -19.1571               -19.1571              -0.0000
r22.00   -19.2799              -19.2799              +0.0000
r23.00   -19.4026              -19.4026              +0.0000
r24.00   -19.5254              -19.5254              +0.0000
```

Exact at every level. The hypothesis that a roughing level may not read its
stop from a control-point contour is **refuted** — the contour is precisely the
tip position that puts the nose tangent to the offset wall.

### 2. The 0.1643 mm was my metric, not the machine

Re-measured as **perpendicular distance** from the swept surface to the target,
which is the only valid comparison where the surface is near-vertical:

```
worst distance INTO the pre-finish target, Z-19.4..-22.5
   Off      -0.2824 mm
   Native   -0.1320 mm
   In CAM   -0.1320 mm
```

Compensation **improves** the steep wall, 0.2824 -> 0.1320. The earlier figure
compared radius-at-Z column by column across an 83 degree wall, where one
0.0667 mm column spans 0.54 mm of radius - so the number measured the
quantisation, not the part.

`test_rough_comp`'s own `radius_span` docstring documents exactly this trap:
*"there is no single radius at that Z, and comparing a swept surface against
the outer one there reports the whole height of the wall as an overcut.
Measured: 4.7405 mm at Z-69.4 on testing_15_2, in every mode including Off,
which is the end wall and not a fault."* That warning was written into this
codebase earlier in the same work, and then walked into anyway.

**Seventh baseline-class error of the session**, and the first one that got as
far as being committed as a finding and written into `openPoints.md` as a live
defect. The lesson is not "measure perpendicular distance" - it is that a new
metric must be run against the KNOWN-GOOD mode and against a surface whose
answer is known by hand *before* its output is believed, not after it produces
an interesting number.

### Standing

Roughing compensation is correct everywhere it has been measured. No code
change was made for this file, and none is needed.
