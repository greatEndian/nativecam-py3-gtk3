# 090 — the data/emitter split, step one of wiring the ladder in

**Asked**: greatEndian, 2026-09-03 — *"wire it in"*.

## Why this had to come first

The wiring needs `windows`, `sect_mode`, `top_x` and the floor stages as
**data** at generation time. They existed only inside `build_sections_gcode`
and `build_floor_ladder_gcode`, which computed them inline and returned G-code
TEXT. So the level table could only have been built by re-parsing G-code this
module had just emitted - which is the sort of thing that works until it
silently does not.

Doing the refactor and the behaviour change in one commit would also have meant
that when the wiring misbehaves there is no way to tell which half did it.

## What moved

- **`section_windows(feature)`** -> `(windows, sect_mode, top_x)` or None.
  Everything `build_sections_gcode` decided stayed exactly where it was; the
  emitter is now only an emitter.
- **`floor_stages(feature, rough_cut)`** -> the stage list. Smaller, because
  `floor_ladder()` already returned a list - only the guards needed factoring:
  the resolve, the depth-of-cut test, and the OD-only refusal that declines
  rather than guessing on a bore.

## The gate a refactor needs

Not the suite - **byte identity**. A suite can stay green while emitted output
shifts, and the whole claim here is that nothing changed.

```
36 configurations generated before and after, SHA-256 compared
IDENTICAL across all configurations
```

Both splits were re-checked against the ORIGINAL baseline rather than against
each other, so a drift introduced by the first and cancelled by the second
could not pass.

Suite green as well: all twelve gates, `cam_map`, flake8.

## What this does NOT do

Nothing is wired. No `.ngc` or `cfg` was touched, the motion is untouched, and
`roughing_ladder` is still read by nobody.

## Step two, and its shape

- Python emits a per-window level table from `roughing_ladder` +
  `phase1_stop`, into the free 1000-2600 window (measured unreferenced, below
  `WDEEP_BASE`; ~550 radii plus a directory fit easily).
- `poly_lathe_mill` reads it at the **four** places the level moves - the
  window init at :735, the advance at :1304, and the two floor clamps at
  :1308 and :1310 - and computes as it does today when the table is absent.
- **A runtime guard is not optional.** The table bakes in `phase1_stop`'s
  PREDICTED handover, and that prediction is proved on 36 configurations, not
  universally. After phase 1 the `.ngc` must compare the ceiling it actually
  arrived at against the one Python assumed and fall back to computing if they
  disagree, rather than walking a ladder built on a wrong ceiling.
- Acceptance: flattened motion byte-identical on all 36, table on against
  table off.
