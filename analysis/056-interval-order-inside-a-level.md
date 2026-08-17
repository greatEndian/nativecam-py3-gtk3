# 056 — Interval order inside one level, measured

Follow-up to `analysis/054` and `055`, which both left this open with the note
*"interval order inside one level is still front-first where a boss splits it —
3 levels of 45 on testing_15_6"*. That was recorded from a glance, not a
measurement. This is the measurement, and it sharpens the finding in three
ways.

## What was asked

Whether the last remaining ordering gap in back-to-front roughing is worth
closing, and what closing it would cost.

## What was measured

testing_15_6, sectioning ON, both directions, intervals grouped per level in
**emission order**:

```
f2b 45 cuts over 28 levels | b2f 45 cuts over 28 levels
levels with more than one interval:  f2b 16,  b2f 16
```

**16 of 28 levels carry more than one interval**, not 3. Of those 16, **13
already reverse correctly**:

```
X32.5805
   f2b  [0.00->-26.35] [-41.81->-68.89]   emission slots 8, 32
   b2f  [-68.89->-41.81] [-26.35->0.00]   emission slots 8, 21
```

The back interval is emitted first, and each interval travels back to front.
That is right.

Only **3 passes of 45** are wrong — the top three levels:

```
X33.5965
   f2b  [0.00->-28.96] [-37.41->-68.89]   emission slots 4, 5
   b2f  [-28.96->0.00] [-68.89->-37.41]   emission slots 4, 5
```

Each interval still travels the correct way (`-28.96 -> 0.00` is toward the
front); it is the ORDER of the two intervals that is front-first.

## The root cause is legible in the emission slots

The two groups differ by exactly one thing:

| case | slots | who orders it |
|---|---|---|
| intervals in DIFFERENT windows | 8 and 21 — far apart | `_sections_back_to_front`, in Python — **correct** |
| intervals in the SAME window | 4 and 5 — adjacent | the runtime scan in `poly_lathe_mill`, sequentially — **front-first** |

`_sections_back_to_front` re-orders the `#3401+` window table at generation
time, so any level whose intervals belong to separate windows is reversed for
free. A level ABOVE the point where the part splits into bands has both its
intervals inside one window, and the interval walk
(`poly_lathe_mill.ngc` ~690–810) discovers them sequentially — cut to a block
point, `lathe_level_next_start`, repeat — so nothing knows the full list before
emitting any of it. Python is never handed two things to order.

That is also why the earlier note said "needs a dry-run or a scratch array".

## What it costs today: nothing measurable

- **Metal**: none. The cut SET is identical between directions — 45 cuts, 44
  distinct, 44 shared, 0 unique to either — proved in `054` and re-proved after
  `055`.
- **Time**: back to front is already the CHEAPER of the two. Rapid travel over
  the whole operation:

```
f2b  150 rapids, 1914.8 mm
b2f  146 rapids, 1888.7 mm
```

  Fewer rapids and 26.1 mm less travel, with the 3 front-first levels included.

## What closing it would cost

Two routes, both real work:

1. **Make those intervals their own windows** so the existing Python reorder
   catches them. Touches `band_windows`/`_sections_back_to_front` and therefore
   the window table every roughing scan walks.
2. **Give `poly_lathe_mill` a dry-run or scratch array** so the interval list is
   known before emission. That is new runtime machinery in the file the standing
   rule wants to shrink.

Either is surgery at the choke point `analysis/032`'s five stacked faults came
from, and `054`'s own gate had to prove byte-identical front-to-back output
across 39 projects to be trusted. For 3 passes of 45, with no metal difference
and no time saved, that is a poor trade.

## Recommendation

**Leave it, unless greatEndian sees it in the preview and wants the order
consistent for its own sake.** It is a consistency gap, not a machining defect,
and the cheap half of it — 13 of the 16 multi-interval levels — is already
right.

## What is still unknown

- Whether it is visible enough in the preview to matter to the operator. That
  is greatEndian's eye, not a number.
- Whether route 1 would disturb the window table's other consumers. Not
  investigated, because the recommendation is not to do it yet.

## Why the earlier note was imprecise

`054` recorded "3 levels of 45" from the symptom without counting how many
multi-interval levels there were in total, so it read as "the interval order is
unhandled" when in fact **13 of 16 are handled** and the residue has a specific,
narrow cause. Recorded here so the next person does not scope the big fix for
the small problem.
