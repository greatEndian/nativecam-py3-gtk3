# 094 — fl_prot becomes a per-level flag, and two claims corrected

**Asked**: greatEndian, 2026-09-03 — *"go on with lvl_floor/fl_prot"*.

## What moved, and what did not

`fl_prot` has exactly one consumer: `skip_thin`'s guard that a protected floor
may never be dropped (`poly_lathe_mill:928`). The runtime tracked it by walking
the floor stages as the ladder reached them - but **the level table already
encodes that walk**, so the answer can be emitted per level instead of
rediscovered.

`protected_flags()` produces it and the table carries a flag beside every
radius. Without the table the runtime tracks `fl_prot` exactly as before.

**`lvl_floor` did NOT move.** It is not only the protected floor - it is the
loop-end test (`current_radius EQ lvl_floor`), the `if_done` clamps, the
thin-reference discriminator and the stage advance's own target. Moving it
means moving the loop's termination, which is a different and larger change.
Said plainly rather than counted as done.

## Two of my own claims corrected by the measurement

**1. The probe reported 0 levels and I nearly read that as "the table is
inert".** It was the instrument: `#[...]` computed indexing inside a
`(debug,...)` comment does not expand, the interpreter errored, and my script
skipped every configuration silently. Assigning the index into a variable
first, and PRINTING `tp.error` instead of swallowing it, gave:

```
4542 levels driven by the table, 260 flagged protected, 0 disagreements
132 levels on the fallback path - the table stood down there
```

So the level table of `analysis/091` **is** genuinely driving - that gate was
not vacuous - and this one is not either.

**2. `analysis/091` said the fallback path is exercised by no configuration.
That is wrong.** `testing_15_blocked` sectioned trips the phase-1 handover,
`lvl_tbl` clears, and **132 levels run the original computation**. The fallback
has real coverage, in the good direction.

## Why the flag check was worth running at all

Motion-identical only proves the two guards agree *where the outcome would
change*. A disagreement at a level that is not thin anyway is invisible to it
and would bite on another part. This compares them **level for level, all
4542**, and fails if zero levels come back flagged - the vacuous-pass trap that
made thirty configurations report green over zero answers earlier in this
session.

## Gates

```
36 configurations, emitted in 36, absent in 0
MOTION IDENTICAL - on equals off, everywhere
4542 levels compared, 0 disagreements, 260 protected
```

Suite green: twelve gates, `cam_map`, `test_lathe_validation`, flake8.

## Left

`lvl_floor` itself, the decisions (thin, blocked, out of band, split into
intervals), the ramp and stop machinery, and the deletion pass once this has
cut on the machine.
