# 111 — how G41.1 establishes across a fillet arc

**Asked**: greatEndian, 2026-09-06 — *"study how G41.1 establishes across a
fillet arc"*, after two ineffective fixes (`analysis/110`).

Answered by running the interpreter on the exact pattern, not from the manual.

## The experiment

The real entry shape, in radius mode so nothing hides in diameter arithmetic:
a 45 degree straight lead, a 1 mm fillet, then along a bore wall at r17.

```
G1 F100 X16 Z1        the straight lead
G3 X17 Z0 I0 K-1      the fillet, tangent to both
G1 Z-20               along the wall
```

## What the interpreter does

**Compensation ON BEFORE the lead:**

```
STRAIGHT_FEED(16.1172, Z 0.3172)      the entry endpoint is DISPLACED
ARC_FEED(0.2000, 16.4000, ...)        the arc is SPLIT in two -
ARC_FEED(-0.4000, 17.0000, ...)       the interpreter rolls the corner
STRAIGHT_FEED(17.0000, Z-20.4000)
```

**Compensation ON AFTER the lead - what the code does today:**

```
STRAIGHT_FEED(16.0000, Z 1.0000)      uncompensated
ARC_FEED(0.0000, 17.0000, ...)        uncompensated, ENDS EXACTLY ON THE WALL
STRAIGHT_FEED(17.0000, Z-20.4000)     only this one is compensated
```

## The answer

**G41.1 establishes across a straight-then-arc entry perfectly well.** The
straight lead is a valid entry move, the offset applies from its endpoint
onward, and the interpreter splits the following arc itself to roll the nose
around the corner. There is no "an arc cannot establish compensation" problem
here, because the arc is not the establishing move - the straight lead is.

The gouge is the other ordering: with comp switched on after the fillet, the
arc's endpoint is uncompensated and lands ON the wall - which is exactly the
measured point, centre `Z0.0000 r17.4000` against a `r17.0000` wall.

## What this says about attempt 2

`analysis/110`'s second attempt - move `tip_comp_on` ahead of the straight lead
- was the RIGHT idea. It did not move the gouge, so it did not take effect on
this project's path. The next step is to find out why, not to invent a third
approach: check where `G41.1` actually sits relative to the lead moves in the
emitted program, which is one grep of the generated file.

Candidate reasons, to be tested rather than reasoned about: the fillet branch
may not reach the insert, `_tip_comp_d` may be 0 under native compensation at
that point, or `comp_done` may not suppress the later `o<co_1>`.

## The trap that is NOT there

The comment in `lathe_poly_pass` warns that a tight blend can trip cutter comp,
and the arc-entry branch avoids programming an arc as the first compensated
move. Both are about an arc being the ESTABLISHING move. With a straight lead
in front of it that concern does not apply - demonstrated above, the arc is
compensated and split without complaint.
