# Session 4 — 2026-08-10 … 15

82 commits on `liveTooling`, all pushed. Written before compaction, per the
standing rule added this session.

## What shipped

**Roughing correctness — the long chain.** Five stacked faults, each invisible
until the one above it was fixed:

1. two scans reading two sources — the stop scan moved onto the Python floor
   contour while the resume scan kept offsetting the record array (`analysis/029`)
2. the rapid lands at the LEAD-IN start, not the resume point, and the clamp is
   a **rate** — `lead_z` per `rough_cut` of level descent (`8fcabae`)
3. one flag answered two questions — where a level resumes, and whether phase 1
   stops here (`1b7db0b`)
4. a clamped stop candidate must not extend the cut (`3df0a4c`)
5. **the roughing floor was built from `resolve_points`, the RAW polyline**,
   while the stop and entry contours use `finish_profile`, the reachable one.
   testing_15_2's undercut collapsed the floor into a 24 mm flat 8 mm too deep.
   One line. This was the root of most of the chain (`5790e01`, `analysis/032`)
6. and then the envelope had to reach the bottom of the last descent — a
   descending segment never yielded a breakpoint at its own bottom (`288b936`)

**Contours and allowances**
- the anisotropic offset follows the curve's own normal; 66 direction reversals
  → 8 on testing_15_2 (`ac61573`)
- the entry contour sits one depth of cut above the **floor**, not the finished
  shape — closed three of greatEndian's six reports at once (`e27a858`)
- the pre-finish allowance is left on **every axis**, not only the radii:
  0.5080 → 0.7620 isotropic, 2.0000 → 2.2540 axial (`3df0a4c`)
- the pre-finish pass is gated on its own switch, via a **global** (`0d23128`)

**Features** — pecking with dwell (`6a4db91`, `9d866be`), tangential extension
front and back (`bd50c55`) and reaching roughing (`f7356af`), cut below the
inner radius (`7ebe403`), Z limits from the workpiece face (`14e50e3`),
front-flank warning and opt-in toolpath (`eab37b1`, `8b2da4e`), high feedrate
as a rate not a mode (`8f60e77`), CNC-side comp the default (`20916fa`),
re-entrant pockets named (`e44bb40`), UI panes at half (`d5afd34`), overlay
renames and Help entry (`efcea35`, `65b6672`).

## What was measured and deliberately NOT built

- **rest machining** — `test_leftover` reports zero wide regions on every
  project. Within one operation with one tool there is nothing to rest-machine;
  it is a second-tool feature (`analysis/047`)
- **undercut suppression** — cannot be roughing-only: the finish pass follows
  the record array, so a skipped pocket is still traced at finishing depth.
  NEEDS A CALL (`analysis/046`)
- **restart into the AXIS tab** — impossible. AXIS uses
  `Tkinter.Frame(container=1)`, and Tk destroys it when the embedded window
  goes. Proven by experiment; the answer is in-process rebuild (`analysis/048`)
- **back-to-front roughing** — the cuts DIFFER (45 vs 40, one shared), it is not
  a reordering. Rework at the choke point; gate written down (`analysis/052`)

## The instruments, which are the real output

`test_leftover` (metal, not tables — control now 21 of 21, `analysis/053`),
`test_x_continuity` (a pass that is ABSENT — greatEndian's own idea, and what
caught the fault three of us missed), `test_behind_boss_ladder`, `test_peck`,
`test_extension`, `test_z_datum`, `test_front_flank`, `test_high_feed`,
`test_section_length`, `test_pane_layout`, `test_below_inner_radius`,
`test_reentrant`, `test_comp_default`.

**The two gates are complementary.** `test_leftover` cannot see a single missing
pass on most geometry — measured, not suspected. `test_x_continuity` can.

## What went wrong, and the habits it bought

- **Five hypotheses reasoned from reading code; all five wrong.** Every fix that
  landed came from an instrument.
- **`ba3fb0c` crashed LinuxCNC** — a CALL argument cannot land atomically with
  its cfg, because a subroutine is re-read at runtime while a saved project
  keeps its template until loaded. Use a global.
- **Probes that produced confident nonsense** until anchored to a known number:
  wrong global names; an interpolator skipping vertical segments (three wrong
  conclusions); a filtered point list interpolated across; cut LENGTH reported
  as metal; `get_back_angle()` reading 0 because `saved_tool` is only set once
  the Tool Change RUNS; a harness validated against `tk.Frame` when AXIS uses
  `container=1`.
- **A unit test can pass while the feature is broken** — the tangential
  extension's diameter/radius bug, and the half-split that measured half in a
  harness and did nothing in the panel.

Habits added to CLAUDE.md and memory: *research, show the path, fix,
self-verify*; and *solve by agent, loop to a gate, verify independently, save
before compaction*.

## Open

41 points, listed in `openPoints.md`. Four need greatEndian: the suppressed
pocket, the obstruction a level clears at pre-finish, the wall pass, and the
1.5 mm gap on 15_6. One is free value: **collision detection is built and
tested but not wired**.

Known asymmetry worth remembering: **cfg defaults and bounds do not reach saved
projects** — the back-clearance range still reads −45…45 on existing ones, and
Native comp applies to newly-added features only.
