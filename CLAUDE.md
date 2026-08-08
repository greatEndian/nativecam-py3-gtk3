# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NativeCAM — a conversational CAM GUI for LinuxCNC (fork of FernV/NativeCAM, ported to Python 3 / GTK3 by greatEndian). Users build a feature tree (turning, facing, polylines, drilling…) in a GTK panel embedded in AXIS/Gmoccapy; the app generates `ncam.ngc` G-code that LinuxCNC loads live. Current active work is on the `liveTooling` branch: lathe polyline/contour cycles and turn-mill (C/Y axis) support.

## **Python first, O-code last — standing rule**

**Solve every problem in Python at generation time. Do not reach for G-code
O-word subroutines when Python can compute the answer first.** greatEndian made
this a standing rule, not a preference for one task.

`lathe_sections.py` is the shape to copy: GTK-free, imports nothing from
`ncam`, called from a `.cfg` `[AFTER]` block via
`<exec>print(lathe_sections.build_*_gcode(self))</exec>`, and it **emits a
point table that the `.ngc` merely walks** (`cam_load`, `_pl_fc_base`,
`_pl_env_count`). Leave the `.ngc` a walker: read the table, move.

Why, concretely: O-code cannot be unit-tested; a CALL line has a length limit
that kills the program with `Command too long`; named parameters must exist at
load-time pre-parse; and debugging means instrument, run rs274, revert, where
Python needs a print.

**And it applies backwards, to O-code that already exists.** greatEndian,
2026-08-08: *"code everything in the python — even existing O-code, move to
python if there is gap"*. Whenever a `.ngc` is opened for any reason — a bug in
it, a feature touching it, a spare gap in the work — look at what it is
*computing* and move that part to Python. Do not leave existing runtime
geometry alone merely because it works. The `.ngc` is meant to **shrink** over
time, not just to stop growing; say in the commit message what moved.

## Commands

```bash
# Run standalone (creates/uses ~/nativecam with symlinks back into this repo)
./ncam.py

# Run embedded in a LinuxCNC sim (the primary way to test changes end-to-end)
rm -f /tmp/linuxcnc.lock && halrun -U
linuxcnc configs/sim/axis/ncam_demo/lathe-mm.ini    # or mill-mm.ini, gmoccapy variants

# Lint — exactly what CI runs (never use wildcard select codes; '_' is a gettext builtin)
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
  --builtins="_" --select=E9,F63,F7,F82
# CI's file list predates the ncam.py module split — also lint the new modules locally:
flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82

# Tests — standalone scripts, no pytest harness; run individually
python3 test_lathe_validation.py   # checks cfg/lathe subroutine calls against .ngc signatures
python3 test_coord_mapping.py      # turn-mill coordinate mapping math
python3 test_vkb.py                # virtual keyboard arithmetic parser

# Motion verification (never point rs274 at a live .var — see Action buckets)
python3 .claude/skills/lathe-gcode-verify/scripts/check_tangent.py --ini <ini> --ngc <ngc>
python3 .claude/skills/lathe-gcode-verify/scripts/prove_tip_comp.py --ini <ini> --ngc <ngc> \
  --op taper|taper_id|boring|facing|radius_od|turning ...   # nose-comp tangency proof

# Debian package
cd debian && ./makedeb.sh
```

## Architecture — the G-code generation pipeline

The whole system is a template-expansion pipeline; understanding it requires connecting four directories:

1. **`catalogs/<machine>/menu.xml`** (machine = mill | lathe | plasma) defines the feature menus/toolbars per machine type. The machine is selected with `ncam -c <machine>`; it is called `cat_name` throughout `ncam.py`.
2. **`cfg/**/*.cfg`** — one INI-style file per feature. `[PARAM_*]` sections define the editable parameters shown in the tree; the `[CALL]` (or `[DEFINITIONS]`) section is a G-code template where `#param_<name>` and `#self_id` get substituted at generation time (see `Feature.process()` in `ncam.py`).
3. **`ncam.py` + the `ncam_*.py` mixins** hold the project tree as XML, expand each feature's template, and write the result to `<ini-dir>/ncam/scripts/ncam.ngc`. The file starts with a defaults block emitted by `Preferences.create_defaults()` — see the critical rule below.
4. **`lib/<machine>/` and `lib/utilities/`** — O-word subroutines (`.ngc`) called by the generated code. LinuxCNC finds them via `SUBROUTINE_PATH` in the ini (e.g. `ncam/my-stuff:ncam/lib/lathe:ncam/lib/utilities`). Note: only one machine's lib dir is on the path — lathe cannot call `lib/mill/` subs; shared code must live in `lib/utilities/` or be copied.

Embedded configs under `configs/sim/*/ncam_demo/` contain an `ncam/` directory with symlinks back into the repo, so editing `cfg/` or `lib/` here takes effect on the next G-code rebuild (subroutine edits need no rebuild at all — LinuxCNC re-reads them on file reload).

`pref_edit.py` is the preferences dialog; `ttt` wraps truetype-tracer for engraving.

### The `ncam.py` module split

`ncam.py` (~3000 lines) is no longer the whole app. It still owns the module-level surface everything else imports — the gtk/gdk aliases, `_`, the path constants (`CFG_DIR`, `CATALOGS_DIR`, …), `Feature`, `Parameter`, `Preferences`, `Tools`, `CellRendererMx`, the `mess_dlg`/`get_float`/`search_path` helpers — but the UI behaviour lives in seven mixins composed at `ncam.py:2422`:

```python
class NCam(NCamFeatureTreeMixin, NCamProjectIOMixin, NCamUIChromeMixin,
           NCamMenuCatalogMixin, NCamAppActionsMixin, NCamTreeviewMixin,
           NCamPreferencesActionsMixin, gtk.Box):
```

`ncam_feature_tree.py` (add/delete/duplicate/undo on the tree), `ncam_project_io.py` (open/save/import/export, G-code write-out), `ncam_ui_chrome.py` (menus/clipboard/help chrome), `ncam_menu_catalog.py` (builds menus+toolbars from `catalogs/*/menu.xml`), `ncam_app_actions.py` (GAction handlers, LinuxCNC interaction), `ncam_treeview.py` (cell renderers and tree display formatting), `ncam_preferences_actions.py` (validation/prefs menu actions).

Each mixin does `import ncam` **and** `from ncam import ...`: the `from` imports bind constants/classes at import time, while mutable module state is reached through the `ncam.` prefix. Keep that pattern — the imports are at the bottom of `ncam.py` (line ~2412) specifically so the module-level surface exists before the mixins load. Adding a name to a mixin's `from ncam import (...)` list is the normal way to use a new helper; moving a helper *into* a mixin will break the other six.

`lathe_sections.py` is deliberately **not** a mixin and imports nothing from `ncam` — it computes lathe polyline profile-wall sections in Python at generation time and is called from `cfg/lathe/polyline.cfg`'s `[AFTER]` block via `<exec>print(lathe_sections.build_sections_gcode(self))</exec>`. That keeps it unit-testable with plain `python3` and avoids a circular import. Any `<exec>` in a `.cfg` runs with `self` = the `Feature`, so cfg files can call Python at G-code generation time.

## LinuxCNC G-code rules that repeatedly cause bugs here

- **Load-time pre-parsing**: LinuxCNC validates all referenced O-subroutines when the file loads. Any global named parameter (`#<_xxx>`) read anywhere in `lib/` subs must be initialized in the defaults block from `create_defaults()` — gated per machine on `self.cat_name` — or loading fails with "Named parameter not defined" even if a later sequential block assigns it.
- **Reserved read-only parameters**: names like `#<_rpm>` (current spindle speed) are LinuxCNC built-ins — reading is fine, assigning fails with "Cannot assign to read-only parameter". Project-owned globals use different names (`#<_rpm_normal>`, `#<_feed_normal>`).
- **Comments must close on the same line** — a `(...)` spanning two lines is an "Unclosed comment" error.
- **A `cfg/` edit does nothing until `version` is bumped.** A saved project
  embeds the whole `after=` template, `<exec>` lines included, so NativeCAM
  reads the STORED copy until migration is triggered. `lib/*.ngc` needs no
  bump — subroutines are re-read at runtime. This asymmetry has silently eaten
  a change: the `.ngc` half took effect and the `.cfg` half did not.
- **Line endings must be LF** in all `.cfg`/`.ngc` files; `\r` characters cause intermittent interpreter syntax errors.
- **Plane/comp guard**: cutter comp must be cancelled (`G40`) before any plane switch (G17/G18/G19).
- **No nested parens inside a comment** — `(bore wall (Z0,r15))` silently halts `rs274` at that line. Whole verification runs have been invalidated by this alone.
- **A comp-entry move must be a straight feed of at least the nose radius, in free air.** An arc cannot establish compensation, and entering comp on the workpiece gouges it.

## Lathe coordinate conventions

The lathe polyline code reuses mill polyline math via a fixed mapping: **Mill X → Lathe Z, Mill Y → Lathe X (radius)**. UI X inputs are diameters; internal storage in `poly_add_item` is radius; `#<_diameter_mode>` is 1 for radius mode, 2 for diameter mode. Lathe operates in G18.

Roughing (`poly_lathe_mill.ngc` + `lathe_level_pass.ngc`) is **level-based**: each pass is a straight Z cut at one fixed diameter, stopped at the first crossing of the *normally-offset* profile (segments offset perpendicular by the current floor allowance) — not a coordinate-shifted retrace of the profile. This means radii/chamfers are only touched by levels that actually reach them, and multi-section profiles rough in one pass per level. The optional pre-finish and finish passes (`lathe_poly_pass.ngc`) instead trace the *actual* contour with a true normal offset produced by dynamic cutter compensation (`G41.1`/`G42.1 D<2×offset>`, `L0` for pure geometric offset, `L#5413` only when "Tool nose comp" is on) — this is what makes internal fillets shrink and external ones grow correctly by the offset instead of just shifting in X. Layering, deepest first: stock → roughing levels (floor = final + finish offset + pre-finish offset) → optional pre-finish contour pass (floor = final + finish offset) → finish pass(es) → final shape.

## Lathe tool-tip (nose-radius) compensation

Most recently completed work. Compensation is always **LinuxCNC native** — never hand-rolled nose geometry.

Three shared subs in `lib/lathe/` carry it, split because the polyline needs the diameter before comp is switched on:

- `tip_comp_dia.ngc CALL [extra_r] [nose_on]` — resolves nose diameter (tool table `#5410`, else the `#<_tip_nose_dia>` override) and orientation (`#5413`, else `#<_tip_orient>`) into the globals `#<_tip_comp_d>` / `#<_tip_comp_l>`, and sets `#<_tip_lead_w>` (= nose_dia × `#<_diameter_mode>`), the minimum radial clearance a comp entry/exit needs.
- `tip_comp_on.ngc CALL [side]` — emits `G41.1`/`G42.1 D#<_tip_comp_d> L#<_tip_comp_l>`, guarded on D > 0.0001.
- `tip_comp_off.ngc` — `G40`.

Per-op wiring: a `PARAM_N_COMP` combo (Off=0 / On=1) in the `.cfg` threaded as a **trailing** `[CALL]` arg — `taper.ngc`/`taper_id.ngc`/`boring.ngc` use `#7`, `facing.ngc` uses `#14`. Live in `boring.cfg`, `facing.cfg`, `taper_oda/odl/ida/idl.cfg`, `polyline.cfg`. The nose-off branch must reproduce the original code verbatim (original G0 rapids included), so `n_comp=0` is a provable no-op.

Comp side is per-op and **inverted between OD and ID** — do not copy one rule to another op:

| sub | default | flips to |
|---|---|---|
| `taper.ngc` (OD) | 42 | 41 when `begin_z LT end_z` |
| `taper_id.ngc` | 41 | 42 when `begin_z LT end_z` |
| `boring.ngc` | 41 | 42 when `begin_z LT end_z` |
| `facing.ngc` | 41 | 42 when `z_factor GT 0` |

Two op-specific consequences worth knowing before touching them: on ID work (`taper_id`, `boring`) the **post-comp radial retract must be widened by `#<_tip_lead_w>`**, or the trailing round nose swings back into the finished wall at the deep corner (~0.9 mm gouge); and `facing.ngc` **skips its lead-in/out arcs when `n_comp > 0`** (an arc cannot establish comp) in favour of a straight run-in beyond the OD — this is documented in the param tooltip because it changes the produced motion.

`radius_od.ngc` and `turning.ngc` were left on their pre-existing native `G41/G42` — both proven geometrically correct rather than rewritten. Notes: `turning`'s straight cuts are uncompensated by design (comp resolves to `G40` when radius ≤ nose), so only its corner-radius modes (2/3) compensate; both error with a large nose ("concave corner cannot be reached without gouging").

Global defaults `#<_tip_nose_dia>` / `#<_tip_orient>` come from prefs via `create_defaults()` (`ncam.py` ~line 2336) and are overridable per tool change in `cfg/lathe/tool-change.cfg`, which also shows a live read-only "nose R / orient" header sourced from `Tools.get_tool_nose_radius()` / `get_tool_orient()`. They apply only when the tool table has no D/Q — the `.cfg` guards on `> 0` so a 0 leaves the machine default alone.

### Proving a comp change

`prove_tip_comp.py` is the acceptance test, not code review: it runs `rs274`, places the nose circle at each compensated control point, and asserts tangency to the target profile with no gouge and full coverage. Correct side must PASS **and** the wrong `--freeside` must FAIL — a single profile line is tangent from both sides, so without the free-side flag a wrong side passes. Test the finish pass only (`_tool_usage=2`) so uncompensated roughing does not pollute the check. Three traps that have each cost a session: the control-point→nose-centre offset for a 90° insert corner is **R√2**, and it is a raw vector — normalising it to R·unit mis-measures; `rs274` runs with `cwd` = the ini dir, so a repo-relative `--tbl` silently aborts the run at `T<n> M6` (omit it and let the ini resolve, or pass an absolute path); and the live `lathe.var` is rewritten by the running GUI, so copy it in a retry loop to get a complete snapshot and pass it with `--var` (a truncated var also aborts at `T<n> M6`, with no error in the output).

## Compensation is all-or-nothing — standing rule

greatEndian, 2026-08-03: **if anything in an operation is compensated, then
everything in it is compensated — roughing included. The artificial sections
the back angle creates are compensated too.**

There is no "the finish pass is the one that matters". A roughing pass that
ignores the nose leaves its wall in the wrong place, and the artificial
back-angle section is a surface the tool has to hit correctly whether or not
the part drawing contains it.

State as of 2026-08-03, so the gap is known rather than rediscovered:

- `lathe_poly_pass.ngc` — pre-finish and finish, **compensated**
- `lathe_level_pass.ngc` — polyline roughing, **NOT compensated** (zero
  `tip_comp_*` references)
- `taper.ngc` / `taper_id.ngc` / `boring.ngc` / `facing.ngc` — comp is switched
  on inside the FINISHING loop only; the roughing loops above it run
  uncompensated

Closing that is ongoing work, not a decision still to be taken.

## Never claim low context without checking it

greatEndian, 2026-08-04: **do not say "I am out of context" — or low on it, or
running short — unless the actual number has been checked this turn.** It was
said twice in one session without looking, and work continued afterwards both
times, so it was simply untrue.

It also reads as an excuse for a shortened deliverable. Scaling work down is
greatEndian's call: finish it, or write down what is left in `openPoints.md`
and `session_N.md`. Saving state is the useful action; announcing scarcity is
not.

## Analysis records

Every analysis that produces a finding — a measurement run, a root-cause hunt, a
comparison of two approaches — gets written to `analysis/NNN-slug.md` **at the
time it is done**, not reconstructed afterwards. Each file carries: what was
asked, what was measured with the actual numbers, the root cause, why it was not
caught earlier, and what is still unknown.

This is a third record and it does not replace the other two: `openPoints.md` is
what is LEFT, `session_N.md` is what HAPPENED, an analysis file is the *working*
behind one finding — in enough detail that it can be re-checked or overturned.
Record failed attempts too: `analysis/001` exists partly because the first fix
was plausible, changed nothing, and was reverted.

## Session records

Before every compaction, automatic or manual, write `session_N.md` at the repo
root: what that session delivered, with the measured numbers and commit hashes,
what was decided, and what went wrong. `openPoints.md` records what is LEFT;
the session files record what HAPPENED. Neither replaces the other.

## Working conventions

- Keep responses concise — action points over prose, no restating the request back.
- For any edit touching more than one file, or any change to `lib/`/`cfg/` G-code generation logic, state a short plan (files touched, verification steps) before writing code — use `/spec-builder` for a new feature or genuinely ambiguous request.
- Before declaring done any change touching `subprocess`/shell calls, file paths built from external input, or `eval`/`exec`, run `/security-audit`.
- Before declaring any change done, or before a `git commit`: `/verifier` (or `/lathe-gcode-verify` for G-code motion changes).
- Before starting a new feature: check `md_files/LEARNINGS-LOG.md` for past edge cases in that area, and this project's own Claude memory (`project`/`feedback` entries) for prior context on the same work.

### Action buckets

- **Autopilot**: read-only exploration, `flake8`/`test_*.py`/`rs274` verification runs, formatting.
- **Ask first**: editing `cfg/`/`lib/`/`ncam.py`, installing packages, anything touching the live `lathe.var`/`ncam.ngc` the user edits in the GUI, git commits.
- **Never do**: `git push --force` / rewriting published commits / `--no-verify` on `liveTooling` or `main`, running `rs274 -v` against a live `.var` file directly (always an isolated scratch copy — see `lathe-gcode-verify`), pushing to `main` without explicit request.

## Development workflow

- `md_files/` holds project docs: `LEARNINGS-LOG.md` (append hard-won lessons there), `DEV-WORKFLOW.md` (phased increment playbook), `LATHE-POLYLINE.md`, `TASKS.md`, `GITHUB-PRACTICES.md`. It is **gitignored** — local working notes, not part of the repo, so never assume a fresh clone has it.
- `graphify-out/` (also untracked) holds a knowledge graph of the Python side: `GRAPH_REPORT.md` for orientation, `graph.json` for queries. Refresh with `graphify update .` (AST-only, no LLM cost) after a refactor; it covers `.py` files only, not `.cfg`/`.ngc`.
- The user typically tests in the AXIS GUI and drops error screenshots into `photo/` — read the newest image there when told "there is an error".
- Reference material captured from other CAM packages goes in `ref/<feature>/` (gitignored, one feature per folder, with a `NOTES.md` stating what it maps to and how faithfully to follow it). Run `/ref-intake` on it: read the material, restate it as a parameter table plus behaviour in *our* vocabulary, and stop for confirmation before writing code. Implement the behaviour, write our own tooltips, never commit the images.
- GTK3 embedding gotchas (from the port): dynamically created menu/toolbars need explicit `show_all()` (parents only call `show()` on the tab); `Gtk.Paned` size-allocate handlers need an `if pos != new_pos` guard to avoid recursion; dialogs need `parent=` + `DESTROY_WITH_PARENT` to avoid phantom windows on exit.
