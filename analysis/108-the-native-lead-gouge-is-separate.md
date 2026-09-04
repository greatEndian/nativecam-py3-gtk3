# 108 — the native lead gouge is a separate defect, and it is only the leads

**Asked**: greatEndian, 2026-09-04 — *"measure the native 1.4929"*.

## Measured

`prove_cam_comp` could not test native compensation - it hard-coded
`param_n_comp: '2'`. A `--mode` flag now chooses, defaulting to 2 so every
existing invocation is unchanged. The proof itself is mechanism-blind, which is
the whole point of having it: both compensations must pass the same test.

On `testing_14_inside_bar` - the stepped bore with a right-hand boring bar,
after the offset fix in `analysis/107`:

```
In-CAM  (mode 2)   contour 0.0000 PASS    whole path 0.0000    27 tangent points
Native  (mode 1)   contour 0.0000 PASS    whole path 0.8000   227 tangent points
```

**Under native compensation the CONTOUR is correct** - the interpreter offsets
it properly - **and the LEAD-IN/OUT gouges by 2R**, the full nose diameter.

## So they are two different faults

`analysis/107` fixed the In-CAM path, where contour AND leads both come from
`offset_contour`; both are now 0.0000.

The native leads are emitted by `lathe_poly_pass.ngc` and never touched
`offset_contour`, so they are untouched by that fix. This is the fault the
notes described as **1.4929 mm ID lead-in/out, native** - and it measures
0.8000 here, on a different part and tool from whatever produced 1.4929.

That also means the fix the notes proposed - widen the entry by
`#<_tip_lead_w>`, mirroring `boring.ngc` and `taper_id.ngc` - is the RIGHT fix
after all, but for the NATIVE path only. `analysis/107` was right that it would
not have fixed In-CAM; it is wrong to conclude it fixes nothing.

## What it looks like

2R is the signature of an approach that reaches the wall before compensation is
established, or leaves after it is cancelled - the round nose swinging into the
finished surface. `boring.ngc` and `taper_id.ngc` already widen their post-comp
radial retract for exactly that reason; the polyline needs the same on its
entry.

## Not fixed here

`lathe_poly_pass.ngc` is motion, ID and compensation at once. The gate is
already in place and is the one this used: `--mode 1` on
`testing_14_inside_bar` must bring `whole path` to 0.0000 while the contour
stays 0.0000 and the wrong-side control keeps failing - plus `--mode 2` and the
36 OD configurations unchanged.
