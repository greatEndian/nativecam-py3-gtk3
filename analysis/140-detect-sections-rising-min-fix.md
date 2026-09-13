# 140 — detect_sections' rising-section min_x fixed at the root

**Asked**: fix `detect_sections()` reporting the wrong `min_x` for a rising
(monotonic non-decreasing) section — `analysis/130`'s finding, not fixed
there. Choose between fixing the root (`detect_sections` itself) or only the
consumer(s) that assume `min_x` means "deepest material in this region", and
justify the choice with real numbers.

## The fix

```python
sec_z_from = pz
sec_min_x = px          # was: float('inf')
```

On a category change, `sec_z_from` was already seeded from the pivot vertex's
own Z (`pz`); `sec_min_x` reset to `float('inf')` instead of the same pivot's
own X (`px`), so it was next updated only by whatever point the loop happened
to process in that same iteration — the section's far end for a rising run,
or (for a run absorbed between two same-Z boundaries) an intermediate vertex,
never the true minimum, which for a monotonic non-decreasing run can only be
at its own start. Seeding with `px` mirrors exactly how the very first
section is already seeded from `points[0]` before the loop starts.

## Blast radius — the three consumers, read before touching anything

| consumer | uses `min_x` from `detect_sections`? | reaches motion? |
|---|---|---|
| `split_peaks` → `_boundary_list` | **No.** `_boundary_list` takes only the `(z_from, z_to)` spans (`_m` discarded) and recomputes its own minimum via `_side_min`, deliberately NOT reusing `detect_sections`' value (`analysis/057`) | Unaffected by construction |
| `_split_level_intervals` | Takes `sections` only to pass spans into `_boundary_list` again | Unaffected by construction |
| `section_windows` → `rank_weakest_first` | Yes, for **ordering** same-band sections in Natural mode (`sect_mode` 0) — the window's own `(z, r_lo, r_hi)` bounds come from `band_windows`' independent `boundary_height`, not from this ordering | Only reaches motion if a rising-non-first section exists AND shares a band with another section AND the wrong rank changes tie-break order — **zero shipped projects have a rising-non-first section that could exercise this**, see below |
| `floor_regions` → `floor_ladder` → `build_floor_ladder_gcode` | **Yes, directly**: `region_floor(min_x, ...)` becomes a real roughing-floor radius written to `#3380+` (`SECT_FLOOR_BASE`) and walked by the re-anchored roughing ladder | **Yes — this is the real, currently-wired consumer**, live via `cfg/lathe/polyline.cfg:842`'s `<exec>` |

## Option chosen: (a), fix the root

`detect_sections`' own contract (used by `floor_regions`' docstring: *"min_x
IS that region's deepest material"*) already promises the corrected
behaviour; `_side_min` exists ONLY because analysis/057 hit this same flaw
once and worked around it locally rather than fix the root, and that
workaround was never generalised to `floor_regions` — this is the second
consumer bitten by the identical bug for the identical reason. Fixing the
root removes the trap for every future caller instead of adding a third
one-off re-derivation (after the original wall-only version and `_side_min`)
that duplicates "find a section's true minimum" logic yet again — exactly
the anti-pattern this project's own history warns about.

## Measured before deciding, not assumed

A direct scan of the raw XML for `detect_sections`' inputs (bypassing the
full generation pipeline) initially reported **zero** of the 46 shipped
projects touching a rising-non-first section at all — which would have made
this a zero-risk, low-value fix. That scan was **wrong**, and finding out why
is itself worth recording: `lathe_sections.py` publishes several module-level
globals (`DIAMETER_MODE`, `WORKPIECE_FACE_Z`, `TOOL_NOSE_R`, …) as a side
effect of a full `to_gcode()` walk over every feature in order; calling
`resolve_points`/`detect_sections` on a `Feature` reconstructed in isolation,
without first walking the whole project through `to_gcode()`, silently used
stale/default values for those globals and produced a **different `points`
list** than real generation does — invalidating the whole scan without
raising an error. Caught by instrumenting `detect_sections` itself
(monkeypatch, trace its real call arguments) during an actual
`app.to_gcode()` walk and finding it disagreed with the standalone scan on
`testing_0.xml`, a project the standalone scan had called clean.

**Lesson for the next person who wants to probe this module standalone**: run
`app.to_gcode()` once (or use the real `gen_project.py` pipeline) before
calling any `lathe_sections` function directly — reconstructing a bare
`Feature` from saved-project XML is not enough to reproduce what generation
actually feeds these functions.

## The real measurement, done properly

Baseline captured with `test_motion_fingerprint.py --write` **before any
edit** (required — unrecoverable otherwise), fix applied, re-run alone (no
concurrent sweep):

```
46 identical, ... -> 30 identical, 16 changed, 0 not in the baseline, of 46
```

Reproduced identically on a second, independent run — the pipeline itself is
deterministic; this is not sweep noise.

**Every one of the 16 changed projects is the same, single mechanism**,
confirmed by tracing `detect_sections`' real calls (old vs. old, via
`git stash` A/B on `lathe_sections.py`, monkeypatch-capturing arguments and
return value during a real `app.to_gcode()` walk) for all 16: a rising,
non-first section's `min_x` moves from its far (shallow) end down to its own
true start — exactly the documented fix, on real project geometry, never a
different or unexpected shape of change.

## Why it reaches motion: floor_ladder correctly drops a spurious stage

Traced `floor_regions`/`floor_stages` directly (not guessed) for the
smallest, middle, and largest cases:

**`testing_0.xml`** (count unchanged, 54 → 54, hash changed). Sections
`(0.5,-5,40)`, `(-5,-10,45→40)`, `(-10,-25.4,45)`. OLD: regions
`(0.5,-5,20.762)`, `(-5,-25.4,23.262)` → two floors kept, `#<_pl_floor_n> = 2`.
NEW: the corrected rising section (`min_x=40`, matching the flat section
before it) merges into the FIRST region → regions `(0.5,-10,20.762)`,
`(-10,-25.4,23.262)`. The second region is now the flat tail at diameter 45
(radius 22.5) uniformly, and `floor_ladder`'s own pre-existing
`region_cut_length` filter — *"a floor taken from a single point is not a
floor... a level there cuts nothing worth an approach"* — correctly measures
**0 mm** of cuttable Z at floor 23.262 there (profile+allowance sits exactly
AT 23.262 everywhere in that span, never under it) and drops the stage. The
OLD boundary, drawn one segment too early by the wrong `min_x`, had
accidentally included part of the genuinely-rising material in that
same span, which DOES need real cutting under 23.262 — so the spurious stage
survived the filter by accident on the wrong geometry. Confirmed against the
real generated `.ngc`: OLD's `#3380/#3381 = 23.262/20.762` block is gone
entirely in NEW (`build_floor_ladder_gcode`'s own `len(floors) < 2: return ''`
guard fires), and the ladder constants shift from the two-stage
`_pl_lad_ltgt=23.262, np=14` to the single-target `_pl_lad_ltgt=20.762, np=19`
— more levels, because one continuous descent to the (unchanged) real target
replaces two separately-anchored stages.

**`testing_12_0.xml`** (count 180 → 192). Same mechanism: OLD kept a spurious
intermediate floor 24.2976 (from a wrongly-early boundary at Z-15); NEW
correctly merges it into the region ending at Z-18.535, leaving a single
floor 13.6909 — the SAME deepest target both times.

**`testing_13_arcs.xml`** (count 3076 → 3041, the largest change). OLD's
seven raw regions collapse through the existing merge-if-close and
cut-length filters to two floors, `12.7817` and `8.762`; NEW's four
(correctly-bounded) regions collapse to just `8.762` — again the identical
deepest target, one fewer artificial stage.

**The invariant checked across all 16, not assumed**: the DEEPEST floor value
— the actual final roughing target — is bit-for-bit identical old vs. new in
every single case. What changes is only whether an intermediate re-anchor
stage was real or an artifact of a wrongly-placed section boundary:

| project | OLD floors | NEW floors | deepest matches |
|---|---|---|---|
| testing_0 | 23.262, 20.762 | 20.762 | yes |
| testing_1 | 23.262, 20.762 | 20.762 | yes |
| testing_12_0 | 24.297534, 13.690932 | 13.690932 | yes |
| testing_12_2 | 27.833068, 20.762 | 20.762 | yes |
| testing_12_3 | 27.833068, 20.762 | 20.762 | yes |
| testing_13_arc_first(_0,_1) | 12.781733, 8.762 | 8.762 | yes |
| testing_13_arcs | 12.781733, 8.762 | 8.762 | yes |
| testing_2 | 23.262, 20.762 | 20.762 | yes |
| testing_3 | 23.262, 20.762 | 20.762 | yes |
| testing_5 | 23.262, 20.762 | 20.762 | yes |
| testing_6 | 24.262, 20.762 | 20.762 | yes |
| testing_7 | 23.262, 20.762 | 20.762 | yes |
| testing_8 | 26.762, 21.762, 20.762 | 20.762 | yes |
| testing_9 | 21.762, 20.762 | 20.762 | yes |

Every one of the 16 changes collapses from 2–3 floors to exactly 1 — meaning
`build_floor_ladder_gcode` now correctly returns `''` for all 16 (its own
`len(floors) < 2` gate), and roughing reverts to the plain single-floor
ladder `poly_lathe_mill.ngc` has always had, exactly as it would if the
multi-floor feature (`analysis/126`, shipped this week) had never fired on
these profiles at all — which, now correctly measured, it never should have.
This also explains why none of the `testing_15_*`/`testing_14_*` profiles —
the ones deliberately built with genuinely distinct floors for that week's
work — appear among the 16: they have no rising-non-first section for this
bug to touch, or their real, distinct floors survive the fix exactly as
before.

**Direction is always safe**: the finish and pre-finish surfaces are
untouched (this bug never reached them); the deepest roughing target never
moves; the only change is removing a re-anchor stage that cut zero
measurable material, per a filter that already existed for exactly this
purpose. Nothing here can gouge or skip real material — the roughing scan
itself still stops on the real profile+allowance at every level regardless
of which stage structure the ladder uses.

## Also verified

`check_tangent.py` on `testing_13_arcs` (the largest change, 35 fewer moves):
`min |dot| = 0.99946` (threshold 0.999) — **[VERDICT: PASS]**. The finish
pass this checks is untouched by this fix by construction (it only reads
`floor_regions`/`floor_ladder`, never the finish contour), so this confirms
the whole program — not just the roughing ladder in isolation — still runs
clean.

## Regression test

`test_sections.py::test_detect_sections_rising_min` — property-based, not a
single pinned number: asserts every non-first RISING section reports its own
start, and (as its own negative control) that every FALLING/FLAT section is
unaffected. Includes `testing_0.xml`'s exact real shape and an unambiguous
zigzag (sloped segments only — a vertical wall sitting exactly on a section
boundary is a different, already-solved question, `_side_min`'s, and mixing
it in would make "the true minimum sampled from this section's own points"
ambiguous for reasons unrelated to this bug). Verified failing on the
pre-fix code (5 of the new checks fail with the old `float('inf')` reset,
confirmed via `git stash` A/B) and passing on the fix.

## Gates

```
flake8 (core files)                                    exit 0
flake8 ncam_*.py lathe_sections.py                      exit 0
python3 cam_map.py                                      exit 0 (9/9)
python3 test_cam_map.py                                 exit 0
python3 test_lathe_validation.py                        exit 0
python3 test_sections.py                                exit 0 (incl. new regression test)
python3 test_sectioning_windows.py                      exit 0
python3 test_geometry_primitives.py                     exit 0
python3 test_surface_equality.py                        exit 0 (46 generated, 38 compared)
python3 test_project_sweep.py                           exit 0 (45 clean of 46, default_template.xml expected)
python3 test_motion_fingerprint.py --baseline           30 identical, 16 changed, 0 missing, of 46 - all 16 explained above
check_tangent.py on testing_13_arcs                     [VERDICT: PASS], min |dot| = 0.99946
```

`test_rough_ends.py` untouched, left failing per its own open question
(tip-vs-cut semantics, greatEndian's call, not this task's).

## Concurrency note

Two other Sonnet sessions landed commits on this branch while this work was
in progress (`37c1952`, `9230065` — unit-test coverage for other pure
functions in `lathe_sections.py`). Both explicitly checked and skipped
anything reaching `detect_sections`/`floor_regions`, deferring to "the
parallel session" (this one) — neither touched `lathe_sections.py`. Verified
by reading both commits' diffs before proceeding; no corruption, no
overlapping edits.

## What is still unknown

- Whether `section_windows`' Natural-mode ordering path (the one real
  consumer this fix ALSO protects, alongside `floor_regions`) is exercised by
  any project outside the 46-project demo catalogue — not checked, out of
  scope for this task's required gate.
