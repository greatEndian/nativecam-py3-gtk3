# 220 — a cfg can now change a parameter's minimum or maximum on an existing project

**Asked**: `openPoints.md` — *"A cfg cannot CHANGE a parameter's minimum or
maximum on an existing project. `update_features` copies the saved bounds
back over the cfg's."* Found narrowing `PARAM_BACK_CLEAR` (`analysis/043`):
cfg declared 0.01..10.0, a saved project kept -45.0..45.0 through migration.

## Consumer survey, before editing anything

`update_features` (`ncam_project_io.py:515`) is the whole migration path —
the only place a saved project's XML is reconciled against the current cfg.
Inside its per-parameter loop (matched by `call`), five attributes were
copied from the OLD saved copy (`p`) onto the freshly-parsed cfg copy (`q`):
`path`, `value`, `minimum_value`, `maximum_value`, `hidden`, `grayed`. Read
each one for what it actually represents, since the bug is exactly a failure
to draw this line:

| attribute | what it is | who should win after migration |
|---|---|---|
| `path` | tree position | neither cfg nor project — recomputed structure, unconditionally kept |
| `value` | what the operator typed | **the saved project** — the whole reason migration exists is to not lose this |
| `minimum_value` / `maximum_value` | a static declaration in `cfg/` | **the cfg** — analysis/043's own comment already argued this; nothing about a bound is project state |
| `hidden` / `grayed` | a per-project UI preference (right-click "Hide", or a validation greying a field) | **the saved project** — these are project-authored state, not cfg declarations, and out of this task's scope regardless |

No other consumer reads `minimum_value`/`maximum_value` off a saved
project's `<param>` element — `Parameter.get_min_value()`/`get_max_value()`
read `self.attr`, which after migration is `q`'s (the cfg's) values either
way once the fix lands. Grepped for `minimum_value`/`maximum_value` across
`ncam*.py`/`pref_edit.py`: only three sites — the two copy-lines removed
here, and the two getters, unaffected.

## The fix

Removed the two unconditional copy-lines. `q` is `Feature(src=src_f)` — a
fresh parse of the *current* cfg — so its own `minimum_value`/`maximum_value`
already ARE the cfg's declaration; not copying them is what lets the cfg
win, narrowing or widening alike. `value` is untouched — still copied from
the saved project exactly as before.

## The value-outside-new-bounds case — the real risk of this fix

Before this fix, a saved value could never legitimately end up outside its
own migrated bounds: the stale (saved) bound always won, so it always still
contained whatever value was saved under it. This fix makes that combination
newly reachable — a cfg author can narrow a range past a value some existing
project already has stored.

**Decision: do not clamp. Surface it instead.** Silently rewriting a saved
cutting number is a worse defect than the one being fixed — the task's own
words, and independently the right call: a clamp is a *guess* about what the
operator meant, and there is no way to make that guess correctly in general
(narrower on which side? to the nearer bound? to a default?). The value is
left exactly as saved, and a notice is raised through `Feature.msg_inv()` —
already the project's own mechanism for exactly this shape of problem,
already proven safe headless: it always prints, and only attempts a GUI
dialog when a visible toplevel exists (`analysis/070` — the guard that made
severity-1 validations safe from batch/test callers in the first place). No
new mechanism invented; reused the one already carrying this responsibility
elsewhere in the codebase, from cfg `[VALIDATION]` blocks. Msgid `900` used
as a fixed sentinel, distinct from any single-digit msgid a feature's own
cfg validation uses, so it can never collide with that feature's own
messages or be silenced by the same `EXCL_MESSAGES` entry.

## Does the version bump interact? Checked, not assumed

`update_features` migrates only when `f_B.get_version() > f_A.get_version()`
— the fresh cfg's version strictly greater than what the saved project
carries. This is unchanged by the fix; a bounds change still needs the same
`version` bump every other cfg change needs, per `CLAUDE.md`'s standing
rule. Measured directly, four saved versions against the real
`cfg/lathe/tool-change.cfg` (currently `1.24`), with a saved value (-20.0)
that only fits the OLD (wide) bound:

```
saved version=0.01  -> bounds 0.01..10.0    (0.01 < 1.24, migrates)
saved version=1.24  -> bounds -45.0..45.0   (equal, does not migrate)
saved version=1.25  -> bounds -45.0..45.0   (greater, does not migrate)
saved version=9.99  -> bounds -45.0..45.0   (greater, does not migrate)
```

Exactly the existing rule, unmodified: without a version bump, a bounds
change (like any other cfg change) does not reach an existing project at
all — `f = f_A` is used as-is.

## Verified

`test_param_bounds_migration.py`, new, run against the REAL migration path
(`NCam.update_features`) and the REAL `cfg/lathe/tool-change.cfg` —
`PARAM_BACK_CLEAR`, the exact parameter `analysis/043` found this on — with a
fabricated minimal `<feature>` standing in for the old saved copy:

- **Narrowing** (analysis/043's own worked example, saved -45.0..45.0 →
  cfg 0.01..10.0, value 2.0 inside both): bounds move to the cfg's, value
  stays `2.0`, no notice (value already fits).
- **Widening** (saved 1.0..5.0 → cfg 0.01..10.0, value 3.0): bounds move to
  the cfg's, value stays `3.0`. Proved as its own case, not assumed
  symmetric with narrowing.
- **Out-of-range** (saved -45.0..45.0, value -20.0 — inside the old bound,
  outside the cfg's 0.01..10.0): bounds still move to the cfg's, value stays
  exactly `-20.0` (not clamped), and the captured stdout contains the notice
  naming the value and both new bounds.
- **Negative control**: the narrowing case's own in-range value (2.0) is
  asserted to print no notice — proves the out-of-range check is not simply
  always firing.

Proven failing on the pre-fix code, not just passing on the fix: `git stash`
of `ncam_project_io.py` alone, same test, same run — 4 of 8 checks fail
(`got -45.0..45.0` / `-45.0..45.0` / `1.0..5.0` / no notice printed),
restored immediately after.

```
flake8 ncam_project_io.py                exit 0
flake8 (core files)                      exit 0
flake8 ncam_*.py lathe_sections.py       exit 0
python3 cam_map.py                       exit 0, 9/9
python3 test_cam_map.py                  exit 0
python3 test_lathe_validation.py         exit 0
python3 test_coord_mapping.py            exit 0
python3 test_vkb.py                      exit 0
python3 test_ui_panel.py                 exit 0
python3 test_menu_layout.py              exit 0 (0 dead of 42)
python3 test_param_bounds_migration.py   exit 0, 8/8, negative control confirmed failing pre-fix
```

## Non-interference

Two other files this task does not own (`ncam_preview.py`, `ncam_preview_ui.py`)
were mid-edit by another session throughout this work — confirmed by
`git diff --stat` before and after every `git stash` used to produce the
negative control above, each scoped to `-- ncam_project_io.py` only, so
those files' uncommitted state was never touched by this work. Not read,
not edited.

## What was NOT done

`hidden`/`grayed` were read during the survey and left exactly as they were
— they are project-authored UI state, not cfg declarations, and changing
their behaviour is outside what this task asked for. `pref_edit.py`,
`lathe_sections.py`, `lib/`, and `cfg/` templates were not touched, per the
task's own ownership boundary.
