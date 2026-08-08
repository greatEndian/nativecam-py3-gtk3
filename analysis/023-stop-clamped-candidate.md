# 023 — A clamped fallback was beating the real crossing

2026-08-08, branch `liveTooling`, from `8b0773b`. Project: `testing_15_5.xml`.

## What was asked

greatEndian, issue 1 of three: *"3rd, 4th, 5th pass from stock envelope in
front of boss segment is not tangent to prefinish contour (sectioning on/off)"*.

## Measured first

Where each front-of-boss cut ends, against the Z at which the pre-finish
contour reaches that same radius:

```
 #  radius    cut ends Z    contour at that r    gap
 3  33.2080    -31.3358    never in front         -
 5  32.7000    -28.3891    -29.4554           +1.0663
 7  32.1920    -26.9929    -27.9293           +0.9364
 9  31.6840    -26.7969    -26.7951           -0.0018   tangent
11  31.1760    -25.8865    -25.8847           -0.0018   tangent
13  30.6680    -25.1398    -25.1384           -0.0014   tangent
```

So it is not "all the first passes": levels 9 and deeper already landed ON the
contour, and two levels stopped about a millimetre short of it.

## The cause

Instrumented `lathe_level_pass`'s stop-extension. At r32.7000 the level crosses
the pre-finish contour **three** times:

```
Z-29.4588   the boss front face      <- the one it should stop on
Z-36.4467   the boss back face
Z-69.8920   the end of the part
```

The extension bounds how far a crossing may pull the stop (`s_reach`). The
first crossing is 1.2534 away and inside its reach, so it stands. The other two
are 8.24 and 41.7 away, far out of reach, and **a crossing beyond the reach is
clamped, not rejected** — it falls back to the feature boundary, `s_fz` =
Z−28.3891.

Then the winner is chosen by "nearest the front". Z−28.3891 is nearer the front
than Z−29.4588, so **the clamped fallback beat the genuine crossing** and the
pass stopped 1.0697 mm short — the 1.0663 measured.

The clamp is the answer to *"there is no crossing within reach"*. It has no
business competing with a crossing that is within reach.

## The fix

Each candidate now carries whether it was clamped. An unclamped candidate wins
outright; among candidates of the same kind, nearest-to-the-front still wins,
exactly as before. Three lines of state, no change to the reach, the clamp or
the feature boundary — all of which were right.

```
 5  32.7000    -29.4588    -29.4554    -0.0034
 7  32.1920    -27.9317    -27.9293    -0.0024
```

Both now land on the contour to the same 0.002-0.003 as the levels that were
already correct.

## The third pass is a different thing — NEEDS A CALL

Level 3, r33.2080, is not covered by this and is not a clamping fault:

```
pre-finish contour peak in front of the boss   r33.1657
level 3                                        r33.2080   (0.0423 ABOVE it)
```

**The level clears the pre-finish contour entirely**, so in front of the boss
there is nothing for it to be tangent to. What stops it at Z−31.3358 is the
FLOOR allowance — fin_off + prefin_off = 0.762 — which the boss does reach.

So it is doing what it was told: roughing holds 0.762 off the profile, and the
boss blocks it at that distance even though it clears the 0.508 the pre-finish
pass needs. The result is a split into two intervals with a retract between,
where one continuous sweep would do.

Letting it sweep over means letting a level pass when it clears the PRE-FINISH
contour rather than the floor allowance, and at the boss peak that leaves
0.5503 instead of 0.762 — still more than the pre-finish pass needs, but less
than the roughing allowance says. That is a change to what roughing guarantees,
and the code carries a warning against exactly this move: halving the scan
offset once turned 487 mm of cut into 875.6 and finished ten ends inside the
contour.

Not guessed. Recorded in `openPoints` as a decision for greatEndian.

## Still unknown

- The whole extension is runtime O-code scanning a table Python already built -
  `s_reach`, the slope term, the flat-boundary clamp and now the clamped-ness
  rule. Per the standing rule it belongs in Python, computing the stop Z per
  level directly. That needs the level ladder in Python, which is most of the
  way there after `analysis/022`.

---

## Issue 2 — the parallel ramp the first pass behind the boss was missing

greatEndian: *"(sectioning off) the first lead in (3rd from stock envelope) is
missing the parallel artificial lead in section extension as every pass behind
it has"*.

### Measured

```
 #  radius    from Z     to Z      side     ramp
 3  33.2080    0.0000   -31.3358   front    -
 4  33.2080  -35.1477   -69.8920   behind   -          <- missing
 6  32.7000  -36.4467   -69.8920   behind   RAMP 2.2004 / 0.5080
 8  32.1920  -38.6471   -69.8920   behind   RAMP 2.2004 / 0.5080
10  31.6840  -40.8475   -69.8919   behind   RAMP 2.2004 / 0.5080
```

### Two causes, both about where the angle comes from

The ramp copies the contour's own angle at the entry, and it took that angle
from the crossing that set the pass's START. That conflated two questions.

**First**, `e_reach` bounds how far BACK the start may be pulled, and it
collapses on a steep segment - rightly, there is no long shallow ramp to be had
on the face of a boss. But the ramp only needs the segment's DIRECTION, and it
was being dropped along with the out-of-reach crossing. The nearest crossing's
direction is now kept whatever the reach says, and the reach goes on bounding
the start alone.

**Second**, and what this pass actually hit: instrumented, it reports
`have=0 ahave=0` — **there is no entry crossing at all**. The entry contour
peaks at **r33.1657** behind the boss and the level sits at **r33.2080**,
0.0423 over it, so it never crosses anywhere near the feature. The deeper
passes cross the long taper below, direction (−33.98, −7.85), slope 0.231 —
the 13° their ramps show.

The surface the pass is leaving is still right there: the entry segment
spanning `w_from`. It is now the last fallback.

```
 4  33.2080  -35.1477  -69.8920  behind  RAMP dz=2.9656 dr=0.5080
```

Slope 0.1713, 9.7° — the local contour angle, shallower than the deeper passes'
13° because the contour is shallower there. Parallel to what it is actually
leaving, which is the point of the segment.

### Verified

`test_rough_comp` Off 0.1115 / Native 0.0503 / In CAM 0.0503, `test_ladder`,
`test_floor_ladder`, `test_rough_ends`, `test_leads`, `test_skip_short` all
pass.

---

## Issue 3 — a radius that fell between two rules, and was never cut

greatEndian: *"(sectioning on) the first pass (4th from stock envelope) with
lead in and parallel section is missing and just 2nd one is present with double
of cutting depth behind the boss segment also"*.

### Measured

```
last full-length level (cuts both sides)   r33.5955
first level behind the boss                r32.6602      <- 0.9353 taken
front-of-boss step                         0.4682
```

0.9353 is exactly **double** the step. The level at **r33.1273** exists in front
of the boss and has no behind-the-boss counterpart at all.

### The cause — two rules, and a gap between them

Instrumented the sectioned level loop. `sect_top_r = 33.1273`,
`_pl_ph1_front_cut = 1`, `_pl_ph1_z_end = -32.1885` — phase 1 cut that radius
from Z0 to Z−32.1885 and then broke, deliberately: *"it stops the instant the
first obstruction is found rather than sweeping the rest of the part at this
radius, which would just be an ordinary, redundant multi-crossing sweep phase
2's own per-section handling already does properly."*

Except phase 2 does not do it, and cannot:

- **window 0** is the full-length one, band `32.6591 … ALL`. It starts one level
  BELOW `sect_top_r` because phase 1 "already cut" that radius — true for the
  front half only.
- **window 2** is the section behind the boss, and it does start fresh at
  `sect_top_r`. But its band is `20 … 32.6591`, and 33.1273 is **above** it —
  over that boundary the sections are merged into window 0.

So the radius is skipped by the window that spans it and out of band in the
window that starts fresh. It is never cut behind the boss, and the next level
takes both bites.

### The fix

Phase 1 finishes the level it is on — it takes the resumed interval instead of
abandoning it — and only then hands over. `_pl_ph1_z_end` becomes where it
really finished, so every section below may skip that radius, which is now true
rather than half true. The old comment's fear of a "redundant sweep" is the
opposite of the case: it is the only pass that covers that radius at all.

```
behind the boss:  33.127  32.660  32.152  31.644  ...
steps:            0.4671  0.5080  0.5080  ...
```

### One own-goal on the way

`ph1_fin` is set when phase 1 hands over and is not reset per level, so the
break it triggers fired in **every** phase-2 window after its first level: the
sectioned program fell from 44 level cuts to **9**. Caught by measuring the
total rather than by looking at the fixed pass. The break is now gated on
`w_idx < 0`, phase 1 alone.

Sectioning ON now cuts 45 levels, 19 of them touching behind the boss, against
44 and 18 with sectioning OFF - and OFF is byte-for-byte unchanged.

### Verified

`test_rough_comp` Off 0.1115 / Native 0.0503 / In CAM 0.0503, `test_ladder`,
`test_floor_ladder`, `test_rough_ends`, `test_leads`, `test_skip_short`,
`test_sections`, flake8 clean.

---

## Two the fixes above caused, 2026-08-08

greatEndian verified and found both. `photo/doubledLeadIn_0.png` and
`photo/wrongExtraLenghtLeadInBehindBossSegment_0.png`.

### The doubled lead-in — the ramp pointed INTO the part

*"before boss section there is path where lead in doubled, means that first
lead in goes at second pass level and then its return in opposite angle to
first pass Z0.0"*. Exactly that, in both modes:

```
feed  Z 1.2151 r34.4231 -> Z 0.5080 r33.7160    dives to the SECOND pass level
feed  Z 0.5080 r33.7160 -> Z 0.5080 r33.7160    no-op
feed  Z 0.5080 r33.7160 -> Z 0.0000 r34.2240    climbs back to the first pass
```

The fallback added for issue 2 armed a ramp on the FRONT passes, where none
existed before. At Z0 the entry segment rises with the front face, so copying
its angle gives slope −1 and puts the ramp's start 0.5080 **inside** the level:
the tool dives to the next pass's radius and climbs back out.

The ramp exists to arrive parallel through material that is already gone, so it
must start on the stock side. It is now armed only when it does. On those front
passes that means no ramp, which is the right answer — the plain lead-in
already handles them, and it is what they had before.

### The ramp behind the boss was longer than its neighbours

*"lead in parallel section at first pass behind the boss segment has to have
same parameters as each other one no extra length"*.

```
 4  33.2080  behind  RAMP dz=2.9656 dr=0.5080   <- mine
 6  32.7000  behind  RAMP dz=2.2004 dr=0.5080
 8  32.1920  behind  RAMP dz=2.2004 dr=0.5080
```

Same 0.5080 of depth, longer in Z, because the fallback copied the segment the
pass merely STARTS on — at the boss foot a short shallow scrap of fillet, slope
0.1713 — while every crossing-derived neighbour lands on the long taper behind
it, slope 0.2309.

**Fixed in Python**, per the standing rule and greatEndian's *"everything code
in python if it is possible"*. `entry_ramp_dirs` names, per entry segment, the
dominant surface just ahead of it — the longest segment within ten depths of
cut — which is what a crossing would have named. It rides out with the entry
contour it indexes, so no saved project has to migrate to get it, and the
runtime now **reads** the angle where it used to derive one:

```
 4  33.2080  behind  RAMP dz=2.2004 dr=0.5080   identical to every other pass
```

The `.ngc` got smaller in the process: the segment-direction arithmetic is gone,
replaced by a table lookup.

### Verified

Doubled lead-in gone in both modes. Sectioning ON 45 level cuts / 19 behind the
boss, OFF 44 / 18, steps 0.4682 0.4681 0.4682 0.4671 0.508… — no double bite.
`test_rough_comp` Off 0.1115 / Native 0.0503 / In CAM 0.0503, `test_ladder`,
`test_floor_ladder`, `test_rough_ends`, `test_leads`, `test_skip_short`,
`test_sections`, `test_lathe_validation`, flake8 clean.

### And it was still wrong with Sectioning ON

greatEndian, on the same screenshot: *"this is not solved yet"*. Right — I had
checked the ramp table on the **unsectioned** run, and the screenshot has
Sectioning ticked.

```
sectioning ON
 5  33.1273  behind  RAMP dz=8.9734 dr=0.5080   <- four times its neighbours
 7  32.6602  behind  RAMP dz=2.2004 dr=0.5080
```

Slope 0.0566: the level at r33.1273 **crosses the near-flat top of the boss**,
and the crossing-derived direction was still preferred over the table. A
crossing names the segment the level happens to meet, which is not the surface
the pass will run along.

The Python table now wins outright and the crossing branches remain only for a
program generated before it existed. Every ramp across three projects in both
modes is now one angle, slope **0.2309**:

```
testing_15_5 sect=1   16 ramps   14 x 2.2004  1 x 2.2003  1 x 1.2336
testing_15_5 sect=0   16 ramps   14 x 2.2004  1 x 2.2003  1 x 1.3198
testing_15_4 sect=1    9 ramps    7 x 2.2004  1 x 2.2003  1 x 1.3199
testing_15_2 sect=1   10 ramps    8 x 2.2004  1 x 2.2003  1 x 1.3199
```

The short one in each is the same angle, proportionally shortened where the cut
cannot fit a full ramp — deliberate, and the reason the test below bounds
length rather than demanding equality.

### `test_ramps.py` — the test that should have existed

Three faults reached greatEndian in one day because the ramp had three sources
for its angle and nothing asserted which fired where. It now asserts, over
three projects in both modes, **69 ramps**:

1. **one angle** — every ramp in a program shares a slope. That is greatEndian's
   criterion exactly, and all three faults broke it.
2. **shorter is allowed, longer is not.**
3. **a ramp never starts inside the level it enters** — the doubled lead-in,
   stated directly.

Not circular: the angle is compared against the OTHER ramps in the same
program, read back out of `rs274`, never against the table Python emitted.

Negative control, by forcing `_pl_eramp_n` to 0 in the generated file — the
runtime gate, so it is the old behaviour exactly:

```
table ON    16 ramps, slopes {0.231: 16}
table OFF   16 ramps, slopes {0.057: 1, 0.231: 15}
```

The 0.057 is the 8.9734 ramp. Assertion 1 fails on it.

---

## The ramp on the family line, and a table-base collision I caused

`photo/leadIn_0.png` — greatEndian drew it: orange the situation, violet what is
wanted. Same angle, shifted horizontally toward the boss at the same two radii.

```
now     Z-32.9473 r33.7160  ->  Z-35.1477 r33.2080
wanted  Z-32.0459 r33.7160  ->  Z-34.2463 r33.2080     +0.9014 in Z
```

Z−34.2463 is exactly where the NEIGHBOURING ramp starts, so the violet puts this
one back on the line the others lie on. greatEndian's reason is the machining
one, not the picture: *"if tool at second pass behind this go inside at 45 lead
in as it is now it will cut at very high roughing surface and length of active
cutting edge will be also longer than in the other cuts"*.

### Why it sat 0.9 out

That level, r33.2080, is 0.042 **above** the entry contour's local peak behind
the boss (r33.1657), so it crosses nothing and its start fell back to the floor
scan — which stands one pre-finish allowance further out, the 0.2509 measured.
Every neighbour starts on a crossing, which is why they land on the line.

### The fix, in Python

`entry_ramp_dirs` already named the surface's direction per segment. It now also
names **a point on that line**, so the start for a non-crossing level is where
that line reaches its radius — one line of arithmetic in the `.ngc`, bounded to
three depths of cut of `w_from` and to the window.

```
 4  33.2080  behind  ramp Z-32.0503 -> Z-34.2507
 6  32.7000  behind  ramp Z-34.2463 -> Z-36.4467
```

The first now ends exactly where the second begins: the ramps chain along one
line. Its clearance over the pre-finish contour stays +0.1159 rather than
0.0000, and that is geometry, not a fault — the level is above the contour's
peak, so no point on it has that radius.

### And the collision, which was mine

The ramp table needed 4 slots per segment instead of 2, so it grew from
3200–3300 to 3200–3380 and the floor-stage table moved to 3380. **Python was
moved and `poly_lathe_mill.ngc` was not** — four reads still at `#3300`, which is
now ramp data. The floor ladder was reading ramp directions as floor radii, and
greatEndian saw it immediately: *"in the sectioning on there are that touched
passes doubles and offsettes in the Z+ directions"*.

Two tests read the same table by regex, `#33\d\d`, which after the move matched
the ramp slots too — narrowed to `#33[89]\d`. That is the second time a table
base moved and something reading it did not: the layout comment at the top of
`lathe_sections.py` is the index, and everything that reads a base must be
grepped when one changes — including the tests.

### Verified, both modes

Sectioning OFF: 44 level cuts, 18 behind the boss, every step 0.508.
Sectioning ON: 45 / 19, steps 0.4682 0.4681 0.4682 0.4671 0.508…, every ramp
tangent at −0.0010. `test_ramps`, `test_floor_ladder`, `test_ladder`,
`test_rough_comp` (Off 0.1115 / Native 0.0503 / In CAM 0.0503), `test_rough_ends`,
`test_leads`, `test_skip_short`, `test_sections`, `test_lathe_validation`,
`test_coord_mapping`, `test_vkb`, flake8 both lists.
