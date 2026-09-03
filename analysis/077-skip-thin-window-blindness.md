# 077 — the thin check now measures thickness, and is still masked

**Asked**: greatEndian, 2026-09-03 — *"fix the window boundary blindness"*.

## The fault

`_pl_prev_lvl` is reset to `stock_r` at the start of every phase-2 window, and
the thin check measured against it. So the first level of a window was judged
**4.6 mm thick** when its real gap to the surface above is a fraction of a
millimetre — the check was blind in exactly the place thin passes come from.

## The fix, and why it is a separation rather than a change

`_pl_prev_lvl` has two callers asking different questions:

- **the retract** wants "a radius already cut, safe to move at" — and `stock_r`
  is the honest answer at a window start, because nothing has been cut in THIS
  window yet;
- **the thin check** wants "the surface immediately above this level", which is
  what decides how much metal it would actually remove.

So `_pl_prev_thin` is new and carries the second meaning. At a phase-2 window
start it is the **section ceiling**: phase 1 has already taken the bar down to
it over this window, so that is the surface above the first level. Unsectioned,
and on phase 1 itself, nothing is above but the bar and `stock_r` is right.
`lvl_floor` is the discriminator — phase 1 aims at the ceiling, a phase-2
window aims at `step_target`.

Both post-cut sites update it alongside `_pl_prev_lvl`.

## IT CHANGES NOTHING TODAY, and here is why

**The reported 0.2591 gap no longer exists.** On testing_15_6 as saved every
step is 0.5080 and nothing is under 0.35 — the phase-2 spread greatEndian ruled
removed those ceiling passes structurally, exactly as `openPoints` predicted
when it lowered this item's priority.

So I went looking for a case that still exercises it, and **Artificial
sectioning produces one**: `sec_len` 3, 5, 8 or 12 gives a **0.0387 mm** step on
testing_15_6 and **0.0903 mm** on testing_15_5. Genuine thin passes.

**And the pass is still not skipped** — 30 levels either way, at any threshold.
Not because the check is still blind: it now sees the 0.0387. It is the GAP
RULE from `analysis/076` refusing, and correctly by its own terms — skipping a
level 0.0387 below the ceiling leaves the next one cutting **0.5467 against a
0.5080 depth of cut**.

So the two fixes meet head on. The thickness reference is right; the safety
rule then declines to act on it.

Motion is byte-identical on testing_15_9, _15_2 and _15_5 in all three
directions, so the separation ships as a no-op.

## THE 0.0387 IS A FLOOR, AND THE QUESTION BELOW WAS WRONG

Checked afterwards, and it overturns what this file first concluded.

The thin step is not near the ceiling at all - it is at **index 27 of 29**,
near the bottom - and it lands EXACTLY on a floor stage:

```
floor stages:  21.0160   20.0160
last radii:  ... 21.5528   21.0547   21.0160   20.5160
                             |- 0.0387 -|
```

That 0.0387 pass IS the region's roughing floor, the surface roughing has to
leave for the pre-finish pass. `fl_prot` already protects it - "each of those
is a real region's floor and must never be skipped either" - and the guard
works: with the gap rule from `analysis/076` fully neutralised, the 21.0160
level is still there. So it is not the safety rule keeping it, and skipping it
would not be a trade against chatter. **It would leave a region's floor uncut.**

So the ladder is not leaving a stray remainder. It is landing on a floor it is
required to land on, and the short step before it is the cost of doing that -
`floor_ladder` re-anchoring per region, which greatEndian asked for: *"floor
has to follow the profile per region"*.

Nothing to fix, and nothing to decide. The section below is kept because it is
what I believed before measuring, and because the reasoning in it - that a
tolerance would separate a 7.6% overshoot from a 98% one - may still be wanted
if a genuine thin non-floor pass ever appears.

## THE DECISION I THOUGHT THIS LEFT - withdrawn, see above

Skipping the ceiling pass overshoots the depth of cut by **0.0387 mm — 7.6%**.
Refusing it keeps a pass that removes 0.0387 mm, which is the scraping,
chattering cut `skip_thin` exists to remove.

A tolerance would let the first through and still refuse the second: the
uniform-ladder halving overshoots by 0.4991, an order of magnitude more. But
any tolerance is a chosen number, and this project already carries an open point
saying so — *"Two 'halves' are choices, not measurements"*. So it goes to
greatEndian rather than being picked here.

## Gates

`test_ladder`, `test_skip_thin_gap`, `test_x_continuity`, `test_leftover`,
`cam_map`, and the motion comparison above.

## Still unknown

- Whether the ceiling pass under Artificial sectioning is worth removing at the
  cost of a 7.6% overshoot. Unanswerable from geometry; it is a machining
  judgement about chatter against tool load.
- The 0.0387 and 0.0903 steps appear only with `sec_len` set. Whether they are
  themselves a defect of the Artificial ladder - a remainder that should have
  been spread like phase 2's - has not been looked at, and would remove the
  question rather than answer it.
