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
