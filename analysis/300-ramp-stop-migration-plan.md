# 300 — Migration plan: the ramp/stop machinery still runtime in `lathe_level_pass.ngc`

2026-09-16, branch `liveTooling`, PLAN lane (read-only in the main tree except
this file and `openPoints.md`). No `lib/`, `cfg/` or `.py` file is touched by
this analysis.

## What was asked

openPoints.md: *"The ramp and stop machinery is still runtime O-code
(`s_reach`, the slope term, the flat-boundary clamp — a big, well-scoped
Python-migration item)"*, with `analysis/023` as the entry point. Plan — do
not implement — moving that machinery out of O-code, following CLAUDE.md's
Python-first rule applied backwards to existing code.

## Path

1. Read `lib/lathe/lathe_level_pass.ngc` in full (1788 lines) and
   `analysis/023`, `analysis/036` for the fault history this code has already
   produced.
2. Grep `lathe_sections.py` (6186 lines) for what tables it already builds for
   this subroutine, and `CAM-MAP.md`/`cam_map.py` for every consumer.
3. Instrument a **scratch copy** of `lathe_level_pass.ngc` (never the tracked
   file) with `(print, ...)` statements at every runtime-decision point, run
   it under `rs274` against `testing_15_5`, `testing_15_6`, `testing_15_9`
   (all three names exist exactly as given), and record the real numbers.
4. Size a candidate new table against the numbered-parameter budget actually
   in use, not an assumption.
5. Write the staged sequence below, each stage independently provable and
   revertible.

---

## 1. Every runtime computation that decides geometry

All line numbers are in the tracked `lib/lathe/lathe_level_pass.ngc` as read
this session (1788 lines total).

| computation | lines | inputs | Python already knows the answer? |
|---|---|---|---|
| Raw perpendicular-offset crossing scan (`o<scan01>`) — offsets every RAW polyline segment by `cross_t` at runtime | 162-259 | polyline record array (`#<pds>+9...`), `cross_t`, `level` | **Yes, and already bypassed.** `o<flc>` at 184-209 sets `scan_i = rec_count` whenever `_pl_flc_n GT 1` (Python's floor contour exists), skipping 211-259 entirely. This code only still runs for a project saved before the floor contour existed. It is dead weight on every current project, not a migration candidate — a deletion candidate once no saved project needs the fallback. |
| Multi-crossing replay (`o<mcross>`, `o<mc01>`) — same offset arithmetic, direction-aware | 270-439 | same, plus `_pl_multi_cross` | **Yes, same story.** `o<mc_flc>` at 290-331 short-circuits it via `_pl_flc_n` exactly the same way. Also fallback-only on current projects. |
| Entry-contour crossing walk + **reach formula** `e_reach = 1.5·rough_cut·\|dz\|/\|dx\|` | 503-618, formula at 582-585 | `_pl_entry_base/_n` (Python's `entry_contour`, `lathe_sections.py:5010`), `_rough_cut` | **Yes.** `e_sdz`/`e_sdx` (line 560-561) are literally the entry-table's own consecutive points — Python already emits them. `_rough_cut` is a project parameter (`cfg/lathe/tool-change.cfg:363`, `param_c_dpt`), readable by `<exec>` at generation time. The formula is pure arithmetic on numbers Python holds; it is recomputed at runtime on **every single call**, once per candidate crossing. |
| Ramp-direction pick (`e_pick`), ramp length/side arming (`e_arm`…`e_room`…`pa_side`) | 932-1037 | `e_whave/e_wdz/e_wdx/e_waz/e_wax` (all from `entry_ramp_dirs`, `lathe_sections.py:1958`), `_pl_ramp_face`, `_pl_x_sgn` | **Mostly already Python** — this is `analysis/023`'s own fix. `entry_ramp_dirs` names the direction and anchor per segment; the O-code reads it. What is left at runtime is per-call arithmetic on a `level` that varies per call (`pa_dz`, `pa_x`) — see the row-explosion problem in §4. |
| **Stop-contour flat-boundary detection** (`s_flat`/`s_fz`) — "where the contour flattens" | 768-780 | `_pl_stop_base/_n` (Python's `build_stop_contour_gcode`, `lathe_sections.py:5340`) only | **Yes, entirely, and it is per-SEGMENT, not per-call.** The flat point is a property of the stop contour alone — it does not depend on `level`, `w_from`, `w_to` or which pass is asking. Every one of the hundreds of calls that reach this block (450 on `testing_15_9` alone — measured, §6) re-walks the same ~135-point table to find the same answer. Cheapest, safest item in this file to move. |
| **Stop-contour reach formula** `s_reach = max(3·rough_cut, 1.5·rough_cut·\|dz\|/\|dx\|)` | 825-831 | `_pl_stop_base/_n`, `_rough_cut` | **Yes**, same reasoning as `e_reach` — pure arithmetic on the stop-table's own consecutive points and a project parameter. Per-segment, not per-call: two different levels crossing the *same* stop-contour segment get the *same* `s_reach`. Recomputed from scratch on every call (450x on `testing_15_9`). |
| **Clamped-candidate rule** (`s_clamp`, `s_take`/`s_near`, `s_ok`/`s_push`) | 832-906 | `s_zc`, `z_end`, `s_reach`, `s_flat`/`s_fz`, plus **`w_to`, `z_end_scan`** (this call's own window bounds) | **Partly.** The clamp VALUE and the "does an unclamped candidate beat a clamped one" rule are pure functions of the stop table + reach (Python-knowable), but the WINNER also depends on `z_end` (this call's scan result) and `w_to` (this window's own bound) — both vary per (window, level) call, not per segment. This is the one piece of the "big four" that cannot collapse to a pure per-segment table without also carrying per-call context — see §3 and §4. |
| Minimal-retract floor-height scan (`o<ret_md>`, `k_*`) | 1402-1459 | `_pl_stop_base/_n`, **`pv_end_z`** (= `_pl_level_z_end`, the *previous actual call's* result) | **No, not standalone.** Genuinely sequence-dependent — see §3. |
| Lead-air gate (`o<ld_gate>`, `#2800+i` = `WDEEP`) | 1175-1279, 1189-1279 | **`#2800+i`, written by `lathe_level_pass` itself at runtime** (`_pl_level_z_end` per window, line 1067 and the write near 1701) | **No.** This table records what THIS RUN actually cut, in the order it was cut — see §3. |
| `lathe_level_next_start` (separate sub, `poly_lathe_mill.ngc:1158` etc.) — re-scans the record array to find the next disjoint interval | not in this file | same record array | **Found while reading the caller, not asked for.** Same family of runtime geometry (the "level scan's own perpendicular offset" the openPoint names), but not measured this session — flagged as a related, out-of-scope item below rather than guessed at. |

**Summary of the four items the openPoint names by name:**
- `s_reach` / slope term → §1 stop-reach row above: **movable per-segment**.
- flat-boundary clamp → §1 flat-boundary row: **movable per-segment, cheapest item here**.
- clamped-candidate rule → **partly movable**; the comparison rule is
  Python-knowable, the winning VALUE needs per-call `z_end`/`w_to`.
- "the level scan's own perpendicular offset" → **already effectively dead
  code** on any project with a floor contour (which is every current
  project); a deletion, not a migration.

---

## 2. Every consumer, by grep and `cam_map.py`

`python3 cam_map.py` (2026-09-16, this session): **all 9 checks PASS**,
including "no parameter window reaches over a slot the O-code writes" and
"every `#<_pl_*>` the O-code reads is defined in `create_defaults`". No
existing collision or dangling reference in this area.

`python3 cam_map.py --map` regenerated `CAM-MAP.md`. Grepping it:

- `_pl_entry_base`, `_pl_entry_n`, `_pl_eramp_base`, `_pl_eramp_n`,
  `_pl_flc_base`, `_pl_flc_n`, `_pl_stop_base`, `_pl_stop_n` — **each read by
  exactly one file: `lib/lathe/lathe_level_pass.ngc`.** No other `.ngc` walks
  these tables.
- `lathe_level_pass` (the sub itself) is **called from exactly one place**:
  `lib/lathe/poly_lathe_mill.ngc` (`CAM-MAP.md:547`).
- `#3400` (`SECT_BASE`, the per-window Z-band table) is both read by
  `lathe_level_pass.ngc` (lines 1233-1234, the `ld_gate` walk) and written by
  Python (`build_sections_gcode`) — a second, independent consumer of a
  *different* table than the ones above.
- `#2800` (`WDEEP_BASE`) is the one table in this whole area **written by the
  O-code itself** (`lathe_level_pass.ngc`) and read back by the same file —
  see §3.

**Blast radius for the movable pieces (§1's per-segment items) is therefore
narrow**: one `.ngc` file (`lathe_level_pass.ngc`), one Python module
(`lathe_sections.py`), and the test files that assert this subroutine's
behaviour by name:
`test_high_feed.py`, `test_level_blocked.py`, `test_ngc_comments.py`,
`test_level_intervals.py`, `test_peck.py`, `test_ramp_orient.py`,
`test_skip_short.py`, `test_roughing_windows.py`, `test_sections.py`,
`test_through_cut.py`, `test_sub_spans.py`, plus the geometry gates named in
`analysis/023`/`036`: `test_ladder`, `test_floor_ladder`, `test_rough_comp`,
`test_rough_ends`, `test_leads`, `test_skip_short`, `test_ramps`,
`test_x_continuity`, `test_behind_boss_ladder`, `test_rough_overlay`,
`test_resume_envelope`, `test_section_length`, `test_stock_to_leave`,
`test_leftover`.

No `cfg/` file, no parameter window (`PARAM_*`), and no other `.ngc` in
`lib/mill` or `lib/utilities` touches any of this — it is lathe-roughing-only,
confirmed by `cam_map.py`'s subroutine-definition check.

---

## 3. What can move and what cannot, with reasons

**Can move (per-segment, geometry-only, already the pattern `entry_ramp_dirs`
proved for the ramp direction):**

- **Stop-contour flat boundary** (`s_flat`/`s_fz`). Depends only on the stop
  contour's own shape. Zero per-call dependency. Python can compute it once
  per stop-contour run and emit a tiny table (or even a single scalar per
  polyline, since the comments describe one feature boundary per profile in
  the measured cases).
- **Stop-contour reach formula** (`s_reach`). Depends only on the stop
  segment's own `dz/dx` and `rough_cut`, both Python-known. Same pattern as
  `entry_ramp_dirs`'s 4-slot-per-segment table — this would be a 5th field
  (or a parallel table) alongside the existing direction data.
- **Entry-contour reach formula** (`e_reach`). Identical reasoning, entry
  side.
- **Dead-code removal**: the raw perpendicular-offset scan (162-259) and its
  multi-crossing twin (270-439) whenever `_pl_flc_n GT 1` — not a migration,
  a deletion once every project in the corpus has a floor contour (needs a
  corpus check, not assumed — see Stage 0 below).

**Cannot move without a larger prerequisite, and why:**

- **The clamped-candidate WINNER** (`s_take`/`s_near`, §1). The comparison
  rule itself is knowable in Python, but evaluating it needs `z_end` (this
  call's own scan result — window- and level-specific) and `w_to` (this
  window's own bound). These are not properties of the stop contour; they are
  properties of *which pass is asking*. Fully precomputing the winner for
  every (window, level) pair is possible in principle but runs into the
  slot budget in §4 before it runs into a "can Python know this" problem —
  it is a resource question, not a knowledge question.
- **Minimal-retract floor scan** (`k_*`, 1402-1459). Needs `pv_end_z` =
  `_pl_level_z_end`, the **actual previous call's result**. If every prior
  call in the chain took the table-driven (not fallback) path, Python's
  static ladder would agree with the runtime value — but `lathe_sections.py`
  itself documents (`lathe_level_table`'s own docstring, line 3175-3183) that
  the window **processing order** across sectioned windows is still decided
  at runtime in `poly_lathe_mill.ngc` (`_pl_sect_mode`, phase-1/phase-2
  handover, `phase1_stop` "proved... on 36 configurations, not
  universally"). Until that ordering is itself table-driven and proven,
  Python's guess at `pv_end_z` is a second answer that can disagree with the
  real one — the exact failure mode `lathe_sections.py`'s own comment at
  4712-4716 warns against for `WDEEP`. **This is not a live-tool-table
  dependency** (no nose radius/orientation is read inside
  `lathe_level_pass.ngc` — that is already resolved earlier into
  `_pl_rgh_oz`/`_pl_ramp_face`, both Python-sourced). It is a **call-order**
  dependency, and the prerequisite is the ladder-order migration already
  tracked by `analysis/080`, `081`, `089`, `118` (visible as the `[~]`
  "ROUGHING LADDER IS TABLE-DRIVEN" item in `openPoints.md`, itself marked
  **NOT SHRUNK YET**).
- **Lead-air gate / `WDEEP`** (`#2800+i`). Same reasoning as the retract
  scan, same prerequisite. This table is written by the O-code precisely
  because it records what THIS run actually cut, in execution order — a
  runtime fact, not a geometry fact.

**Net finding for §3**: nothing in this file is blocked by live machine
state (tool table, spindle, offsets). Everything that is blocked is blocked
by **call-order state that Python does not yet own** — a narrower, already-
in-progress prerequisite, not a new unknown.

---

## 4. Resource: numbered-parameter slot budget, measured

Full current layout (from `lathe_sections.py`'s own `_BASE`/`_TOP` constants,
cross-checked against `cam_map.py`'s "parameter windows do not overlap" PASS):

```
1000-1800  LVL        800   roughing level ladder
1800-2400  ERAMP      600   entry ramp directions (4/segment)
2400-2600  FLANK      200
2600-2800  free       200
2800-3000  WDEEP      200   runtime-written, per window
3000-3140  RESUME     140
3140-3160  free        20
3160-3200  LVLSPLIT    40
3200-3380  free       180
3380-3400  SECT_FLOOR  20
3400-3600  SECT       200
3600-3850  FLOORC     250
3850-4050  FC         200
4050-4330  ENTRY      280
4330-4600  STOP       270
4600-4984  CAM        384
---------------------------
allocated: 3584   free: 400   (span 1000-4984 = 3984)
```

4984 is the real ceiling, not 5000: `lathe_sections.py:4493-4499` — `#5061+`
is LinuxCNC's own (probe/home/offsets/tool table), and `#4984-#4999` is
`poly_add_item`'s own scratch on every machine, so a table straying past 4984
would be overwritten by the very subroutine that builds the record array.

**Worst real project, measured two ways:**

1. **Directly, this session** — the instrumented run (§6) on `testing_15_9`
   with its saved settings: **274** `lathe_level_pass` calls in one program
   (sectioned, multi-crossing continuations included).
2. **The codebase's own documented worst case**, sourced from
   `lathe_sections.py:3090-3098` (`analysis/118`): a 17-window Artificial part
   at 32 levels needs **544** (window, level) rows — this is the number the
   *existing* `LVL` table was sized against, and it is itself a measured
   ceiling ("peak across all 46 projects is 180" after sharing identical
   runs), not an assumption.

**Why this matters for a new per-(window, level) table**: unlike the `LVL`
radii table, a table of *resolved* `z_end` (or `s_best`/`s_bcl`) cannot
dedupe the way radii do — two windows sharing the same level radii do **not**
share the same `w_from`/`w_to`, so they do not share the same stop
extension. At even 2 slots/row (`z_start`, `z_end`) the 544-row worst case
needs **1088 slots** — nearly 3x the entire 400 free today, and more than
double the largest existing single table (`LVL`'s 800). This is the same
shape of problem `analysis/118` names directly: *"it needed 226 parameter
slots where 200 were free."*

**Conclusion for §4**: a flat per-(window, level) resolved-stop table is
**not resource-feasible today**. The per-SEGMENT tables proposed in §3 (stop
reach, flat boundary) are the ones sized against the stop/entry contour's own
point count (≤270/2=135 and ≤280/2=140 points respectively, both already
provisioned), not against the level ladder — this is why §5 stages the
per-segment items first and defers the per-row winner.

---

## 5. Staged sequence, smallest first

**Stage 0 — corpus check, no code change.** Confirm `_pl_flc_n GT 1` (floor
contour present) on all 46 projects, so the raw perpendicular-offset scan
(162-259, 270-439) is provably dead on the whole corpus before anyone plans
its removal. *Proof:* a one-line grep/generate-and-check script reporting
`_pl_flc_n` on all 46 `.ngc` outputs; the number that proves it is 46/46 GT 1.
*Untouched-case proof:* not applicable — nothing changes yet.
*Fallback:* none needed, this stage only reads.

**Stage 1 — Python shadow function, zero `.ngc` change.** Write a pure
Python function in `lathe_sections.py` that reproduces `s_reach`/`s_flat`/
`s_fz`/`e_reach` from the same tables the O-code already reads (stop
contour, entry contour, `rough_cut`). *Proof:* run it against the exact
numbers captured in §6 below — 608 stop-side rows (`SREACH`/`SCLAMP`) and 850
entry-side rows (`ENTRYCAND`) across the three projects — and require exact
agreement to 1e-4 mm. *Untouched-case proof:* not applicable, nothing in
`lib/` changes. *Fallback:* delete the function; nothing shipped moves.

**Stage 2 — per-segment table, `.ngc` shrinks.** Emit the Stage-1 values as
two new per-segment fields (mirroring `entry_ramp_dirs`'s existing 4-slot
pattern): stop-reach and flat-boundary alongside the stop contour, entry-reach
alongside the entry contour. Delete the runtime `o<s_rch>`/`o<e_rch>` formula
blocks and the `o<s_fl>` flat-scan loop; replace with a table read, gated on
a new `_pl_stopreach_n`-style count exactly like `_pl_eramp_n` today, so a
project generated before this change falls back to the current formula
byte-for-byte. *Proof:* `s_reach`/`s_flat`/`e_reach` read from the table equal
the values `test_project_sweep.py` (or a new differential check reusing §6's
harness) measures with the gate forced to 0 (old path), on all 46 projects.
*Untouched-case proof:* `test_motion_fingerprint.py --baseline` before/after,
byte-identical motion, plus the existing `test_ladder`, `test_floor_ladder`,
`test_ramps`, `test_rough_comp`, `test_x_continuity` suite green. *Fallback:*
the gate constant at 0, same mechanism `_pl_eramp_n` already proves works —
a program generated before the table existed keeps the current formula.
*Slot cost:* ≤270/2×1 (stop reach) + ≤280/2×1 (flat, likely far fewer since
it is one boundary per feature, not per point) + ≤280/2×1 (entry reach) —
order of 150-270 slots against 400 free; fits without touching the 544-row
problem in §4.

**Stage 3 — clamped-candidate winner (blocked, not scheduled).** Requires
either (a) accepting the per-call context cannot be avoided and finding
≥1088 free slots (not available today — see §4), or (b) the ladder-order
migration (`analysis/080/081/089/118`) reaching the point where window
processing order is itself table-driven and *proven* (not "nominal"), after
which `pv_end_z`/`WDEEP` become Python-predictable too and a smaller,
sequence-aware encoding becomes possible. **Do not schedule this stage until
that prerequisite's own gate (currently `[~]` in `openPoints.md`, "NOT SHRUNK
YET") closes.**

**Stage 4 — minimal-retract scan and `WDEEP` (blocked on the same
prerequisite as Stage 3).**

---

## 6. Measurements — current O-code, three projects, real numbers

**Method.** Copied `lib/lathe/lathe_level_pass.ngc` to a scratch file
(`/tmp/analysis300/instr_sub/lathe_level_pass.ngc`, never the tracked file)
and added `(print, ...)` statements — confirmed these go to `stdout`, not the
canon output, with a throwaway probe sub first. Copied
`configs/sim/axis/ncam_demo` to `/tmp/analysis300/ncam_demo_scratch`
(`cp -a`, symlinks preserved, so nothing in the real repo was touched) and
edited **only that scratch copy's** `lathe-mm.ini` to put the instrumented
directory first on `SUBROUTINE_PATH`; every other subroutine still resolves
to the real `lib/lathe` through the untouched `ncam/lib` symlink. Generated
each project's `.ngc` with `gen_project.py` (no live catalogue touched) and
ran `rs274` with `cwd` = the scratch ini's own directory (the documented
gotcha — a first attempt run from the wrong `cwd` produced an unrelated
"EOF... seeking o-word" error, confirmed by reproducing it against the
**unmodified** real ini too, i.e. not caused by the instrumentation) against
a scratch copy of the var file, never the live one. Every `gen_project.py`
and `rs274` invocation ran under `flock /tmp/ncam-rs274.lock`.

`testing_15_5.xml`, `testing_15_6.xml`, `testing_15_9.xml` all exist exactly
under `configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/` — no
substitution needed.

**Row counts** (one row = one `o<lathe_level_pass> CALL`):

| project | levels/calls | stop-side candidate rows (`SREACH`/`SCLAMP`) | entry-side candidate rows (`ENTRYCAND`) | flat-boundary hits | clamped candidate stood (`STAKE`) |
|---|---|---|---|---|---|
| testing_15_5 | 47 | 79 | 109 | 27 | 16 |
| testing_15_6 | 47 | 79 | 109 | 27 | 16 |
| testing_15_9 | 274 | 450 | 632 | 174 | 6 |

**`s_reach` values actually produced** (the floor is `3·rough_cut`; the
project's `rough_cut` = 0.508 mm, so the floor is 1.524 mm exactly, confirmed
in every sample):

- min observed: **1.524000** (the floor, unmodified by slope) — e.g.
  `testing_15_9`: `A300 SREACH lvl=32.976427 sz=-29.283486 sreach=1.524000
  sslp=0.000014 zend=-69.591970` type rows are common wherever the segment is
  near-vertical.
- max observed: **2.929396** — identical on all three projects, e.g.
  `testing_15_6`: `A300 SREACH lvl=32.969072 sz=-29.255212 sreach=2.929396
  sslp=2.929396 zend=-69.591970` — the slope term dominating on a shallow
  flank, well above the "0.90-1.00 mm" range the in-code comments (825-839)
  describe as typical, confirming the slope term is doing real work, not
  just a safety margin.

**A clamped candidate winning the pass** (the exact fault class
`analysis/023` fixed once already — this is the *current, already-fixed*
code correctly choosing between a clamped and a real crossing, captured as
ground truth for Stage 1's differential test):

```
testing_15_5: A300 STOPFINAL lvl=32.924912 shave=1 sbcl=1 sbest=-29.803721 zend=-29.268170
testing_15_9: A300 STOPFINAL lvl=32.470534 shave=1 sbcl=1 sbest=-28.305104 zend=-27.780192
```

**Flat-boundary clamp firing** (`testing_15_9`):

```
A300 SFLAT lvl=34.494107 sfz=-26.876784
A300 SFLAT lvl=33.988214 sfz=-26.876784
```

— confirming the flat point is the SAME `sfz` across different `level`
values querying the same region, exactly the "per-segment, not per-call"
property §1/§3 rely on.

**Full logs** (for anyone re-running Stage 1's differential test against
this exact ground truth): `/tmp/analysis300/testing_15_5.stdout.log`,
`testing_15_6.stdout.log`, `testing_15_9.stdout.log` — 368 `STOPFINAL` rows,
608 `SREACH`/`SCLAMP` rows, 850 `ENTRYCAND` rows total. These are scratch
files outside the repo (per the PLAN lane's write restriction) and will not
survive indefinitely — Stage 1's own work should re-run the same
instrumentation (the recipe above is complete enough to reproduce) rather
than depend on this exact `/tmp` path.

---

## Still unknown

- `lathe_level_next_start`'s own re-scan (found while reading the caller,
  §1's last row) — not measured this session, not costed, not staged. A
  separate small analysis before anyone schedules it.
- Stage 0's actual 46-project sweep was not run this session (PLAN lane
  budget went to the three named projects per the task spec) — the claim
  that the raw scan is dead code rests on the `o<flc>`/`o<mc_flc>` gate logic
  being unconditional on `_pl_flc_n`, read directly from the code, not yet
  confirmed against all 46 `.ngc` outputs.
- The stale comment at `lathe_sections.py:1733` ("the polyline's own
  argument slots stop at #3159") does not match the current layout (`LVL_BASE
  = 1000`, no collision reported by `cam_map.py`). Likely describes a
  different, sub-call-local numbering that predates the current table set —
  not chased further here since it does not affect the 1000-4984 budget
  `cam_map.py` actually verifies.
