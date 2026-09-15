# Task: "Restart NativeCAM" must rebuild in place, not leave AXIS with an empty tab

Read `/home/user/nativeCamDev/CLAUDE.md`, then
`/home/user/nativeCamDev/SONNET-LANES.md`. **Lane: GUI, in a worktree.**
Analysis range: **`analysis/280`–`289`**.

```bash
cd /home/user/nativeCamDev && python3 worker_worktree.py create restart-rebuild
cd ~/nativecam-worktrees/restart-rebuild
```

## The problem, already measured — do not re-derive it

`openPoints.md`, search *"RESTART NATIVECAM LANDS OUTSIDE THE AXIS TAB"*, and
`analysis/048-restart-lands-outside-axis.md`. Read both in full.

- `action_restart_ncam` (`ncam_app_actions.py:462`) saves, forks a relaunch
  child (`_spawn_relaunch`, `:538`) and quits the main loop.
- AXIS embeds the panel in a Tk frame with `container=1`. **Tk destroys that
  frame when the embedded window goes away**, so the replacement's XID is dead,
  `Gtk.Plug.new()` raises `BadWindow`, gladevcp swallows it, and the panel
  comes back as its own toplevel. Measured under Xvfb, not reasoned.
- AXIS's `load_gladevcp_panel()` runs once with no re-entry point. **No
  process restart can ever return to the tab.**

## The fix to build — an IN-PROCESS rebuild

The menu item exists to pick up edited `cfg/` and `catalogs/` files, not to get
a new pid. Rebuild inside the running process:

1. save the current project — `action_saveCurrent` (`ncam_feature_tree.py:55`);
2. rebuild menus and toolbars from `catalogs/<machine>/menu.xml` —
   `build_menu_from_node` (`ncam_menu_catalog.py:386`) and everything that
   calls it, including the Utilities menu at `ncam_menu_catalog.py:284`;
3. reload the project so every feature re-reads its `.cfg` — through
   `update_features` (`ncam_project_io.py:515`), the version-migration path
   that already runs on every bump;
4. leave the Gtk.Plug, the HAL component and the preview pane **untouched**.

## Plan the blast radius before editing

Per `CLAUDE.md`: find by grep, not memory, **everything** the startup sequence
builds that a rebuild must tear down or leave alone — action groups and
accelerators (a second `ca(...)` registration of the same action name),
signal handlers connected at startup, `show_all()` on new menus (the GTK3
embedding gotcha in `CLAUDE.md`), module-level state in `ncam.` that
`update_features` reads, the undo stack, the current selection, GLib timeouts
(`be094c2` was a timeout that outlived its widget). Write that table into your
analysis file before the first edit.

Decide and state what happens to the old relaunch path (`_spawn_relaunch`):
remove it if nothing else needs it, rather than keep dead code.

## Verify it yourself

Standalone NativeCAM writes to `~/nativecam` (`ncam.py:3065`), which the main
tree also uses. **Isolate it** or you will re-point the main tree's symlinks:

```bash
export HOME=$(mktemp -d)        # scratch home for every GUI run
xvfb-run -a python3 ncam.py -c lathe
```

`test_pane_layout.py` is an existing Xvfb-driven harness — copy its pattern.

The proofs, each with a number:

- **A cfg edit is picked up.** Change a parameter's display name in a scratch
  copy of a `.cfg`, trigger the rebuild, read it back from the tree model.
- **A catalog edit is picked up.** Add a menu entry in a scratch
  `menu.xml`, rebuild, find it in the rebuilt menu.
- **Nothing is duplicated.** Count actions, menu items, toolbar buttons and
  connected handlers before and after **three** consecutive rebuilds — equal.
- **The project survives.** Feature count, every parameter value and the
  generated `ncam.ngc` sha1 are identical before and after a rebuild of an
  unchanged tree.
- **The process survives.** Same pid, and a regenerate still works after it.
- `test_menu_layout.py` (cause count must not grow past 7), `test_ui_panel.py`,
  flake8 over the touched modules.

The one check you cannot do: embedded in real AXIS. Say so in the report and
give greatEndian the exact steps to confirm the panel stays in its tab.

## Deliverable

Commits on `worker/restart-rebuild`; `analysis/28N-...md` with the
blast-radius table, the proofs and their numbers; the `openPoints.md` entry
updated. Report every gate's exit code.
