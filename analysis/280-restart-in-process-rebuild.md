# 280 — "Restart NativeCAM" becomes an in-process rebuild

2026-09-16, branch `worker/restart-rebuild` (worktree off `liveTooling`), GUI
lane. Continues `analysis/048`, which measured the cause (Tk destroys a
`container=1` frame when its embedded child exits, so no re-exec can ever
land back in the AXIS tab) and scoped but did not build the fix.

## What was asked

Replace `action_restart_ncam`'s fork/exec/quit with an in-process rebuild:
save, rebuild menus/toolbars from the catalog, reload the project through
`update_features` so every feature re-reads its `.cfg`, leave the `Gtk.Plug`,
HAL component and preview pane untouched.

## Blast radius — found by grep, before any edit

| what the startup sequence builds | where | touched by rebuild? | how |
|---|---|---|---|
| `self.catalog` (parsed `menu.xml`/`menu-custom.xml`) | `ncam.py:3132-3151` (`__init__`) | **rebuild** | re-parse from disk via new shared `_load_catalog_xml()`, same regex/`search_path` logic as `__init__`, factored out so both call the same code |
| `ncam.TB_CATALOG` (toolbar defs keyed by rank) | `get_toolbar_actions()`, `ncam_menu_catalog.py:438` | **rebuild** | already resets `ncam.TB_CATALOG = {}` at the top of the toolbar branch — safe to call again |
| `self.menubar` | `create_menubar()`, `ncam_menu_catalog.py:146` | **rebuild** | already idempotent: `if self.menubar is not None: self.menubar.destroy()` then rebuilds and `pack_start`s a new one — same pattern `_apply_icon_colour` already uses on a live panel |
| `self.nc_toolbar` | `create_nc_toolbar()`, `ncam_menu_catalog.py:494` | **rebuild** | same idempotent destroy/rebuild pattern |
| menubar/toolbar packing order in `main_box` | `restore_bar_order()`, `ncam_app_actions.py:335` | **rebuild** | both `create_*` calls `pack_start` (append) — existing helper (already used by `_apply_icon_colour`, NOT by `action_preferences` — a pre-existing gap out of scope here) re-orders back to position 0/1/2 |
| Add-dialog icon store + `self.catalog_src`/`self.catalog_path` | `create_add_dialog()`, `ncam_app_actions.py:628` | **rebuild** | `catalog_src` points into the OLD `self.catalog` tree; calling `create_add_dialog()` again re-derives it from the new tree and repopulates `icon_store` via `update_catalog()` — new `ListStore` object, `add_iconview.set_model()` swaps it, no leak |
| `gaction_group` (`Gio.SimpleActionGroup`, "app" prefix) | `create_actions()`, `ncam_app_actions.py:645` | **NOT touched** | `add_action()` on a name that already exists replaces the old `GSimpleAction` (GHashTable keyed by name), but every `ca(...)` call ALSO does `self.accel_group.connect(key, mods, ...)` — that is a plain multi-entry accelerator table, calling it twice means a keypress fires BOTH the old and new callback. **Decision: never call `create_actions()` again.** Confirmed nothing else needs it — menu items look up `app.<name>` by string at activate time, so leaving the actions alone and only rebuilding the menu/toolbar widgets around them is sufficient and duplicate-free |
| `self.accel_group` / `self.accels` dict | `__init__:3213-3221` | **NOT touched** | not rebuilt; `create_menubar()`'s `_create_menu_item` reads `self.accels[action_name]` unchanged |
| `self.pop_up` / `self.pop_up2` (right-click menus) | `create_popups()`, `ncam_menu_catalog.py:38` | **NOT touched** | built entirely from `self.actionXxx` action objects (Digit1-6, DataType, Undo, …) — no catalog content, so a catalog reload does not affect them, and they are never rebuilt today except at startup |
| undo stack (`self.undo_list`, `self.undo_pointer`) | `ncam_feature_tree.py` | **reset** | `load_currentWork()` — the existing project-open path used for the rebuild's project-reload step — calls `self.clear_undo()` itself. Same as opening any project; expected |
| current selection (`selected_feature*`) | various | **reset** | `load_currentWork()`'s `expand_and_select((0,))` resets it the same way opening a project always does |
| GLib timeouts: auto-refresh (`ncam_feature_tree.py:548`), simulation tick (`ncam_preview_ui.py:867`) | | **NOT touched** | neither is owned by anything the rebuild destroys — the treeview and preview-pane widgets are left alone entirely (per the task's explicit "leave the preview pane untouched"), so `_cancel_autorefresh_timer()`'s normal re-arm on `load_currentWork()`'s `self.action(nxml)` call is the only interaction, identical to a normal project open |
| `Gtk.Plug` / HAL component | outside `NCam`, in gladevcp/AXIS | **NOT touched** | never referenced by anything in the rebuild path |
| `Feature`/`.cfg` caching | `Feature.from_src()`, `ncam.py:2004` | **N/A — no cache exists** | reads the `.cfg` file fresh with `io.open()` on every construction; `update_features()` constructs a fresh `Feature(src=...)` per feature, so a `.cfg` edit is picked up automatically, no cache to invalidate |
| pixbuf cache (`PIXBUF_DICT`) | `ncam.py` `get_pixbuf`/`set_icon_accent` | **NOT touched** | only cleared on an icon-colour change; a catalog edit that reuses existing icon files needs no clear (confirmed not exercised by the icon-swap proof below, which reuses an existing icon) |

## The fix

New shared method `_load_catalog_xml()` in `ncam_menu_catalog.py` (`NCamMenuCatalogMixin`),
extracted from the exact block `__init__` already used (`menu-custom.xml` then
`menu.xml` fallback, `_(`/`)_` stripped, `etree.fromstring`), raising
`RuntimeError` instead of `sys.exit(1)` — `__init__` catches it and still
exits (unchanged startup behaviour); the rebuild catches it and reports via
`mess_dlg` without touching the running panel.

New method `_rebuild_panel()` in `ncam_app_actions.py`:

```python
def _rebuild_panel(self):
    self.catalog = self._load_catalog_xml()
    self.get_toolbar_actions()
    self.create_menubar()
    self.create_nc_toolbar()
    self.create_add_dialog()
    self.menubar.show_all()
    self.nc_toolbar.show_all()
    self.restore_bar_order()
    self.load_currentWork()
```

`action_restart_ncam` now: confirm dialog (text rewritten — no longer claims
the panel lands outside the tab, since it no longer does), save, call
`_rebuild_panel()` inside try/except reporting failure via `mess_dlg`. No
`gtk.main_quit()`, no relaunch.

## `_spawn_relaunch` — removed, not kept as a fallback

Sole caller was `action_restart_ncam`; `analysis/048` measured, not guessed,
that the container XID is dead by the time the child execs — **no** path
through `_spawn_relaunch` can ever reach the tab, so keeping it as a
"fallback" would be keeping a provably-broken code path with no test to catch
its breakage silently regressing further. Removed the method and its
`_relaunch_fd` arm-guard entirely (grep confirmed no other reference anywhere
in the tree, including tests).

## Proofs — numbers, not review

See harness `test_restart_rebuild.py` (Xvfb, own `HOME`, copies the demo
sim config into a scratch dir exactly like `test_menu_layout.py::_check_popups`
does). Results below were captured with:

```
export HOME=$(mktemp -d)
xvfb-run -a python3 test_restart_rebuild.py
```

All PASS, exit 0. The proofs, with their numbers:

- **cfg edit picked up** (`PROOF 1`) - `cfg/lathe/facing.cfg`'s `PARAM_B_X`
  name edited to `"Begin diameter EDITED"` and its `version` bumped by 1.0 in
  a materialized scratch copy (never the tracked file - `git status` checked
  clean before and after); `app.update_features()` on a fabricated saved
  `<feature type="facing" version="0.01">` returns the new name and the new
  version. Confirms the FEATURE-level `name` is intentionally NOT re-picked
  (copied from the old saved xml, preserving a user rename across a cfg
  edit) while a PARAMETER's `name` always comes fresh from the cfg - read
  the whole migration loop in `ncam_project_io.py:515` before picking this
  proof; the feature-level property would have proven the opposite of what
  was asked.

  **A scare worth recording**: mid-session, `git status` briefly showed
  `cfg/lathe/facing.cfg` as modified with exactly this edit's content.
  Reverted immediately with `git checkout -- cfg/lathe/facing.cfg`, then
  re-verified independently with `diff <(git show HEAD:cfg/lathe/facing.cfg)
  cfg/lathe/facing.cfg` - byte-identical - and `git status --porcelain`
  clean for the rest of the session, checked again at hand-off. The exact
  moment/mechanism was not pinned down, but the harness's write path was
  re-audited line by line and is sound as it stands: the only `open(...,
  'w')` in the whole file writes to `facing_cfg = os.path.join(cfg_link,
  'lathe', 'facing.cfg')` where `cfg_link = os.path.join(dst, 'ncam',
  'cfg')` and `dst` is always a fresh `tempfile.mkdtemp()` result - never
  `HERE/cfg/...`. Several background copies of this same test were
  launched and killed by PID earlier in the session while debugging the
  two Xvfb hangs below, so a stale/overlapping run is the leading
  candidate, not a bug in the script as it reads now - but that is not
  proven, only the CURRENT clean state and the CURRENT script's safety
  are. Recorded here rather than swept under, because CLAUDE.md is
  explicit that a tracked-file mutation is the one class of mistake to
  never wave past.
- **catalog edit picked up** (`PROOF 2`) - one `<menuitem>` inserted into a
  materialized scratch `catalogs/lathe/menu.xml` (never the tracked file);
  after `_rebuild_panel()`, `count_menu_items(app.menubar)` is exactly
  baseline+1, and the new item is present by its label (catalog-built items
  connect `"activate"` directly - `build_menu_from_node` sets no Gio action
  name, unlike the static menubar items `_create_menu_item` builds, so the
  proof has to search by label, not `get_action_name()`).
- **nothing duplicated across 3 rebuilds** (`PROOF 3`) - `create_actions()`
  wrapped with a call counter: **0** calls across 3 `_rebuild_panel()` calls
  (only the original `__init__` call ever happens). Action count, GAction
  name count, menu item count and toolbar button count all identical across
  all 3 rebuilds.
- **the project survives, unchanged** (`PROOF 4`) - feature count and the
  full `treestore_to_xml()` serialization byte-identical before/after 3
  rebuilds; `ncam.ngc`'s sha1 identical before/after.
- **the process survives** (`PROOF 5`) - `os.getpid()` identical throughout;
  a `write_ngc()` regenerate after 3 rebuilds still produces a non-empty
  file.

## Other gates

- `flake8 ncam.py ncam_app_actions.py ncam_menu_catalog.py
  test_restart_rebuild.py --builtins="_" --select=E9,F63,F7,F82` - exit 0.
- `test_ui_panel.py` - exit 0, unaffected (touches `ncam_ui_chrome.py`,
  which this change does not).
- `test_menu_layout.py` - **exit 1 in this worktree, but not a regression -
  proven by an A/B run, not assumed.** `_check_popups()` builds a real
  `ncam.NCam()` and found an 8th no-selection traceback cause
  (`action_appendItm`, alongside the 6 documented ones and `action_renameF`)
  where the test's own gate wants ≤7. Root cause: a fresh worktree's demo
  `ncam/` (from `worker_worktree.py link-sim`) carries only the `cfg`/`lib`/
  `graphics` symlinks, not the real, gitignored
  `ncam/catalogs/lathe/projects/current_work.xml` the main tree has
  accumulated from actual use - `SONNET-LANES.md` documents this exact gap
  ("a worktree has none of them"). With no saved current-work project,
  `_check_popups()` falls back to `action_new_project()`'s bare default
  template, and `action_appendItm` ("Add to Items") raises on that empty
  selection state where it does not against the main tree's real, populated
  one.

  Proved with an A/B, not just reasoned: ran the identical, **unmodified**
  `test_menu_layout.py` three ways -
  1. main tree (`/home/user/nativeCamDev`, my diff not present, its own
     real `current_work.xml`) - **exit 0, exactly 7 causes**.
  2. this worktree, my diff active, empty project (no `current_work.xml`)
     - **exit 1, 8 causes** (`action_appendItm` added).
  3. this worktree, my diff active, main tree's real `ncam/catalogs` and
     `ncam/my-stuff` copied in (gitignored, `git status` clean, removed
     again afterward) - **exit 0, exactly 7 causes**, matching (1).

  (3) isolates the one variable: same code as (2), same fixture as (1),
  passes. The 8th cause is the worktree's missing project-state fixture,
  not this change. Two more local, gitignored fixtures were needed before
  ANY real `ncam.NCam()` could even be built here without hanging - see
  "Two hangs found and fixed, both pre-existing" below.

## Two hangs found and fixed, both pre-existing environment gaps

Neither is caused by this change; both block *any* headless real-`NCam()`
test in a fresh worktree, so they had to be fixed to get real numbers at
all. Both fixes are local, gitignored files - `git status --porcelain`
checked clean after each.

1. **Missing tool table.** `Tools.set_file()` (`ncam.py:665`) resolves the
   ini's `TOOL_TABLE` with `search_warning.dialog` - a miss calls
   `mess_dlg()`, which is a **modal `.run()`** with nothing under Xvfb to
   click it. `configs/sim/*/ncam_demo/*.tbl` is `.gitignore`d (locally
   generated state), and a fresh worktree never had one. Fixed by copying
   the project's own canonical `configs/common/lathe_mm.tbl` to
   `configs/sim/axis/ncam_demo/lathe_mm.tbl`.
2. **Missing M123 marker.** `NCam.__init__` (`ncam.py`, near the end) calls
   `create_M_file()` whenever `NCAM_DIR/scripts/M123` does not exist yet -
   and `create_M_file()` itself unconditionally ends in a blocking
   `mess_dlg('LinuxCNC needs to be restarted now')` (`ncam.py:656`). The
   main tree's `ncam/scripts/M123` exists from a real prior launch; a fresh
   worktree's `ncam/` (from `link-sim`) never gets one. Confirmed by
   screenshot (`xwd`+`convert` against the Xvfb display while the process
   sat at 0:00 CPU time after 900+ real seconds) before diagnosing it in the
   source - the "measure before concluding" rule paid for itself here: the
   first hypothesis (TOOL_TABLE dialog again) was wrong, this is a second,
   distinct dialog. Fixed by creating an empty
   `configs/sim/axis/ncam_demo/ncam/scripts/M123`.

Both are exactly the class of "local generated state a fresh worktree
lacks" `SONNET-LANES.md` and `WORKTREES.md` already document for the 46
test projects - not new problems, just two more instances of the same one,
now named so the next worktree worker does not lose an hour to them.
