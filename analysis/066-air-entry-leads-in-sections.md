# 066 — entry leads into metal that is already gone

**Asked**: greatEndian, 2026-08-31, with `photo/leadInPresent_2.png` — *"from
stock envelope to part profile are behind the boss element present all
sectionning passes artificial lead ins extensions which are necessary only at
the part prefinish contour contact .. 10th section from the front could have
skipped artificial lead in from 1-3 passes and only 4th in the part contact it
should has it"*.

## What was measured

`testing_15_9.xml`, Artificial sectioning, front to back. Section index 9 — the
10th from the front — has 5 passes:

| pass | level r | roughing floor at its start | reaches the part? |
|---|---|---|---|
| 1 | 34.4941 | 32.8658 | no |
| 2 | 33.9882 | 32.8658 | no |
| 3 | 33.4823 | 32.8658 | no |
| **4** | 32.9764 | 32.8658 | **yes** |
| 5 | 32.4705 | 32.3782 | yes |

Exactly the split reported. Every one of those five passes paid the same entry:
a 1.0000 mm straight lead at 45 degrees plus a 2.2583 mm profile-angle ramp —
**3.2583 mm of feed against a 4.167 mm cut.**

A time-ordered material simulation over the whole program (every cutting move
lowers the surface it passes under; each move sampled along its length against
that state) put a number on it:

**689 lead and ramp moves, 693.4 mm, cut nothing at all — 35.5% of the entire
roughing feed distance** — against 194 moves and 210.9 mm that do real work.

## Root cause

With Artificial sectioning the ladder is computed **once and shared by every
section window**, so section N and section N-1 cut at exactly the same radii.
A pass whose level the previous section already reached leads in through a
column that section has fully cleared: the straight lead and the ramp both run
through air and arrive parallel to nothing.

## The rule, and the one that does not work

The gate is: **a pass's entry lead is air ⟺ its level is at or above the
deepest level the PREVIOUS SECTION ACTUALLY CUT.** That predicts every one of
the 15 passes across sections 8, 9 and 10.

**Testing against the roughing floor instead mispredicts in both directions,**
and it was the first thing tried. A section's ladder does not reach its own
floor: section 9 stopped at r33.4823 with its floor at 32.8658, so the next
level down is *above* the floor and still cuts 0.5059 mm into the step that
ladder left. What is gone is what was actually **cut**, so that is what has to
be asked. `_pl_last_cut_lvl` records it; `poly_lathe_mill` carries it into
`_pl_psec_deep` as each window opens.

## What was built

`lathe_level_pass.ngc` zeroes `pa_on` **and** `ap_ll`/`ap_rr` when the gate
fires, which drops the pass onto the no-lead path that already existed and was
already proven — stand off in Z by the clearance, descend X there through the
cleared column, cut.

**Zeroing only the ramp is what made an earlier attempt at this worth 22%
instead of 35%**: the pass did not lose its approach, it fell back to the plain
1.0 mm lead at 45 degrees, an X step of 0.7072 — deeper than one depth of cut —
so the air time came straight back as a plunge.

## Numbers

`testing_15_9.xml`:

| direction | air lead moves | cutting leads | roughing feed | rapids into metal |
|---|---|---|---|---|
| 0 front→back, before | 689 / 693.4 mm | 194 / 210.9 mm | 1951.1 mm | none of 811 |
| 0 front→back, **after** | **300 / 282.9 mm** | **194 / 210.9 mm** | **1540.6 mm** | none of 811 |
| 1 back→front, before | 338 / 235.6 mm | 545 / 668.7 mm | 1951.1 mm | 64 @ 0.0041 |
| 1 back→front, **after** | 32 / 9.6 mm | 468 / 491.0 mm | **1547.4 mm** | 60 @ 0.0042 |
| 2 both, before and after | 556 / 560.0 mm | 327 / 344.2 mm | 1951.1 mm | none of 811 |

The cutting leads are **unchanged to the millimetre** front-to-back: the work is
untouched and only air was removed. The 0.0042 mm on direction 1 is grid
discretisation, present identically before the change (0.0041) and four hits
fewer after it.

The moves still counted as air are largely **lead-OUTs**, deliberately left
alone: a retreat leaves the cut this pass has just made, which is a different
question and not what was reported.

## Two regressions this introduced, both caught by measurement

Neither was visible in the reported case, and both were one full depth of cut.

**Natural sectioning — 0.4962 to 0.4991 mm into standing metal.** Natural orders
its windows weakest/smallest-diameter FIRST, so "the window processed before
this one" can be somewhere else on the part entirely and its deepest level says
nothing about the metal beside this one. A deep level carried over from a far
window made every later level look already cut: `testing_15_2`, `_15_4` and
`_15_5` dropped to 2 ramps or fewer, and their radial descents then rapided into
the part. All 142 and 88 of their rapids are clean before the change.

**Both directions — 0.5059 mm.** `rough_dir` 2 alternates the entry END per
pass, so every other pass leads in over the boundary with the section that has
NOT been cut yet. 111 of 811 rapids went into standing metal where the same
program is clean on all 811 before.

Both modes now stand the gate down and measure **exactly** as they did before it
existed — the numbers in the table above are byte-for-byte identical, and
`test_air_leads.py` asserts those specific counts so a future widening of the
gate fails there rather than on a machine.

## Why the probe is trustworthy

Its first run reported **29 rapids in standing metal, worst 14.8088 mm** — at
Z+0.7071, which is in front of the stock face where there is no material at all.
The grid had been filled across the whole Z range. Bounding it at `_wp_z`
removed all 29. That is the whole finding class CLAUDE.md's "validate the
instrument" rule exists for, and it would have read as a catastrophic collision.

The positive control then failed to fire on its first attempt too — the
mutation was written as `type(m)(**m.__dict__)` and the move object has no
`__dict__`, so it silently returned the move unchanged. Rewritten as an offset
passed into the sampler, sinking every rapid by 1 mm now fires at exactly
1.0000 mm depth. `test_air_leads.py` runs that self-test as one of its
assertions.

## Gates

`cam_map`, `test_leftover` (control fired on 24 of 24), `test_ramps` (68 ramps —
the same count as before, so the Artificial-only bound left the ramps this test
looks at in place), `test_x_continuity`, `test_ladder`, `test_leads`,
`test_skip_short`, `test_sections`, `test_lathe_validation`,
`test_coord_mapping`, `check_tangent`, and the new `test_air_leads`.

## Still unknown

- **Natural sectioning keeps all of its air time.** Doing it there needs a
  per-window record of what each window reached, looked up by which window
  actually contains the lead's start Z, rather than a single carried value.
  Recorded in `openPoints.md`.
- **Both directions likewise.** The same per-window record plus a test of which
  END this particular pass enters at would cover it.
- The 0.0042 mm on direction 1 is assumed to be grid discretisation on a sloped
  floor. It matches the baseline and is far below any machining significance,
  but it has not been chased to ground.
