---
name: plan-and-test
description: "Use during implementation of a non-trivial fix or feature, after /spec-builder has produced an approved plan and before writing the actual lib/cfg/ncam.py change. Sequences the work test-first and closes with a two-stage review. Complements spec-builder (upstream: what to build) and verifier (downstream: does it pass) - this is the middle phase."
---

# /plan-and-test

This project has **no pytest/unittest harness** — `test_lathe_validation.py`, `test_coord_mapping.py`, `test_vkb.py` are standalone scripts with hand-rolled assertions, and G-code motion is verified via `/lathe-gcode-verify`'s `rs274` trace, not test stubs. "Write a unit test stub first" doesn't map onto this codebase literally — adapt the intent (define what verification will prove the fix works, before writing the fix) to the tools that actually exist here.

## Steps

1. **Define the verification before writing the fix.** Concretely: which existing test script gains a new case, or what specific `rs274`/tangent/arc-presence check (in the style of `/lathe-gcode-verify`) would prove this specific change correct. Write that check (or the scratch script for a one-off scenario) first, run it against the *unmodified* code, and confirm it currently fails or is inapplicable — a check that already "passes" against unfixed code proves nothing.
2. **Implement the change.**
3. **Two-stage review**, done as two genuinely separate passes, not one merged skim:
   - **Spec compliance**: re-read the approved plan from `/spec-builder` (or the user's original ask if no plan step ran) line by line — does the diff actually do each stated thing, nothing silently dropped, nothing silently added beyond scope?
   - **Code quality**: readability, consistency with this file's existing style (see CLAUDE.md's own conventions — e.g. `.ngc` global-qualification rules if this touched a split-out module, comment discipline), no leftover debug prints (`grep -c print` on any `.ngc`/`.py` touched, matching the check this project has needed before).
4. Hand off to `/verifier` (or `/lathe-gcode-verify`) for the final deterministic gate — this skill's review is qualitative and human-facing; the verdict gate is the hard pass/fail.

## Gotchas & Edge Cases

- Don't invent a `test_foo.py` file with a pytest/unittest skeleton just to satisfy "write a test first" — it wouldn't be collected or run by anything in this project's actual workflow (`CLAUDE.md`'s Commands section runs each `test_*.py` directly with `python3`). If a genuinely new standalone check is warranted, follow that same convention: a plain script with `print`/`assert` and a clear pass/fail message, added to the Commands list in `CLAUDE.md` if it's meant to be a permanent addition.
- The two review stages catch different failure modes — spec-compliance catches "did the wrong thing" or "did too little/too much," code-quality catches "did the right thing badly." Merging them into one pass tends to only catch whichever one you were thinking about first.
- If `/spec-builder` wasn't run first (a small, already-fully-specified fix), skip straight to step 1 here — this skill doesn't require the upstream one for trivial changes.
