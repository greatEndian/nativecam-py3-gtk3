# 210 — Phase 1's ceiling level is cut a second time by phase 2

2026-09-15, branch `liveTooling`. Asked by `SONNET-PROMPT-BLOCKED-DUP.md`: find
the duplicated roughing pass recorded in `openPoints.md` and remove it without
moving metal.

The duplicate found is **not** the one the prompt describes. The recorded item
is the front interval of the first *blocked* level (`34.0636 0.0000 ->
-31.2092` on testing_15_6, the obstruction path). What the sweep actually found
is a duplicate on the **clean** path, on seven other projects. The recorded one
is no longer reproducible — see "What was not fixed".

## The bug

`roughing_ladder` (`lathe_sections.py:2641`) walks phase 1 up to the section
ceiling `top`. `walk()` appends a level **before** testing the floor-equality
break, so `top` is phase 1's own last entry. Every phase-2 window then starts
its own walk at that same radius: `lvl_start` is `p2_start`, which is `top`
(or `top_override`, whatever phase 1 was truncated at).

`poly_lathe_mill.ngc` has a dedup flag for exactly this, `_pl_ph1_front_cut`
(`analysis/058`) — but it is only ever set on the **obstruction** branch
(`poly_lathe_mill.ngc:1215`, `:1323`, `:1414`). When phase 1 reaches its
ceiling with nothing blocking it, the flag stays 0, window 0 has no way to know
the radius was already cut, and it cuts it again: lead-in, full-length cut,
lead-out, retract — the second one entirely in air.

Measured on the default generation path, `testing_9_6.xml`: X28.262 over
Z0.0 → Z−49.238, byte-identical, moves 13–16 and 17–20 of 182.

## The fix

`roughing_ladder` drops the first level of a phase-2 window when it equals
phase 1's own last radius, within the 0.002 mm tolerance the function already
uses to recognise a truncated `top_override`. Phase 1 always finishes the level
it last touches before handing over (`analysis/058`), so that radius never
needs a second visit.

Python only — it changes the table emitted by `build_level_table_gcode`
(`:3210`) and the equivalent `roughing_call_plan` (`:3499`). **`poly_lathe_mill.ngc`
is untouched**, per the standing Python-first rule.

## Measured, before and after

Fingerprint over all 46 projects (`test_motion_fingerprint.py`), baseline taken
from `HEAD` with the fix stashed out:

```
39 identical, 7 changed, 0 not in the baseline, of 46
```

The 7 changed are exactly the 7 the duplicate sweep named. Every one **loses**
moves; none gains:

| project | moves before → after | feeds |
|---|---|---|
| testing_9_5   | 280 → 274 | 163 → 160 |
| testing_9_6   | 182 → 178 |  74 →  73 |
| testing_9_6_1 | 194 → 190 |  80 →  79 |
| testing_9_8   | 188 → 184 |  77 →  76 |
| testing_10    | 482 → 470 | 371 → 362 |
| testing_11    | 490 → 478 | 379 → 370 |
| testing_12_0  | 192 → 180 | 147 → 138 |

The three that lose 12 moves are the multi-window projects: the drop applies to
every phase-2 window whose walk starts on that shared boundary, not only to
window 0.

**No pass went missing** — the count of distinct Z-cutting levels and the top
four radii are identical before and after on every project (20 levels on the
9_x/10/11 group, 11 on 12_0; controls 31, 31, 12). This was the real risk: had
the dropped level been one the `analysis/058` skip flag still expected, the
result would have been a *missing* pass rather than a removed duplicate.

Controls, already duplicate-free and covering the obstruction/handover case
`analysis/058` fixed, are byte-identical: testing_15_5 (478 moves),
testing_15_6 (494), testing_15_blocked (114).

## Gates, all run on the fix as committed

```
flake8 (ncam_*, lathe_sections, test_ceiling_dup)   rc=0
cam_map.py                                          rc=0
run_tests.py x7 (cam_map, lathe_validation,
  level_intervals, level_blocked, sub_spans,
  ladder, x_continuity)                             7 passed, 0 failed
test_ladder_python.py / test_ladder_account.py      rc=0 both, before and after
test_surface_equality.py                            rc=0  (38 with both tables)
test_project_sweep.py                               rc=0  (45 clean, 1 expected:
                                                     default_template, no motion)
test_ceiling_dup.py  on HEAD (unfixed)              rc=1, all 7 fail  ← instrument validated
test_ceiling_dup.py  fixed                          rc=0, 10/10
```

The unfixed run is the part that matters: a regression test that cannot fail is
worth nothing, and `analysis/127` is this project's own record of one that
could not.

## Why no gate caught it before

The second pass cuts air. The surface is already at depth, so
`test_surface_equality` sees the same surface, `test_x_continuity` sees no step
larger than a depth of cut (the step to the duplicate is zero), and no leftover
check sees standing metal. Every gate asks whether what exists is correct;
none asked whether anything is emitted twice. Same shape as the lesson recorded
for the missing-pass bug — **enumerate what should be there**, in this case by
signature-counting every cutting move rather than inspecting the ones present.

## What was not fixed

The `openPoints.md` item this task was drawn from — the front interval of the
first blocked level emitted twice, `34.0636 0.0000 -> -31.2092` on
testing_15_6 — **did not reproduce**. testing_15_6 is one of the three controls
and shows zero duplicated cutting moves both before and after this change, with
its motion byte-identical across it. It is a different path (obstruction, where
`_pl_ph1_front_cut` is live) and was plausibly closed by `analysis/058` itself.
Recorded as not-reproducible rather than fixed: if it returns, it needs a fresh
reproduction, not this fix.

## Provenance

The code change was produced by the BLOCKED-DUP worker session, which stopped
before committing and without writing this file. The gates above were re-run
here from scratch — including the before/after fingerprint, which no longer
existed — and the fix was reviewed against the `analysis/058` skip flag before
being committed.
