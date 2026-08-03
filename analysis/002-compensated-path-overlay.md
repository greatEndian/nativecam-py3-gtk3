# 002 — Making tool nose compensation visible in the preview

2026-08-03. Asked by greatEndian; the request contained a question that turned
out to be already answered, and a real gap underneath it.

## What was asked

*"we need to add new contour/new preview which represents path after
compensation because now we see uncompensated I think — or show the real preview
but moving the tool will be managed by compensated path to be precise also
during the path preview simulation"*

Also: *"add property to each polyline and default is the CNC side"*.

## What was measured

**The drawn toolpath is already the compensated path.** `parse_program` runs
`rs274` and reads the canon, which is emitted *after* the interpreter applies
`G41.1`/`G42.1`. The proof is the surface measurement already in the repo: it
sweeps the nose circle along the drawn path and compares to the programmed
contour, reporting

    Off 0.1094    Native 0.0080    In CAM 0.0080

from identical code. The only thing differing between those runs is the path, so
the path must be post-compensation. The simulated tool therefore already moves
on the compensated path — the second half of the request needed no work.

**The default is already the CNC side.** `cfg/lathe/polyline.cfg`'s
`PARAM_N_COMP` is `value = 1`, Native LinuxCNC. Every polyline already carries
the property.

**But every saved project has compensation OFF:**

    testing_11        n_comp = 0
    testing_13_arcs   n_comp = 0, 0
    testing_15_2      n_comp = 0, 0
    testing_15_3      n_comp = 0, 1

and the live generated program carries `#3159 = 0`. So on the project in front
of greatEndian there is genuinely no nose compensation in the path — the pass
still holds its allowance through `G41.1 D[2*shift_r] L0`, but no nose. Their
reading was right; the cause was not the preview.

## What was done

A teal overlay showing where the control point travels once compensation is
applied, from `lathe_sections.offset_contour` — the same function In CAM emits —
following the existing callback route (`_contour(cb)`, drawn by `_draw_profile`,
gated on the existing Display ▸ Contour toggle). The legend gains the swatch
**and the mode**: `comp: CNC` / `comp: CAM` / `comp: off`. The mode is the part
that actually answers the question.

With compensation off the overlay draws **nothing**. A line lying on the profile
would claim a compensation that is not happening, and off is the state every
saved project is in.

## The overlay is a self-check, and it earned that on the first run

Python predicts; the interpreter does. `test_comp_overlay.py` compares the two:
generate the project in **Off** mode, whose last finish pass carries
`shift_r = 0` and so applies no offset at all — that path *is* the programmed
profile — then offset it in Python and compare against a **Native** run of the
same project. Not circular: two different runs, two different mechanisms.

First run reported 0.8566 mm apart, which looked like a fault. It was not:

    idx  0  Z  1.3071  gap 0.3061   lead-in, before the contour
    idx  1  Z  0.6000  gap 0.1172   the comp entry point
    idx 25  Z-29.9846  gap 0.0001   <- the contour body
    idx 36  Z-70.4000  gap 0.1172   lead-out
    idx 37  Z-70.0000  gap 0.1172
    idx 38  Z-69.2929  gap 0.8566   the retreat into air

Every disagreement is a lead move, which the overlay deliberately does not draw
and which is placed by the orientation-aware entry rule rather than the contour
offset. **Along the contour the two agree to 0.0001 mm** — 34 points, worst
0.0001. The test excludes exactly those five and asserts that at least one of
them still differs, so the exclusion cannot quietly grow to hide a real fault.

No corner exclusion was needed: at a convex vertex the interpreter rolls the
nose round on an arc and Python emits the same arc as chords under a 0.005 mm
sagitta bound, so they agree there too.

## Still unknown

- **Whether the saved projects should be switched to Native.** greatEndian's
  call, not a migration to slip in. It matters: with all of them Off, the
  Native path is only ever exercised by the measurement harness, never by
  anyone opening a project.
- Whether the teal reads well against the profile in AXIS at working zoom. Only
  greatEndian can say, with a polyline switched to Native.

## Verified

- overlay absent with `n_comp = 0`, present with `1`
- prediction against interpreter: 34 contour points, worst 0.0001 mm
- motion unchanged — testing_15_2 Off 0.1094 / Native 0.0080 / In CAM 0.0080
- flake8 both lists; fifteen `test_*.py` green, including `test_preview_ui`
