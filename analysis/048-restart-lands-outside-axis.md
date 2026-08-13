# 048 — Why the restarted panel lands outside AXIS

2026-08-13, branch `liveTooling`. greatEndian: *"restart is working but it starts
in separated window outside axis ui... investigate how to reimplement to axis"*.

`96e91ec` fixed the HAL half — the panel now genuinely restarts. It comes back in
its own toplevel instead of in the AXIS tab.

## The cause, by experiment

The question was whether the container XID survives the child's exit and whether
a second process can reparent into it. Three processes under Xvfb: a Tk window
holding a frame, a GTK process doing exactly what `gladevcp.xembed.reparent`
does, and — after killing it — a third doing the same again. X errors printed,
never trapped, because gladevcp hides them under `Gdk.error_trap_push()`.

**First run, with a plain `tk.Frame`:**

```
container xid = 2097158
A: PARENT_OF 4194307 = 2097158      lands inside
after A exits, container: ALIVE
B: PARENT_OF 4194307 = 2097158      a second process reparents in fine
```

And the real relaunch mechanism — fork, wait on a pipe for the parent to exit,
`setsid`, `execv` with the same `sys.argv` — also landed back inside.

**That control was against the wrong widget.** AXIS does not use a plain frame:

```python
f = Tkinter.Frame(root_window, container=1, borderwidth=0, highlightthickness=0)
```

`container=1`. Re-running the identical experiment against a container frame:

```
A parent: PARENT_OF 4194307 = 2097156      still embeds fine
RELAUNCHING
relaunched said: PLUG A 4194307 ...        the new process did reparent
container children now: XERROR BadWindow, resource_id 0x00200004
```

**The container window no longer exists.** Tk destroys a `container=1` frame when
the window embedded in it goes away. So by the time the replacement starts, the
XID on its command line is dead: `Gtk.Plug.new()` on a destroyed window raises
`BadWindow`, gladevcp swallows it, and the plug stays an independent toplevel.

That is the reported symptom exactly, and it means **no re-exec can ever land in
the tab** — the container is gone before the replacement runs.

## Why AXIS cannot be asked to rebuild it

`load_gladevcp_panel()` is called once, at line 4291, with no re-entry point and
no IPC. AXIS tracks only the `halcmd loadusr` wrapper, which exits 0 immediately
after the component appears, so AXIS never notices gladevcp dying and offers
nothing to recreate the tab. Returning the panel to the tab needs LinuxCNC
restarted.

## What the harness got wrong, and it is the lesson

The first run validated itself against a known-good case, as required — and the
known-good case was the wrong widget. A plain frame survives its child; a
container frame does not. The harness proved a true statement about a thing AXIS
does not use.

## What is left

**In-process rebuild.** The point of "Restart NativeCAM" is to pick up changed
`cfg/` and `catalogs/` files, not to obtain a new pid — and everything needed is
reachable without touching the plug, the HAL component or the process:

- save the current project (`action_saveCurrent`, already called);
- rebuild the menus and toolbars from `catalogs/<machine>/menu.xml` —
  `ncam_menu_catalog.py`, `build_menu_from_node` and its callers;
- reload the project, which re-reads each feature's `.cfg` through
  `ncam_project_io.update_features` — the migration path that already exists and
  is exercised on every version bump;
- leave the preview pane, the plug and the HAL component alone.

Not built here: it is a real change to the startup sequence and wants its own
plan. Scoped rather than attempted blind.

## Meanwhile

The confirmation dialog now says what actually happens — the panel reopens in its
own window, the tab is left empty, and only a LinuxCNC restart returns it. It
previously promised only that "LinuxCNC and the machine are not touched", which
is true and not the part that matters.
