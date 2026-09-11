# 128 — read-only "raw code" viewer for a tree item

**Asked**: openPoints "EVERY TREE ELEMENT SHOULD OPEN ITS OWN RAW CODE, for a
user or an integrator to customise." greatEndian, 2026-09-11: *"each element of
tree in the NCam should be able to open raw default present code to customize
it from point of user or integrator"*. Scoped to the read-only half only — the
write half needs a decision on what happens when a `cfg` `version` bump would
replace a customised copy, which has not been made.

## What was built

- `ncam_feature_tree.py`: `action_showCode`, a non-modal singleton
  `Gtk.Window` with one read-only monospace `TextView` tab per non-empty
  section a `Feature` carries (`call`, `definitions`, `before`, `after`,
  `validation`, `init`), plus a header showing `type`, `id`, and `src=`.
- `ncam_app_actions.py`: `actionShowCode` GAction, same `ca(...)` pattern as
  the existing `actionShowF` ("Show All Fields"), with a sensitivity line
  (`enabled = selected_feature is not None`).
- `ncam_menu_catalog.py`: wired into both right-click popups (`pop_up`,
  `pop_up2`) and the View menu, beside `actionShowF`.

Nothing new is stored. `Feature.attr` already carries every one of these keys
on both code paths: `from_src` (`ncam.py:2072`) populates them from the `.cfg`
`[CALL]`/`[DEFINITIONS]`/... sections, and `from_xml` copies `xml.keys()`
straight across — which is what `to_xml` dumped them as in the first place.
`self.selected_feature` was already the right target regardless of what kind
of tree row is selected: `get_selected_feature` (`ncam_feature_tree.py:104`)
walks up to the owning `Feature` whether the row is the feature itself, a
header, or a parameter.

## Read before writing

`get_toplevel()` on an embedded `NCam` (a `Gtk.Box`) does not always return a
real `Gtk.Window` — it doesn't when `NCam` has not been packed into one yet,
which is exactly the shape of `test_menu_layout.py`'s harness. Newer code in
this repo (`ncam_ui_chrome.py:176`, `ncam.py:3224`) already guards this with
`isinstance(top, gtk.Window) and top is not self` before calling
`set_transient_for`; older code (`action_renameF`) does not and throws in that
same harness today. Copied the guarded form rather than the unguarded one.

## Measured, not just read

Ran a real `ncam.NCam()` against the demo lathe config (not code review):

- Selected the `workpiece` feature from `material.cfg`, fired the action:
  produced a `Call` tab with the real 592-character template text and a
  `Validation` tab (its `before`/`after`/`init`/`definitions` are empty, so
  those tabs are correctly omitted) — header read
  `workpiece   id = workpiece_001` / `src = lathe/material.cfg`.
- Moved selection to the next row (`tool_change.cfg`), fired the action again:
  same window object reused (`win1 is win2` → `True`), tabs repopulated with
  that feature's own 2335-character `Call` text — content genuinely differs
  from the first feature's, not a stale cache.
- `test_menu_layout.py`'s click-through, which actually instantiates `NCam()`
  and activates every popup-menu action, went from 41 to 43 items with
  **0 dead** both before and after — the new action fires cleanly and does not
  throw in that harness (unlike the pre-existing `Rename`, which does, for the
  `get_toplevel()` reason above — not something this work touches).

## The motion-fingerprint gate, and a self-inflicted false alarm

First attempt reported **28 changed of 46**, all `NOGEN → real hash`. That
looked alarming but was self-inflicted: the `--write` baseline was launched in
the background and then `cam_map.py`/`test_cam_map.py`/`test_lathe_validation.py`
etc. were run concurrently with it — exactly the interleaving CLAUDE.md warns
about ("Run ONE heavy sweep at a time"). 18 projects picked up `NOGEN` in the
baseline capture from that collision, and the real run afterwards correctly
generated them, which the diff reported as "changed" against a corrupt
baseline.

Redone properly: `git stash` the three touched files, `--write` a clean
baseline alone (no NOGEN anywhere, 46/46), `git stash pop`, `--baseline`
compare alone.

**Result: 46 identical, 0 changed, 0 not in the baseline, of 46.** No `cfg/`,
`lib/`, or generation code was touched, so this is the expected outcome, now
actually proven rather than assumed.

## Also run clean

`flake8` (both file groups), `cam_map.py` + `test_cam_map.py` (6/6, all
negative controls fire), `test_lathe_validation.py`, `test_coord_mapping.py`,
`test_vkb.py`, `test_surface_equality.py` (46 generated, 38 compared), and
`test_project_sweep.py` (45 clean of 46 — `default_template.xml`'s "no motion"
is the one pre-existing expected failure, an empty project, not this change).

## Not done here

The write half (customise + persist across a `version` migration) — deferred,
per the plan, pending greatEndian's decision on keep/merge/show-both.
