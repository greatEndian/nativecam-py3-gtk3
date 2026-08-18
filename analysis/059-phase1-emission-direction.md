# 059 — Phase 1 learns the emission direction

greatEndian, 2026-08-17: *"teach phase 1 the emission direction"*. The last
ordering gap in back-to-front roughing, left open by `analysis/057` and
narrowed by `058`.

## What was asked

Back to front was already correct in every respect that matters — the cut SET
is identical between the directions, and window-driven multi-interval levels
are emitted back-first, because `_sections_back_to_front` re-orders the
`#3401+` window table in Python.

**Two sweeps are not window-driven**, and so were out of that fix's reach.
Both are in `lib/lathe/poly_lathe_mill.ngc`:

- **Sectioning ON, phase 1** — the unsectioned full-length "violet" pass,
  `w_idx < 0`, with its own multi-crossing loop.
- **Sectioning OFF** — the single full-length window `poly_lathe_mill` builds
  itself.

Both discover a boss's two intervals sequentially — cut,
`lathe_level_next_start`, cut — so nothing knows the second interval exists
until the first has been written.

## Measured, before

Probe anchored to `057`'s figures first: testing_15_6 sectioning ON reads
44 cuts / 44 distinct with back-first 15, front-first 1, the residue X34.0636.

```
                      sectioning ON          sectioning OFF
testing_15_6      back 15 / front 1        back  0 / front 15
testing_15_5      back 15 / front 1        back  0 / front 16
testing_11        back 15 / front 1        back  0 / front 16
```

Sectioning OFF was never front-first by accident — it was front-first
*everywhere*, on every multi-interval level.

## The design

Same geometry as `_split_level_intervals`, and the same reason it is sound.
The gap a boss opens in a level is `{ z : profile(z) + allowance >= level }`,
which can only GROW as the level drops. So the gaps at every level below a peak
are nested around the peak's own Z: **one split point per peak serves every
level it blocks**, and `peak height + allowance` is the radius at or below
which it certainly does. Above that the level may run straight through and must
NOT be split — splitting there would cut as two spans what was cut as one, and
the cut set would move.

`build_level_split_gcode()` emits the peaks, each with its own threshold, and
the runtime walks the level in sub-spans between the peaks active at that
level, back-most first.

**The scan remains the authority.** A split point is only a bound handed to it;
it still finds where each cut actually starts and stops. This is the lesson of
`058` applied deliberately: `lathe_level_next_start`'s resume answer can land
just inside a rise (−34.171 where clear ground starts at −35.000), so
Python-computed boundaries and scan-computed boundaries are **not**
interchangeable. A split point sits at the peak, safely inside the blocked gap,
where the two cannot disagree about whether there is material.

Peaks only, as in `_split_level_intervals`: a step or a flat-to-rise blocks a
level just as well, but everything past it is above the level too, so a
sub-span behind it would cut nothing.

It returns `''` — changing nothing at all — for front to back, for a profile
with no peak, and if the table would overflow. `#<_pl_p1s_n>` defaults to 0 in
`create_defaults`, so front to back and every file generated before this
existed walk each level in one span exactly as they did.

## A near-miss that became a permanent check

The table was going to go in "the free gap at 3140", which is what the brief
for this work specified — twice, across two briefs.

**Only 3160–3200 was ever free.** `cfg/lathe/polyline.cfg` stages the
polyline's own CALL arguments in plain numbered parameters at **#3141–#3159**.
That block sits BETWEEN two declared windows, so `cam_map`'s overlap check
could not see it, and a table at 3140 would have silently overwritten the
feature's own arguments.

Caught while placing the table. `cam_map` gained a `cfg_scratch()` extractor so
it cannot happen twice, and the table sits at `LVLSPLIT_BASE = 3160`,
`LVLSPLIT_TOP = 3200` — 40 slots, twenty peaks, with the same
refuse-rather-than-overflow guard `_split_level_intervals` has.

Two comments still said "#3140" and "60 slots" after the move; corrected,
because they would have re-planted the mistake for the next reader.

## Measured, after

```
                      sectioning ON          sectioning OFF
testing_15_6      back 16 / front 0        back 15 / front 0
testing_15_5      back 16 / front 0        back 16 / front 0
testing_11        back 16 / front 0        back 16 / front 0
```

**Front-first: 0 everywhere.** Both residues `057` and `058` recorded are gone,
and sectioning OFF — which was never in the original ask and surfaced as a
side-finding — is fixed by the same change, because both paths run the same
interval walk.

## The gate

| item | result |
|---|---|
| 16 of 16 back-first, sectioning ON | **PASS** — 15_6, 15_5, 11 |
| testing_11 front-first 0 | **PASS** |
| sectioning OFF back-first | **PASS** — 0/15 → 15/0 and 0/16 → 16/0 |
| front-to-back order unchanged | **PASS** |
| front-to-back byte-identical | **PASS** — one line, `#<_pl_p1s_n> = 0.0`, the required `create_defaults` entry |
| cut SET identical, before vs after, both directions | **PASS** — 8 combinations, **lost 0, gained 0**, no duplicates |
| `cuts == distinct` still holds | **PASS** — 44/44, 46/46, 42/42, 45/45, 35/35, 34/34 |
| standing metal | **PASS** — 0.7219 / 0.8579 / 0.6473 / 0.5681, identical between directions |
| `test_leftover` | **PASS** 46/46, control fired 21 of 21 |
| `test_x_continuity` | **PASS** 17/17, worst gap 0.0000, control fires |
| overcut past the pre-finish contour | **PASS** — 0.0503 both directions, bound 0.08 |
| tangency | **PASS** — min \|dot\| 1.00000 |
| cfg version bumped 1.61 → 1.62 | **PASS** |
| no CALL arity change | **PASS** — `#<w_to>` → `#<lv_to>`, same argument count |
| O-code syntax scan, flake8, `cam_map` 6/6, `test_lathe_validation`, `test_sections`, `test_ngc_comments`, `test_cam_map`, `test_all_projects` | **PASS** |

**Lost 0 / gained 0 across eight combinations is the assertion that matters.**
Only the order moved. That is the whole claim of this change, and of the
direction as a feature.

## What is still unknown

- **The 40-slot table caps at twenty peaks.** No demo project comes close, and
  overflow refuses the split rather than corrupting anything, but a very
  complex profile would silently keep the old front-first order. It would look
  like "back to front is right on my other parts but not this one".
- **`param_dir` = 2, both directions**, remains untouched and open — greatEndian
  left it open explicitly.
- The split table is emitted from `polyline.cfg`'s `[AFTER]` block, so a saved
  project only gets it after migration to 1.62. That is the normal cfg
  asymmetry, but it means an unmigrated project keeps the old order until
  opened and saved.

## Why this took four rounds

`054` established the cut set. `057` ordered everything a window carries. `058`
removed a duplicate that was masking one residue. `059` reached the two sweeps
no window covers. Each round's gate was the previous round's property, which is
what kept the cut set from drifting while the emission was rearranged four
times — and the arithmetic that exposed the duplicate in `058` (a count against
a distinct-count) came out of `057` measuring something else entirely.
