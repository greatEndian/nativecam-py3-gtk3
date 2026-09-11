# 131 — test_menu_layout's 22 tracebacks: category (ii), pinned by cause not count

**Asked**: `test_menu_layout.py` passes while printing 22 tracebacks
(`grep -c Traceback` confirmed the number, and analysis/126 had already noted
it in passing without chasing it). Decide whether they are real errors a user
can hit (fix to 0, with a negative control) or unavoidable harness noise
(assert the count does not grow, with the reason written next to it) — and
make the gate able to fail either way.

## What actually raises, traced to source

Captured with `contextlib.redirect_stderr` around the popup walk (22
tracebacks, matching the grep count exactly) and grouped by the innermost
`ncam_*` frame:

| callback | count | reads |
|---|---|---|
| `action_digits` | 12 | `self.treestore.get(self.selected_param, 0)` |
| `action_hideField` | 2 | same |
| `action_chng_group` | 2 | same |
| `action_gcode` | 2 | same |
| `action_revert_type` | 2 | same |
| `action_removeItem` | 1 | `parent.tag` on a `None` parent |
| `action_renameF` | 1 | `get_toplevel()` for a dialog's `transient_for` |

Seven distinct call sites, not 22 distinct bugs — the outer `ncam_app_actions.py`
`<lambda>` wrapper (`ca()`'s installed handler) appears in every one of them
and is not itself a cause.

## Why these six are unreachable by a real user

The test's own walk **forces** every menu item's action enabled before
clicking it (`act.set_enabled(True)`) specifically so a genuinely dead button
is still caught — but that also fires callbacks the real sensitivity guards
would have kept disabled.

Measured directly: a freshly-constructed `NCam()` against the demo project has
`selected_type == 'workpiece'` (a real auto-selection from `load_currentWork`,
`ncam.py:3304`) and `selected_param is None` — because the initial selection
lands on a top-level **feature**, and `selected_param` is only ever set once a
row that IS a parameter (float/bool/combo/header/…) is genuinely selected.
`set_actions_sensitives()` disables `HideField`/`Digits`/`DataType`/
`RevertType`/`ChngGrp`/`RemoveItm` in exactly that state — real sensitivity is
what prevents a real click from ever reaching these six with
`selected_param is None`. Only the test's forced bypass reaches them.

`action_renameF`'s `get_toplevel()` crash is a different mechanism entirely:
`NCam()` in this test is never packed into a real `Gtk.Window`, so
`get_toplevel()` returns the bare `NCam` (a `Gtk.Box`) itself. Both real entry
points pack it into one **before** any interaction is possible — `ncam.py`'s
own `__main__` (`window.get_content_area().add(ncam)` at line 3538, before
`window.run()`) and the AXIS embedding — so a real user's `get_toplevel()`
always resolves to a real window by the time Rename could be clicked.

## The decision: (ii), by the count of CAUSES not tracebacks

7 distinct call sites, all unreachable in real use. Pinned by cause count
rather than the raw 22, because the raw number would legitimately drift with
unrelated menu changes (adding a digit-precision option, say) without a new
failure mode appearing — the thing worth gating is a **seventh cause**, not a
twenty-third traceback.

```python
KNOWN_TRACEBACK_CAUSES = 7
...
check('no-selection click noise does not grow past the known causes',
      len(sites) <= KNOWN_TRACEBACK_CAUSES, ...)
```

## Both directions proven

Real run: `saw 7 call sites, want <= 7` — PASS.

Manually lowered the threshold to 6 (not committed, reverted immediately
after) to prove the assertion can actually fail: `saw 7 call sites, want <= 6`
— FAIL, then reverted and re-confirmed PASS at 7.

A separate, permanent negative control — `_check_traceback_capture_control()`
— proves the *capture mechanism itself* catches a real signal-callback
exception, independent of the popup walk: a throwaway `Gio.SimpleAction`
with a callback that raises, activated inside the same
`contextlib.redirect_stderr` capture, asserted to produce exactly one
`Traceback`. This is the thing analysis/126's `demo_paned_recursion` lesson
warns about — a control that doesn't really exercise the mechanism is a false
green in a better disguise — so this control exercises the actual GObject
exception-to-stderr path, not just the arithmetic comparison.

## Not fixed, and not meant to be

None of the six selection-state crashes are made to return early or degrade
gracefully. They are not reachable, so there is nothing a real user needs
protecting from; "fixing" them here would be adding dead defensive code for a
path that already can't be reached, which is not what analysis/126 or this
task asked for. If a **new** cause appears, the count check fails and says so.
