# 076 — a skipped thin pass may not open a gap past the depth of cut

**Asked**: greatEndian, 2026-09-03 — *"go on with skip_thin"*.

## The fault, reproduced exactly

`_pl_prev_lvl` does not advance when a level is skipped, so the NEXT level is
two steps from the last one actually cut. With a threshold above the ladder step
that alternates — thin, skip, keep, thin, skip, keep — and every kept level
lands two steps below its predecessor.

testing_15_2, doc 0.5080, before:

| threshold | levels | worst gap |
|---|---|---|
| 0.0000 | 18 | 0.4992 |
| 0.2540 | 18 | 0.4992 |
| **0.5070** | **13** | **0.9983** |
| 0.6000 | 13 | 0.9983 |
| 0.9000 | 13 | 0.9983 |

13 levels and 0.9983 is exactly what `openPoints.md` recorded, to four decimals,
so this is the same fault and the same measurement — not a lookalike.

**A gap past the depth of cut against a part surface is the failure
`test_x_continuity` exists to prevent.** And 0.5070 is UNDER the 0.5080 depth of
cut, which is the part that makes it dangerous: the setting looks conservative
and halves the ladder anyway.

## Why clamping the parameter cannot fix it

The number that matters is the **ladder step**, worked out at runtime, and it can
be under the depth of cut — 0.4991 here, once phase 2's spread made the ladder
uniform. So no maximum typed into `cfg/lathe/polyline.cfg` is safe on every
part. The skip itself has to refuse, because it is the only place that knows
both the step and what was last cut.

## The fix

One condition: a level is skipped only if the level that would FOLLOW it still
sits within one depth of cut of the last level actually cut.

```
#<thin_nxt> = [#<current_radius> + #<first_step>]
... skip only when ABS[#<thin_nxt> - #<_pl_prev_lvl>] LE #<_rough_cut> + eps
```

`first_step` and not `cut_step`: the advance about to be used differs from the
nominal one on the first level after an anchor, and taking `cut_step` there
would misjudge exactly the level the anchoring exists to place.

After: **18 levels and a 0.4992 worst gap at every threshold from 0 to 0.9.**

## IT IS NOT INERT, and I checked because I expected it might be

Every demo project has a uniform ladder — no step below 0.4962, no thin step
anywhere — so on those the refusal means nothing is ever skipped. That is the
spread doing its job structurally, as `openPoints` predicted when greatEndian
ruled it.

But `testing_15_5` carries `skip_thin` at **0.3 mm** in the saved project, and
there the skip WAS firing and WAS opening a gap. The refusal gives that level
back: **458 → 464 moves** front to back, 426 → 432 and 444 → 446 in the other
directions. So the setting still acts on a real project; it just no longer acts
destructively.

## A CONTROL THAT WAS ASSERTING THE BUG

`test_ladder` required that *"a threshold above the thinnest gap DOES drop a
level"*. On a uniform ladder — which the spread makes by construction — dropping
any level necessarily opens a 0.9983 gap. So that assertion demanded the fault.

Its own comment already conceded this: *"That is a real fault in `_pl_skip_thin`
and it is written up in openPoints; it is not this control's job to assert it
away."* It tried to dodge by calibrating to `thinnest + 0.02` capped under the
doc — 0.5070 — but on a uniform ladder every effective threshold triggers the
halving, so the dodge did not work.

Inverted, not waived: it now asserts the ladder stays whole and opens no gap
past the doc. **On the build before the refusal the same threshold gave 13
levels, so the new assertion fails there just as loudly** — it discriminates in
the same place, for the opposite outcome.

## Two pinned expectations moved, and why that is legitimate

`test_air_leads` and `test_z_limits` both pin testing_15_5 figures and both
failed. That is the recovered level, not drift: 57 cutting leads → 58,
roughing feed 1144.4 → 1215.6 mm, motion `128ebb273ba5`/458 → `d5ba90092f17`/464.
Updated with the reason written beside them.

## Gates

`test_ladder`, `test_x_continuity`, `test_skip_short`, `test_leftover`,
`test_sections`, `test_behind_boss_ladder`, `test_ramps`, `test_air_leads`,
`test_extension`, `test_z_limits`, `test_x_limits`, `cam_map`, and the new
**`test_skip_thin_gap`** — which sweeps the thresholds that provably failed
before and asserts both the gap bound and the level count.

## Still unknown

- **The window-boundary blindness is untouched** and is the other half of this
  entry. `_pl_prev_lvl` is reset to `stock_r` at the start of each phase-2
  window, so the first level of a window is judged 4.6 mm thick instead of its
  real 0.2591 — the check is blind exactly where thin passes come from. The fix
  is to separate the two uses of that global: a per-region thickness reference
  for the thin check, a safe-radius reference for the retract. Designed, not
  built, and it is now the only skip_thin fault left.
