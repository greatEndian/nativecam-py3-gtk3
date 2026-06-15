# Lathe Polyline Implementation Plan (I1)

## Overview
Adapt the existing Milling Polyline system for Lathe operations (G18 XZ plane).

## Coordinate Mapping
To reuse as much logic as possible from the `poly_add_item` and `trace` subroutines:
- **Mill X** -> **Lathe Z** (Length)
- **Mill Y** -> **Lathe X** (Radius/Diameter)
- **Mill Z** (Depth/Plunge) -> **Lathe X Offset** (for roughing passes)

## Required Configuration Files (cfg/lathe/)
- [ ] `polyline.cfg`: The main polyline container.
- [ ] `polyline-to.cfg`: Straight line item.
- [ ] `polyline-arc-to.cfg`: Arc item.
- [ ] `polyline-arc-ij.cfg`: Arc with center item.
- [ ] `polyline-polar.cfg`: Polar line item.

## Required Subroutines (lib/lathe/)
- [ ] `poly_lathe_mill.ngc`: Adapted from `mill/poly_mill.ngc`.
  - Must use `G18`.
  - Must handle `X` and `Z` axes.
  - Must handle diameter mode (`#<_diameter_mode>`).
- [ ] `trace_lathe.ngc`: Adapted from `mill/trace.ngc`.
- [ ] `g123_lathe.ngc`: Adapted from `mill/g123.ngc`.
  - Uses `I` and `K` for arcs in G18.

## Menu Integration
- [ ] Update `catalogs/lathe/menu.xml` to include a "Polylines" sub-menu.

## Technical Decisions
- **Roughing Strategy**: Initially implement "profile-shift" roughing where the entire polyline is offset in X for each pass.
- **Diameter Mode**: All X-axis inputs in the UI will be treated as diameters if the machine is so configured, matching the behavior of `turning.cfg`.
