# 020 — Direct assertions on the roughing start and the retreat height

2026-08-08, branch `liveTooling`, from `ee5c977`.

## What was asked

greatEndian picked item (c) out of the housekeeping bundle in `openPoints`:

> **Nothing asserts the roughing start or the retreat height directly** — added
> 2026-08-04. `test_leads.py` covers the pre-finish and finish passes only. A
> regression in either would show up as `test_rough_comp`'s overcut number
> moving (0.0394 mm today), which is indirect and easy to explain away.

Both ends of a roughing level were changed twice in the previous session —
`analysis/010` (the level fell back to a raw profile Z, so the nose began
cutting 0.4 mm past the drawn segment) and then the Begin Z clamp — and neither
had a test of its own.

## What the levels actually do, measured

`testing_15_2` and `testing_15_4`, all three compensation modes, generated
headlessly and traced through `rs274`:

| | Begin Z | levels | starting on Begin Z | frontmost start | retreat |
|---|---|---|---|---|---|
| 15_2 Off | 0.0000 | 29 | 19 | Z0.0000 | r31.8160 |
| 15_2 Native | 0.0000 | 29 | 19 | Z0.0000 | r31.8160 |
| 15_2 In CAM | 0.0000 | 29 | 19 | Z0.0000 | r31.8160 |
| 15_4 Off | 0.0000 | 28 | 19 | Z0.0000 | r31.8160 |
| 15_4 Native | 0.0000 | 28 | 19 | Z0.0000 | r31.8160 |
| 15_4 In CAM | 0.0000 | 28 | 19 | Z0.0000 | r31.8160 |

No level starts in front of Begin Z in any mode. The retreat runs **1.8160 mm
clear of the r30.0000 bar** — `#<_wp_dia_od> + #<_x_clear>`, where `_x_clear` is
the tool's own nose diameter plus 1.016 — and **no roughing rapid removes
material** in any mode, measured by sweeping the real nose circle against the
material as it stands at that point in the program rather than against raw bar.

## The assertions, and why each is not circular

`test_rough_ends.py`, standalone like the rest.

1. **The start is Begin Z, both halves of the equality.** Nothing starts in
   front of it, and something starts exactly on it. The one-sided half alone is
   not enough and the O-code says so in as many words: the nose shift moves the
   start *past* the reference, and a "never in front of it" test lets that
   through — which is the bug `analysis/010` fixed.

2. **It tracks.** Assertion 1 alone would pass on a program that always started
   at Z0.0 for reasons of its own, because Begin Z is 0.0 in every saved
   project. The same project is generated again with Begin Z at −5.0 and the
   start has to move exactly with it. This is the assertion with teeth.

3. **Compensation does not move it.** Off, Native and In CAM on the same Z.
   The same asymmetry `analysis/009` and `analysis/010` each found at opposite
   ends of a pass: one end carrying the nose while the other did not.

4. **No roughing rapid removes material** — the retreat height, measured, not
   read off the code.

5. **The return traverse clears the stock envelope**, which states the retreat
   height as a number instead of as an absence of collisions.

The stock is read out of the program (`#<_wp_dia_od>`, `#<_wp_z>`) rather than
hard-coded, so a project whose bar changes cannot quietly invalidate 4 and 5.

`begin_z()` reads the **last** `#<_pl_begin_z>` assignment, not the first:
`create_defaults` writes a 0.0 placeholder at the top of every program so the
load-time pre-parse finds the name defined, and the polyline assigns the real
value later. Reading the first match gets the placeholder and the whole file
passes against a program that ignores Begin Z entirely.

## Negative controls — both run, both fire

Not a code review. Each fix was removed from a private copy of `lib/` and the
measurement re-run.

**NC1, the Begin Z clamp deleted** (`#<z_start> = #<_org_z>` removed):

```
Off     start Z1.0000    (with the clamp: Z0.0000)
Native  start Z0.6000    (with the clamp: Z0.0000)
```

That fails assertion 1 (1.0 is in front of Begin Z 0.0), assertion 3 (Off and
Native disagree by exactly the 0.4 nose shift) and assertion 2. It also
reproduces `analysis/010`'s finding exactly: without the clamp the start falls
back to the window start minus the orientation term, so the two compensated
modes start 0.4 mm from where Off does.

**NC2, the full retract lowered 2 mm inside the bar**
(`G0 X[#<_wp_dia_od> + #<_x_clear>]` → `G0 X[#<_wp_dia_od> - 2.0]`):

```
baseline          worst rapid cut 0.0000 mm    lowest traverse r31.8160
retreat -2 mm     worst rapid cut 1.0000 mm    lowest traverse r29.0000
```

Both retreat assertions fire.

The file also carries its own aliveness check for assertion 4, because that one
reports 0.0000 mm on a healthy program and a measurement that can only ever say
zero says nothing: a synthetic rapid driven 1 mm inside a 30 mm bar must be
caught by the same code path before the real answer is believed.

## What went wrong on the way — and it cost the repo a file

Building NC1 deleted `lib/lathe/lathe_level_pass.ngc` **from the repository**.

The scratch config is a copy of `configs/sim/axis/ncam_demo`, and the plan was
to patch the copy's `ncam/lib/lathe/lathe_level_pass.ngc` so the repo was never
touched. What was missed: **NCam recreates `<config>/ncam/lib` as a symlink into
the repo every time it generates.** The copy was dereferenced into real files
first, then generation replaced that directory with a link, and the `os.remove`
that followed resolved through the link and deleted the real file.

Two runs before that had silently measured nothing for the same reason — the
patched copy was overwritten by the symlink during generation, so `rs274` read
the unpatched repo file and reported the baseline numbers. The tell was a
`(DEBUG, ...)` marker inserted into the patched sub that produced **zero**
`MESSAGE` lines in the canon, and then a deleted file that did not stop the run.

Recovered with `git checkout -- lib/lathe/lathe_level_pass.ngc`; the file was
committed at `468a4f1` and unmodified, md5 `5e220d6b`, 785 lines, and
`test_rough_comp` was re-run afterwards to confirm the restore.

The rule this yields, now in `LEARNINGS-LOG.md`: **replace the `ncam/lib`
symlink itself after generation, never write to a path underneath it.** The
sequence that works is copy config → generate → `os.remove` the symlink →
`copytree` the repo `lib` into its place → patch → run `rs274`, which is safe
because subroutines are re-read at runtime.

## Still unknown

- `test_rough_comp` reports Off 0.1116 / Native 0.0503 / In CAM 0.0503 today,
  where `openPoints` records 0.0394 on 2026-08-04. The subroutine is
  byte-identical to `HEAD`, so the number moved with the commits made after
  that note, not with this work. Nobody noticed, which is the argument for this
  file existing.
- The retreat is asserted on **OD** work only. The stock-clearance check
  disables itself when the levels are not below the bar, so an ID polyline gets
  assertion 4 and not 5.
- Begin Z **in front of** the profile start is not covered. With Begin Z 2.0 on
  a profile starting at Z1.0 the clamp deliberately does not fire and the start
  is the window start minus the nose term — Off Z1.0000, Native Z0.6000. That
  is the documented behaviour of a one-sided rule, not a fault, but no test
  states it either way and the O-code notes the `z_dir −1` case is untested.
