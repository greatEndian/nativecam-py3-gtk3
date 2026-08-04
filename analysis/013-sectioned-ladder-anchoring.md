# 013 — Why the roughing ladder shifts out in X when Sectioning is on

2026-08-04, branch `liveTooling`. greatEndian: *"why is the roughing passing
slightly shifted out in X axis if sectionning is on?"* — asked twice, because
the first answer was guesswork. This one is instrumented.

**Resolution: by design.** greatEndian, after seeing the numbers: *"with
sectionning its a separated sections and it has own rules"*. No change made.

## Measured

`(DEBUG, ...)` emitted at the top of the level loop in `poly_lathe_mill.ngc`,
read out of the rs274 canon, testing_15_2, Native:

```
sect OFF   widx=-1   start=30.0000  floor=21.0160  first=-0.348  step=-0.508  passes=18
sect ON    widx=-1   start=30.0000  floor=29.8894  first=-0.348  step=-0.508
           widx=0    start=29.3814  floor=21.0160  first=-0.508  step=-0.508
           widx=1..6 start=29.3814 / 29.8894, floor=21.0160, first=-0.508
```

Resulting ladders:

| | levels | top | bottom two steps |
|---|---|---|---|
| sect OFF | 18 | 29.6520 | 0.5080, 0.5080 |
| sect ON | 19 | 29.8894 | 0.5080, **0.2374** |
| sect OFF, pass_from=Stock | 19 | 29.5138 | 0.4862, 0.4862 |

Three distinct patterns — Sectioning is not equivalent to either anchoring
mode, which is what made it look like a fault.

## Mechanism

Sectioning splits roughing into two phases with **separate ranges**:

- **Phase 1** (`w_idx = -1`, the "violet" pass): stock → `sect_top_r`, the
  section ceiling, here **29.8894**. Its `first_step` of −0.348 overshoots that
  floor immediately (30.0 − 0.348 = 29.652, already past 29.8894), so the
  `if_done` clamp pulls it back and phase 1 cuts a **single** level, at the
  ceiling.
- **Phase 2** (`w_idx = 0…6`, one window per section): restarts at
  `sect_top_r`, or one step below it via the `p2_front` branch, with
  `first = −0.508` — a full step. Its ladder is anchored on the section
  ceiling, and 29.3814 → 21.0160 is 16.47 steps of 0.508, so the floor clamp
  leaves a **0.2374** remainder on the last level.

So the whole ladder sits 0.2374 further out, and the remainder that
*Space passes from = Final contour* intends for the first cut through oversize
stock is consumed by the phase-1/phase-2 split instead.

Accepted consequences: first cut off the stock **0.1106** (a skim), last cut
**0.2374** (a sliver just above the pre-finish). Unsectioned, Final-contour
anchoring puts 0.3480 on the first cut and lands the last level exactly on
21.0160.

## Two things this cost, worth not repeating

- **A wrong answer given first.** I claimed Python emits no section table
  because the profile contains arcs, and that only phase 1 could run. The
  generated file carries `_pl_sect_count = 7`. Reading branch conditions is
  not measuring which branch runs.
- **A wrong hypothesis before that**: that Sectioning was behaving as
  `pass_from = Stock`. Generating with that setting produced a *third* ladder
  (19 levels, top 29.5138, even 0.4862 steps), refuting it in one command.

`(DEBUG, ...)` lines survive into the canon as `MESSAGE(...)` and are the
cheap way to settle any "which branch ran, with what numbers" question in this
codebase. Nothing else in this session answered it.
