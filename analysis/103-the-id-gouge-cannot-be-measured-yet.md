# 103 — the ID gouge: the recorded numbers do not reproduce

**Asked**: greatEndian, 2026-09-04 — *"go with 4"*, the measured-but-unfixed
defects. Starting with the two ID gouges, documented as very likely one fault:
**0.2929 mm** comp entry into the wall, **1.4929 mm** ID lead-in/out native.

## The reproduction is invalid, twice over

**First: `testing_14_inside` has compensation OFF.** `#param_n_comp = 0`. I ran
a compensation proof against an uncompensated path and got a FAIL that means
nothing. The recorded numbers were taken with the mode set; the saved project
does not carry it. *Verify in the configuration the report came from* - the
project's own settings contradicted the note and I checked them only after
running.

**Second: the prover cannot discriminate on this bore.** Two reproducers were
made - `testing_14_inside_cam.xml` (n_comp 2) and `_nat.xml` (n_comp 1) - and
they genuinely differ:

```
testing_14_inside      sha 5f1bb371  #3159 = 0   4 cam lines
testing_14_inside_cam  sha fc0683e4  #3159 = 2   8 cam lines
testing_14_inside_nat  sha c0777e56  #3159 = 1   4 cam lines
```

Three different programs - and `prove_cam_comp` reports **identical** results
for all three, compensation off included:

```
contour        : gouge 0.3542, 2 tangent points, 3 segment(s) uncovered -> FAIL
wrong-side ctrl: gouge 0.8000, 15 tangent points, 0 segment(s) uncovered -> FAIL
```

By the tool's own design rule the correct side must PASS and the free side must
FAIL. Both fail, on all three. **It cannot tell a compensated path from an
uncompensated one here**, so nothing it says about this project can be trusted -
including the 0.3542 that first looked like a worse version of the defect.

Two tangent points on a four-segment profile, with three segments uncovered,
says it is barely finding the finish pass at all.

## Ruled out first: not a regression of mine

`testing_14_inside` is NOT among the 36 configurations everything in
`analysis/080`-`102` was gated on - they are all `testing_15_*`, none a bore.
So the `orient` threading was never checked against it. Generated at HEAD and
at the commit before that change:

```
HEAD  5f1bb37139fc7ca2
pre   5f1bb37139fc7ca2   IDENTICAL
```

Not mine. But the gap is real: **no ID project is in the gate set**, and every
claim about bores in this session rests on nothing.

## What has to happen before the defect can be fixed

`prove_cam_comp` needs validating on ID work - check it against a number
already known, the standing rule for any probe. Until it discriminates,
`0.2929` and `1.4929` cannot be re-measured, and a fix to
`lathe_poly_pass.ngc` - motion, ID, compensation - would be unverifiable.

The proposed fix itself still looks right and is unchanged: `boring.ngc` and
`taper_id.ngc` already widen their post-comp radial retract by
`#<_tip_lead_w>`, and the polyline needs the same widening on the ENTRY side.
It is not being made blind.

## Kept

The two reproducers. They cost nothing, they carry the modes the note describes,
and they are where the instrument work will be checked.

## Correction, same day - the diagnosis above is WRONG

`prove_cam_comp` OVERRIDES the project when it generates:

```
{"param_n_comp": "2", "param_op": "2", "param_f_pass": "1", "param_pf_on": "0"}
```

It always tests IN-CAM FINISHING ONLY, whatever the project saved. So:

- **identical results across the three reproducers is EXPECTED**, not evidence
  of a broken instrument - all three were tested as In-CAM;
- the two reproducers are **pointless**: `n_comp` is overridden either way;
- `testing_14_inside` having `n_comp = 0` does not matter to this tool at all,
  so my first objection was also void;
- the wrong-side control DID fail correctly - gouge 0.8000, which is 2R, fully
  into the material - so the proof discriminates exactly as designed.

**The tool is not broken. The failure is real.** In-CAM compensation on this
bore leaves 3 of 4 profile segments UNCOVERED with a 0.3542 contour gouge, and
that is the defect to chase.

I reached for "the instrument is untrustworthy" - which has been true four times
today - without first reading what the tool does to the project. Being right
about instruments repeatedly is not a licence to assume it a fifth time.
