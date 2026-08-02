# Session 0 — 2026-08-01 / 08-02, branch `liveTooling`

From `c126a76` to `4a549ae`. Everything below is pushed; the tree was left
clean. Open work lives in `openPoints.md` — this file is the record of what
happened, that one is the record of what is left.

## Delivered

**Preview / simulation**

- `3b47eb5` Pre-finish passes coloured apart. Move category and feed rate were
  both *measured* as discriminators and both failed; the marker the subroutine
  writes is the only ground truth. `poly_lathe_mill` brackets the pass, the
  parser keeps nested markers (`Move.subs`).
- `a8118fb` Every lathe op brackets its finishing pass — facing, turning,
  boring, both tapers, radius_od, polyline. Five appear in no saved project, so
  `test_phase_markers.py` calls them directly.
- `859f7d2` Pane fits the panel: **522 px → 281 px** minimum width, 3 control
  rows → 1. A `Gtk.FlowBox` was tried and rejected on measurement (uniform
  columns, 208 px of height for nothing); a `Gtk.Menu` is its own X window and
  is not clipped by the embedded panel.
- `068d1a5` **Flat tab** — the program as plain G-code. 26,862 canon lines →
  299. Proved by re-running it: 235 moves, worst difference 0.000000 mm.
- `4896b94` **Info + Statistics**, with a real time estimate: G94/G95 and
  G96/G97 handled, unknown-rate moves counted and never guessed.
- `fdfa99d` **Collision detection**, tested but deliberately **not wired** —
  its output depends on the unresolved tool-shape question.
- `be094c2` **AXIS crash fixed**: a GLib timeout outlived the panel and took
  LinuxCNC down with an X BadWindow. Diagnosed by reasoning, not reproduced.

**Tool geometry**

- `2fb8048` Flank length moved to the Tool Change; grey tool silhouette drawn,
  in millimetres rather than pixels.
- `1e81103` Tool-table angles are measured **off the perpendicular** — an edge
  sits at 90 − angle from Z. This made the drawn tool agree with the shadow
  ramp for the first time. Holder face is the tangent on the *back* of the nose.
- `1cb2c8e` One grey for the whole tool.

**Lathe G-code**

- `310a06b` The accessible contour treats the flank as **unbounded** —
  greatEndian withdrew the premise the release was built on. Paused behind
  `FLANK_BOUNDS_CONTOUR`, not deleted.
- `d2bb5f8` **Back-angle clearance**, default 2°, so the artificial wall stands
  off the flank instead of rubbing along it.
- `163b0e4` A skipped roughing pass no longer **feeds into the part**; off by
  default.
- `4226c13` `d5384b5` `125f644` **The entry contour, in Python**, and levels
  now start on it.

## The lead-in work, in detail

The session's largest thread. Target: roughing levels entering the volume
behind the highest peak started **4.512 mm short in Z** of the ramp, 36.1 mm of
uncut metal on testing_15_2.

- **Step 1** — the constant, *printed not derived* after two derivations came
  out wrong: `cross_t = 1.016 mm`, the finish offset 0.508 plus one whole
  roughing depth of cut from *Space passes from = Final contour*.
- **Two failed attempts**, both reverted and both understood: changing the
  shared allowance moved phase 1's *detector*, not the cutter; changing phase
  2's own calls made `lathe_level_pass` reject the interval as blocked.
- **Step 2a/2b, Python-first** — `entry_contour()` offsets the contour once at
  generation time and emits a table; `lathe_level_pass` walks it. Result:

  | | before | after |
  |---|---|---|
  | gap per level | 4.512 mm | **2.254 mm** |
  | uncut behind the peak | 36.1 mm | **20.3 mm** |
  | roughing cut length | 466.4 mm | **487.0 mm** |
  | gouges | 0 | **0** |
  | ends of levels not behind the peak | — | **unchanged, all 18** |

## Decisions taken (do not re-litigate without asking)

- **Python first, O-code last** — `c6ea3b0`, now at the top of `CLAUDE.md`.
- The accessible contour treats the flank as **unbounded**.
- Roughing enters at **one roughing depth of cut** from the contour.
- The stop kept the floor allowance *while the start moved*; that is now
  superseded — see the endings item in `openPoints.md`.
- Skip-short passes **off** by default; back-angle clearance **2°** default.

## What went wrong, and the method it produced

Three wrong readings, all from the same cause: **measuring against a stale
artefact.** An `.ngc` generated earlier in a session is not a safe baseline,
and neither is a toolpath parsed earlier — `parse_program` re-runs the
interpreter against whatever `lib/lathe` is on disk *at that moment*. One
"correction" was itself wrong and had to be retracted.

**Generate and parse both sides in one run, under the file state you mean.**

Two more worth keeping:

- A silent factor of two in `entry_contour`: the profile arrives in
  **diameters** and the offset is a **radius**, and a perpendicular offset is
  not the same construction in the two spaces. Caught only by cross-checking
  against the interpreter's own scan — the code read as correct.
- Two O-code traps, both hit: a 15th CALL argument kills the program with
  `Command too long`, and a local first assigned inside a branch reads as *not
  defined* under load-time pre-parse.
