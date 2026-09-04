# 097 — level_calls, and the last data/emitter split

**Asked**: greatEndian, 2026-09-04 — *"wire the interval table"*, then *"go on
with level_calls"*. These are its two prerequisites; the `.ngc` is untouched.

## The size question, settled against my own estimate

I said the interval table probably would not fit - "windows do not share
intervals the way they share ladders, roughly 2200 slots against 1450 free".
Measured:

```
raw=1110   deduped=68   calls=555   15_9 s1
```

**Raw fits, and deduped it is 68** - a 16x reduction, because Artificial
windows repeat their (from, to) pairs far more than I assumed. The estimate was
a guess and the measurement contradicted it. The space objection is gone.

## floor_contour_data()

`build_floor_contour_gcode` computed the floor contour AND the resume envelope
inline and returned G-code text. The interval walk needs both as data, so the
computation is now `floor_contour_data()` returning `(env, renv, rough_dir)`
and the emitter calls it. Both tables still come from ONE `env`, which is what
stops them drifting - the emitter records what that cost when they did.

## level_calls()

The whole interval walk as a library function, and `test_level_intervals` now
CALLS it instead of carrying its own copy. Same proof, one implementation:

```
36 configurations, 2731 interval walks, 765 multi-interval, 3496 calls
```

**Blocked calls are part of the sequence and must not be dropped.** They emit
no motion, so leaving them out looks free - but `o<p1_none>` fires exactly when
a call comes back blocked with nothing yet cut on the level, and that is the
phase-1 handover, which really fires and moves the ceiling 3.556 mm on
testing_15_blocked. A sequence of only the cutting intervals would silently
stop it happening.

## A false alarm I nearly reported

The split's identity check came back "all 36 differ". That was a **stale
baseline**: `before.txt` predated today's ladder head, region 2, the protected
flag, the dedupe and the termination change, every one of which legitimately
adds globals or tables to the generated file. Re-run against the file as it
stood immediately before the split:

```
IDENTICAL across all 36 - the split changed nothing
```

Had I not checked what that baseline predated, I would have reported a
regression that does not exist. A byte-identity gate is only as good as the
baseline's date.

## Left for the wiring itself

The emitter, and `poly_lathe_mill` reading the next (from, to) instead of
calling `lathe_level_next_start`. Gates: motion identical, and a separate check
that the table actually drives the walk rather than falling through - the one
that caught the near-miss on the termination change.
