# 060 — Both directions (`param_dir` = 2)

Date: 2026-08-18. Branch `liveTooling`, from `1ea086d`.

## What was asked

greatEndian: **"now do the both directions"**. `param_dir` = 2, the last open
item on lathe polyline roughing, whose tooltip in `cfg/lathe/polyline.cfg`
promises *"Both directions alternates per pass. Profile Shift strategy only."*

## What it actually did — measured before touching anything

Two faults, both on `testing_15_6`, `param_n_comp=0`, Profile Shift.

**1. It did not alternate.** Travel sign of every level cut, in emission order
(probe: rs274 through `ncam_preview.parse_program`, roughing feed moves with
|ΔX| < 1e-4 and |ΔZ| > 0.01):

```
sectioning ON    dir 0   43 cuts   rep 42   -------------------------------------------
                 dir 1   43 cuts   rep 42   +++++++++++++++++++++++++++++++++++++++++++
                 dir 2   28 cuts   rep 27   ----------------------------
```

`dir 2` was byte-for-byte the same travel direction as `dir 0`. Zero
alternations.

**2. It did not rough behind the boss.** `dir 2`'s cut list was a strict
SUBSET of `dir 0`'s — 28 of 43 by this probe's filter, missing exactly the 15
behind-boss intervals:

```
lost   (26.4845, -68.892, -67.373)
lost   (26.9925, -68.892, -65.173)
lost   (27.5005, -68.892, -62.972)
lost   (28.0085, -68.892, -60.772)
lost   (28.5165, -68.892, -58.572)
lost   (29.0245, -68.892, -56.371)   … 15 in all
```

Stock field (lowest radius any roughing feed move reaches at each Z, 0.05 mm
grid, linear along each move):

| Z | dir 0 | dir 2 | difference |
|---|---|---|---|
| −40.0 | 32.8041 | 34.0636 | **+1.2595** |
| −50.0 | 30.4954 | 34.0636 | **+3.5682** |
| −60.0 | 28.1867 | 34.0636 | **+5.8769** |
| −67.0 | 26.5706 | 34.0636 | **+7.4930** |

`dir 2` stopped dead at r34.0636 — the level where phase 1 first meets the boss
— and never went deeper behind it. Sectioning OFF was the same shape: 26 of 41
cuts, +1.42 to +7.62 mm.

The finish pass was identical in all three directions, so the part is the same
and that material was genuinely left standing.

**Instrument validation.** These numbers were reproduced independently before
being believed. The 28-cut count and the 34.0636 residue matched the figures in
the task to the digit; the dir-0 field came out 32.8041 / 30.4954 / 28.1867 /
26.5706 against the 32.6945 / 30.3996 / 28.0894 / 26.4848 supplied, a
consistent ≤0.11 mm offset from a different sampling grid, and the cut count
43 against 44 from a slightly stricter "what counts as a cut" filter. Same
shape, same magnitudes, one probe consistently applied to both sides of every
comparison. `test_x_continuity`, which counts differently again, reports 44.

## Root cause

**One line: `rough_frame_dir(2)` returned 2.**

`rough_frame_dir` maps a user direction onto the frame the roughing
DECOMPOSITION is worked out in. Since `analysis/054` direction 1 maps to 0 —
same windows, same levels, same intervals, reversed emission. Direction 2 was
left mapping to itself, and every consumer that takes a frame direction then
saw a 2 it had its own branch for:

- `flank_sides(2)` returned `(1, -1)`, i.e. peaks on BOTH sides cast a shadow,
  docstring reasoning *"Both directions has to take both, since each pass meets
  a different face of the same boss."*
- `mirror_dir(2)` returned 2, so the leading flank shadowed both sides again.
- `resume_envelope` was handed −1 (`1 if rough_dir == 0 else -1`).

**The `flank_sides` reasoning was the cause, and it is backwards.** The
reachable envelope is what roughing stops against. Taking both sides makes it
the INTERSECTION of the two directions' reachable sets, so "both directions"
reached strictly LESS than either single direction — the exact opposite of the
physics. A tool that can approach from both ends reaches MORE. And the premise
is right about the wrong object: each PASS meets one face of the boss, with one
direction and therefore one shadow. The constraint is per pass, not per
program, and an envelope is per program — so the envelope must be one
direction's, and the honest one to pick is the one whose cut set direction 2 is
required to reproduce.

`build_sections_gcode` also skipped its `_sections_back_to_front` /
`_split_level_intervals` step for direction 2 (the guard read
`frame_dir != rough_dir`), but that only orders windows; it was not part of
either fault.

## The design

**Direction 2 is direction 0's decomposition, emitted alternately.** Same
windows in the same order, same levels, same intervals, same cut set — each
emitted pass cut from the opposite end to the one before it. That is the
tooltip read literally ("alternates per pass") and it is the principle
`analysis/054` established for direction 1: a direction is a traversal, not a
second decomposition.

Python (`lathe_sections.py`):

- `rough_frame_dir` — `0 if rough_dir in (1, 2) else rough_dir`. This alone
  fixes fault 2 completely, because every table that feeds the roughing scans
  goes through it.
- `flank_sides` — the 2 branch is **deleted**; it now answers `(-1,)` for 1 and
  `(1,)` for anything else, and its docstring says it takes a FRAME direction.
- `mirror_dir` — likewise, `0 if rough_dir == 1 else 1`.
- `build_sections_gcode` — the back-to-front window re-order is gated on
  `rough_dir == 1`, not on `frame_dir != rough_dir`. Direction 2 must keep
  direction 0's window ORDER, or it would inherit direction 1's traversal on
  top of the alternation.
- `build_level_split_gcode` — same, `rough_dir != 1` returns ''.
- `finish_profile` — `param_f_dir` now goes through `rough_frame_dir` too. That
  combo offers "Both directions" as well, and a 2 there reached `flank_sides`
  untranslated with the identical fault.
- `ncam_preview_ui` — the two drawn twins of the entry/stop tables take the
  frame direction, so the picture cannot disagree with the table.

O-code, the minimum that cannot be Python:

- `poly_lathe_mill.ngc` sets `#<_pl_cut_alt> = 1` when `rough_dir` is 2, and
  clears it before the contour passes.
- `lathe_level_pass.ngc` flips `#<_pl_cut_rev>` at its very end.

**Why the flip is not in Python.** The parity is a function of how many passes
have been emitted, and only the runtime knows that: a level can be skipped as
too thin (`_pl_min_pass`), refused as blocked before the window or by the
multi-crossing scan, or split into several disjoint intervals by a boss.
Python is never handed the pass list. What DID move into Python is the whole of
the rest — the frame mapping, the envelope, the window order — and the O-code
addition is nine lines of flag, no geometry.

**Why the flip sits at the END of `lathe_level_pass`.** It is the only point
that knows a pass really cut. The three `return`s above it — blocked before the
window, blocked by the multi-crossing scan, and shorter than `_pl_min_pass` —
all leave without emitting motion, and flipping on one of those would put two
consecutive visible cuts the same way round. It also has to be past every
motion because the whole subroutine reads `_pl_cut_rev` as one value: moved
earlier, it would emit an entry lead for one direction and a retreat for the
other.

**Why `lathe_level_pass` needed no other change.** Everything it computes —
the crossing scan, the multi-crossing replay, the entry contour, the stop
table, the interval, both leads, both blend circles, the profile-angle ramp —
is worked out from `w_from` toward `w_to` and is direction-free. `_pl_cut_rev`
is read only at emission (`em_z0`/`em_z1`, the `end_sw` entry/retreat swap, the
ramp). That is `analysis/055`'s work: back to front is the same motion played
backwards. It is what makes per-pass alternation a five-line change instead of
a mirror geometry.

**Also fixed, latent:** `#<_pl_p1s_n>` (the level-split table count) is a
global the cfg emits only for direction 1, so a project with a back-to-front
polyline ahead of a front-to-back one left its peaks behind for the second.
`poly_lathe_mill` now clears it when `rough_dir != 1`. No single-polyline
project could see it; it becomes reachable the moment `_pl_cut_rev` varies
within a program, which is exactly what direction 2 does.

## Alternatives rejected

- **Give direction 2 the union of the two reachable envelopes.** Physically the
  most reach, and wrong here twice over. It would change the cut SET away from
  direction 0's, which is the property the whole direction is measured on; and
  merging two piecewise-linear dilations manufactures corners tighter than the
  nose, which the interpreter refuses outright — measured on testing_15_5 and
  recorded in `flank_envelope`'s own docstring. Left as an open question below.
- **Give direction 2 direction 1's window order as well** (i.e. keep the guard
  as `frame_dir != rough_dir`). Two traversal changes at once, no ask for it,
  and it would have moved the split levels on top of the alternation.
- **Alternate per WINDOW or per level rather than per pass.** The tooltip says
  per pass, and a level with two disjoint intervals would then cut both the
  same way round — repeats in the string for no reason.
- **Encode "alternate" inside `_pl_cut_rev`** (e.g. the value 2) to avoid a new
  global. Every existing test is `[#<_pl_cut_rev> GT 0]`; a 2 would read as
  "reversed" everywhere. A new flag with a `create_defaults()` entry is the
  documented pattern and costs one inert line in the generated file.

## Failed attempts

None to report on the fix itself — the blast-radius grep found every direction
branch before the first edit and all of them were consumers of
`rough_frame_dir`, which is why the change is small.

The **probe** failed twice first, and both were caught by anchoring rather than
by inspection. It first unpacked `Move.a` as `(z, x)` when the preview stores
`(x, y, z)`, which produced a plausible-looking table of 97 "cuts" whose signs
alternated in all three directions — a result that would have said the feature
already worked. It then built the stock field from level cuts alone, giving
dir 0 26.9925 at Z−67 against the known 26.4848; including every roughing feed
move and interpolating along it brought that to 26.5706. Neither error was
visible in the code; both were visible against a number already known.

## After

Same probe, same filter, after the change:

```
testing_15_6  sec OFF  dir 2   41 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
testing_15_6  sec ON   dir 2   43 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
testing_15_5  sec OFF  dir 2   44 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
testing_15_5  sec ON   dir 2   45 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
testing_15_2  sec OFF  dir 2   27 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-
testing_15_2  sec ON   dir 2   29 cuts  rep 0  -+-+-+-+-+-+-+-+-+-+-+-+-+-+-
```

**A perfect zigzag, 0 repeats, on every project × sectioning combination.** No
pass was skipped or blocked in any of them, so the achievable minimum was 0 and
it was reached. The count matches direction 0's exactly, everywhere.

Cut set, dir 2 against dir 0, as multisets of (radius, min Z, max Z): **lost 0,
gained 0** in all six combinations.

Stock field, dir 2 against dir 0:

| Z | 15_6 sec OFF | 15_6 sec ON | 15_5 sec OFF | 15_5 sec ON |
|---|---|---|---|---|
| −40.0 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| −50.0 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| −60.0 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| −67.0 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |

Identical, not "within 0.01".

## The gate

| item | result |
|---|---|
| **A1** it alternates | **PASS** — perfect zigzag, **0 repeats**, 6 of 6 combinations on 15_5/15_6, and on 15_2 as well |
| **A2** same cut SET as direction 0 | **PASS** — **lost 0, gained 0**, 6 of 6; was a 15-cut subset |
| **A3** no metal left standing | **PASS** — stock field **identical to 0.0000 mm** at Z −40/−50/−60/−67; was +1.26 to +7.49 |
| **A4** `test_leftover` + `test_x_continuity` cover direction 2 | **PASS** — both extended; green in all **six** sectioning × direction combinations, `test_x_continuity` worst gap 0.0000 everywhere and its control fires, `test_leftover` control fired **21 of 21** |
| **B5** directions 0 and 1 unchanged | **PASS** — 12 of 12 (15_5, 15_6, 15_2 × sectioning × direction 0/1) differ by **exactly one line**, `#<_pl_cut_alt> = 0.0`, the required `create_defaults` entry. Zero other lines. Same form `analysis/059` accepted for `#<_pl_p1s_n>`. |
| **B6** direction 1 interval order | **PASS** — back-first **16 / front-first 0** sectioning ON on 15_6, 15_5 and 11; sectioning OFF **15/0, 16/0, 16/0** — `analysis/059`'s numbers to the digit. `cuts == distinct` in all 18 runs (44/44, 45/45, 41/41, 43/43, 34/34, 35/35). |
| **B7** standing metal for 0 and 1 | **PASS** — 0.7219 / 0.8579 (15_5 off/ON), 0.6473 / 0.5681 (15_6 off/ON), and **direction 2 identical to both** |
| **B8** overcut and tangency | **PASS** — `test_rough_comp` on testing_15_2: Off / Native / In CAM all **0.0503 mm at Z0.3**; `check_tangent` **PASS** for direction 2 on 15_2, 15_5, 15_6 × sectioning, 6 of 6 |
| **C** flake8 (both file sets), `cam_map` **6/6**, `test_lathe_validation` (40 calls), `test_all_projects` **40/40** loads+migrates, `test_sections`, `test_ngc_comments` (217 files), `test_cam_map`, `test_front_flank` | **PASS** |
| no CALL arity change | **PASS** — `#<_pl_cut_alt>` is a global with a `create_defaults()` entry; no subroutine signature moved |
| cfg version | **not bumped, and must not be** — no `.cfg` was edited. The tooltip already promised this behaviour. |

`test_leads.py` still fails on `testing_13_arcs` mode "Off" — pre-existing at
`1ea086d`, unchanged, not chased.

## What is still unknown

- **Direction 2 does not yet reach MORE than direction 0.** It removes the same
  metal in a better order. The physically available gain — a reversed pass can
  enter the shadow a forward pass cannot — is deliberately not taken, because
  it would change the cut set and because merging two dilations manufactures
  sub-nose corners the interpreter refuses. If it is ever wanted it is a third
  decomposition, with its own analysis and its own gate, not a tweak here.
- **The alternation is not cycle-time-aware.** It is a pure parity flip, so on
  a part where consecutive levels are far apart in Z the return move is a long
  cut through air at feed rather than a rapid. No project measured shows this;
  a very sparse ladder might.
- **Parity across windows.** With Sectioning on, the flip carries from the last
  pass of one window into the first pass of the next, so a window can open
  going either way. That is what "alternates per pass" says and it costs
  nothing, but if greatEndian wants each section to open front-to-back the flag
  would be reset at the `w_idx` loop head — one line, not done because it was
  not asked for.
- **`param_f_dir` = 2 (finish direction) is still not implemented.** It now
  dilates correctly rather than shadowing both sides, so it behaves as
  direction 0 instead of leaving material — but the finish passes do not
  alternate. Separate open point.
