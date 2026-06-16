# LinuxCNC 2.10+ Compatibility Findings

This document tracks research and potential fixes for running NativeCAM on LinuxCNC 2.10+ (Debian 13 Trixie).

## 1. Reported Issue: Disappearing Windows
Some users report that the NativeCAM tab or embedded window "disappears" or remains blank when running in newer LinuxCNC environments (GtkVCP/GladeVCP).

### Analysis
*   **XEMBED Lifecycle**: NativeCAM uses `gladevcp -x {XID}` for embedding. This relies on the X11 XEMBED protocol via `Gtk.Plug` (created by `gladevcp`) and `Gtk.Socket` (provided by the host GUI like Axis or Gmoccapy).
*   **GTK3 Realization**: In GTK3, widgets must be realized in a specific order for embedding to work. If a widget is shown or realized before it is properly attached to the `Plug`, the embedding may fail.
*   **Wayland**: If the OS is running Wayland instead of X11, `Gtk.Plug` and `Gtk.Socket` will **not work**. LinuxCNC 2.10 still defaults to X11 for most GUIs, but users on newer distros might be using Wayland.

### Potential Fixes / Recommendations
1.  **Defer Realization**: Ensure `NCam` doesn't force realization of itself or its children until it's attached to the toplevel.
2.  **Size Requests**: Some newer window managers or GTK versions may hide windows with a 0x0 size request. We have already implemented `self.set_size_request(120, 80)` in `__init__`, which is a good first step.
3.  **Check for X11**: Add a check in `ncam.py` to warn if the environment is not X11.
    ```python
    from gi.repository import Gdk
    if not Gdk.Display.get_default().get_name().startswith('X11'):
        print("Warning: NativeCAM embedding requires X11. Wayland detected.")
    ```

## 2. GAction Migration (Technical Debt)
NativeCAM currently uses `Gtk.Action` and `Gtk.UIManager`, which are deprecated in GTK3 and removed in GTK4. While they still work in the current `python3-gi` environment, they trigger many warnings and may be removed in future LinuxCNC versions.

### Proposed Path
*   **Step 1**: Map all existing `Gtk.Action` names in `ncam.py` to their functionality.
*   **Step 2**: Create a `GActionGroup` and add `GSimpleAction` for each item.
*   **Step 3**: Update `ncam.ui` to use a `Gtk.MenuBar` and `Gtk.Toolbar` connected to these actions.

## 3. Human Verification Strategy for 2.10
Since we cannot easily simulate a full LinuxCNC 2.10 environment, the human operator should verify:
1.  **Standalone Run**: Does `./ncam.py` open a dialog correctly?
2.  **Embedded Run**: Does `ncam -i config.ini -c mill` work and show the tab in Axis?
3.  **Log Check**: Check `~/.linuxcnc.log` for any "XEMBED" or "Socket" error messages.
