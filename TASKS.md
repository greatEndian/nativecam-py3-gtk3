# Open Points & Development Tasks

This file tracks unresolved issues and planned improvements for the NativeCAM Python 3 / GTK3 port.

## 1. Lathe Feature Parity (Priority: High)
- [x] **Lathe Polyline Support**: Adapt the `mill` polyline logic for `lathe` coordinates (X/Z).
- [x] **Lathe Contour Cycles**: Verify and fix G71/G72 integration for complex paths. Added native G71.1/G72.1 support via `[DEFINITIONS]` O-word subroutines.
- [x] **Missing CFG Files**: Added polyline-arc-to, polyline-arc-ij, polyline-polar. Improved roughing in poly_lathe_mill.ngc.

## 2. GTK3 Stability & Hardening (Priority: High)
- [x] **GTK3 Dialog Hardening**: Fixed phantom popups and segmentation faults in calculator (VKB) and parameter editor dialogs by setting transient parents, `DESTROY_WITH_PARENT` flags, and adding safe-access guards around `dialog.run()` results.
- [x] **UI Scaling**: Further refine `set_position` and Paned window logic to ensure visibility on low-res screens by reducing hardcoded `width_request` values and dynamically capping Paned handles via `size-allocate` hooks.
- [x] **Phantom Popups**: Ensure 100% of popups (combos, VKB) are destroyed on LinuxCNC exit.

## 3. G-Code Generation & Compatibility (Priority: Medium)
- [x] **LinuxCNC 2.10+ Compatibility**: Investigating XEMBED / Socket Plug lifecycle issues that cause disappearing windows in newer GtkVCP environments. (Fixed via Deferred Realization).
- [x] **Subroutine Validation**: Improved error reporting and path validation logic using `os.path.samefile` to correctly handle symlinks in `SUBROUTINE_PATH`.
- [x] **EOF / O-Word Errors**: Fixed CRLF issues in all lathe cfg/ngc files. Corrected crash in ncam.py action_save_ngc. Optimized Facing and Tool Change.

## 4. Technical Debt (Priority: Low)
- [ ] **GTK Action/UIManager Migration**: Plan a transition from deprecated `Gtk.Action` to modern `GAction` and `GMenu`. (Increment 4.1 bridge and 4.2 Project/Edit menus complete).
- [x] **Dependency Management**: Update `debian/control` and add a `requirements.txt` for non-debian users.
