# 083 — the interval walk, fully predicted in Python

**Asked**: greatEndian, 2026-09-03 — *"go on with the interval walk"*, the layer
`analysis/082` named as the last thing between the blocked replica and a
migration.

## Why there is a walk at all

A level behind a boss is not one pass. `lathe_level_pass` runs until the
profile rises above the level; `poly_lathe_mill` then asks
`lathe_level_next_start` where the level may resume, and calls again. That loop
is why the blocked gate saw **3373 calls** over 30 configurations holding only
807 levels.

```
l_fr = sg_from
loop:
    lathe_level_pass(... l_fr, lv_to)     -> _level_blocked, _pl_level_z_end
    search_from = l_fr    if blocked      (the sub returns before exporting an end)
                = z_end   otherwise
    found, z = resume answer(level, search_from, lv_to)
    if not found: break
    l_fr = z
```

## What is now in Python

Three pure functions, and **nothing in the toolpath reads any of them**:

- `resume_z(resume_env, level, search_from, w_to, mm)` — the answer
  `lathe_level_next_start` reports in `_pl_env_found` / `_pl_env_z`, which
  `poly_lathe_mill` takes whenever the resume envelope exists. A walk of the
  envelope table Python already emits, interpolated on the level, with two
  separate tests: genuinely past `search_from` by more than `resume_margin`,
  and inside the window. The margin is **0.01 x mm and not the 0.001 grazing
  epsilon** the level scans use - a different question. Without it the joint
  the previous pass ended on is re-detected as a new interval and the level
  never terminates.
- `level_stop_z(...)` — `_pl_level_z_end`: the crossing, clamped at the window
  end, where **the window end carries the nose term and the crossing does
  not**.
- `_level_scan(...)` — the shared body, so `level_blocked` and `level_stop_z`
  cannot drift apart. `level_blocked`'s signature and behaviour are unchanged.

## The gate

`test_level_intervals`. For every level, the **entire** sequence of calls is
predicted - each interval's start, and where the sequence ends. Not a spot
check on one continuation: the whole chain, and it has to stop where the O-code
stopped.

```
30 configurations, 2656 interval walks, 717 of them multi-interval, 3373 calls
```

## The measurement that changed the plan

z_end is refined against the stop contour with a tool-reach clamp
(`lathe_level_pass.ngc:904`) after the plain crossing gives a first value, and
I did not want to replicate that blind. So the walk was **first proved with
z_end fed back in from the record**, and the refinement measured:

```
the plain crossing already gives z_end on 1854 of 1854 cutting calls
the stop contour and reach clamp move the other 0
```

Exact on all five projects - so the observation could be dropped and z_end
predicted too. **The test now takes nothing from the record**: blocked, z_end
and every continuation are predicted, and the record is only what they are
judged against.

Measuring first is what made that safe. Guessing that the refinement was
inert would have been the same move as guessing it was not.

## Coverage, stated rather than implied

- The stop-contour refinement **never fires on these five projects**. It is
  carried in the O-code for cases that do - the comment at
  `lathe_level_pass.ngc:895` records testing_15_2 with the axial allowance at
  2.000, which this sweep does not set. The summary line still prints the
  count, so a project that exercises it shows up as a disagreement rather than
  as silence.
- 717 of 2656 walks are multi-interval, so the continuation is genuinely
  exercised and not merely defaulted past. A check asserts that rather than
  hoping.
- A negative control asks `resume_z` the same question from the window end and
  requires the answer to change.

## What is left before the .ngc can read any of it

The **sub-span walk**: `sg_from` / `sg_to`, which come from the split table at
`#3160` and the `o<wh_seg>` loop above the interval walk. That decides where
each interval walk BEGINS. Everything inside it is now predicted.

And the ordering `analysis/081` recorded still holds: `skip_thin` reads
`_pl_prev_thin`, which advances only where a level actually cuts - so it comes
after this, not before.

## Gates

`test_level_intervals` (new), `test_level_blocked`, `test_ladder_account`,
`test_ladder_python`, `test_ladder`, `test_leftover`, `test_x_continuity`,
`test_ramps`, `test_sections`, `test_bidir_warn`, `cam_map`, flake8. Motion
untouched: no `.ngc` or `cfg` edited, and the instrument is proved inert.
