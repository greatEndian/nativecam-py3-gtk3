# 065 — "Retract = Minimal" was dead code, and why it could not simply be switched on

**Asked**: greatEndian, 2026-08-31 — *"there is a lot of the cutting air
passings"*, then *"yes, chase the retract rapids"*, then *"yes, build the safe
minimal retract"*.

## What was measured

Project `testing_15_9.xml`, lathe roughing, `Retract` set to `Minimal` in the
GUI. Rapid distance was identical to `Full`. That is the finding: **the setting
did nothing on any project, ever.**

`poly_lathe_mill.ngc` carried an unconditional-in-practice override:

```gcode
o<mx_ret> if [#<_pl_multi_cross> GT 0]
        #<_pl_ret_mode> = 0
o<mx_ret> endif
```

`_pl_multi_cross` is set by `polyline.cfg` for every polyline, so the branch
always taken and `_pl_ret_mode` always landed on 0 = Full. A shipped combo box
with a dead option.

## Why the override was right at the time

Minimal retract's reference was `#<_pl_prev_lvl>` — "the previous level"
— and that is only safe on a profile whose levels are single intervals. As soon
as a boss splits a level into disjoint intervals, the band above the previous
level is cut *where the tool has been*, while the boss between here and the next
interval is still standing. The retract then sits permanently below that boss on
every smaller level after it. The override traded cycle time for an absolute
upper bound, which was the correct call for a reference that could not see the
boss.

So removing the override alone is a crash, not a fix. The staleness had to be
fixed at its source.

## The fix

`lathe_level_pass.ngc` now derives the retract radius from **the highest
material between where the tool is and where it is going**, not from the
previous level:

- `#<pv_end_z>` is captured at the top of the sub, before this pass overwrites
  it: `#<_pl_level_z_end>` still holds the *previous* pass's finish Z there, and
  is the only thing in scope that knows where the traverse starts from.
- the span `[pv_end_z, z_start]` is walked against the roughing-floor table
  (`_pl_stop_base` / `_pl_stop_n`) that the stop scan already reads. Any segment
  overlapping the span contributes both endpoints; the floor is piecewise linear
  so its maximum over a span always sits at a breakpoint.
- `#<pk>` = max(previous level, that peak); `ret_x = (pk + _pl_ret_dist) *
  _diameter_mode`, capped at `_wp_dia_od + _x_clear`.

A boss now raises the retract by construction, so the override is gone.

**It falls back to full retract, deliberately, in two cases**: no floor table
(`_pl_stop_n` = 0) — with nothing to verify against, guessing is worse than
being slow; and ID work (`_pl_side` != 0), whose retract is a different geometry
this has not been measured against.

## Numbers

`testing_15_9.xml`, same 799 rapids either way:

| | rapid distance | total roughing motion | tightest clearance over the roughing floor |
|---|---|---|---|
| Full | 4688.3 mm | 6451.6 mm | +3.3508 at Z-32.8577 |
| Minimal | **1898.3 mm** | **3661.6 mm** | **+1.0693 at Z-32.1929** |

60% of the rapid distance and 43% of total roughing motion. Full is byte-identical
to its pre-change program (hash `39e29494a301`), so the untouched case is proven
untouched.

**The clearance line is the number that matters**, not the distance. Every
Z traverse was sampled along its length against the roughing floor; the tightest
is +1.0693, which is `_pl_ret_dist` (1.016) plus margin, and never negative. A
shorter retract that dipped into standing metal would have measured negative here.

Gates: `cam_map`, `test_leftover` (24/24 control fired), `test_x_continuity`,
`test_ramps` (68 ramps), `test_ladder`, `test_leads`, `test_skip_short`,
`test_sections`, `check_tangent` (min |dot| 1.00000) — all pass.

## Two failures on the way, both instrument faults

**"Command too long".** The overlap test was first written as one
`o<k_ov> if [...]` condition covering all four cases. LinuxCNC refused the file
outright at the line-length limit CLAUDE.md warns about. Split into four short
tests `k_a`/`k_b`/`k_c`/`k_d` each setting `#<k_ov1>`.

**1793 moves with `op=None` and zero roughing rapids.** Looked exactly like a
program that had aborted. It had not — the same 1978 moves were present. A
comment line of mine began `(end at this point ...)`, and `ncam_preview` parses
`COMMENT("(begin|end) ...")` as an operation marker, so a line of prose opening
with that word popped the operation stack and orphaned every move after it.
**No comment in these files may open with "end" or "begin".** A warning to that
effect now sits at the point in `lathe_level_pass.ngc` where it was written.

Both cost a full generate-and-measure cycle, and both were the tool lying rather
than the change being wrong — the case CLAUDE.md's "validate the instrument
before trusting it" exists for.

## Still unknown

- ID work (`_pl_side` != 0) still takes full retract. Whether the same peak
  reference is correct there is unmeasured, not decided.
- The peak is taken over the roughing *floor*. On a pass whose traverse spans a
  region where the floor is far below what is actually still standing (the very
  first levels, where stock is largely uncut), the reference is the floor and the
  previous level, and the previous level is what carries it. No case has been
  found where that reads low, but it has not been proven that none exists.
