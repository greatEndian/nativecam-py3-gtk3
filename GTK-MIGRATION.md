# GTK Migration Plan: GtkAction to GAction

This document outlines the strategy for migrating NativeCAM from the deprecated `Gtk.Action` and `Gtk.UIManager` to modern `GAction` and `Gtk.Builder` (UI definition).

## 1. Current State
NativeCAM uses `Gtk.ActionGroup` and `Gtk.UIManager` to dynamically build its menus and toolbars.
*   **Action Definition**: Centralized in `NCam.create_actions()` using a helper `ca()`.
*   **Menu/Toolbar Building**: XML-based strings in `ncam.py` (near line 3650) are passed to `ui_manager.add_ui_from_string()`.
*   **Catalog Actions**: Dynamic actions for each catalog item (Mill, Lathe, Plasma) are created during initialization.

## 2. Target Architecture
*   **GActionGroup**: Replace `Gtk.ActionGroup` with `GSimpleActionGroup` (or add actions directly to the `Gtk.Application` or `Gtk.Window`).
*   **GAction**: Replace each `Gtk.Action` with `GSimpleAction`.
*   **GtkBuilder XML**: Replace `UIManager` XML with `Gtk.Builder` XML for `<menu>` and `<object class="GtkToolbar">`.
*   **Accel Group**: Connect accelerators directly to the toplevel window.

## 3. Step-by-Step Migration Strategy

### Step 3.1: Map All Actions
| Name | Type | Callback | Accel |
| :--- | :--- | :--- | :--- |
| `New` | Simple | `action_new_project` | `<Ctrl>N` |
| `Open` | Simple | `action_open_project` | `<Ctrl>O` |
| `Save` | Simple | `action_save_project` | `<Ctrl>S` |
| `Undo` | Simple | `action_undo` | `<Ctrl>Z` |
| `AutoRefresh` | Toggle | `_on_autorefresh_toggled` | None |
| ... | ... | ... | ... |

### Step 3.2: Implement `GAction` Wrapper
Create a new helper to replace `ca()`:
```python
def add_gaction(self, name, callback, state=None):
    if state is not None:
        action = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(state))
        action.connect("change-state", callback)
    else:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
    self.add_action(action)
```

### Step 3.3: Update UI Templates
Migrate the `UI_STRING` from `UIManager` format to `GtkBuilder` format.

### Step 3.4: Connect Toolbars and Menus
Update `ncam.ui` or the dynamic creation code to use the new action names (e.g., `app.save` or `win.save`).

## 4. Benefits
*   **Stability**: Removes hundreds of `DeprecationWarning` logs.
*   **Performance**: `GAction` is more efficient than the legacy `Gtk.Action`.
*   **Future Proofing**: Essential for eventual GTK4 compatibility.

## 5. Next Increments
*   **I4.1**: Refactor `ca()` to support both `Gtk.Action` (for compatibility) and `GAction`.
*   **I4.2**: Batch migrate "Project" and "Edit" menus.
*   **I4.3**: Batch migrate "View" and "Catalog" menus.
*   **I4.4**: Remove `UIManager` and all legacy action code.
