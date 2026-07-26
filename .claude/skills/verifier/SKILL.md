---
name: verifier
description: "Use before declaring any code change in this repo done. Runs the project's actual lint/test suite (not a generic one) and returns a hard [VERDICT: PASS] or [VERDICT: FAIL - reason]. For changes to lathe G-code generation specifically, use lathe-gcode-verify instead/in addition - it traces real motion, this only runs static checks."
---

# /verifier

Deterministic pass/fail gate for this repo's own checks — the ones already named in `CLAUDE.md`, run for real rather than assumed.

## Steps

Run all of these; do not stop at the first pass and assume the rest are fine:

```bash
flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
  --builtins="_" --select=E9,F63,F7,F82

python3 test_lathe_validation.py
python3 test_coord_mapping.py
python3 test_vkb.py
```

Then, only if the change touched anything under `lib/lathe/` or `lib/mill/` `.ngc` files or lathe/mill `.cfg` `[CALL]` templates: run `/lathe-gcode-verify` too (static checks here don't catch a tangent discontinuity or a silently-dropped fillet — only an actual `rs274` motion trace does).

## Acceptance criteria check

If the task that prompted this had explicit, stated requirements (a bug report's specific symptom, a user-given list, a plan's "Definition of Done") — restate each one as a checklist item and mark it satisfied or not, individually, before the verdict line. Don't fold "ran flake8 clean" into "therefore everything the user asked for works" — a change can be lint-clean and test-passing while still not doing what was asked. This check has no fixed shape; it's whatever the actual task specified, verified against what was actually done, not against a generic template.

## Definition of Done

- `flake8` exit code 0 with the exact select codes above (never widen to a bare `--select=F` or similar — CLAUDE.md is explicit about this: `_` is a real gettext builtin, not an undefined name, and wildcard codes reintroduce noise this project has already tuned out).
- All three `test_*.py` scripts exit 0.
- If G-code motion was touched: `/lathe-gcode-verify` also reports `[VERDICT: PASS]`.

Report every command's actual exit code and any non-empty output — do not summarize a clean run as "looks good" without showing what ran.

End with exactly one line:
```
[VERDICT: PASS]
```
or
```
[VERDICT: FAIL - <which check, what it said>]
```

## Gotchas & Edge Cases

- `test_lathe_validation.py`'s "NO SIGNATURE" warnings (e.g. for `select.ngc`, `trace_lathe.ngc`, `get_max.ngc`, `get_offsets.ngc`) are pre-existing and not failures — the script itself exits 0 despite printing them. Don't misread a 🟡 line as a FAIL; check the actual process exit code and the "All scanned lathe subroutine calls match their signatures!" summary line.
- These test scripts are standalone, not pytest-collected — running `pytest` here silently discovers nothing useful; always invoke them directly with `python3 <script>.py`.
- A clean `flake8`/test run does not mean the G-code is correct — it means the Python glue and call signatures are consistent. Motion correctness (tangency, no dropped fillets, right depths) is a completely different failure class that only `/lathe-gcode-verify`'s actual `rs274` trace catches.
