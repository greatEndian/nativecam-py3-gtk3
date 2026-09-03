# 091 — the ladder wired in: the .ngc reads its levels

**Asked**: greatEndian, 2026-09-03 — *"go on with step 2"*.

**This is the first change in the whole arc that can move metal.** Everything
before it was prediction with nothing wired.

## What changed

`lathe_sections.build_level_table_gcode()` emits the roughing levels per
window into the free `#1000-2600` block, and `poly_lathe_mill` reads the next
radius instead of working the ladder out again. Four sites move the level and
all four now consult the table:

- the per-window start, which also looks the window's run up by index
- the advance
- the two floor clamps, left exactly as they were - with a correct table they
  are no-ops, and they stay as the safety net

`first_step` is still maintained, and deliberately: `skip_thin` reads it to
work out where the ladder would go if a level were dropped, so the table sets
it to the REAL next step rather than the nominal one.

## The nominal ladder, and the guard that makes that safe

The table is the **nominal** ladder. Where phase 1 is blocked from its own
window start with nothing cut, `poly_lathe_mill` reassigns `sect_top_r` and
every later window starts somewhere the table does not know about
(`analysis/088`). `phase1_stop` predicts that and is proved - but on 36
configurations, not universally, and **a table built on a wrong ceiling would
cut a wrong ladder in metal**.

So the three sites that reassign the ceiling clear `#<lvl_tbl>`, and the
subroutine falls back to the computation it has always had. The guard sits
exactly where the feedback happens rather than trying to anticipate it.

Predicting the handover into the table is a later step, with its own evidence.

## The acceptance gate

Not the suite. The same generated program with **one number changed** -
`_pl_lvl_n` forced to 0, which disarms the table and nothing else - flattened
and compared:

```
36 configurations, table emitted in 36, absent in 0
MOTION IDENTICAL - table on equals table off, everywhere
```

Same program, same subroutines, one flag. Any divergence would have meant the
table walks a different ladder from the code it replaces.

Suite green as well - twelve gates, `cam_map`, `test_lathe_validation`, flake8.

## Two things caught on the way

1. **`#<_pl_cut_rev> = 0` appears twice** - the setup at :311 and the reset
   before the contour passes at :1321. The anchor assert fired before anything
   was written, so the file was untouched; re-anchored on the unique line
   above it.
2. **`test_roughing_windows` broke on its own instrument.** Its per-window
   record was anchored on `#<current_radius> = #<lvl_start>`, which the wiring
   pushed into an `else` branch - so it fired only when the table is absent,
   which is now never. Re-anchored on the table lookup, which runs
   unconditionally once per window. Caught by *"the unsectioned single window
   is exercised"*, the coverage check added after the 27-vs-6 conflation
   (`analysis/087`): without it the instrument would have recorded fewer
   windows and the test would have passed on a partial sweep.

## Compatibility

`_pl_lvl_n = 0` in `create_defaults` means an older saved project - or any
profile this cannot describe - takes exactly the ladder it always took.
`polyline.cfg` 1.72 -> 1.73 so saved projects migrate and pick the new
`<exec>` up.

## What has NOT moved out of the O-code

The ladder's SEQUENCE is Python's now. The subroutine still computes
`dirsign`, `step_target`, the two step sizes, `lvl_floor` and `fl_prot`, and
still owns every decision about what a level DOES - thin, blocked, out of
band, split into intervals. Those are the next candidates, and each needs the
same treatment: proved first, wired second, gated on identical motion.

## Untested still

Unchanged from `analysis/089`: `sect_top_r` sites 2 and 3 remain at 0 fires,
`band=0` across the sweep, and the stop-contour reach clamp moves `z_end` on 0
of 1902 cutting calls. And the fallback path itself is now exercised by no
configuration in the sweep - the table is emitted in all 36 - so it is proved
only by the table-off half of the gate.
