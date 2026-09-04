# 110 — the native entry gouge: two fixes attempted, both reverted

**Asked**: greatEndian, 2026-09-04 — *"fix the native lead"*, then *"move
tip_comp_on before the lead-in"*.

**Not fixed.** Both attempts were ineffective and both are reverted. The tree is
back at `c6debc3` for `lib/`. What follows is what they ruled out, which is the
only thing they produced.

## Attempt 1 - widen the ID approach

Mirroring `taper_id.ngc:92`, `lathe_poly_pass`'s ID approach was moved a further
`_tip_lead_w` off the wall when compensating.

**No change: gouge still 0.8000.** The approach positions the tool BEFORE the
lead; the gouge is where compensation is established. Different moves.

## Attempt 2 - establish comp on the lead

`tip_comp_on` moved ahead of the straight lead's `G1`, ID-only, gated on
`_tip_comp_d`, so the lead itself would be the entry move - which is what the
arc-entry branch at :284 already does deliberately.

**Motion changed - 227 to 240 tangent points - and the gouge did not: still
0.8000, still the same single point.**

## What attempt 2 taught, which attempt 1 did not

The project's lead parameters:

```
param_li_len 1.0 mm     param_li_rad 1.0 mm
```

`li_rad > 0` means the FILLET path runs. The `G1` I moved compensation ahead of
only reaches the fillet's tangent point - **an ARC completes the entry**, and an
arc cannot establish compensation. That is why the branch already carries a
comment about tight blends and cutter comp.

So the entry on this project is: rapid, straight feed to the tangent point, arc
onto the profile. Establishing comp before the straight part does not change
where the ARC lands, and the arc is the move that arrives at the gouging point.

## The measurement, unchanged throughout

```
620 sampled points, 1 gouging
   centre Z 0.0000  r 17.4000   bound r 17.0000   into 0.4000  [feed]
```

One point, the bore mouth, nose centre at `wall + R`. Contour clean at 0.0000
in both compensation modes; only the lead gouges, only under native.

## What the next attempt needs to establish first

How LinuxCNC settles `G41.1` when the move that reaches the profile is an ARC
following a straight lead. Until that is known, a third change is another guess:
the candidates are lengthening the straight part so comp is fully established
before the fillet, suppressing the fillet under native comp on ID, or entering
without the arc entirely - and choosing between them by reasoning is exactly
what produced these two reverts.

## Standing count

Three wrong diagnoses (`analysis/103`, `104`, `106`) and now two ineffective
fixes on this one defect. Every correct step came from instrumenting the thing
itself; every wrong one came from reasoning about what the code should do. The
locator that gave the single coordinate took one run.
