# 021 — The housekeeping bundle, measured instead of assumed

2026-08-08, branch `liveTooling`, from `9ddaa1b`.

## What was asked

greatEndian: *"go 14"* — the housekeeping group in `openPoints`, three parts:
the two zero-length feeds per contour pass, the unbounded flank leftover, and
the migration side-effects. All three were carried as adjectives ("harmless",
"only the drawn silhouette", "worth a look in AXIS"). This measures them.

## (a) The two zero-length feeds — NOT removed, deliberately

`lathe_poly_pass.ngc:366` emits `G1 X[#<phys_x>] Z#<end_z>` right after
`tip_comp_off`. Where the pass carries no offset and no nose term
(`comp_r` 0, `ex_oz` 0) that resolves to the point the tool already occupies,
so the move is exactly zero length: one at the end of the pre-finish pass and
one at the end of the finish pass on `testing_15_2`.

The obvious cleanup is to skip the line when it is a no-op. **It must not be
done**, and the reason is not the G-code:

`test_leads.py`'s exit-line check is literally *"a zero-length move exists in
the tail"*, asserted in **all three modes**. That formulation is what survived
after three wrong ones — locating the exit line by position broke when the modes
stopped having equal move counts, and measuring the largest Z jerk caught the
lead-out BLEND ARC (0.3902 mm, then 0.2168 mm) and failed on Off itself. The
no-op is the only property the exit line has that a regression cannot imitate:
a fault does not move the no-op elsewhere, it removes it.

So removing the two moves would delete the regression detector for
`analysis/009` — the 0.5657 mm = R√2 jerk out of the finished corner — in
exchange for two moves out of 323. The trade is not worth making.

What was actually wrong was my earlier description of it as *"the honest fix is
to skip the line when `comp_r` is 0"*. That is the mode set the detector lives
in.

**Left as it is, and `openPoints` now says why** so it is not re-proposed.

## (b) The unbounded flank — 10.0899 mm, not 9.73

Asked `lathe_sections.unreachable_spans` directly, with the same arguments
`cfg/lathe/polyline.cfg:375` passes it (back 75.0, flank 16.0, clearance 2.0):

| project | clearance | span | worst radius gap |
|---|---|---|---|
| testing_15_2 | **2.0 (today's default)** | Z−70.22 … −35.77 | **10.0899 mm** |
| testing_15_2 | 0.0 | Z−70.22 … −36.31 | 9.7337 mm |
| testing_15_4 | 2.0 | Z−70.22 … −35.73 | 10.0892 mm |
| testing_15_4 | 0.0 | Z−70.22 … −36.26 | 9.7329 mm |

**The 9.73 mm in `openPoints` is the clearance-0 figure** — the number as it
stood before the back-angle clearance default arrived. With the 2° default in
force the shadow is 0.3562 mm deeper in radius and reaches 0.54 mm further
along Z. Same shape of finding as `analysis/020`'s stale 0.0394: a number
written down once and left to age.

This is still a consequence of a decision and not a defect — the region behind
the boss cannot be reached by this tool from this side, the warning names the
span, and reaching it needs a second tool or a second setup, not a code change.

**A sweep-based measurement of the same thing was tried first and thrown away.**
Comparing the simulated part against the programmed contour at each Z reported
1.0399 mm over Z−19.84 … −24.99 and a nonsensical −20.7071 mm "overcut". Both
are artefacts: the profile runs ABOVE the r30 bar between Z−29 and Z−44 (so the
bar itself reads as an overcut of up to 2.58 mm) and the peak sits on the steep
wall at Z−20, where radius-at-Z across a near-vertical stretch means nothing.
This is the trap `test_rough_comp`'s own docstring records at Z−69.4 — it caught
this file too. The analytic span is the right source; the sweep is not.

## (c) The migration defaults — one changes motion, three do not

`testing_15_2`, Native, generated with each default at its old and new value and
the move lists compared position by position:

| default | motion |
|---|---|
| **Back angle clearance 0 → 2.0°** | **323 → 345 moves, 198 differ** |
| Flank length 16 → 25 mm | **byte-identical** |
| Holder shank 0 → 25 mm | **byte-identical** |
| Skip short passes (off by default) | identical at the default; 0.3 changes 307 moves |

So of the four:

- **The 2° back angle clearance is the one that matters.** Every migrated
  project's roughing changed — 198 of 323 moves — and by (b) it also deepens
  the unreachable shadow 0.3562 mm. This is the one worth a look in AXIS.
- **Flank length and shank height are provably picture-only.** The note that
  `testing_15_2` and `15_3` "need their flank length re-entered" is now
  confirmed harmless to the part: 16 mm and 25 mm produce the same program to
  the digit. Re-enter them for the silhouette, not for the metal.
- **Skip short passes off by default is a real no-op**, not merely believed to
  be one.

## Still unknown

- Whether the 2° clearance leaves the right amount. It is a standoff so the
  back edge does not rub, and 198 changed moves is what that costs; whether the
  resulting part is better is greatEndian's judgement in AXIS, not a number
  measurable here.
- (b) was measured on the two 15-series projects only. A shallower back angle
  or a shorter obstruction would give a different span, and no project here
  exercises that.
