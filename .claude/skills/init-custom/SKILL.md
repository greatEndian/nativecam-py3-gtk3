---
name: init-custom
description: "Use when adding a brand-new lathe/mill/plasma feature to NativeCAM (a new entry in the feature tree, not a fix to an existing one). Scaffolds the .cfg + catalog + subroutine + test wiring this codebase actually uses - not a generic framework template."
---

# /init-custom

Scaffold a new NativeCAM feature. There is no code-generator for this — it's three files kept in sync by hand. This skill exists so that sync doesn't get missed.

## The real pattern (verified against `cfg/lathe/turning.cfg`)

A feature is **not** a Python class you write — it's a template expanded by `Feature.process()` in `ncam.py`. Three pieces, all required:

1. **`cfg/<machine>/<feature>.cfg`** — INI-style. `[SUBROUTINE]` section: `version`, `icon`, `name`, `type`, `help`, `order` (space-separated param IDs controlling tree display order). One `[PARAM_<ID>]` section per editable field (`type` = `bool`/`float`/`sub-header`/etc., `value`/`metric_value` defaults, `header` links it under a `sub-header`). `[CALL]` section: the G-code template — `content =` followed by indented lines using `#param_<id>` and `#self_id` substitution, `#sub_name` for the O-word name.
2. **`catalogs/<machine>/menu.xml`** — add a `<menuitem action='...' name=... tool_tip=... icon="..." src="<machine>/<feature>.cfg"/>` inside the right `<menu>` group, and a matching `<toolitem action='...'/>` if it should also appear on the toolbar.
3. **`lib/<machine>/*.ngc`** (only if the feature calls a shared subroutine rather than inlining everything in `[CALL]`) — O-word sub with a `(CALL name[1] name[2] ...)` signature comment on the line right after `o<name> sub`. `test_lathe_validation.py` parses this comment to check call-site arg counts match.

## Steps

1. Ask (don't guess): machine (`mill`/`lathe`/`plasma`), feature name, and whether it needs a new shared subroutine in `lib/` or is self-contained in `[CALL]`.
2. Copy the closest existing `.cfg` as a starting point (e.g. `cfg/lathe/turning.cfg` for a straight-line lathe cut) rather than writing one from scratch — matching an existing structure is how this codebase avoids the load-time pre-parsing gotcha below.
3. Add the catalog entry. Confirm `src="<machine>/<feature>.cfg"` matches the new file's actual path exactly.
4. If a new `lib/` subroutine is added: put the `(CALL ...)` signature comment on the line immediately after `sub`, in the same argument order as the calls in `[CALL]`.
5. **Verify — do not skip:** run `/verifier` (flake8 + `test_lathe_validation.py` at minimum; the latter is what actually catches a mismatched call signature).
6. If the feature reads any `#<_xxx>` global named parameter in a `lib/` sub, confirm it's initialized in `Preferences.create_defaults()` (see CLAUDE.md's "Load-time pre-parsing" gotcha) — LinuxCNC validates every referenced sub at load time, so a missing default fails the *load*, not just this feature's run.

## Gotchas & Edge Cases

- A `.cfg` with no matching `catalogs/<machine>/menu.xml` entry silently never appears in the tree — no error, just missing. Always add both in the same change.
- `order` in `[SUBROUTINE]` controls displayed field order, not evaluation order — don't infer dependency order from it.
- Comments in `[CALL]` content must close on the same line (`(...)`, not multi-line) or LinuxCNC reports "Unclosed comment" at load, not at the point of the actual typo.
- Copy-pasting an existing `.cfg` and forgetting to change `type =` in `[SUBROUTINE]` produces a feature that LOOKS right in the tree but writes G-code under the wrong `type`, breaking anything that dispatches on it later (undo/redo type-checks, `test_lathe_validation.py`'s signature lookup by subroutine name, etc.) — the `type` field and the filename/subroutine name should all agree.
