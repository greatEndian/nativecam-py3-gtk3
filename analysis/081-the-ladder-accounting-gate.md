# 081 — gate two: the ladder invents nothing

**Asked**: greatEndian, 2026-09-03 — *"go"*, on the gate `analysis/080` said had
to come before the `.ngc` reads the Python ladder.

## Why gate one was not enough, in one sentence

`test_ladder_python` proves every level the program **cuts** lies on the
predicted ladder. That is one-way, and it is blind to a level the ladder
**invents**: nothing is cut there, so containment stays true no matter how much
extra the prediction carries.

The migration turns on the other direction. A ladder the `.ngc` walks would cut
whatever it holds.

## What gate two asserts

Per configuration, with one record per level out of an instrumented
`poly_lathe_mill`:

```
predicted = cut + thin + out-of-band + past-stock + blocked + unvisited
```

and the unvisited part must be a **tail** — past every visited level — never a
**hole**. A hole is exactly the shape a phantom takes: a level in the middle of
a run that the runtime never looked at.

## The instrument, and proving it inert

`lib/` in the repo is never touched. The whole tree is copied to a temp dir, one
`(debug, LVLREC ...)` line is inserted immediately above the `o<lvl_ok>` gate,
and the scratch config's `ncam/lib` symlink is repointed at the copy. The line
emits a `MESSAGE` canon call and no motion.

That is the claim, not the evidence, so the test checks it: the same program
flattened through a clean lib and through the instrumented one must be
**identical**, and the record must actually have fired. A probe that changes
what it measures has cost this project whole runs before.

The insertion is anchored on the gate's own text and **refuses to run** if it
matches other than exactly once, rather than instrumenting the wrong line.

## What it caught

**First run: 27 of 30 clean, 3 failed** — `testing_15_9` with Artificial
sectioning, all three directions, the same four levels:

```
hole = [33.4671, 33.9751, 34.4831, 34.9911]        0.508 apart, the depth of cut
```

`offrec` and `offcut` were both empty, so the arithmetic was right; the ladder
simply held four levels nobody visits. They sit on a **different grid** from the
windows' own (34.4941, 33.9882, …), so they were pure invention.

The cause is written in the O-code in words, `poly_lathe_mill.ngc:587`:

> *Artificial - `_pl_sect_mode` 1 - has no violet/ceiling phase at all - every
> window gets the full roughing depth, sequentially, so `w_idx` starts straight
> at the first window instead of at -1.*

`roughing_ladder` emitted a phase-1 ceiling pass regardless of mode. One line:

```python
if sect_mode != 1 and abs(top - start_r) > EPS:
```

**After: 0 of 30.** `pred` 819 → 807 — exactly the twelve phantoms, 4 levels ×
3 directions — while `cut` stayed at **744**. The fix removed only invention.

## Numbers

```
30 configurations
pred=807  cut=744  thin=18  band=0  stock=6  blocked=24  unvis=0
0 configurations with an unexplained level
```

`band=0` across the whole sweep is worth noting: the out-of-band rejection never
fires on these five projects, so that path is **carried but untested here**. It
is not evidence the rule is dead - it needs a project with split windows.

## What is STILL not proved

Which levels get skipped is read out of the record, not predicted. Python knows
the level SET; the runtime still owns the decisions.

And one of them cannot move without the other: **`skip_thin` cannot go to Python
ahead of the stop scan.** `_pl_prev_thin` advances only where a level actually
cuts (`poly_lathe_mill.ngc:1089` and `:1178`), so the thin decision reads cut
history, which reads the blocked decision. That is a real ordering constraint on
the migration, found by reading for this gate rather than by guessing at it.

## Gates

`test_ladder_account` (new), `test_ladder_python`, `test_ladder`,
`test_leftover`, `test_x_continuity`, `test_ramps`, `test_sections`,
`test_bidir_warn`, `cam_map`, flake8. Motion untouched: no `.ngc` or `cfg` was
edited, and the instrument is proved inert.
