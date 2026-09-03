# 087 — the 27-vs-6 gap: my counter was wrong, and the condition is simple

**Asked**: greatEndian, 2026-09-03 — *"chase the 27 vs 6 gap"*, from
`analysis/086`: 27 configurations appeared to run a ceiling phase while only 6
handed over.

## There were never 27

```
unsectioned 15, Artificial 3, Natural 12; handed over 6
```

`test_roughing_windows` counted ceiling phases as `w_idx < 0`. **The
unsectioned single window carries index -1 too** - `poly_lathe_mill` initialises
`w_idx` to -1 and the sectioning-off branch never touches it, and
`roughing_windows` reproduces that faithfully. So 27 = 15 unsectioned + 12
Natural, and 15 of them were never ceiling phases at all.

The index being shared is by design. Counting the two together is not, and an
overstated coverage number is exactly the kind of thing that quietly justifies
a wrong conclusion later. The check is now split in two - a Natural ceiling
phase and an unsectioned single window are each asserted separately - and the
corrected run reports **12 and 15**, agreeing with the independent probe.

## The real gap, 12 vs 6, and its condition

```
proj   sect dir     kind     ceiling   start      p1 end
15_2   1    0/1/2   natural  30.0000   30.0000    cut=0
15_4   1    0/1/2   natural  30.0000   30.0000    cut=0
15_5   1    0/1/2   natural  33.4211   35.0000    cut=1
15_6   1    0/1/2   natural  33.4671   35.0000    cut=1
15_9   1    0/1/2   artif    -         -          never reached
```

**The ceiling equals the start radius on 15_2 and 15_4.** 30.0000 against
30.0000: phase 1 has zero depth, cuts nothing, `p1_cut` is 0, and the handover
does not fire. On 15_5 and 15_6 the ceiling sits below the start, phase 1 has
real depth, cuts, and hands over. A clean 6/6 split on one comparison.

The handover site is **reached in all 12** - `cut=0` is printed, not "never
reached" - so there is no hidden alternate exit from phase 1 to account for.

## What that does to the migration boundary

`sect_top_r` against `start_radius` is a **generation-time** comparison;
`roughing_ladder` already clamps `top` into exactly that band. And the value
the handover stores, `_pl_ph1_z_end`, is `_pl_level_z_end`, which
`level_stop_z` predicts exactly - 1854 of 1854 (`analysis/083`).

So the last runtime dependency looks reducible to generation time. With `086`
already showing the three `sect_top_r` mutation sites never fire, what remains
of the handover is one flag and one Z, both apparently predictable.

## The caveat, stated because it is the whole risk

`p1_cut = 0` coincides with **zero depth** in every one of these twelve. A part
where phase 1 has depth but is blocked everywhere would separate "has depth"
from "cut something", and no project in the sweep does that. The rule is proved
on these twelve; it is not proved in general, and a project of that shape is
what would settle it.

## Gates

`test_roughing_windows` re-run with the corrected counters: 30 configurations,
179 windows, 152 banded, 12 Natural ceiling phases, 15 unsectioned single
windows, all predictions matching. No `.ngc`, `cfg` or generation code changed.
