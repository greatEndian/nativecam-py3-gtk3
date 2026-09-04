# 098 — skip_thin predicted, and the last input derived

**Asked**: greatEndian, 2026-09-04 — *"okay then generate the flat Gcode from
python instead of filling the index level?"*, then *"go on with skip_thin"*.

## The idea, and why it is better than the table

greatEndian's: rather than emit a table the `.ngc` indexes, emit the **calls
themselves** as literal G-code. It needs **no parameter slots at all**, which
removes the blocker `analysis/097` measured - the index alone wanted 1088 of
the 1453 free slots, 8x the data it addressed.

It is also the only version that makes the `.ngc` genuinely SHRINK: with the
calls written out, the window / sub-span / level / interval loops stop
existing, rather than gaining another bypass.

The price is that with no loop there are no runtime decisions, so Python must
predict every one. This closes the last one.

## window_calls()

`skip_thin` cannot be a function of the ladder alone, which is why this
simulates a whole window rather than answering per level. `_pl_prev_thin` is
the surface immediately above the level being judged and it advances **only
where a level actually cuts** - so the thin test reads the cut history, the cut
history reads the blocked answer, and the blocked answer comes from the
interval walk. They have to be walked together, in order.

```
4542 levels compared, 0 disagreements
```

against the O-code's own `lvl_in_band` and `lvl_thin` flags, per window, fed
the same `prev_thin` the runtime started each window with.

## The order of the checks is not the obvious one

First run: **30 disagreements, every one at r=30.0000 - exactly `stock_r` -
with the O-code saying `thin` where Python said `stock`.**

`lvl_thin` is computed INDEPENDENTLY of the stock test: `o<lvl_ok>` requires
`band AND not-thin AND below-stock`, so a level sitting at the stock can carry
the thin flag as well. Testing stock first names 30 levels `stock` that the
runtime calls `thin`.

Both skip the level either way, so no motion depends on it - but the flat
G-code will carry the reason as a comment, and a generated program that says
`stock` where the machine's logic says `thin` is one you cannot trust when
reading it back. The order now matches the O-code.

## The last missing input

`e_z` / `l_z` were the one thing the tests took from an instrumented record
rather than deriving. `resolve_points` excludes the polyline's origin - the
record array does not store it either - so the raw pair is `points[0]` and
`points[-1]`, before the extension and the Z-limit clamp:

```
36 polylines compared, 0 disagreements
```

Emitted as `_pl_lad_ez` / `_pl_lad_lz`, read by nothing, motion identical.

## Every decision now has a Python predictor

```
windows 085   sub-spans 084   ladder 080/081   blocked 082
intervals 083/089   protected floors 094   handover 089   thin 098
```

`out of band` is the exception and cannot be proved here: `band=0` across the
whole sweep, so the rejection never fires on any test project.

## A third silent instrument

The thin probe reported `0 levels compared, 0 disagreements` and that reads
exactly like a pass. The window header was anchored on
`#<current_radius> = #<lvl_start>`, which the level-table wiring moved into an
`else` branch - so it only fired when the table is ABSENT, which is now never.
The same anchor mistake as `test_roughing_windows` in `analysis/091`.

Three instruments have now measured nothing and said so quietly in one
session: `#[...]` inside a `(debug,)` comment, an assert that fired before its
write, and this. **The probe now exits non-zero when it records nothing**, and
that should be the default everywhere.

## Left

The emitter and the `.ngc`. Gates: motion identical, plus a check that the
flat path is actually taken. And `band` stays unverifiable until a project with
split windows exists.
