# 057 — Interval order inside a level, fixed by giving each interval a window

2026-08-17, branch `liveTooling`, from `4b666ff`. Closes the last item
`analysis/054` and `055` left open and `056` measured.

## What was asked

greatEndian ruled: fix the interval order inside a level **by the
separate-windows route** — the Python-first one — not by a scratch array in
`poly_lathe_mill`. `056`'s recommendation had been to leave it; the ruling
overrode that.

The brief also named the crux the route had to survive: **intervals are
per-LEVEL, not per-BAND**. A window is `(z_from, z_to, r_lo, r_hi)` over a
whole radius band, but the boss is tapered, so the Z gap it opens moves with
the level — `-28.96..-37.41` at X33.5965 against `-27.48..-39.61` at X33.0885.
If the abstraction could not carry that, the answer was to say so.

## The crux dissolves: the gaps are NESTED

It carries it, and the reason is one line of geometry.

The gap a boss opens in a level is `{ z : profile(z) + allowance >= level }`.
Lower the level and that set can only GROW, so the gaps at every level below a
peak are nested around the peak's own Z. Measured, on testing_15_6:

```
X34.0636   gap -35.00 .. -31.21
X33.5965   gap -37.41 .. -28.96
X33.0885   gap -39.61 .. -27.48        peak (dome apex) at Z-32.50
```

Z-32.50 is inside all three. **One split point serves every level in the
band** — the split does not have to move with the level, only to sit at the
peak.

That fixes the split point. The band's TOP edge is the second half:

- a level at or below `peak_height + allowance` is blocked at the peak — the
  scan offsets the profile outward by `fin_off + prefin_off`, and a normal
  offset at a vertex is never nearer the profile than the radial one, so the
  offset apex is at least that high;
- a level ABOVE it may run straight through, and splitting the window there
  would cut it as two spans where it was one — which is exactly the cut SET
  the whole direction exists to preserve.

So each affected window keeps a full-span copy of itself over the band above
`peak_height + allowance`, and only the band below is split. On testing_15_6
that threshold is `32.6591 + 1.508 = 34.167` in radius, and the measurement
brackets it exactly: **X34.5318 is unblocked and cuts full length; X34.0636,
the next level down, is the first of the three that split.** The model was not
fitted to that — it predicted it.

## What was measured, before

Probe validated against `056` first: same 45 cuts, 44 distinct, 28 levels, 16
multi-interval, 13 back-first / 3 front-first, same emission slots.

```
testing_15_6 sectioning ON, back to front, BEFORE
   X34.0636   front [s01 -31.21->  0.00] [s02 -31.21->  0.00] [s03 -68.89->-35.00]
   X33.5965   front [s04 -28.96->  0.00] [s05 -68.89->-37.41]
   X33.0885   front [s06 -27.48->  0.00] [s07 -68.89->-39.61]
   X32.5805   BACK  [s08 -68.89->-41.81] [s21 -26.35->  0.00]
   ... 12 more, all BACK
   multi-interval levels: back-first 13, front-first 3
```

**Where the three actually came from — the diagnosis needed one correction.**
`056` put them in the topmost merged window; an instrumented run
(`(debug, ...)` on every `lathe_level_pass` call, read out of the canon dump)
shows the emission is:

```
w=-1  r=34.5318  from=0        -> cut 0 .. -68.892        phase 1
w=-1  r=34.0636  from=0        -> cut 0 .. -31.209        phase 1
w=-1  r=34.0636  from=-34.171  -> NO CUT                  phase 1 gives up
w=0   r=34.0636  from=0        -> cut 0 .. -31.209        window 0, a DUPLICATE
w=0   r=34.0636  from=-34.600  -> cut -35.000 .. -68.892
w=0   r=33.5965 ...                                       window 0
w=0   r=33.0885 ...                                       window 0
```

So six of the seven cuts are window 0's, as `056` said, and the seventh —
X34.0636's front interval — is emitted TWICE, once by phase 1 and once by
window 0. That duplicate is the "45 cuts, 44 distinct" arithmetic `054`
recorded, and its cause is now known; see *Found on the way* below.

## The fix

All of it in `lathe_sections.py`; **not one line of O-code changed**, and the
window table's format is untouched. `poly_lathe_mill` reads the same four
slots per window it has always read.

`_split_level_intervals()`, applied only in direction 1, after
`_sections_back_to_front`:

- for each window, take the section boundaries strictly inside its span that
  are **peaks** — material lower on both sides — and whose
  `boundary_height + allowance` is above the window's own band bottom;
- the sub-band top is the LOWEST such threshold, so every level in the
  sub-band is blocked at EVERY split point in it;
- emit the window unchanged over `(top, r_hi)`, then one piece per interval
  over `(r_lo, top)`, back-most piece first — the same "furthest from the
  profile's own first point" rule `_sections_back_to_front` uses.

Two supporting pieces:

- `level_allowance()` — `fin_off + prefin_off` in the diameter units the
  windows and `boundary_height` are carried in. This is `lvl_d` in
  `poly_lathe_mill`, and the RADIAL one: with *Separate Z offset* on the two
  differ, but the level scan is handed a single number (CALL args 13 and 25).
- `_boundary_list()` — every internal boundary with its height and whether it
  is a peak.

**The peak test is not `detect_sections`' own `min_x`.** That is taken over
the points a section RECEIVES, which on a straight rise is just its far end —
so a boss made of two plain tapers has the peak as its own minimum and would
be rejected. `_side_min` takes the minimum over the section's points
*excluding the boundary vertex*, which is the honest question: is there
material below this boundary on each side. Caught by the unit test, not by the
projects: testing_15_6's dome is an arc, so its intermediate points hid the
flaw. Fixing it added a split on testing_9 and changed nothing on the 15_x
family.

A non-peak boundary — a step, a flat-to-rise — is deliberately not split on.
It blocks a level just as well, but everything past it is above the level too,
so the level simply stops there and a piece behind it would cut nothing. Left
in, it produced 15 windows on testing_15_6 where 10 do the work.

### Why direction 1 only

Front to back has the same alternation and could be given the same treatment,
but the gate is byte-identical front-to-back output, and re-grouping its
emission is not byte-identical. The split is gated on the same test
`_sections_back_to_front` is.

## Measured, after

```
testing_15_6 sectioning ON, back to front, AFTER
   X34.0636   mixed [s01 -31.21->  0.00] [s02 -68.89->-35.00] [s05 -31.21->  0.00]
   X33.5965   BACK  [s03 -68.89->-37.41] [s06 -28.96->  0.00]
   X33.0885   BACK  [s04 -68.89->-39.61] [s07 -27.48->  0.00]
   ... 13 more, all BACK
   multi-interval levels: back-first 15, front-first 0
```

**Front-first: 3 → 0.** Fifteen of the sixteen are now strictly back-first.

The sixteenth, X34.0636, is `[phase 1 front][window back][window front]` —
its window pair IS reversed, and what is left in front of it is phase 1's own
cut, the duplicate. It cannot be made back-first without removing that
duplicate, and removing it changes front-to-back output. Reported as "mixed"
rather than dressed up as a pass: strictly, gate A1 is 15 of 16, not 16.

testing_15_5 behaves identically: front-first 3 → 0, 15 strictly back-first,
X33.1273 mixed for the same reason.

**testing_11, where the residue is plainer.** Generated from a worktree at
`4b666ff` for a true before, since the split changes its window table too
(28 lines):

```
before   16 multi-interval levels, back-first 14, front-first 2
after    16 multi-interval levels, back-first 15, front-first 1
```

The one left is X29.0000 with THREE intervals, all emitted by phase 1:

```
X29.0000  [s01 -14.27->0.00] [s02 -49.27->-16.22] [s03 -79.08->-51.22]
```

**Phase 1 is not window-driven** - `w_idx < 0`, one full-length pass over the
levels above the section ceiling, with its own multi-crossing loop - so no
window table can re-order it. Every window-driven multi-interval level in
every project measured is back-first; the residue in both shapes it takes
(15_6's duplicate, 11's three intervals) is phase 1's own handover level.
That is a separate, smaller fix and it belongs to whoever gives phase 1 a
window table.

## The gate

| # | item | result |
|---|---|---|
| A1 | the 3 front-first levels join the 13 | **15 of 16** strictly back-first, **front-first 0**; the 16th is the phase-1 duplicate level, window pair reversed. Every window-driven level is back-first; testing_11 14/2 → 15/1, its residue phase 1's own three intervals |
| A2 | front-to-back interval order unchanged | **PASS** — front-first everywhere, byte-identical output |
| B3 | cut SET identical between directions, testing_15_6 sect ON | **PASS** — 45 cuts, 44 distinct, 44 shared, 0 unique either way, 45/45 travelling back to front |
| B4 | front to back byte-identical to `4b666ff` | **PASS** — all **39** demo projects with stored settings, 0 lines differing, plus explicit f2b runs on 15_5/15_6/15_2 × sectioning off and ON |
| B5 | standing metal unchanged | **PASS** — 0.7219 / 0.8579 (15_5 off/ON), 0.6473 / 0.5681 (15_6 off/ON), identical in both directions |
| B6 | `test_x_continuity`, `test_leftover` in four combinations | **PASS** — x-continuity worst gap 0.0000 in all four, control fires; leftover green, control fires on 21 of 21 |
| B7 | overcut past the pre-finish contour, testing_15_2 | **PASS** — 0.0503 both directions, 110 roughing moves each (bound 0.08); `check_tangent` PASS, min \|dot\| 1.00000 |
| C | lint / maps / suites | flake8 clean both lists, `cam_map` 6/6, `test_lathe_validation` 40 calls, `test_all_projects` all green, `test_sections` green including the new checks |

Cut sets, every project, sectioning ON, both directions — the broad form of
B3:

```
testing_15_6  45/44 both, 0 unique   testing_15_5  47/46 both, 0 unique
testing_15_2  30/29 both, 0 unique   testing_15_4  29/29 both, 0 unique
testing_9     25/25 both, 0 unique
```

(15_6, 15_5, 15_2 and 15_4 reproduce `analysis/054`'s own table exactly.)

**Slot count, the resource the brief asked to measure first.** All 39 demo
projects, sectioning ON, both directions:

```
worst case 64 slots (16 windows) - testing_13_arc_first / testing_13_arcs,
                                    unchanged by the split
largest growth from the split      testing_11    16 -> 28 slots
                                   testing_9_x   12 -> 20 slots
                                   testing_15_x  32 -> 40 slots
                                   testing_9     32 -> 40 slots
of 200 slots (50 windows) at 3400-3600
```

Worst case is **32% of the table** and the split adds at most 8 slots to any
project measured. A guard refuses the split — keeping the unsplit list — if it
would ever overflow, since a truncated window table is metal left standing;
`test_sections` covers that branch.

**A bonus, measured with the probe validated against `056`'s own numbers**
(f2b 150 rapids / 1914.8 mm, b2f 146 / 1888.7 mm reproduced exactly):

```
back to front rapid travel  1888.7 -> 1877.9 mm, 146 rapids
```

10.8 mm less than before, 36.9 mm less than front to back. Grouping a level's
intervals by window instead of alternating across the boss travels slightly
less, so the change is not merely cosmetic.

## Found on the way — a duplicate roughing pass, PRE-EXISTING

`poly_lathe_mill.ngc` line ~715: when phase 1's continuation past an
obstruction comes back blocked, it takes the `blk_lvl_p1` branch, which sets
`_pl_ph1_front_cut = 0` — "nothing was cut at all so phase 2 must still do
this exact radius fresh". At the handover level that is not true: the FIRST
interval was cut, and only the continuation was blocked. Phase 2's window then
redoes the whole radius, so the front interval is cut twice, in air the second
time.

Measured on testing_15_6 sectioning ON: X34.0636, Z0 → -31.209, emitted twice,
with a full retract between. It is the whole of the "45 cuts, 44 distinct"
difference, and it is present in BOTH directions, unchanged by this work.

Not fixed here: removing it changes front-to-back output, which gate B4
forbids, and gating it to direction 1 would make the two directions emit
different numbers of cuts, which gate B3 forbids. Recorded in `openPoints.md`
as its own item.

## Attempts and dead ends

- **Lifting every band edge by the allowance** — the tidiest-looking fix, since
  the band edges are computed from RAW boundary heights while the runtime
  blocks at height + allowance, so the whole table is arguably off by `lvl_d`.
  Rejected before it was written: it moves band membership for every level
  within one allowance of every boundary, across all 39 projects, to fix three
  passes. The blast radius is the whole decomposition; the split's is a band
  at most `allowance` tall.
- **Splitting on every merged-away boundary, peak or not** — written and
  measured. Safe (the extra pieces cut nothing) but produced 15 windows on
  testing_15_6 against 10, and 60 slots against 40, for no cuts. Replaced by
  the peak test.
- **Using `detect_sections`' `min_x` as the peak test** — written, and wrong on
  a straight-taper boss for the reason above. The unit test caught it; the
  demo projects would not have.

## What went wrong on the way — the baseline worktree re-pointed the LIVE config

The byte-identity gate needs a real before, so a worktree was made at `4b666ff`
and the demo config's gitignored parts — `ncam/`, the tool tables, the var —
were symlinked into it from the live config. Running `gen_project.py --repo
<worktree>` against that config then **re-pointed the live config's own
`ncam/cfg`, `ncam/lib` and `ncam/graphics` symlinks into the worktree**: NCam
rewrites them to its own `SYS_DIR` at start-up, and through the shared `ncam/`
directory that start-up was writing into the live config.

It surfaced only when the worktree was removed and every rs274 run started
failing with `EOF in file ... seeking o-word: o<facing>` — the interpreter
searching the program itself because `SUBROUTINE_PATH` no longer resolved.
Symlinks restored to `/home/user/nativeCamDev/{cfg,lib,graphics}` and the final
probe re-run from the committed tree: 15 back-first, 0 front-first, 45/45.

**No measurement is invalidated**, and the reason is checkable rather than
assumed: this change touches no `cfg/` or `lib/` file (`git diff 4b666ff --stat
-- cfg lib` is empty), so the worktree's copies and the repo's are byte-identical
and it makes no difference which was on the path.

`analysis/055` recorded the mirror-image trap — a baseline run silently using
the WORKING tree's `lib/` through absolute symlinks. This is the same hazard
pointing the other way: **link a worktree config at the live `ncam/` directory
and the tool will re-point the live one.** Give the baseline its own `ncam/`
copy instead.

## What is still unknown

- **Phase 1's own handover level is still front-ordered.** It has no window
  table, so nothing in Python can re-order it: on testing_15_6 that is the
  duplicate above, on testing_11 a level with three intervals emitted front to
  back. Giving phase 1 windows is the fix, and it is a bigger change than this
  one - its ladder, its ceiling handover and `_pl_ph1_front_cut` all hang off
  it being a single unsectioned pass.
- **Sectioning OFF is untouched.** With Sectioning off there is no window table
  at all — `poly_lathe_mill` builds its own single full-length window — so
  every multi-interval level there is still front-first in direction 1. Fixing
  it means emitting windows where today there are none, which needs the
  runtime's `_pl_sectioning` gate to change. Not attempted.
- **The sub-band top is a lower bound, not the exact blocking height.** A
  normal offset at a sharp peak sits HIGHER than `height + allowance` (the
  miter), so a level between the two is blocked but sits above the sub-band and
  stays front-first. Safe by construction — the error is always in the
  direction of doing less — and no such level exists in any project measured.
  If one ever shows up it will look like "one level of the group is still
  front-first".
- **`p2_front` and the split pieces.** When phase 1 hands over cleanly
  (`_pl_ph1_front_cut = 1`) a window's `lvl_start` depends on its own
  `w_from`, so split pieces could start their ladders one level apart from the
  window they replaced. `_pl_ph1_front_cut` is 0 on every project measured
  (15_6, 15_5, 15_2, 15_4 — instrumented and read out), and the all-project cut
  sets agree, so it does not arise today. It is the one place a future profile
  could make the split change the cut set.
- **`param_dir` = 2, both directions**, still untouched.
