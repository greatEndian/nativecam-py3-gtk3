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
