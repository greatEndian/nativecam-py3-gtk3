# 051 — High feedrate: the mode was the wrong shape

2026-08-15. greatEndian: *"High feedrate mode is now floating point selection
instead of Radio button, but it shouldnt be at all there should be only high
feedrate mode feedrate floating point and if it is non zero it is on then"*.

Two complaints, and the second answers the first.

## The rendering fault was real

`[PARAM_HF_MODE]` was declared `type = combo` with six `options`, which should
render as a picker — but it also carried `digits = 0`, and it presented as a
float entry. Rather than chase which of the two the renderer believed, the
parameter is gone: greatEndian does not want the mode at all.

## Why a mode was never worth its weight here

`analysis/044` measured the fact the six choices existed for: **148 positioning
moves on testing_15_5, 99 radial, 49 axial, and none moving both axes**. A
single-axis G0 is straight on any control, so the dogleg case the modes exist to
manage does not arise, and three of the six were identical on this output. They
were offered only so a setting carried the same meaning as in the package it
came from — which is not a good enough reason for a parameter that has to be
understood before it can be ignored.

## What it is now

One parameter, `High feedrate`. **Non-zero is on**, and it converts every
positioning move; zero leaves them all true rapids. Zero is also the only safe
reading of "no rate", because `G1 F0` stops the machine — the subroutine already
fell back to a rapid on it, so that behaviour is unchanged and is now the whole
switch rather than a guard behind one.

Deleted, not left inert: `PARAM_HF_MODE`, its `order` entry, the two
`<eval>`-derived globals `_pl_hf_x` / `_pl_hf_z`, their `create_defaults`
entries, and the per-axis pick in `hf_move`.

**Kept:** the feed restore. That risk is real and was measured — `F` is modal,
and `lathe_level_pass` has a path where the level cut takes the last `F` set, so
a converted move that did not put the caller's feed back would cut at
positioning speed. All 21 call sites still pass the feed that must be in force
afterwards.

## Measured

testing_15_5:

```
rate 0      470 moves, 148 rapids, 0 at the rate   d14e9d952c14
rate 2000   470 moves,   0 rapids, 148 at the rate  c6d2cabc8e50
```

`d14e9d952c14` is the hash from before the feature existed, so zero is
byte-identical. Move count identical, so a converted move goes where the rapid
went. And exactly 148 moves run at the rate against 148 converted — not one
more, which is the feed-leak check.

## The test

`test_high_feed`'s mode cases are replaced by rate-zero and rate-non-zero. It
keeps the fact the feature is shaped around — that no positioning move travels
both axes — because that is why a mode was never needed, and it is worth
noticing if it ever stops being true.
