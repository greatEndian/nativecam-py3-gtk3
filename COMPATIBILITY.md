# LinuxCNC 2.10+ Compatibility Findings

This document tracks the research and solutions implemented for running NativeCAM on LinuxCNC 2.9/2.10+ (Debian 13 Trixie).

## 1. Resolved Issue: Disappearing Windows in Embedded Mode
The issue where the NativeCAM tab or embedded window would "disappear" or remain blank in newer LinuxCNC environments (GtkVCP/GladeVCP) has been addressed.

### Analysis
*   **XEMBED Lifecycle**: NativeCAM uses `gladevcp -x {XID}` for embedding. This relies on the X11 XEMBED protocol via `Gtk.Plug` (created by `gladevcp`) and `Gtk.Socket` (provided by the host GUI like Axis or Gmoccapy).
*   **GTK3 Realization**: In GTK3, widgets must be realized in a specific order for embedding to work. If a widget is shown or realized before it is properly attached to the `Plug`, the embedding may fail.
*   **Wayland**: If the OS is running Wayland instead of X11, `Gtk.Plug` and `Gtk.Socket` will **not work**. LinuxCNC 2.10 still defaults to X11 for most GUIs, but users on newer distros might be using Wayland.

### Implemented Solutions
1.  **Deferred Realization**: The `NCam` class now uses `realize` and `size-allocate` signal handlers (`_on_realize`, `_setup_toplevel_integration`) to ensure it only fully initializes after being attached to its parent toplevel window. This resolved the XEMBED race condition.
2.  **Minimum Size Request**: A `self.set_size_request(120, 80)` call was added to `NCam.__init__` to prevent window managers from hiding the widget due to an initial 0x0 size.
3.  **Wayland Detection**: A check for non-X11 display servers was added to the top of `ncam.py`. It now prints a clear warning to the console if a Wayland environment is detected, informing the user that embedding will not work.

## 2. Completed: GAction Migration
The technical debt related to `Gtk.Action` and `Gtk.UIManager` has been fully paid down.

### Status: 100% Complete
*   All `Gtk.Action` and `Gtk.RadioAction` instances have been replaced with modern `Gio.SimpleAction` objects.
*   The deprecated `Gtk.ActionGroup` has been removed entirely.
*   The UI now uses a standard `Gtk.MenuBar` and `Gtk.Toolbar` connected to the new `GAction`s. This has eliminated hundreds of deprecation warnings and makes the application more robust for future GTK versions.

## 3. Human Verification Checklist for 2.10+
To confirm compatibility, the operator should verify:
1.  **Standalone Run**: Does `./ncam.py` open a dialog correctly?
2.  **Embedded Run**: Does `ncam -i config.ini -c mill` work and show the tab correctly in Axis or Gmoccapy?
3.  **Log Check**: Check `~/.linuxcnc.log` for any "XEMBED" or "Socket" error messages.
4.  **Wayland Check**: If running on a Wayland-by-default system (e.g., modern Ubuntu/Fedora), confirm that a warning is printed to the console when launching LinuxCNC with an embedded NativeCAM tab.
