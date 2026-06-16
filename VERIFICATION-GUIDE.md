# NativeCAM Human Verification & Testing Guide

This guide provides a structured way for a human operator to verify the solution's integrity, focusing on UI behavior and G-code correctness.

## 1. Critical Safety & Integrity Points (Check First)
These are the "No-Go" points. If any fail, the build is considered broken.

| Point | Verification Method | Expected Result |
| :--- | :--- | :--- |
| **G-Code Syntax** | Open a generated `.ngc` in a text editor. | No `\r` (CR) characters (check with `cat -e`). Balanced `o... sub` and `o... endsub`. |
| **Coordinate Safety** | Check `G10 L2` lines in Lathe roughing. | Coordinates must not result in tool-chuck collision. |
| **Dialog Stability** | Rapidly open/close the Calculator (VKB) 10 times. | No Segmentation Fault or application hang. |
| **Subroutine Path** | Run `ncam.py` and add any item. | No "File not found" errors in the terminal or UI. |

---

## 2. Interactive Step-by-Step Test Plan
Follow these steps to verify the core workflow.

### Test A: Lathe Polyline & Contour (The "New Feature" Test)
1. **Action**: Open NativeCAM, select **Lathe Catalog**.
2. **Action**: Add a **Polyline** item.
3. **Action**: Add 3 points forming a profile (e.g., Z0 X10 -> Z-10 X10 -> Z-20 X20).
   *   **Expected**: UI preview updates immediately with the profile.
4. **Action**: Add a **G71 Roughing Cycle** and link it to the Polyline.
5. **Action**: Click **Refresh/Generate**.
   *   **Expected**: Terminal shows `Processing G71...`. G-code contains `G71` or the equivalent O-word subroutine call.
6. **Known Reply**: If UI shows "Missing profile reference", check if the Polyline `ID` matches the G71 `Profile ID`.

### Test B: UI Scaling & Responsiveness
1. **Action**: Resize the main window to the smallest possible size (800x600).
2. **Action**: Observe the **Paned** handles (dividers between tree and params).
   *   **Expected**: The handles should not "disappear" or move off-screen.
   *   **Verify**: You should still be able to grab the divider and move it.

### Test C: G-Code Generation (The "Audit" Test)
1. **Action**: Select **Mill Catalog** -> **Rectangle**.
2. **Action**: Click **Save G-Code**.
3. **Action**: Open the saved file.
   *   **Verify**: File starts with `%` (optional but standard) and ends with `M2` or `M30`.
   *   **Verify**: All O-numbers are unique (e.g., `o100`, `o101`).

---

## 3. Known Issues & "Expected" Warnings
*   **Warning**: `Gtk-Message: GtkDialog mapped without a transient parent.`
    *   *Status*: Minor. We have fixed most, but some legacy items might still trigger this. It is NOT a crash.
*   **Warning**: `Pango-WARNING: failed to create font...`
    *   *Status*: System-dependent. Can be ignored if text is visible.
*   **Error**: `XEMBED / Socket error`
    *   *Status*: **CRITICAL** for LinuxCNC 2.10. Report immediately if NativeCAM window is blank.

## 4. How to Report Results
When you verify a step, mark it as:
*   ✅ **PASS**: Behavior matches expectation.
*   ⚠️ **WARN**: Works, but UI looks "off" or warnings appear in terminal.
*   ❌ **FAIL**: Crash, incorrect G-code, or missing functionality.
