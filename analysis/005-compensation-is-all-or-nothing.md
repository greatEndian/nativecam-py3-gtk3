# 005 — Compensation is all-or-nothing; the OD taper's roughing now obeys it

2026-08-03. greatEndian: *"if is something compensated, there is compensated
everything even roughing... also artificial created sections are compensated
also"*, then *"implement compensation of outside taper"*.

## The rule

If an operation has nose compensation on, **every** pass in it is compensated —
roughing included — and the artificial back-angle sections are compensated too.
"Only the finish pass matters" is not the model: a roughing wall that ignores
the nose is left in the wrong place, and on a taper that error is the full
R·(1−cos) of the angle.

Recorded in `CLAUDE.md` and in Claude memory as a standing rule.

## State when the rule was given

| | compensated? |
|---|---|
| `lathe_poly_pass.ngc` — pre-finish and finish | yes, 7 `tip_comp_*` references |
| `lathe_level_pass.ngc` — polyline roughing | **no, zero references** |
| `taper` / `taper_id` / `boring` / `facing` | comp switched on **inside the finishing loop only** |

## What was done — the OD taper

`taper.ngc` resolved its nose geometry and comp side *inside* the finish block,
below the roughing loops, so roughing could not have used them. Both are now
resolved above the roughing block, and a roughing offset vector is computed
whenever `n_comp > 0`:

    o<tip_comp_vec> CALL [t_side] [end_z - begin_z] [(begin_x - end_x)/dm] [0]
    r_ofz = _tip_off_z
    r_ofx = _tip_off_x * _diameter_mode

applied to the angled cuts in both roughing branches — "Follow drive line" and
"Angular". The globals are cleared afterwards so the finish block keeps setting
them itself, unchanged.

**Roughing takes the offset in the coordinates, not from the interpreter**, in
BOTH compensated modes. Roughing has no interpreter comp in any mode, so there
is nothing to double up with — and this is the same shape as the pre-finish fix
in `analysis/004`: geometry we own, applied to the points.

## Measured

No saved project contains a taper feature, so this needed a standalone driver
calling `o<taper>` directly — the pattern `lathe-gcode-verify` prescribes for
exactly this case. Tool T3, `D2.54`, so nose R 1.27, orientation Q3 (diagonal).

    Off      20 roughing feed moves
    Native   20 roughing feed moves     20 of 20 moved, max 2.4535 mm
    In CAM   20 roughing feed moves     20 of 20 moved, max 2.4535 mm

Both compensated modes shift the roughing **identically**, which is the intent,
and Off is untouched. The magnitude is bounded correctly: a normal term plus a
diagonal orientation term cannot exceed R·(1+√2) = **3.066 mm** for this tool,
and 2.4535 sits inside that and well above R alone — a pure normal offset would
have been 1.27.

A first attempt compared ALL feed moves and reported "21 of 21 moved, max
16.1588 mm", which looked like a fault. It was not: Native emits one extra move
(the comp-establishing feed), so index-matched comparison shifted every pair.
Comparing the roughing feeds alone made the counts equal and the number fell to
2.4535. **A comparison between two lists of different length is not a
measurement.**

## Still unknown

- **The polyline's roughing is still uncompensated** — `lathe_level_pass.ngc`,
  the biggest remaining gap under this rule, and the one greatEndian saw behind
  the boss.
- **`taper_id`, `boring`, `facing`** have the same shape and are untouched.
- **The artificial back-angle sections** are named in the rule and not yet
  addressed anywhere.
- Whether the taper's roughing offset should also carry the roughing allowance,
  as the pre-finish contour now does. Not investigated.

## Verified

- roughing moves in both compensated modes, Off unchanged, magnitude bounded by
  the nose geometry
- the polyline is untouched: pre-finish to finish separation still
  Off +0.5072/+0.5742, Native +0.5080/+0.5710, In CAM +0.5080/+0.5711
- `test_lathe_validation`, `test_comp_side`, `test_facing`, `test_sections`,
  `test_lathe_comp`, `test_arc_endpoint` green; flake8 clean
