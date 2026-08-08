# Lathe polyline — gaps against a reference CAM package

Implementation notes. greatEndian is capturing screenshots from their own CAM
software; each one gets read here, restated **in our vocabulary**, and compared
against what `cfg/lathe/polyline.cfg` already has. **Only what we do NOT have
gets written down.** Anything we already do, under whatever name, is noted as
equivalent and dropped from the list.

Working rule, from `CLAUDE.md`: reference material is read and restated, never
copied. Screenshots live in `photo/` or `ref/<feature>/`, both gitignored, and
are never committed. This file is tracked, because it is what we implement from.

Nothing is implemented off this list without greatEndian confirming the entry
first — `/ref-intake` stops for confirmation before any code.

---

## What our polyline has today

`cfg/lathe/polyline.cfg` version **1.43**, 44 parameters. The baseline any
screenshot is compared against.

| group | parameters |
|---|---|
| **Roughing** | Strategy, Operation, Respect tool back angle, Pre-finish pass, Space passes from, Skip short roughing passes, Skip thin roughing passes, Pause after roughing, Direction, Re-entrant profile, Pre-finish offset (per side), X wall cut, Z section length, Sectioning |
| **Retract / start point** | Retract, Retract distance, Return to start point, Start point X, Start point Z, Z lead-in distance |
| **Finishing** | Tool nose comp, Offset (per side), Passes, Direction |
| **Lead in / out** | Lead-in length / angle / radius / feed, Lead-out length / angle / radius / feed |
| **X axis** | Side, Start Diameter, Final Diameter |
| **Z axis** | Start Z |
| **Geometry** | Items (Line To, Line Polar, Arc To Coords, Arc I,K) |

Depth of cut, feeds and speeds come from the **Tool Change** feature, not from
the polyline: `_rough_cut`, `_finish_cut`, `_rough_feed`, `_finish_feed`, plus
the nose radius / orientation and the back-angle geometry.

Behaviour already implemented that a screenshot may show as a property, and
which we should NOT re-add under a new name:

- roughing levels stop on the **pre-finish contour**, not on the raw profile;
- one roughing **floor per region** of the profile, the ladder re-anchoring on
  each (`analysis/022`);
- the profile-angle **ramp** into each pass, all on one line (`analysis/023`);
- **tool nose compensation**, CNC-side or CAM-side, on the contour passes;
- the **reachable contour** — the tool's back angle shadow — and a warning
  naming any span that cannot be made.

---

## Gaps

*Empty until the first screenshot is read.*

Each entry, once there is one:

- **What it is** — the reference package's own term, and what it appears to do.
- **In our vocabulary** — the parameter or behaviour it would be here.
- **Why it is a gap** — what we cannot express today.
- **What it would touch** — cfg parameter, Python, `.ngc`, preview.
- **Open question** — anything the screenshot does not settle.

---

## Read and dismissed

*Things a screenshot showed that we already have, kept so they are not
re-raised.*
