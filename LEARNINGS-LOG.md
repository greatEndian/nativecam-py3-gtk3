# Learnings Log - NativeCAM Python 3 / GTK3 Port

## Lathe Polyline & Contour Cycles (Increment 1 & Contour Integration)
- **Coordinate Mapping**: confirmed that Mill X maps to Lathe Z, and Mill Y maps to Lathe X (Radius).
- **Diameter Mode**: Lathe X inputs in UI are diameters, but internal storage in `poly_add_item` (Mill-Y) should be radius for consistency with `poly_create` math.
- **Subroutine Path**: NativeCAM's `ncam.py` only adds one catalog's `lib/` to the `SUBROUTINE_PATH`. Reusing Mill subroutines in Lathe requires either copying them to `lib/lathe/` or moving them to `lib/utilities/`.
- **Roughing (Fallback)**: Implemented a "profile-shift" roughing strategy in `poly_lathe_mill.ngc` by shifting the coordinate system with `G10 L2` for each pass. This allows reusing the same trace logic without recalculating the entire profile for each offset.
- **Lead-in/Out**: Lathe needs its own `lead_in` and `lead_out` subroutines as the Mill ones are too complex and tied to XY plane. Created simple versions for now.
- **G71/G72 Integration**: Implemented native LinuxCNC 2.9+ G71.1/G72.1 (Type II contour roughing) support directly in `polyline.cfg`. By utilizing the `[DEFINITIONS]` block in NativeCAM's XML-to-NGC parser, we can dynamically generate an `O-word` subroutine that encapsulates the `o<trace_lathe>` calls. LinuxCNC's interpreter intercepts the G-code moves emitted by `trace_lathe` during the cycle, flawlessly mapping NativeCAM's internal array data to a standard G71 toolpath without needing complex NGC intersection math.

## G-Code Syntax Audit (Increment 3)
- **CRLF Issues**: Discovered that almost all files in the `lathe` port had Windows line endings (`\r\n`). This caused "occasional syntax errors" in LinuxCNC as the `\r` character was interpreted as part of the G-code words or block delimiters. Batch converted all `.cfg` and `.ngc` files to LF.
- **Indentation Audit**: Fixed inconsistent indentation in `facing.ngc` to ensure block delete characters (`/`) are handled correctly by all parsers.
- **Variable Consistency**: Confirmed that named parameters in LinuxCNC are case-insensitive (`#<_X_rapid>` == `#<_x_rapid>`), but standardized on consistent casing where possible.

## GTK3 Stability & UI Scaling (Increment 2)
- **Phantom Popups & Segfaults**: GTK3 dialogs instantiated with `gtk.Dialog()` and no parent can become "phantom popups" when the main application (e.g., LinuxCNC) exits. Adding `parent=toplevel` and `flags=gtk.DialogFlags.DESTROY_WITH_PARENT` ensures proper cleanup.
- **Safe `dialog.run()` Access**: When a dialog is destroyed by its parent during a `run()` loop, it returns `gtk.ResponseType.NONE`. Safely check `if response == gtk.ResponseType.OK:` before accessing child widgets (like `entry.get_text()` or `treeview.get_selection()`) to prevent `TypeError` or segmentation faults caused by accessing partially destroyed widgets.
- **Python 3 Substring Logic**: Replaced buggy string validation (`if filename[-4] != ".ngc" not in filename`) with explicit `filename.lower().endswith(".ngc")`.
- **Paned Window Scaling**: Restoring saved Paned positions (via `set_position()`) unconditionally can cause UI elements to be clipped or completely hidden on low-resolution screens. Implemented `size-allocate` event hooks on `GtkHPaned` and `GtkVPaned` to dynamically clamp the position based on `allocation.width` and `allocation.height`, ensuring both children remain visible. Also lowered `width_request` properties in `ncam.glade` to allow GTK3 to compress the window naturally for smaller displays.

## GitHub Infrastructure & CI/CD (June 16, 2026)
- **Flake8 Version Drift**: A persistent CI failure was caused by a version mismatch between the local `flake8` (v5) and the CI `flake8` (v7+). The CI command used `--select=E9,F63,F7,F82`. Version 7 introduced `F824` (unused global variable), which was caught by the `F82` wildcard, causing CI to fail while local tests passed. **Lesson**: Never use wildcards for linter selection codes; always list exact codes (e.g., `F821,F822`) or pin linter versions in CI.
- **CI Build Pathing**: When verifying a Debian build in GitHub Actions, `debian/rules` must be executed from the project root (e.g., `./debian/rules clean`), not from within the `debian/` directory, so that `dh` can find the `control` file.
- **Gettext Linting**: Functions injected into the global namespace via `gettext.install()` (like `_`) will trigger `F821 undefined name` errors in static analysis tools. Use `--builtins="_"` in the `flake8` configuration to maintain CI "green" status without introducing runtime boilerplate.
- **XEMBED vs Wayland**: Confirmed that NativeCAM's tab-embedding strategy (XEMBED) is fundamentally incompatible with Wayland. Added a diagnostic check to `ncam.py` to alert users in these environments.
- **Arithmetic Input Support**: Confirmed that NativeCAM's built-in Virtual Keyboard/Calculator (VKB) supports basic arithmetic expressions (e.g., `20-30`, `5*10`, `(10+5)/2`). This allows users to perform small calculations directly within the parameter input fields for `int` and `float` types.
- **Python 2 Legacy Tech Debt**: Replaced dozens of bare `except:` blocks with `except Exception:` and `except ValueError:` across the application to prevent NativeCAM from swallowing `KeyboardInterrupt` / `SystemExit` signals. Also replaced inline `open().read()` calls with `with open() as f:` context managers to close file handlers and avoid `ResourceWarning` leaks.
- **GTK3 Object Deprecations**: Replaced legacy `Gtk.Table` in the Virtual Keyboard with modern `Gtk.Grid`. Replaced all direct `dialog.vbox` attribute accesses with `dialog.get_content_area()`. Converted the main `NCam` widget inheritance from the deprecated `Gtk.VBox` to a standard `Gtk.Box(orientation=VERTICAL)`.

## Future Architectural Requirements
- **Live Tooling (Turn-Mill)**: Architecture needs to support **C and Y axis milling** in Lathe mode. This requires coordinate mapping flexibility to switch between G18 and G17/G19 planes, and ensuring the `ncam.py` tool table integration correctly identifies live tools.
- **Plane Switching Guards (G40)**: LinuxCNC strictly enforces that cutter compensation (`G40`) must be explicitly canceled before switching planes (`G17`, `G18`, `G19`). Failing to cancel `G41`/`G42` before a plane change throws an interpreter error. All Turn-Mill generated G-code must explicitly issue `G40` before transitioning out of the default `G18` lathe plane.

## Competitive Analysis & Inspiration
- **QTDragon Integration**: QTDragon is a modern Qt/Python3 GUI that includes advanced probing and basic conversational wizards (facing, holes). A frequent community request is embedding NativeCAM *inside* QTDragon for advanced conversational features. We should ensure our Python 3/GTK3 port architecture is modular enough to allow embedding in QtVCP/QTDragon environments via XEMBED or similar mechanisms.
- **Features vs NativeCAM**: NativeCAM is the direct successor to the legacy 'Features' system. Key advantages to maintain and emphasize include instant live preview, 'grouping' capabilities for repeated toolpaths, and direct tool-table synchronization.
