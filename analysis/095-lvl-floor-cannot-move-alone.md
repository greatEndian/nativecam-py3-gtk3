# 095 — lvl_floor cannot move on its own, and the table got 2.3x smaller

**Asked**: greatEndian, 2026-09-04 — *"go on with lvl_floor"*.

## The attempt, and why it failed

`level_floors()` emits the floor each level aims at, mirroring the runtime's
per-window stage walk. Wired into `poly_lathe_mill` it **broke the part**:

```
15_5 s0 d0  MOTION DIFFERS  466 moves against 472
```

The cause is exact. The window-start write lands **before** the stage-arming
block at `:858-864`, which decides whether to arm `fl_i` by testing
`lvl_floor` against the LAST stage. Overwritten to stage 0, that test fails,
the stage machinery never arms, `fl_more` never advances, and the ladder breaks
at the first floor instead of walking them.

## The measurement that makes the conclusion trustworthy

The emitted value is **not wrong**:

```
4542 levels compared, 0 disagreements
```

It agrees with the runtime's own `lvl_floor` everywhere. So this is not a
faulty replica - it is a value that cannot be written where it was written.

**`lvl_floor` therefore cannot be moved on its own.** The runtime's value is
already correct, and the arming depends on reading it BEFORE any table value.
Moving it means moving `fl_i` and the loop's own termination with it - a
larger change than any so far, because `if_next` also carries the phase-1
handover (`p1_end`) and the `ph1_brk` break.

`level_floors()` is kept in Python, unwired, with this recorded on it: the
stage-machinery migration needs exactly that function and it is already proved.

The emitted array was **withdrawn** rather than left in place. Data the program
never reads is worse than none.

## What did land: the table is 2.3x smaller

Measuring the slots before adding anything - the blast-radius rule's "measure
the resource against the real projects" - said a third array would not fit:

```
top=2683  windows=17  radii=544   15_9 s1   against a 2600 ceiling
```

Artificial sectioning gives every window the SAME ladder and the table stored
it 17 times. The directory already addresses runs by offset, so identical runs
now share one copy, keyed on the radii AND the staged flag - phase 1 aims at
the ceiling rather than a floor, so it carries different per-level answers for
the same radii.

```
top=1147  windows=17  radii=32   15_9 s1
```

**544 radii -> 32.** That also removes a real risk: at 2683 the table would
have silently declined and fallen back on the biggest part, exactly the failure
the anisotropic stock-to-leave hit at 226 slots against 200 free.

Motion identical across 36 configurations, before and after.

## Two smaller notes

- `flake8`'s `F821` caught the ceiling being wrong before any run: I reached
  for `top` in the table builder where it was not in scope, which would have
  been the RAW `_pl_sect_top_dia` rather than the clamped one. `ladder_phases`
  owns both clamps and now supplies it.
- The lvl_floor probe had to REVERT the writes first. With `lvl_floor`
  overwritten there is nothing left to compare against - the instrument would
  have compared the table with itself and reported perfect agreement.

## Gates

```
36 configurations, emitted in 36, absent in 0
MOTION IDENTICAL - on equals off, everywhere
```

Suite green: twelve gates, `cam_map`, `test_lathe_validation`, flake8.

## Left

`lvl_floor` with `fl_i` and the loop termination, together. The decisions -
thin, blocked, out of band, split into intervals. The ramp and stop machinery.
The deletion pass.
