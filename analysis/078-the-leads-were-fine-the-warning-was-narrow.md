# 078 — the leads did not need gating; the warning was too narrow

**Asked**: greatEndian, 2026-09-03 — *"go on with the leads"*, the last item in
`openPoints`' "Both directions WARNS but is not yet CORRECT": *"the entry/exit
leads are not gated per pass direction the way the ramp now is"*.

## The leads are sound, in every direction

`test_leads` sets `param_n_comp` and has never set `param_dir` at all, so the
leads had never been checked back to front or alternating. That was the real
gap — a coverage hole, not a defect.

Applying its own criterion — no lead move may cut into the material — across
all three directions on testing_15_5 and testing_15_2:

```
dir 0  no lead cuts into the material
dir 1  no lead cuts into the material
dir 2  no lead cuts into the material
```

## And gating them WOULD HAVE BEEN WRONG

The ramp is gated because its purpose is to **arrive parallel to a surface**,
and that is void when the insert cannot cut that way — it arrives parallel to
nothing. A plain lead's purpose is to **ease into the cut**, and that survives
the direction entirely.

Gating leads by the insert facing would drop **every** lead on back-to-front,
which is a legitimate mode with a left-hand tool. The open point's framing —
"gate them the way the ramp is gated" — would have made the toolpath worse.

`test_leads` now covers all three directions so the hole cannot reopen.

## What the investigation DID find

**The warning fired only for `param_dir` = 2, which is narrower than what the
toolpath already believes.** `_pl_ramp_face` treats back-to-front with an
ordinary right-hand insert exactly as it treats the alternating mode: measured,
testing_15_9 with T2 Q2 keeps **15 ramps front to back and drops all of them
back to front**, because the tool cannot cut that way. The operator was told
nothing.

So the question is not "is the mode alternating" but "can this insert cut the
direction asked for". `wrong_way_dirs(orient, rough_dir)`:

| | dir 0 | dir 1 | dir 2 |
|---|---|---|---|
| orient 2, cuts −Z | quiet | **WARNS** | **WARNS** |
| orient 1, cuts +Z | **WARNS** | quiet | **WARNS** |
| orient 9, neutral | quiet | quiet | quiet |

One rule, no second branch: a single direction is wrong only when it is the
opposite one, which also catches a MIRRORED insert used front to back.

Still warn-and-proceed, greatEndian's ruling from `analysis/070`, and still
nothing refused. cfg 1.71 → 1.72.

## Gates

`test_bidir_warn` (13 assertions, now pinning the truth table above),
`test_leads` (extended to all three directions), `test_leftover`, `test_ladder`,
`test_x_continuity`, `test_skip_thin_gap`, `test_ramp_orient`, `test_ramps`,
`test_air_leads`, `test_z_limits`, `test_x_limits`, `test_sections`,
`test_flank_envelope`, `cam_map`.

## Still unknown

- Whether a **left-hand tool** would make back-to-front behave the way
  front-to-back does with the shipped one. `ramp_facing` says it should, and
  `test_ramp_orient` shows the ramps coming back when the tool table's Q is
  mirrored - but no demo project carries a genuinely left-hand tool, so it has
  only been exercised by editing Q in a scratch copy.
