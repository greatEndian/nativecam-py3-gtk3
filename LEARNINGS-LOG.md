# Learnings Log - NativeCAM Python 3 / GTK3 Port

## Lathe Polyline Implementation (Increment 1)
- **Coordinate Mapping**: confirmed that Mill X maps to Lathe Z, and Mill Y maps to Lathe X (Radius).
- **Diameter Mode**: Lathe X inputs in UI are diameters, but internal storage in `poly_add_item` (Mill-Y) should be radius for consistency with `poly_create` math.
- **Subroutine Path**: NativeCAM's `ncam.py` only adds one catalog's `lib/` to the `SUBROUTINE_PATH`. Reusing Mill subroutines in Lathe requires either copying them to `lib/lathe/` or moving them to `lib/utilities/`.
- **Roughing**: Implemented a "profile-shift" roughing strategy in `poly_lathe_mill.ngc` by shifting the coordinate system with `G10 L2` for each pass. This allows reusing the same trace logic without recalculating the entire profile for each offset.
- **Lead-in/Out**: Lathe needs its own `lead_in` and `lead_out` subroutines as the Mill ones are too complex and tied to XY plane. Created simple versions for now.

## G-Code Syntax Audit (Increment 3)
- **CRLF Issues**: Discovered that almost all files in the `lathe` port had Windows line endings (`\r\n`). This caused "occasional syntax errors" in LinuxCNC as the `\r` character was interpreted as part of the G-code words or block delimiters. Batch converted all `.cfg` and `.ngc` files to LF.
- **Python Crash**: Fixed a broken filename check in `ncam.py`'s `action_save_ngc` that used invalid logic (`if filename[-4] != ".ngc" not in filename :`), which would crash in Python 3.
- **Indentation Audit**: Fixed inconsistent indentation in `facing.ngc` to ensure block delete characters (`/`) are handled correctly by all parsers.
- **Variable Consistency**: Confirmed that named parameters in LinuxCNC are case-insensitive (`#<_X_rapid>` == `#<_x_rapid>`), but standardized on consistent casing where possible.

