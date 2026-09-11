# 132 — the raw-code viewer's real gap was which MENU it was on, not the guard

**Asked**: `e3eb103`'s `action_showCode` guards `feature is None`, but the tree
also carries parameter rows (bool/combo/float/header/…). Does selecting one
open a near-empty window without saying so plainly, and should the action be
disabled there instead — giving a user a clear difference between "empty"
and "broken"?

## Investigated, not assumed: where a parameter row's selection actually goes

`get_selected_feature` (`ncam_feature_tree.py:104`, bound to `self.treeview`,
the FEATURE tree) always walks up past every row whose `type` is in
`SUPPORTED_DATA_TYPES` — which is every parameter/header/items type there is —
before setting `self.selected_feature`. Read the list: a feature's own `type`
(`"workpiece"`, `"polyline"`, …) is never itself a member, so the walk
provably terminates on a real `Feature`, never a `Parameter`, whichever kind
of row was selected in that tree. Confirmed empirically against a real
`NCam()`: selecting each distinct row type present in the demo project
(`workpiece`, `tool_change`, `facing`, `polyline`, its `items` group, and its
`poly-line-to`/`poly_arc_to_coords` children) and firing `action_showCode`
resolved `self.selected_feature` to a genuine `Feature` every time, with real,
distinct per-feature content — no crash, nothing empty that shouldn't be.

**The actual gap is a second tree entirely.** NativeCAM has `self.treeview2`
— the details/parameter pane for whatever is currently selected in
`self.treeview` — with its own popup, `pop_up2`, which `e3eb103` also wired
"Show Raw Code" into. `tv2_selected` (`ncam_treeview.py:167`), treeview2's
selection handler, sets `self.selected_type` and `self.selected_param`
directly and **never touches `self.selected_feature` at all**. So firing
"Show Raw Code" from `pop_up2` does not crash and does not show something
wrong — it always shows the *owning feature's* template, correctly, but
identically regardless of which bool/combo/float row was actually
right-clicked. A user right-clicking one specific parameter, expecting
something about *that* parameter, and getting the whole feature's template
back with no acknowledgement of what they clicked — reads as broken, not
merely unhelpful.

## The fix: don't offer it where it can't mean what it looks like it means

Removed "Show Raw Code" from `pop_up2` only. "Raw code" (`call`/`definitions`/
`before`/`after`/`validation`/`init`) is a `Feature`-level concept; a
parameter row does not carry one of its own, so the action cannot be made
correct there without inventing content that isn't real. `pop_up` (the
feature tree) and the View menu are unaffected and remain the only places it
appears — both are provably always feature-scoped, never parameter-scoped.

Verified against a real `NCam()`: `pop_up` and the menubar still carry
`app.ShowCode`; `pop_up2` does not. `test_menu_layout.py`'s click-through goes
from 43 to 42 items with **0 dead**, unaffected otherwise.

## Hardened anyway, for a different reason than the one asked

The walk-up invariant holds today by construction, not by luck — a future
change to `SUPPORTED_DATA_TYPES` or to `get_selected_feature` could silently
break it. `Parameter` also answers `get_attr()` (returning `None` for every
key it doesn't carry), so a `Parameter` leaking through as `self.selected_feature`
would render identically to a genuinely empty `Feature` — exactly the
"empty" vs "broken" confusion this task named, just from a different cause
than the one that turned out to be real. Added a cheap `isinstance(feature,
Feature)` check in `action_showCode` itself: if it is ever not a real
`Feature`, say so in a dialog naming the actual type, rather than silently
rendering "(this feature carries no template)" for a wrong-object-type leak.
This is insurance against a future regression, not a fix for anything
currently reachable — the empirical walk above found no path that trips it
today.

## Verified

`test_menu_layout.py`: 0 dead of 42 (was 43). `flake8` on the touched files:
clean. `test_motion_fingerprint.py`: 46 identical, 0 changed, of 46 — this
session's shared gate, covering tasks A, B and C together (`analysis/130`,
`analysis/131`), since none of the three touch `cfg/`, `lib/`, or generation
code at all.
