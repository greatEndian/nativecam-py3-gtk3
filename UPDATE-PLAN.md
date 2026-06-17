# Update Plan: NativeCAM Python 3 / GTK3 Port Enhancements

This plan follows the `DEV-WORKFLOW.md` template to address identified open points in discrete increments.

## Increment 1 (I1): Lathe Polyline Support (Research & Mark)
**Goal:** Enable polyline features for Lathe by adapting the existing Mill logic.
- **Phase 1 (Study):** Compare `cfg/mill/polyline.cfg` with existing lathe configs (e.g., `cfg/lathe/turning.cfg`). Identify coordinate mapping (X/Y -> X/Z or Diam/Z).
- **Phase 2 (Research):** Review LinuxCNC G71/G72 requirements for profile definitions.
- **Phase 3 (Mark):** Document the mapping and potential G-code changes in `TASKS.md` or a new `LATHE-POLYLINE.md`.
- **Phase 4 (Consult):** Present the proposed mapping to the user.

## Increment 2 (I2): GTK3 Dialog Stability (Harden & Test)
**Goal:** Eliminate segmentation faults in the calculator and parameter editor.
- **Phase 1 (Study):** Identify all dialog-related calls in `ncam.py` and `pref_edit.py`. Look for `destroy()` vs `hide()` patterns.
- **Phase 2 (Build/Test):** Attempt to reproduce the crash via rapid open/close cycles in a standalone environment.
- **Phase 3 (Verify):** Implement the `Gtk.MessageDialog` pattern (if not already used) and verify memory/reference safety.

## Increment 3 (I3): G-Code Syntax Audit (Verify & Fix)
**Goal:** Resolve occasional "EOF" and "O-Word" errors in generated G-code.
- **Phase 1 (Study):** Use `grep` to find all `O<word>` generation in the python codebase and `.ngc` files in `lib/lathe/` and `lib/mill/`.
- **Phase 2 (Test):** Create a minimal reproduction `.ni` configuration that triggers the reported "Facing" or "Tool Change" error.
- **Phase 3 (Verify):** Ensure all generated subroutines have balanced `o<code> sub` / `o<code> endsub` and correct file terminations.

## Increment 4 (I4): Technical Debt - Modernizing UI Logic
**Goal:** Start the transition away from deprecated `Gtk.Action`.
- **Phase 1 (Study):** Map current `Gtk.Action` entries in `ncam.py` to `GAction`.
- **Phase 2 (Mark):** Draft a migration path that doesn't break the existing menu/toolbar structure.

## Increment 5 (I5): Live Tooling (Turn-Mill) Implementation
**Goal:** Enable C and Y axis milling operations within the Lathe catalog by implementing plane switching and live tool identification.
- [x] **Phase 1 (Scope & Study):** Review the `Tools` class in `ncam.py` to identify how live tools vs. static turning tools can be parsed from the LinuxCNC tool table.
- [x] **Phase 2 (Mark):** Document the required G-code transitions (switching between G18 XZ and G17/G19 planes) for safe Turn-Mill operations.
- [x] **Phase 3 (Implement):** Modify `Tools.load_table()` and port necessary milling features into the Lathe catalog with the correct coordinate mapping.
- [x] **Phase 4 (Verify):** Use offline numeric proof and a headless LinuxCNC INI configuration to validate safe plane switching and C/Y axis commands.

---
### Workflow Notes (from DEV-WORKFLOW.md)
- **Golden Rule:** Ensure standalone mode and default behavior remain bit-identical where possible.
- **Validation:** Use "Offline Numeric Proof" for coordinate mappings in Lathe Polyline.
- **Recording:** Append discoveries to a `LEARNINGS-LOG.md` (to be created).
