# 260 — negative stock to leave fails silently past its bound

**Asked**: `openPoints.md` — *"`offset_contour` already cuts past the model
correctly down to `extra > -nose_r` ... At -0.40 and -0.50 the guard returns
the profile unchanged: ask for 0.5 past the model and get 0.0, with no
warning."* Guard half only — exposing the parameter (lowering the cfg
minimum below 0.0) is explicitly out of scope; that needs a decision about
roughing, which cannot hold a negative allowance without a nose, and is
greatEndian's call, not this task's.

## Reproduced, before touching anything

`offset_contour(prof, 0.4, 9, 1, extra)` on a plain 40mm-diameter cylinder:

```
extra=-0.1000 nose=0.4 -> diameter 40.6000   (correct: -0.1000 effective)
extra=-0.3900 nose=0.4 -> diameter 40.0200   (correct: -0.3900 effective)
extra=-0.4000 nose=0.4 -> diameter 40.0000   (SILENT: profile unchanged, no warning)
extra=-0.5000 nose=0.4 -> diameter 40.0000   (SILENT: profile unchanged, no warning)
```

Root cause, `lathe_sections.py:4277` (pre-fix):

```python
if not points or len(points) < 2 or nose_r + max(extra, extra_z) <= EPS:
    return list(points)
```

One guard did two jobs. `nose_r=0, extra=0` (a real, tested no-op —
`test_offset_contour.py`'s "a zero nose radius returns the profile") and
`nose_r=0.4, extra=-0.4` (a request for more retreat than a 0.4 nose has to
give) both land on `nose_r + max(extra, extra_z) <= EPS` and get the same
silent `return list(points)`. The second case is the defect: it looks
identical to "no offset requested" when it is actually "request refused."

## Caller survey

Grepped `offset_contour(` across the tree:

| caller | extra it can pass today | can reach the bound? |
|---|---|---|
| `lathe_sections.py:4594` `build_cam_comp_gcode`, via `cam_pass_offsets` | `fin_off * (n-i)/n`, `fin_off` itself | never negative — `param_f_off`/`param_f_off_z` cfg minimum is `0.0` |
| `lathe_sections.py:5817` `build_prefinish_contour_gcode` | `stock_pair()` → same params, guarded `<= EPS` returns `''` before the call | never negative, and already skips the call entirely when the allowance is ~0 |
| `ncam_preview_ui.py:1355` (`_preview_...` comp-mode overlay) | `extra` not even passed (defaults to `0.0`) | never negative |
| `test_offset_contour.py`, `test_stock_to_leave.py`, `test_tip_comp_vec.py`, `test_comp_overlay.py`, `test_sections.py` | direct calls, any float | only a test can reach it today |
| `.claude/skills/lathe-gcode-verify/scripts/prove_cam_comp.py:378` | `R` (nose radius) via `side=-side`, no negative `extra` | never negative |

**Where the message has to surface**: nowhere in the live CAM/preview path
today, because every production caller is bounded to `extra >= 0.0` by the
cfg minimum (`grep minimum_value cfg/lathe/polyline.cfg` — `param_f_off` /
`param_f_off_z` both `0.0`). The only place this bound is currently
reachable is a direct Python call — a test, or future code. A warning
comment threaded through `build_cam_comp_gcode`'s own `_refuse()` (the
existing "(WARNING - ...)" mechanism it already uses for a missing nose
radius or a collapsed offset) would be a no-op today since that path can
never construct a negative `extra` — adding one now would be dead code with
nothing to verify it against, and is deferred to the exposure task, where it
belongs together with the roughing decision. `ncam_preview_ui.py`'s caller
already wraps the whole comp-mode overlay in `try/except Exception: return
None`, so a raised exception there degrades to "no overlay" exactly the way
a missing nose radius already does — safe, no crash, consistent with every
other refusal that function's `except` already swallows.

**Decision: raise, don't clamp.** `analysis/220`'s principle (`update_features`
narrowing a param's bounds) applies unchanged: *"silently rewriting a saved
[user] number is worse than the [bug] being fixed... a clamp is a guess
about what the operator meant, and there is no way to make that guess
correctly in general."* The same reasoning holds here — clamping `extra` to
`-nose_r` would silently give back a different, smaller retreat than asked
for, indistinguishable from the current bug except in degree. `offset_contour`
is a pure Python function with no GUI of its own reachable from here (see the
caller survey), so the loudest correct signal at this layer is a `ValueError`
naming the bound and the value asked for — not a return-value sentinel, which
a caller could keep discarding exactly as today's `0.0` was.

## The fix

`lathe_sections.py:4275-4282`. Split the single guard into what it always
should have been two decisions:

```python
if not points or len(points) < 2:
    return list(points)
total_extra = max(extra, extra_z)
if nose_r <= EPS and total_extra <= EPS:
    return list(points)               # no nose, no allowance - the real no-op
if nose_r + total_extra <= EPS:
    raise ValueError(
        'offset_contour: extra %.4f (extra_z %.4f) exceeds what a %.4f '
        'nose allows - the bound is extra > %.4f (-nose_r); the request '
        'cannot be honoured' % (extra, extra_z, nose_r, -nose_r))
roll = nose_r + extra
```

`nose_r <= EPS` is the split: `build_prefinish_contour_gcode` calls this
with `nose_r=0.0` and a real positive `extra` (a pure geometric offset with
no orientation term) and must keep working exactly as before — verified
below. Every case with a real nose (`nose_r > EPS`) that used to fall
through to the silent branch now raises, including the boundary
`extra == -nose_r` exactly (measured `-0.40` above) — chosen as refused, not
accepted-as-zero, because the openPoints wording frames it as "the first
refused value," and because a caller asking for exactly the nose radius of
retreat has hit the edge of what the geometry model defines, not asked for
nothing.

Known residual, left alone as out of scope for a guard-only task: the guard
still uses `max(extra, extra_z)` from the original code, so an anisotropic
call where only `extra_z` breaches the bound (`extra` fine, `extra_z` past
`-nose_r`) is not caught — it wasn't caught before either, and no repro case
or caller demands it; changing that would be a second, separate decision
about the anisotropic path, not this guard.

## Verification

- `python3 test_negative_stock_guard.py` (new, 6 checks): last good value
  (-0.39), a second in-bound value (-0.10), the boundary exactly at `-nose_r`
  (-0.40, now refused), past the boundary (-0.50, refused), the established
  no-op (`nose_r=0, extra=0`, still silent), and the pure-geometric-offset
  path (`nose_r=0`, positive `extra`, still offsets) — all PASS.
- Motion fingerprint, 46/46 projects, recorded before the edit
  (`fp_before_260.txt`, taken after `486577e` landed) and compared after:

  ```
  46 identical, 0 changed, 0 not in the baseline, of 46
  ```

  Confirms the guard never reached live geometry — every one of the 46 test
  projects is bounded to `extra >= 0.0` by the cfg minimum, so none of them
  could have exercised the changed branch either way.

## Gates

| gate | result |
|---|---|
| `flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82` | exit 0 |
| `python3 run_tests.py test_offset_contour.py test_cam_map.py test_lathe_validation.py test_geometry_primitives.py test_negative_stock_guard.py` | 5 run, 5 passed, 0 failed |
| `python3 cam_map.py` | exit 0, all 9 checks PASS |
| `flock ... python3 test_surface_equality.py` | exit 0 — "46 projects generated, 38 with both tables compared / One surface, both users." |
| `flock ... python3 test_project_sweep.py` | exit 0 — "46 projects: 45 clean, 1 broken (1 expected)" (`default_template.xml`, no motion, a known non-project case, not caused by this change) |
| `flock ... python3 test_motion_fingerprint.py --baseline fp_before_260.txt` | exit 0 — 46 identical, 0 changed |

## What is still open

The exposure half of the original open point — raising the cfg minimum
below `0.0` so a negative allowance is actually reachable from the UI — is
**not done here** and needs greatEndian's decision: roughing cannot hold a
negative allowance without a nose (roughing levels are computed independent
of any tool nose today), so exposing the parameter is a decision about
roughing's own model, not a guard change. `openPoints.md` is updated to
reflect the guard as done and the exposure half as the remaining item.
