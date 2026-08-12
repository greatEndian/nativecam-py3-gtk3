# 036 — The first pass after the boss: a stop taken at a *falling* crossing

2026-08-12, branch `liveTooling`, from `a59bfe1`.

## What was reported

greatEndian, three times, latterly with a screenshot
(`photo/firstPassMissingBehindBoss.png`): on `testing_15_6.xml` the **first
roughing pass after the boss segment is missing**. On `testing_15_5.xml` it is
correct.

Two agents and the coordinator had each concluded from the tables that nothing
was missing. All three were wrong, and the reason is recorded below because it
is the more useful half of this file.

## Why it was missed three times

Every previous check looked at the passes that **exist** behind the boss and
found them regular. The fault is a level with **no behind-boss interval at
all** — invisible unless you ask which levels are absent. Dumping the whole
ladder sorted by X, with the front and behind intervals side by side, showed it
in one line:

```
34.5318   0.0000 -> -68.8920    full length, clears the dome
34.0636   0.0000 -> -34.5908    FRONT ONLY  <-- no behind interval
33.5955   0.0000 -> -28.9567    front
33.5955  -37.4178 -> -68.8920   first behind pass
```

The ladder step is 0.4682, but **behind the dome it jumps 34.5318 → 33.5955 =
0.9363, exactly double**. Level 34.0636 is missing there and the next level
takes its work.

It also passed every existing test, and that is not a gap in the tests so much
as a fact about the geometry: the level cuts *through* the dome, gouging at most
**0.1005 mm** into the floor allowance. The floor stands `fin + prefin` =
1.508 mm above the part on this project, so 0.1 mm into it leaves 1.408 mm — the
part is untouched, `test_rough_comp` sees no overcut past the pre-finish
contour, and `test_leftover` sees no metal standing because the next level down
removes it.

## The geometry

The floor contour of `testing_15_6` is a **dome**, not a boss on a cylinder:

```
rises  X19.5492 (Z+1.35)  ->  peak X34.1641 (Z-32.79 .. -33.01)
falls  X26.2368 (Z-68.89) ->  end wall rises to X35.1657
```

For level 34.063647 there are three crossings: **rising** at ≈Z−31.21,
**falling** at ≈Z−34.60, and rising again at the end wall.

## Root cause

`lathe_level_pass`'s scan gets it right. The stop table then undoes it:

```
LP lvl=34.531823  found=1  zc=-68.891999  scan=-68.891999  zend=-68.891999
LP lvl=34.063647  found=1  zc=-31.209182  scan=-31.209182  zend=-34.590818
```

`scan` is `z_end` before the stop block, `zend` after. The scan correctly ends
the level at **Z−31.209** on the dome's rising flank; the stop block then
**extends it 3.3816 mm to Z−34.591 — the FALLING crossing** — so the cut sweeps
through the dome and the level's behind-dome interval is lost.

The crossing test was a bare sign change:

```
o<s_cross> if [[[#<s_px> - #<l_eff>] * [#<s_cx> - #<l_eff>]] LT 0]
```

which fires on any crossing, in either direction. A falling crossing is the
point where the level **leaves** blocked territory. Extending a cut to it
necessarily means sweeping through the blockage in between — the very thing the
`s_reach` bound above it exists to prevent, and whose own comment already warns
it must not *"jump regions where the level is BELOW the local roughing floor and
has no business cutting."* The bound simply cannot stop this case: `s_reach` is
`3 × doc` = 1.524 mm, but its slope term `1.5 · doc · |dz|/|dx|` reaches about
4.5 mm on the dome's shallow flank, so the 3.38 mm extension is admitted.

**The right bound here is direction, not distance.** The fix restricts the stop
crossing to one that *enters* blocked territory, using the same convention the
multi-crossing walk already uses for `dirup` in `o<mcf_w>`:

```
o<s_cross> if [[#<s_px> LT #<l_eff>] AND [#<s_cx> GE #<l_eff>]]
```

One line, in `lib/lathe/lathe_level_pass.ngc`. Nothing in Python, `.cfg` or the
parameter windows, so nothing migrates.

## Before → after, testing_15_6 behind the dome

| | before | after |
|---|---|---|
| levels behind the dome | 34.5318, then 33.5955 | 34.5318, **34.0636**, 33.5965 |
| step across the dome | **0.9363** (2 × doc) | 0.4682, 0.4671 (regular) |
| level cuts | 48 | 49 |
| 34.0636's front cut ends | Z−34.5908 (through the dome) | Z−31.2092 (at the flank) |

`testing_15_5` is unchanged: topmost behind-boss **33.2080** sectioning off,
**33.1273** on.

## `test_x_continuity.py` — greatEndian's check, and two corrections it needed

His idea: remember the last X of a level pass and compare it with the next; a
step that is not one depth of cut is a missing pass. Shipped, with two changes
the measurements forced.

**It is one-sided.** With `Space passes from = Final contour` the ladder is
anchored on the floor, so the top step of a region is a remainder — 0.4682 and
0.4671 against a 0.5080 depth of cut, both legitimate. Only a step that
**exceeds** the depth of cut is a missing pass.

**The comparison must be positional.** A first version matched each pass with
the next one down whose Z span overlapped it, and **could not see this bug**: the
full-length pass at 34.5318 overlaps 34.0636 *in front of* the dome, so 34.0636
was taken as its neighbour and the gap *behind* the dome was never examined. It
reported a worst step of 0.0000 on a program with a missing pass. Walking Z and
comparing the levels that actually cut at each station reports it at once:

```
X34.5318 -> X33.5955  gap 0.9363  first seen at Z-37.5000
```

Validated both ways: **FAILs with the fix reverted**, passes with it applied,
and its negative control (deleting a level from the parsed program) fires.

A third correction was to the probe, not the code: the first version collected
every constant-X feed and so swept the **pre-finish and finish passes** into the
ladder — they appear at X20.5080 (final 20.0 + the 0.508 finish offset) and
X20.0000, making the last roughing level look 1.0160 above its neighbour.
`test_rough_comp` filters them with `not m.subs`; this now does too.

## Noted, not fixed

The front interval of the first blocked level is **emitted twice** — identical
moves, `34.0636 0.0000 -> -31.2092` on this project, and `33.5955` before the
fix. Pre-existing, follows whichever level is first blocked, and costs an
air-cutting repeat rather than any wrong metal. Out of scope here.

## Verified

`test_x_continuity`, `test_leftover`, `test_behind_boss_ladder`,
`test_rough_comp`, `test_stock_to_leave`, `test_rough_ends`,
`test_rough_overlay`, `test_all_projects`, `test_ladder`, `test_floor_ladder`,
`test_ramps`, `test_section_length`, `test_resume_envelope`, `cam_map`, flake8.
