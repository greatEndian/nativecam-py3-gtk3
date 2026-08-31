# 067 — the entry-lead gate, asked by geometry instead of by order

**Asked**: greatEndian, 2026-08-31 — *"do same for natural sectionning and both
directions"*, after `analysis/066` bounded the gate to Artificial sectioning.

## What was wrong with the first version

`analysis/066` carried ONE value: the deepest level the previously **processed**
window cut. That is the neighbour an entry lead reaches into only when the
processing order follows the part. It does under Artificial; it does not under
Natural, which orders windows weakest/smallest-diameter first, nor under Both
directions, which alternates the entry END per pass so every other pass leads in
over the boundary with a section not yet cut. Left live in those two, rapids
descended **0.4962–0.4991 mm** and **0.5059 mm** into standing metal.

## What replaced it

A **per-window record, looked up by Z span**. `#2800 + i` holds the deepest level
window `i` has cut so far; `lathe_level_pass` walks the window table, takes the
**maximum** over every window the lead's Z span touches except its own, and
gates on `level >= that`.

The order stops mattering, because a window that has not run yet still reads
999999 and carries the comparison by itself — an uncut neighbour cannot claim to
have cleared anything. That single property is what makes one mechanism cover
all four mode combinations.

**The table costs nothing.** 1000–2999 was measured to be completely
unreferenced — by `cfg/`, `lib/`, `ncam.py` and `lathe_sections.py` alike, and
by the whole generated program, whose lowest numbered parameter is 3000. 200
slots against the window table's own 50-window ceiling, so it can never be the
binding limit.

`_pl_wdeep_ok` guards a project generated before the table existed, whose slots
would read 0 — "cut to the centre" — and drop every lead on the part.

## Numbers

Air **entry** leads are what the gate targets; the rest of the air is retreats,
left alone on purpose.

| case | entry-air before | entry-air after | roughing feed |
|---|---|---|---|
| Artificial front→back | 408 / 419.4 mm | **19 / 9.0 mm** | 1951.1 → 1540.6 mm |
| Artificial back→front | — | **0 / 0.0 mm** | 1951.1 → 1547.4 mm |
| **Both directions** | — | **10 / 5.0 mm** | 1951.1 → **1744.2 mm** |
| Natural, testing_15_5 | 20 / 10.0 mm | 20 / 10.0 mm | 1326.2 mm, unchanged |
| Natural, testing_15_2 | 16 / 7.9 mm | 16 / 7.9 mm | 700.9 mm, unchanged |

Leads that cut metal are preserved exactly in every case. All rapids run through
cleared metal, except the 60 hits at 0.0042 mm on back-to-front which are grid
discretisation on a sloped floor — present identically before any of this work
(64 at 0.0041) and four orders of magnitude below a depth of cut.

## NATURAL HAD NOTHING TO TAKE, and that is a result, not a failure

The gate is live for Natural and finds almost nothing: **10.0 mm and 7.9 mm** of
air entry lead on the two Natural projects, against 419.4 mm on Artificial.

The reason is in the window table. Natural's windows carry a **radius band**
(`w_rlo`/`w_rhi`, slots 3 and 4), so they partition the ladder between them —
each window cuts a fresh band. Artificial's windows have no meaningful band and
every one of them re-walks the whole shared ladder, which is where the
redundancy came from. Natural never had it.

So *"do same for natural sectionning"* is done in the sense that matters — the
gate now applies there and is no longer bounded out — and the honest result is
that it removes 10 mm rather than 400. `test_air_leads.py` asserts those figures
so the absence of a saving is a recorded fact rather than a suspicion.

## Two faults on the way, both found by instrumenting rather than reading

**`z_dir` is not a Z direction.** It is 1 when `w_from GE w_to`, so a forward
pass travels toward *decreasing* Z at `z_dir` 1 — the cut is
`z_end = z_start - z_dir * length`. The approach therefore comes from `z_start
PLUS z_dir * length`, and having that sign inverted made the walk find no
neighbouring window at all: `seen=0`, `ref=-999999` on every pass of window 5.
Reading the code had suggested the opposite; a `(debug, ...)` line printing
`w`, `level`, `seen` and `ref` per pass settled it in one run.

**The gate was placed before `z_end_cut` exists.** It sat at line 1042 and
`z_end_cut` is not final until 1224, so both reversed directions died on
`Named parameter #<z_end_cut> not defined`. Moved below the lead resolution and
above the approach point.

Also worth recording: a plain `(DBG ...)` comment prints nothing and expands no
parameters. Only `(debug, ...)` does. One wasted run.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (control fired on 24 of 24),
`test_ramps` (68, unchanged), `test_x_continuity`, `test_ladder`, `test_leads`,
`test_skip_short`, `test_sections`, `test_lathe_validation`,
`test_coord_mapping`, `check_tangent` (min |dot| 1.00000), and `test_air_leads` —
26 assertions across all five mode combinations, including its own self-test.

## Still unknown

- **Lead-OUTs are still not gated**, and they are now the bulk of the remaining
  air: 273.6 mm of the 282.6 on Artificial front-to-back. A retreat leaves the
  cut the pass has just made, which is a different question from an entry into
  metal that was already gone, and it has not been asked whether it earns its
  feed.
- The 0.0042 mm overlap on back-to-front is assumed to be discretisation. It
  matches the baseline exactly but has not been chased to ground.
