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

---

## Addendum, 2026-08-06 — the sliver defeats "Space passes from = Final contour"

greatEndian, `photo/spacingFromIssue_0.png`: *"one pass offsetted right then
second one from contour is very near to first and other ones is counting from
this second one .. It has to behave differently as offset all passes from first
one nearest to contour"*.

The description is exact. Measured on testing_15_2 with `param_pass_from = 1`
(Final contour) and `param_sectioning = 1`, both read from the project file:

```
Sectioning ON    19 levels   stock 30.0000 -> 29.8894  gap 0.1106
                 29.8894 ... 21.2534        17 gaps of 0.5080
                 21.2534 -> 21.0160         gap 0.2374   <- the sliver
Sectioning OFF   18 levels   29.6520 ... 21.0160, every gap 0.5080,
                 remainder 0.3480 at the stock
```

**This is not the by-design behaviour recorded above.** That entry covers the
ladder being anchored on the section ceiling and sitting 0.2374 further out —
accepted. What is NOT acceptable is the consequence at the other end: the
remainder lands **at the contour**, leaving a level grazing the finished
surface for a sliver, which is the precise thing the Final-contour option
exists to prevent and says so in its own comment. Sectioning off, the same
option behaves exactly as greatEndian asks.

### Attempted fix, reverted

Giving **each window its own ladder**, derived from its own start and floor.
It is worse, and the measurement says so immediately:

```
Final contour  20 levels  gaps 0.2374 0.2706 0.2374 0.5080 ...
Stock          28 levels  gaps 0.5009 0.0062 0.5013 0.0058 ...
```

Near-duplicate levels 0.006 apart. **The windows must SHARE one ladder** -
there are eight of them (phase 1 plus seven sections) with different starts,
so per-window derivation makes their levels miss each other. Reverted; the
tree is back to 19 levels with the sliver.

### The fix that follows from that failure

One global ladder, anchored on the floor as it already is, and **phase 2 must
start ON one of its levels**. Today it starts at `sect_top_r` (or
`sect_top_r + cut_step`), and the section ceiling is not a ladder level -
29.8894 against a grid of 21.0160 + k*0.508. Snapping `sect_top_r` to the
nearest ladder level at or above the ceiling puts phase 2 on the grid, and the
last level then lands exactly on the floor with the remainder back at the
stock where the option promises it.

Acceptance: Final contour + Sectioning gives every gap 0.5080 with the
remainder at the stock; Stock anchoring keeps even gaps; `test_rough_comp`,
`test_leads` and `check_tangent` unchanged.

### Fixed — two ladders, 2026-08-06

greatEndian: *"there have to be two different ladders.. one from stock and
second for Final Contour"*. That is the design, and it is what the failed
per-window attempt was groping at: the split is by PHASE, not by window.

- **Phase 1**, stock → section ceiling: nothing in that range is near the
  finished surface, so it is spaced evenly and ends exactly on the ceiling.
- **Phase 2**, ceiling → floor: whole depths of cut from the floor outward,
  remainder on its own first pass. Computed once and shared by all seven
  section windows, so their levels line up.

One further correction was needed: the `p2_front` branch started a window at
`ceiling + cut_step`, which is between grid levels once the remainder lives on
the first step. It now starts at `ceiling + first_step` - the first grid level -
and spends the remainder there, so every later step is a whole one.

```
                 before                              after
Final contour    17 x 0.5080 then 0.2374 AT THE      0.2374 at the top, then
                 CONTOUR                             17 x 0.5080, deepest 21.0160
Stock            18 x 0.4862 then 0.3756             0.5071 throughout
```

`test_ladder.py` asserts both promises and fails without the fix on both.
`test_rough_comp`, `test_leads`, `test_sections`, `test_rough_overlay`,
`test_lathe_validation` pass; `check_tangent` min |dot| 1.00000.
