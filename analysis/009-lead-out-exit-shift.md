# 009 — The lead-out shortage: the exit shift never got the orientation term

2026-08-04, branch `liveTooling`.

## What was asked

greatEndian: *"go and fix lead in and lead out shortage"*, against the
criterion stated 2026-08-04: *"lead in and lead out can not end in the part or
stock therefore we need them, to be like when comp off there is no play"*.
Pictures: `photo/leadInIssueCompensation_0.png`,
`photo/leadOutIssueCompensation_0.png`.

## What was measured first, and what it ruled out

The criterion is testable, so it was tested before anything was changed: sweep
the real nose circle along each lead move against the material **as it stands
at that point in the program** — roughing has already been past — and ask
whether the move removes anything.

| | pre-finish lead-in | lead-out | finish lead-in | lead-out |
|---|---|---|---|---|
| Off | clear | clear | clear | clear |
| Native | clear | clear | clear | clear |
| In CAM | clear | clear | clear | clear |

**No lead ends in material on either test project.** That is worth stating
plainly rather than quietly fixing something else: the literal reading of the
complaint does not reproduce, and the fault is the second half of the
sentence — *"be like when comp off"*.

The **lead-in** was then checked point by point and is correct. Off's straight
lead runs 1.000 from (Z1.7071, r20.7071) to the contour start (Z1.0, r20.0).
Native runs 1.000 from (Z1.3071, r20.7071) to (Z0.6, r20.0) — shifted, but the
nose centre sits at control + R·orient, so the **cutting edge** starts at
(1.7071, 20.7071) and first touches the r20 cylinder at Z1.0: the same two
places Off's tip occupies. Nothing to fix. That is `c16df1f`'s pre-shift
working.

## The fault

`lathe_poly_pass.ngc` cancels compensation (`o<tip_comp_off>`, G40) immediately
after the contour trace, then emits a `G1` naming where the tool physically is,
because `_cut_phys_z`/`_cut_phys_x` only track the **raw programmed** endpoint.
That point was computed as

```
#<end_z>  = [#<_cut_phys_z> + #<comp_r> * #<_ext_nz>]
#<phys_x> = [#<_cut_phys_x> + #<comp_r> * #<_ext_nx>]
```

— a plain normal offset, **with no orientation term**. The entry pre-shift
gained that term in `c16df1f`; the exit was left behind. The two ends have to
move together.

After G40 the control point *is* the tip, so if that `G1` names a point the
tool is not standing on, **cancelling compensation becomes a real move**.
Measured on `testing_15_2`, finish pass:

```
Z-70.4000 r29.6000 -> Z-70.0000 r30.0000     0.5657 mm   <-- G40 jerk
Z-70.0000 r30.0000 -> Z-69.2929 r30.7071     1.0000 mm   lead-out
```

0.5657 mm is exactly |(0.4, 0.4)| — the raw orientation vector, R√2, not R.
The tool jerks out of the corner it has just finished, and the retreat runs
**1.5657 mm where 1.000 was asked for**. That is the shortage: not a lead that
is too short, a lead that starts in the wrong place.

## Which mode was right

Native and In CAM disagreed on the lead-out by exactly (0.4, 0.4). In CAM
carries its offset in its own Python point table and has `comp_r` 0, so it
never entered that arithmetic — **In CAM was right and Native was wrong**, the
same way round as the arc-truncation finding of 2026-08-02. The fix makes
Native agree with In CAM, not the other way round.

## The fix

The exit gains the term, gated exactly as the entry gates it — on `L > 0`
(a pure geometric `L0` offset takes no orientation term) and on a non-zero
`comp_r`:

```
#<ex_oz> = 0
#<ex_ox> = 0
o<ex_or> if [[#<_tip_comp_l> GT 0] AND [#<comp_r> GT 0.000001]]
    #<ex_oz> = #<_pl_nose_oz>
    #<ex_ox> = #<_pl_nose_ox>
o<ex_or> endif
#<end_z>  = [#<_cut_phys_z> + [#<comp_r> * #<_ext_nz>] - #<ex_oz>]
#<phys_x> = [#<_cut_phys_x> + [#<comp_r> * #<_ext_nx>] - #<ex_ox>]
```

No new global and no signature change: `_pl_nose_oz`/`_pl_nose_ox` are already
required by the entry in the same file, so nothing new has to exist at
load-time pre-parse and the live `ncam.ngc` needs no hand-patch.

## Measured after

```
Off      contour end -> exit line 0.0000 -> lead-out 1.0000
Native   contour end -> exit line 0.0000 -> lead-out 1.0000
In CAM   contour end -> exit line 0.0000 -> lead-out 1.0000
```

Native and In CAM now place every lead endpoint identically, to 1e-3, on both
`testing_15_2` and `testing_13_arcs`. `check_tangent` reports
`[VERDICT: PASS]`, min |dot| 1.00000 over 20362 canon events;
`test_rough_comp` and `test_comp_overlay` still pass unchanged.

## The test

`test_leads.py`, new, on two projects × three modes. Four assertions: no lead
move removes material; every lead is the length Off makes it; cancelling
compensation moves nothing; Native and In CAM place every lead identically.

**Verified to fail without the fix** — 4 failures, `Native ... jerks 0.5657 mm`
on both projects, and the Native/In CAM disagreement of exactly (0.4, 0.4).

Note that the material sweep passes *even without the fix*: the 0.5657 mm jerk
travels outward, into air. The fix is about placement and length, not a gouge,
and the test says so by keeping the two claims separate.

## What went wrong while writing the test

The exit line was first identified as *"the move before the lead-out"*. With a
lead-out blend radius that is the **arc**, so the check reported
`prefinish lead-out jerks 0.3902 mm` on `testing_13_arcs` — **in all three
modes including Off**. A measurement that fires on the baseline is not a
measurement; that is the third time this trap has been hit here (5.0452 mm
"gouge", 17.83 mm "error", now 0.3902 mm "jerk"). Fixed by locating the exit
line **by position**: it is the one move that is exactly zero length in Off,
and the same position is then read in the mode being judged.

## Still unknown

- Roughing (`lathe_level_pass.ngc`) has no exit shift at all — it is
  table-driven and never runs interpreter compensation, so there is nothing
  of this shape to correct. Its leads are **not** covered by `test_leads.py`;
  only the pre-finish and finish passes are.
- The same exit arithmetic exists per-op in `taper.ngc`, `taper_id.ngc`,
  `boring.ngc` and `facing.ngc`. Whether any of them cancels compensation at a
  point the tool is not standing on has not been checked.

---

## Addendum, 2026-08-04 — the contour now ends on the polyline's own last X

greatEndian, from `photo/leadOutIssue_0.png`: *"it have to finish at blue
prefinish contour which has to end in X at last polyline segment X coordination
or stock envelope"*.

The compensated control point stopped **0.4000 short**: the pass ended at
r29.6000 so the NOSE contact landed on r30.0000. The surface was right; the
tool's own X — and the contour drawn from it — finished inside the bar.

```
                 before            after
Off      pf ends r30.0000    r30.0000     (already there, no move emitted)
Native   pf ends r29.6000    r30.0000
In CAM   pf ends r29.6000    r30.0000
lead-out            1.0000 from there, all three, unchanged
```

A separate pure-radial `G1` **after** the G40 no-op, not folded into it — that
line must keep naming where the tool already stands or the fault this analysis
is about comes straight back. `_cut_phys_x` is the last polyline segment's X,
so no new input is needed and a profile ending below the stock is followed just
as faithfully as one running out to it.

**In CAM needed a second term.** Its record table IS the offset control-point
path, so its own `_cut_phys_x` is already the short 29.6000 and cannot supply
the target. `_pl_rgh_ox` — the orientation term already gated in Python — plus
`comp_r` to tell the modes apart: Native has the interpreter doing the offset
and needs no uplift, In CAM has `comp_r` 0 and needs exactly one nose term.

Verified: `check_tangent` PASS min |dot| 1.00000, `test_rough_comp`,
`test_sections`, `test_comp_overlay` and `test_lathe_validation` all pass,
`test_leads` 24/24.

### Both tests had to be repaired, and neither was loosened

`test_comp_overlay`'s `LEAD_OUT` 3 → 4, because a real fourth non-contour move
now exists at that end. Its "exactly the excluded moves differ" check still
requires at least one to genuinely differ, so the exclusion cannot grow
silently.

`test_leads`' exit-line check was **wrong three times** before it was right,
and every failure was move-identification rather than motion:

1. *"the move before the lead-out"* — caught the lead-out BLEND ARC, 0.3902 mm,
   failing on Off itself.
2. *by position in Off's tail* — broke the moment the modes stopped having
   equal move counts, which is exactly what this change did.
3. *the largest Z jerk of everything but the last move* — caught the blend arc
   again, 0.2168 mm, on Off again.

It now asserts the one property the exit line actually has: **a zero-length
move exists in the tail.** Not circular — a regression does not move the
no-op elsewhere, it removes it. Negative control run: with the orientation
term deleted, `Native cancelling compensation is still a no-op` FAILS and Off
still passes.

The tail window also had to widen 4 → 6: a blend radius costs three moves and
the new last-X move a fourth, which pushed the no-op out of the window.
