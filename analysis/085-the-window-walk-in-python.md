# 085 — the window walk, and the top of the roughing stack

**Asked**: greatEndian, 2026-09-03 — *"go on with the window walk"*, the layer
`analysis/084` named as last.

## The stack, now that it is complete

Each layer was proved **given the one above it**, working down:

```
window    085   this file
sub-span  084
interval  083
level set 080 / 081 / 082
```

`roughing_windows()` is the top. **Nothing in the toolpath reads any of it.**

## Three shapes, and the index is part of the answer

- **Sectioning off**: exactly ONE window over the whole profile. The runtime
  computes `w_len` as the whole span **plus 1** precisely so the first window
  swallows everything. `sec_len` belongs to Artificial mode and is consumed at
  generation time - letting it slice here made the Sectioning switch appear to
  do nothing.
- **Artificial** (`sect_mode` 1): the table windows alone, `w_idx` from 0. No
  ceiling phase - every window takes the full roughing depth in its own span.
- **Natural**: a phase-1 window over the whole profile at index -1, then the
  table windows.

The index is not a counter. `lathe_level_pass` records each window's deepest
cut at `#2800 + w_idx` and reads its NEIGHBOURS back to decide whether an entry
lead has metal to enter, so an index is a **position along the part** - which
is why Natural ordering windows weakest-first and Both directions alternating
the entry end do not break it.

## The Z bounds are predicted, not taken

Only the profile's RAW first and last Z come out of the record. Python applies
the back extension and then clamps into the Z limits - **that order on
purpose**, a limit being a hard bound where an extension is a request.

That clamp is not cosmetic. Skipping it was a safety bug: roughing read the raw
record array while every contour read the trimmed tables, so a level that did
not cross the trimmed profile had nothing to stop it and ran the full bar -
measured on testing_15_5 at Z-70.8000 against an End Z of -40.

## Numbers

```
30 configurations, 179 windows, 152 with a radius band, 27 ceiling phases
```

Every window: index, Z span and radius band. Three coverage checks assert the
banded windows and the ceiling phase are actually exercised rather than
defaulted past, and a control re-runs each configuration under the OTHER
sectioning mode and requires a different sweep.

## What is deliberately NOT claimed

`lvl_start` and `lvl_floor` - what each window does with its ladder. Those
belong to the ladder layer, and on Natural sectioning they depend on the
**phase-1 handover**: `poly_lathe_mill` reassigns `sect_top_r` when phase 1
stops on an obstruction, and sets `_pl_ph1_front_cut` / `_pl_ph1_z_end` from
how far it actually got.

**That feedback is the one thing in the whole roughing stack that is not a
generation-time question.** Everything else is now a table walk Python can
reproduce; this is a runtime OUTCOME feeding back into the geometry the later
windows use. It is why the window layer was left until last, and it is the
honest boundary of the migration: a `.ngc` that merely walked tables would have
to either drop the handover or keep that one decision at runtime.

## Gates

`test_roughing_windows` (new), `test_sub_spans`, `test_level_intervals`,
`test_level_blocked`, `test_ladder_account`, `test_ladder_python`,
`test_ladder`, `test_leftover`, `test_x_continuity`, `test_ramps`,
`test_sections`, `test_bidir_warn`, `cam_map`, flake8. Motion untouched: no
`.ngc` or `cfg` edited, and the instrument is proved inert.

## Correction, 2026-09-03

The boundary this file names - the handover reassigning `sect_top_r` - was
reasoned from reading, not measured. All three of its sites fire **0 times**
over the same 30 configurations. See `analysis/086`. What fires is the narrower
`_pl_ph1_front_cut` / `_pl_ph1_z_end`, in 6 of 30.
