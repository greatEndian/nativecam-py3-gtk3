# Session 3 — 2026-08-04 to 08-08, branch `liveTooling`

From `8394aa4` to `468a4f1`. Everything pushed, tree clean apart from an
untracked AXIS `autosave.halscope`. `openPoints.md` is what is LEFT; this is
what HAPPENED.

## Delivered

**Roughing path faults, all measured and negative-controlled**

| commit | fault | number |
|---|---|---|
| `91e8cf9` | a level swept **through the boss** with the pre-finish pass off | 2.7697 mm into it, 11 of 31 cuts |
| `df0a9e9` `03c7aa8` `c66fae0` | passes started 1.0 / 0.6 mm in front of Begin Z | all three pass types now start there |
| `3727e16` | Sectioning defeated *Space passes from* | remainder was at the contour, now at the stock |
| `2827c51` | thin pass at the stock envelope | `Skip thin roughing passes`, 0 = off |
| `cf29e14` | stop extension carried a level **19.4436 mm** beside the pre-finish | bounded; legitimate ones are 0.90-1.0034 |
| `e8d97f9` | the scan held **1.016** off the profile where 0.762 was configured | Final-contour anchoring reassigns `step_target` |
| `81b4405` | leads capped to 0.125 on the first interval | now the property's 1.000 |
| `7ed2cea` `468a4f1` | the chamfer pass: length and shape | 1.052 mm, lead-in / cut / lead-out |

**Preview** — `141ff47` dashed roughing entry+stop overlay; `b2879c2` the
**pre-finish SURFACE** and a legend that says which lines are surfaces and
which are tool paths; `82a1bac` `_rough_contours` moved onto `PreviewPane`
after it blanked the plot on every draw.

**`331186f`** Send ▸ dropdown can hand LinuxCNC the **flat G-code**. Verified
the same motion: 241 = 241 non-zero feeds, 843.3072 = 843.3072 mm, endpoint
sets identical. `FLAT_HEADER`'s claim that work offsets are baked in was wrong
- setting G54 Z to 12.0 leaves the canon byte-identical - and that claim was
the only reason it said "not a program to load".

## Reverted, and why

- `57eea44` roughing retreat clamped to the stock - stretched every retreat
  past the 1 mm the properties ask for.
- `224c0b9` level truncation - built on `level - stop_contour`, which is what
  is left BELOW a level rather than what it takes. Cut 10 honest passes to
  1.299 mm.
- the lead cap - a lead takes its property value, it is not scaled to the cut.
- the descent onto the contour - once the extension reached the feature
  boundary it only added an 0.081 mm move between cut and lead-out.

## What went wrong

- **One complaint, six wrong readings.** The chamfer pass. Truncate the level;
  cap the leads; read "tangent" as touching; treat "too short" as tangency;
  clamp to an arbitrary length; keep a descent that had become redundant. Two
  `AskUserQuestion` calls with the geometry written out settled what six
  attempts had not. **The rule: when a reading has been wrong twice, ask with
  numbers.** It went into `analysis/019` after the fourth miss.
- **A committed finding had to be retracted.** `9af9201` reported compensated
  roughing overcutting the steep wall by 0.1643 mm; `3bcad37` refuted it. The
  metric compared radius-at-Z across an 83 degree wall where one column spans
  0.54 mm of radius - the exact trap `test_rough_comp`'s own docstring
  documents. Seventh baseline-class metric error of the work.
- **An invalid bisect.** `lib/*.ngc` are read at rs274 RUNTIME, so checking out
  an old lib and parsing a separately-generated file measures nothing: six
  commits gave byte-identical output, and matching md5s gave it away.
- **String-grep tests pass while the code is broken.** Every check on the
  roughing overlay was a grep; all passed while `_rough_contours` sat on the
  wrong class and blanked the plot. They import and use `hasattr` now, with the
  converse asserted so the check is shown to discriminate.
- A script named `bisect.py` shadows the stdlib module.

## Next, in order

1. **One ladder floor for the whole part** (`openPoints`, `analysis/019`). On
   testing_15_4 it comes from Final Diameter r19 and applies everywhere, which
   is why the chamfer gets levels that only graze it AND the cylinder gets one
   0.016 from its pre-finish contour. Several of this session's fixes are
   working around it.
2. The **Sectioning crash** and the **restart button**.
3. `taper_id` / `boring` / `facing` roughing compensation.
