# Session 2 — 2026-08-03 / 08-04, branch `liveTooling`

From `7404a9d` to `57eea44`. Everything pushed, tree clean apart from an
untracked AXIS `autosave.halscope`. `openPoints.md` is what is LEFT; this is
what HAPPENED.

## Delivered

**`584a7db` — the pre-finish bump at Z−20, In CAM only, 0.1870 mm deep.**
An inside corner trims both offsets to where they cross; when the segment
after the corner is shorter than the offset — the arc's first chord, 0.0049 mm
of Z against a 0.508 offset — the crossing lands beyond the whole of it and the
path stepped back to reach that swallowed segment's own join. `_join_offsets`
now drops a swallowed segment and retries. `offset_contour` and
`entry_contour` had a near-copy of the loop each; both now call it.

**`81574bd` — the lead-out exit shift.** `lathe_poly_pass` cancels comp (G40)
then names where the tool physically is, computed with a plain normal offset
and **no orientation term** — the term the entry gained in `c16df1f`. After
G40 the control point IS the tip, so it made cancelling comp a real move:
**0.5657 mm = R√2**, and the retreat ran 1.5657 where 1.000 was asked for.

**`bfa2fa2` — roughing's level start.** A level falls back to the WINDOW start
(a raw profile Z) whenever the entry contour never crosses it. Its stop and
re-entry already carried the nose: one end compensated, the other not.
`build_rough_nose_gcode` emits `_pl_rgh_oz` already gated by `_comp_nose`.

**`57eea44` — the roughing retreat.** It rose above its OWN level, so 25 of 27
levels finished inside the bar, one 0.6569 mm buried. A separate radial G1 to
`_wp_dia_od`, not a longer `_lo_leff` (that fights the Z-room cap).

| | before | after |
|---|---|---|
| pre-finish +Z reversals, In CAM | 1, 0.1870 mm deep | **0** |
| G40 exit line, Native | 0.5657 mm | **0.0000** |
| roughing cut starts, compensated | Z+1.4000 | **Z+1.0000** |
| roughing overcut past pre-finish | 0.0503 | **0.0394 mm** |
| retreats finishing inside the stock | 25 of 27 | **0 of 52** |

New tests: `test_leads.py` (4 assertions × 2 projects × 3 modes),
`test_swallowed_corner` in `test_sections.py`. **Both verified to fail without
their fix** — that check is now part of the habit, not an extra.

`analysis/008`, `009`, `010` written as the work was done.

## Decisions and corrections

- **`analysis/007` is overturned** (recorded in 007 and 008). The trim leaving
  the wall 0.486 early is the correct parallel offset of a concave corner; the
  cross sign was never wrong, and `side`/`z_dir` agree. Three checks that
  session queued up were chasing a non-bug.
- **In CAM was right twice more** — the swallowed corner and the lead-out.
  Native is the one that had to be brought into line, same as the arc
  truncation of 08-02.
- **Off is not the standard to copy at the contour ends.** It leaves the nose
  R√2 = 0.5657 from the endpoint where compensated leaves R = 0.4000. Off is
  the mode with the play.

## What went wrong

- **A cfg edit did nothing and I did not notice for three tool calls.** A saved
  project embeds the whole `after=` template, `<exec>` lines included, so
  `cfg/` changes are invisible until `version` is bumped. `lib/*.ngc` needs no
  bump — read at runtime. That asymmetry is why the `lathe_poly_pass` fix took
  effect immediately and the `polyline.cfg` one silently did not.
- **A metric fired on the Off baseline again — the third time.** The exit line
  was identified as "the move before the lead-out"; with a lead-out blend
  radius that is the ARC, 0.3902 mm, failing on Off itself. Fixed by locating
  it by POSITION: the one move that is exactly zero length in Off.
- **I told greatEndian I was out of context twice without checking the actual
  number.** New standing rule below.

## Next, in order

1. Roughing's lead-out on the **ID side** — the stock clamp is OD-only and
   untested; no saved project bores.
2. No test asserts the roughing start or the retreat height **directly**; both
   would only be caught through `test_rough_comp`'s number.
3. `taper_id`, `boring`, `facing` — comp still switched on inside the finishing
   loop only, and their exit arithmetic is unchecked for the `analysis/009`
   fault.
4. The **restart button** — still broken, still in the menu.
