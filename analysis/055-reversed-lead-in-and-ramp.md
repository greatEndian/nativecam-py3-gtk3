# 055 — The lead-in and the ramp on a reversed pass

greatEndian, 2026-08-15: *"fix the missing lead-in and ramp for reversed
passes"*.

## What was asked

`904a345` made back-to-front roughing emit the same cut set as front-to-back,
reversing only the emission. It deliberately switched two things off on a
reversed pass and recorded them as the next step:

- `#<pa_on> = 0` — the profile-angle ramp, armed from the entry-contour
  crossing at `z_start`;
- the straight lead-in branch, which runs backward from the pass start.

Both are armed from `z_start`, the front of the interval. Front to back that is
where the pass BEGINS, so the lead runs through air. Back to front `z_start`
became where the pass FINISHES, so the same lead would have driven into
material the cut had not reached yet. Gating them off was correct as a holding
position and wrong as an answer.

## The measured cost, before

`test_leftover`, worst metal standing proud, measured on `904a345`:

| project / mode | f2b | b2f |
|---|---|---|
| testing_15_5 sect off | 0.7219 | **1.1827** |
| testing_15_5 sect ON | 0.8579 | **1.1517** |
| testing_15_6 sect off | 0.6473 | **0.7324** |
| testing_15_6 sect ON | 0.5681 | **0.8126** |

And the leads were absent in the motion, not merely different — counting
roughing feeds that move BOTH axes, on testing_15_5 sectioning off:

```
904a345   f2b  level 45   lead/ramp 106
          b2f  level 45   lead/ramp  45
```

45 against 106: one plain approach descent per pass and nothing else.

## The root cause, and why the obvious fix was the wrong one

The brief for this work — written by me — proposed building a **mirror entry
contour** for the back end in Python, on the reasoning that `entry_contour` and
`resume_envelope` answer "coming from the front, how close can the tool
descend", so the reversed pass needs the same answer from the back.

**That was unnecessary, and the agent was right to ignore it.** There is no
second envelope to compute, because there is no second geometry:

> Back to front is the SAME MOTION PLAYED BACKWARDS — the same lead lines, the
> same blend circles, the same profile-angle ramp, the same cut — emitted end
> to start instead of start to end.

Each lead belongs to an **END of the pass** and keeps its own geometry in both
directions: the `li` lead at the `z_start` end, the `lo` lead at the `z_end`
end. The only thing `#<_pl_cut_rev>` decides is which of the two is traversed
INWARD as the approach and which OUTWARD as the retreat.

So `e_dir` — introduced by `904a345` as the emission direction — is **deleted**.
It was a second frame, and a second frame is exactly what `054` removed from
the decomposition for the same reason. The fault was that `904a345` reversed a
frame where it should have swapped two roles.

Two consequences fell straight out, both of which had been direction-gated in
`904a345` and should not have been:

- the `lo` lead's length cap belongs to the lead at the `z_end` end, which sits
  in the same place with the same length whichever way the cut is emitted;
- the lead-out arc that bottoms out on the pre-finish line is the SAME arc at
  the SAME end either way — back to front simply drives through it on the way
  in. The direction-gated clip made `z_end_cut` differ between directions,
  which is precisely the "same cut set" property the reversal exists to keep.

The lead resolution had to move OUT of the block that emits it, because which
of the two ends is emitted first depends on the direction and both must be in
hand by then. It is pure arithmetic and emits nothing, which is why front to
back is unchanged. A related trap was avoided on the way: a named parameter
first assigned inside a branch fails LinuxCNC's load-time pre-parse, so the
`lo` geometry is initialised unconditionally.

## The result

| project / mode | f2b | b2f before | **b2f after** |
|---|---|---|---|
| testing_15_5 sect off | 0.7219 | 1.1827 | **0.7219** |
| testing_15_5 sect ON | 0.8579 | 1.1517 | **0.8579** |
| testing_15_6 sect off | 0.6473 | 0.7324 | **0.6473** |
| testing_15_6 sect ON | 0.5681 | 0.8126 | **0.5681** |

Identical to four decimals, not merely within the 0.10 mm the gate asked for —
which is the signature of the same motion rather than a second one tuned to
match. The lead count agrees the same way: **b2f 106 against f2b 106**, where
it was 45.

## The gate

| item | result |
|---|---|
| standing metal, b2f down to f2b | **PASS** — identical, 4 projects/modes |
| a reversed pass has a lead-in and a ramp | **PASS** — 45 → 106 lead/ramp moves, = f2b |
| no gouge — overcut past the pre-finish contour | **PASS** — 0.0503 both directions (bound 0.08); 110 rough moves each |
| tangency | **PASS** — min \|dot\| 1.00000 over 127869 canon events |
| cut SET preserved (testing_15_6 sect ON) | **PASS** — 45 cuts, 44 distinct, 44 shared, **0 unique either way**; 45/45 b2f passes travel back to front |
| front to back byte-identical to `904a345` | **PASS** — **0 lines differ**, 15_5 and 15_6 × sectioning off and on |
| `test_x_continuity` | **PASS** — 17/17, worst gap 0.0000 in all four combinations, control fires |
| `test_leftover` | **PASS** — 46/46, control fires on 21 of 21 |
| `cam_map` | **PASS** 6/6 |
| `test_lathe_validation` | **PASS**, 40 calls |

On the baseline the overcut probe read f2b 0.0503 / b2f 0.0490 with 110 against
60 roughing moves; after, both read 0.0503 with 110 moves each.

## Instruments, and how each was validated before it was believed

The standing rule is that a probe is not trusted until it reproduces a number
already known. Both new ones were anchored first:

- **lead/ramp counter** — classifies roughing feeds as level cut (pure Z),
  radial, or both-axes. Run on `904a345` first, where the leads are known to be
  gated off, it reported **f2b 106 / b2f 45**. A probe that could not see the
  documented gap would not have been used on the fix.
- **overcut probe** — reuses `test_rough_comp`'s construction verbatim (same
  target contour, same `StockField` sweep, same `radius_at` flat guard) and
  varies `param_dir` instead of `param_n_comp`. On the baseline it reproduced
  `test_rough_comp`'s own documented **0.0503** for the fixed entry contour.

The front-to-back identity check used an isolated worktree at `904a345` with
its own config whose `cfg`/`lib`/`graphics` symlinks point into that worktree —
the demo config's symlinks are absolute into the repo, so without re-pointing
them a "baseline" run silently uses the working tree's `lib/` and proves
nothing.

## What went wrong on the way

- **The first agent run died on a session limit** partway through, leaving the
  change uncommitted, no analysis file, and five scratch probes in the repo
  root. The work was preserved as a patch before anything else was touched, and
  the whole gate was then re-run independently rather than resumed on trust.
- **The brief sent the agent at the wrong solution.** It specified a mirror
  entry contour in Python and spent a paragraph on parameter-window budget
  (~60 free slots at 3140–3200, everything else packed to 4984 of 5000). None
  of it was needed. The instinct was "Python first", but the question here was
  never a geometry computation — it was which end of an already-computed lead
  the tool arrives at, and that is emission, not geometry. **Python first does
  not mean move things into Python that are not geometry**; the `.ngc` in fact
  got simpler, losing `e_dir`.
- A first reading of the diff as "113 lines of new O-code logic and zero
  Python" was wrong: 103 of the 220 added lines are comments, and the code is a
  restructure of lead resolution that already existed, not new geometry.

## Still unknown / not done

- **Interval order within one level is still front-first** where a boss splits
  it — unchanged by this work, and front to back alternates the same way.
- **Natural sectioning's weakest-first ranking is still replaced by geometric
  section order** in direction 1, per greatEndian's spec. `_sections_back_to_front`
  is the one place to change if the rigidity ranking is wanted back.
- **`param_dir` = 2 (both directions) is untouched.**
- `test_leads.py` fails on `testing_13_arcs` mode "Off" — pre-existing, verified
  identical before this change.
