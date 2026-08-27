# 061 — The thin roughing pass at the boss top, and where it comes from

2026-08-21. `liveTooling`, on top of the uncommitted section-ceiling work.

## What was asked

greatEndian: *"there is tangential top boss point pass which is present across
any offset values.. which is wrong it should be present only if it depth is
equal or higher then 1/2 of depth of cut"*, on
`testing_15_6.xml`; and then, narrowing it: *"now position is at roughing 4th
from the outside envelope, but it is floating with increasting or decreasing
the prefinish offset"*.

## What was measured, before touching anything

`testing_15_6`, doc `#<_rough_cut>` = 0.5080 throughout, levels listed
outside-in, step = radius below the level above it.

| pre-finish offset | the level | step | × doc | position from envelope |
|---|---|---|---|---|
| 0.00 | X32.7160 | 0.4511 | 0.89 | 5th |
| 0.15 | X33.2080 | **0.1091** | **0.21** | 5th |
| 0.30 (default) | X33.2080 | 0.2591 | 0.51 | 5th |
| 0.60 | X33.7160 | **0.0511** | **0.10** | **4th** |
| 1.00 | X33.7160 | 0.4511 | 0.89 | 3rd |

Two facts fall out of the table. The pass **exists at every offset** — it is
structural, not a rounding accident. And its depth is **uncorrelated with the
offset**: 0.89, 0.21, 0.51, 0.10, 0.89 as the offset rises monotonically.

## Root cause

`poly_lathe_mill.ngc` builds **two ladders** when Sectioning is on:

- phase 1, stock → section ceiling, spaced EVENLY (`p1_step = span / p1_n`);
- phase 2, ceiling → floor, and with *Space passes from = Final contour*
  (`_pl_pass_from > 0`) it takes **whole depths of cut measured from the floor**
  and puts the leftover on its own first pass:
  `p2_first = span - p2_step * (p2_n - 1)`.

That first pass of phase 2 sits **on the section ceiling**, which the
uncommitted `lathe_sections.py` change now defines as
`ceiling(points) + level_allowance()` = the profile's highest point plus
`fin_off + prefin_off`. So it lands tangent to the boss top and removes only
the leftover.

The floating position and the uncorrelated depth are the same fact: the ceiling
moves **continuously** with the pre-finish offset while the phase-2 ladder is
anchored on the **floor**, so the remainder is `span mod doc` — anything from 0
to a full depth of cut, cycling as the offset sweeps.

**The unsectioned ladder does the same thing and is correct.** At `:236` the
remainder goes on the first pass *at the stock*, where it is a full-length cut
through oversize material; its own comment says the point is to avoid "a level
sitting just clear of the finished surface and grazing it for a sliver". Phase 2
inherited the trick into the one place where that is exactly what it produces.

## The fix

Spread, do not drop. Deleting the thin level leaves the one below it taking
`remainder + doc`, over the depth of cut and against the finished surface — the
invariant `test_x_continuity` exists to hold. Dividing the same span into the
same `p2_n` steps keeps every step under the depth of cut, still lands the last
one exactly on the floor, and cannot itself produce a thin pass: for `n >= 2`
the smallest even step is `doc/2` exactly. It is the anchoring the Stock branch
already uses, borrowed only for the case that would rub.

```
o<p2_thin> if [ABS[#<p2_first>] LT [0.5 * #<_rough_cut>]]
    #<p2_step>  = [[#<lad_tgt> - #<sect_top_r>] / #<p2_n>]
    #<p2_first> = #<p2_step>
o<p2_thin> endif
```

### After

| pre-finish offset | step | × doc | |
|---|---|---|---|
| 0.00 | 0.4511 | 0.89 | unchanged |
| 0.15 | 0.4920 | 0.97 | was 0.1091 / 0.21 |
| 0.30 | 0.2591 | 0.51 | unchanged — over the threshold, kept by the rule |
| 0.60 | 0.4897 | 0.96 | was 0.0511 / 0.10 |
| 1.00 | 0.4511 | 0.89 | unchanged |

Level-cut counts are unchanged in every column (44/44/44/43/41), so nothing was
dropped — the same passes are differently spaced. testing_15_6 at default
settings is **byte-identical** to before the change.

## A load-time abort found on the way

Nothing could be measured at first: 16 of 55 tests were failing with

```
Named parameter #<p1_cut> not defined
o<p1_end> if [[#<w_idx> LT 0] AND [#<_pl_sectioning> GT 0] AND [#<p1_cut> GT 0]]
```

`#<p1_cut> = 0` is assigned at `:723`, **inside** `o<lvl_ok>`; the new
`o<p1_end>` block from the uncommitted work reads it at `:1118`, **after**
`o<lvl_ok> endif`. A level that is out of band, thin, or past stock never enters
`lvl_ok`, and if that level sits on `lvl_floor` the read comes first. Fixed by
initialising it at the level-loop head, which is also what it means — it is a
per-level flag. Generation was never affected, only the run, which is why the
fault was invisible to anything that only builds the file.

## Why it was not caught earlier

- **The thin pass**: no gate measures a pass's DEPTH. `test_x_continuity`
  asserts no step is larger than a depth of cut — one-sided by design, because
  a small top remainder is legitimate on the unsectioned ladder. Nothing
  asserted a lower bound, so a 0.0511 mm pass reads as healthy.
- **`p1_cut`**: it needs a level to reach `lvl_floor` without entering
  `lvl_ok`, which no project in the suite hit until the ceiling started
  carrying the roughing allowance.

## What is still unknown

- **At the default 0.30 the pass survives at 0.51 × doc** — 0.2591 against a
  0.2540 threshold, over by 0.0051. That is the stated rule applied literally.
  If greatEndian still does not want that pass, the threshold is the dial, and
  it should be said as a number rather than nudged.
- **`n = 1` cannot be helped**: if phase 2 has room for a single pass and that
  pass is thin, it is also the floor and must exist. Not seen on any project
  measured.
- **`_pl_skip_thin` is inert on this project, and that is MEASURED, not
  inferred.** `test_ladder` sets `param_skip_thin = doc/2` — the very number
  greatEndian asked for — and asserts a level disappears. It now reports **18
  levels with the threshold against 18 without**. The likely mechanism is that
  `_pl_prev_lvl` resets to `stock_r` at the head of every window (`:620`), so
  the first level of a phase-2 window is measured against raw stock and always
  looks thick — but the mechanism is a hypothesis; the inertness is the
  measurement. Repairing it is not free: `lathe_level_pass.ngc:999` computes
  the retract from `_pl_prev_lvl`, so carrying the true previous level across a
  window boundary lowers the retract into a band that may still hold uncut
  stock. It needs its own analysis.

  **This is why the fix above is not obviously the right one.** The behaviour
  greatEndian asked for is already a shipped setting that DROPS the level;
  spreading keeps a pass there and moves every other level in the ladder. Both
  options are put to him with numbers rather than guessed at.
- Python-first debt: the decision is still made in O-code because `lad_tgt`
  comes from the runtime floor-stage machinery (`#[3380]`, `anch_floor`,
  clamps). Moving it is openPoints' "the ramp and stop machinery is still
  runtime O-code".


## Two faults the abort was hiding

Removing the `p1_cut` abort turned two passing tests red. Isolated by reverting
the ladder hunk and keeping only the `p1_cut` fix: **both fail identically with
the ladder change absent**, so neither is caused by it. Before the fix the
program died partway and both tests measured the truncated output.

- `test_behind_boss_ladder`, testing_15_6, `param_sectioning=0`: *the last pass
  still cuts 2.8021 mm, more than the 2.3247 step* — the ladder behind the boss
  is truncated, the same class as the fault fixed on 2026-08-12.
- `test_ladder`: the `skip_thin = doc/2` control drops nothing, 18 against 18.

**A test that passes on an aborted program is not passing.** Neither test
checks that the interpreter reached the end of the file; both take whatever
moves rs274 emitted before it stopped. That is worth fixing in the harness
before either fault is chased, or the next measurement is worth as little as
these two were.
