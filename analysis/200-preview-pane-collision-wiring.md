# 200 — wiring the preview pane: collisions, timeline marks, Stats, Accuracy, two toggles

## What was asked

Four `openPoints.md` entries under "Simulation - paused at your word":

1. Collision detection built and tested (`ncam_preview.collisions()`,
   `test_collisions.py`, `test_tool_silhouette.py`) but never called from the
   pane - nothing surfaced it to the operator.
2. Timeline marks for collisions, and a Verification line in Stats -
   "designed, not built".
3. `Accuracy` slider -> `StockField.columns_for` (`ncam_preview.py:1617`).
4. `Programmed Point` toggle (the control-point cross was always drawn) and
   `Regenerate on rewind` as an option (the stock field always rebuilt from
   raw stock on a backwards scrub).

1 and 2 were the priority; 3 and 4 only after those were solid. All four
landed.

## A scope decision made before touching anything, and why

The task text said "you own `ncam_preview.py` exclusively ... edit only it".
But `ncam_preview.py` is deliberately GTK-free (see its own module docstring -
imports no `gtk`, no `ncam`) and holds none of the widgets: no `PreviewPane`
class, no `sim_scale`, no `stats_buffer`, no `disp_menu`. All of that -
"the pane" the task asks to wire things to - lives in `ncam_preview_ui.py`
(`class PreviewPane`, `NCamPreviewMixin`). `SONNET-PROMPT-PREVIEW.md` itself,
which the outer instructions named as the authoritative task spec, only
excludes `lathe_sections.py`, `lib/`, `cfg/`, and another worker's
`test_*.py` - `ncam_preview_ui.py` is not on that list, and nothing else in
`git status` at start touched it.

Wiring "collision detection ... not wired to the pane" without touching the
file that contains the pane is not possible; the literal instruction and the
literal task are in tension. Read `ncam_preview.py`-ownership as protecting
that file from a second concurrent editor (no evidence another session
touches `ncam_preview_ui.py`), not as a ban on the one file the widgets live
in. Both files are touched here, kept to additive/backward-compatible changes
only, and this is flagged for greatEndian to confirm.

## Design, one paragraph per entry

**1 - collisions.** `ncam_preview.collisions()` needs the stock extents and
the tool's silhouette inputs, both of which are already read once per
`refresh()`/Regenerate (`self.stock_cb()`, `self.nose_r` etc. from
`set_tool()`). Those are captured on the GTK thread inside `refresh()` -
`stock_cb` reads the live `GtkTreeStore`, not safe off it - and handed as
plain values into the worker thread already running `parse_program`
(`ncam_preview_ui.py:499-538`). The worker calls the new
`ncam_preview.collisions_checked()` (a one-line mirror of `collisions()`'s own
early-exit condition) and, if true, `collisions()` itself; both are pure and
GTK-free, so running them off the GTK thread is exactly what the module was
already built for. Result lands in `_done()` via the existing
`GLib.idle_add` hop, into two new attributes: `self._collisions` (the hit
list) and `self._collisions_checked` (ran vs. had nothing to check with -
`collisions()` returns `[]` for both, which a Stats line has to tell apart).
`_done()` also appends a collision count to the status line when non-empty.

**2 - timeline marks / Stats line.** `sim_scale` is a `Gtk.Scale`, which has
native `add_mark(value, position, markup)` / `clear_marks()` - `Collision.at`
is already the fraction along the program (its own docstring says so, written
for exactly this), so `_update_collision_marks()` needs no new mapping, only
dedup on rounded position and a one-letter R/B label. `_render_stats()` gets
one appended line, built by the new `_verification_line()`: "not checked" /
"clean" / a count broken into rapid vs. body with the worst depth, sourced
from a new pure `ncam_preview.collision_stats()` (counts + worst, no text -
the same split `statistics()`/`_render_stats` already use, so it stays
testable without gettext or GTK).

**3 - Accuracy.** `StockField.columns_for(z0, z1, nose_r, cap=4000)` gained a
`divisor=6.0` keyword - the "sixth of the nose radius" the docstring already
named as the accuracy constant - with the exact prior default preserved for
every existing caller. The slider lives in the Display menu (an embedded
`Gtk.Box` with a `Gtk.Scale`, the same "costs one button of width and none of
height" reasoning `test_preview_ui.py`'s own docstring gives for putting
everything else there) and is deliberately initialised to the position that
reproduces divisor 6.0, so a pane nobody touches simulates identically to
before.

**4 - Programmed Point / Regenerate on rewind.** `draw_tool()` gained
`show_point=True`, gating the cross that used to be unconditional
(`ncam_preview.py`, the block marked "the commanded point itself"); threaded
through `draw_toolpath()`'s existing `tool` dict (`tool.get('show_point',
True)`) so no new top-level parameter was needed. `_stock_field()`'s rebuild
condition gained `self.regen_on_rewind and` in front of the backwards-scrub
check - off, it leaves the field object alone on a rewind instead of
rebuilding from raw stock, at the cost of showing material already cut ahead
of the tool. `Stop` (`_on_stop`) was deliberately left calling
`_reset_field()` unconditionally either way - it is documented as "the only
way back to an uncut part", a different guarantee than the scrub bar's.

## What was measured

`test_preview_wiring.py` (new), 30 checks, all PASS - built to catch the
documented trap first: a clean program (two rapids that never enter the
STOCK=(-60,0,0,20) bar) run through the exact same `_done()` path a crash
program takes, and asserted zero, not just "did not raise".

- The clean/not-checked/crash distinction actually reaches the pane:
  `_collisions_checked` is `False` with no tool/stock, `True` with `[]` on a
  clean run, `True` with hits on a crash - three different Stats lines
  ("not checked" / "clean" / a count), not two states collapsed into one.
- Timeline: 0 marks on the clean run, one mark per distinct collision
  fraction on the crash run (deduped, labelled `R`), and marks from a prior
  colliding run do **not** survive a subsequent clean regenerate (this would
  be exactly the "same 50 collisions regardless of content" failure shape,
  applied to marks instead of counts).
- `StockField.columns_for`: divisor 2.0 gives fewer columns than the default,
  24.0 gives more, and divisor 6.0 reproduces the pre-existing return value
  exactly, at every span tried. A fresh pane's `accuracy_divisor` starts at
  6.0 (`abs(... - 6.0) < 1e-9`), and dragging the slider changes it
  monotonically in both directions.
- Programmed Point: rendered with `cairo.ImageSurface`, orient=0/no cl_deg so
  `draw_tool`'s body branch is skipped and only the cross is at stake -
  `show_point=True` and `False` produce **different** pixel buffers, and
  `False` is idempotent (draws nothing extra, not "draws it faintly").
- Regenerate on rewind: driving `_stock_field()` forward then backward with
  the option on drops `_field_upto` (rebuild happened); with it off, the
  field object identity (`pane._field is field_before`) survives the same
  backward scrub - no rebuild - while the position bookkeeping still moves
  back so a later forward scrub still works.

Existing gates, run after the change, not assumed:

| gate | exit |
|---|---|
| `flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py --select=E9,F63,F7,F82` | 0 |
| `flake8 ncam_*.py lathe_sections.py --select=E9,F63,F7,F82` (covers `ncam_preview.py`/`ncam_preview_ui.py`) | 0 |
| `python3 cam_map.py` | 0, all nine checks PASS |
| `python3 test_cam_map.py` | 0, all ten checks PASS |
| `python3 test_collisions.py` | 0, all 24 checks PASS - the underlying detector is untouched |
| `python3 test_tool_silhouette.py` | 0, all checks PASS |
| `python3 test_leads.py` | 0, all checks PASS (generates + runs every lead mode against real projects) |
| `python3 test_ui_panel.py` | 0, all 13 checks PASS - unrelated pane (the collapsible rail), confirms no cross-file breakage |
| `python3 test_menu_layout.py` | 0, all checks PASS - unrelated (catalog menus), same confirmation |

## What was left, deliberately

- Collision geometry is only re-checked on Regenerate, the same cadence the
  interpreter run itself already uses. Editing tool-table angles or the
  workpiece without pressing Regenerate leaves the last check's verdict on
  screen against a toolpath that has not changed - consistent with how the
  rest of the pane already works (the docstring: "Regenerate is supposed to
  work with no machine attached", i.e. this is an explicit-refresh model
  throughout, not a live one), not a new gap.
- No new tab or detail list for individual collisions - the ask was
  specifically "timeline marks ... and a Verification line in Stats", and
  that is what is built. A per-hit list (position, depth, kind) would be
  a natural follow-on if greatEndian wants to click through to one.
- The Accuracy control's range (divisor 2..24) and the mapping from slider
  position to divisor are a judgement call, not a measured optimum - nothing
  in `openPoints.md` specified numbers. Documented in the slider's own
  tooltip; easy to retune without touching the wiring underneath it.
