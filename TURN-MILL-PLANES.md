# Turn-Mill Plane Switching (G17 / G18 / G19)

This document details the G-code transitions required for safe Live Tooling (Turn-Mill) operations within NativeCAM's Lathe catalog (Increment 5).

## 1. Plane Definitions in LinuxCNC
- **`G18` (XZ Plane):** The default plane for Lathe operations. Circular interpolation (`G2`/`G3`) and cutter compensation (`G41`/`G42`) operate on the X and Z axes. *Note: X is typically in diameter mode (`G7`).*
- **`G17` (XY Plane):** Face Milling. Used when applying endmills, drills, or taps to the face of the turned part.
- **`G19` (YZ Plane):** Cross / OD Milling. Used when applying tools to the outside diameter (OD) of the part.

## 2. Safe Plane Transition Protocol
LinuxCNC enforces strict rules regarding plane switching. Attempting to change planes while certain modes are active will result in interpreter errors.

Whenever a NativeCAM Live Tool feature is called, the generated G-code **must** execute the following sequence:

1. **Safe Retract:** Move to a safe Z and X clearance (e.g., `G0 X#<_x_clear> Z#<_z_clear>`).
2. **Cancel Cutter Compensation (`G40`):** *CRITICAL.* LinuxCNC will throw an error if a `G17/G18/G19` command is issued while `G41` or `G42` is active.
3. **Cancel Canned Cycles (`G80`):** Ensure no lingering drill/bore cycles are active.
4. **Spindle Transition:** 
   - Stop main turning spindle (`M5`).
   - Engage C-axis indexing (if applicable).
   - Start live tooling spindle (often mapped as secondary spindle, e.g., `M3 $1` or machine-specific `M103`/`M104`).
5. **Switch Plane:** Issue `G17` or `G19`.

*To return to standard turning, the inverse transition must occur, ending with `G18`.*

## 3. Coordinate & Axis Mapping Strategy
For Milling features imported into the Lathe catalog:
- **Face Milling (G17):** 
  - NativeCAM Mill `X` -> Lathe `X` (or `C` depending on kinematics).
  - NativeCAM Mill `Y` -> Lathe `Y`.
  - NativeCAM Mill `Z` (Depth) -> Lathe `Z`.
- **Cross Milling (G19):**
  - NativeCAM Mill `X` -> Lathe `Y` (or `C`).
  - NativeCAM Mill `Y` -> Lathe `Z`.
  - NativeCAM Mill `Z` (Depth) -> Lathe `X` (Depth of cut).

## 4. Verification Checkpoints
- **G40 Guard:** Audit all generated turn-mill `.ngc` files to guarantee `G40` precedes `G17`/`G19`.
- **Diameter Mode Conflict:** Ensure milling operations in the X-axis account for `G7` (Diameter mode) vs `G8` (Radius mode) if the machine does not automatically switch interpreting X based on the active plane.
- **Tool Table:** Utilize the `TOOL_TABLE.is_live_tool()` and `TOOL_TABLE.get_tool_diameter()` logic now implemented in `ncam.py` to automatically trigger plane switching when a live tool is loaded.

## 5. Implementation in NativeCAM (.cfg files)
With the live tool detection built into `ncam.py`, turning features can dynamically switch planes using NativeCAM's `<eval>` tags.

**Example `[CALL]` section in a milling feature ported to the Lathe catalog:**
```ini
[CALL]
content =
    ; If the selected tool is live, cancel comp, switch spindle, and drop into G17
    <eval> 'G40\nM5\nM3 $1\nG17' if TOOL_TABLE.is_live_tool(get_int(self.get_param('tool').get_value())) else '' </eval>
    
    ; ... execute milling toolpath ...
    
    ; Return to standard turning plane when done
    <eval> 'G18' if TOOL_TABLE.is_live_tool(get_int(self.get_param('tool').get_value())) else '' </eval>
```