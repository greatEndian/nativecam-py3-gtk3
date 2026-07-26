---
name: spec-builder
description: "Use before starting any new feature or non-trivial multi-file change in this repo - not for a one-line fix or a change the user already specified exactly. Interviews the user to pin down goal, boundaries, and edge cases, then outputs a compartmentalized step plan, before any code is written."
---

# /spec-builder

Turn a vague ask into a concrete, scoped plan before touching code. This is Claude Code's own plan-mode machinery (`EnterPlanMode`/`AskUserQuestion`/`ExitPlanMode`) applied specifically to this repo's actual shape — not a generic template.

## When to use this vs. just starting

- **Use it**: "add a new lathe feature," "support X in turn-mill," anything where the request could reasonably be built two different ways, or where you'd have to guess at a parameter/behavior the user didn't specify.
- **Skip it**: the user already gave exact file paths, exact values, or a fully specified change ("set `lo_rad` default to 0.5 in `turning.cfg`"). Interviewing about something already fully specified just wastes their time.

## Steps

1. **Interview — up to 3 targeted questions**, using `AskUserQuestion`, not open-ended prose:
   - The actual goal/symptom this solves (not just the mechanism requested — CLAUDE.md's own G-code gotchas exist because a mechanism-first request without the underlying goal has repeatedly missed a load-time or coordinate-mapping constraint).
   - Boundary conditions: which machine(s) (mill/lathe/plasma), whether it touches `lib/` subroutines shared across machines (recall: lathe cannot call `lib/mill/` — CLAUDE.md), whether it needs a new catalog entry.
   - Non-negotiables: anything that must NOT change (existing feature behavior, parameter defaults other features read).
2. **Deconstruct into increments.** Small, independently-verifiable steps — match the granularity `init-custom` uses for a new feature (cfg → catalog entry → subroutine → verify), not one giant diff. Reuse `init-custom`'s scaffold if this is in fact a new feature.
3. **State assumptions explicitly and stop.** Anything you're inferring rather than being told — list it, then wait for confirmation before writing code. Do not proceed past this point in the same turn.
4. Once confirmed, hand off to normal implementation, ending with `/verifier` (or `/lathe-gcode-verify` if G-code motion was touched) before declaring done.

## Gotchas & Edge Cases

- Don't ask 3 questions when 1 resolves the ambiguity, and don't ask about something the user's message already answered — re-asking a settled point reads as not having listened.
- "Compartmentalized execution steps" means steps a human can approve or reject individually, not steps sized for token-counting — a 5-line step and a 200-line step are both fine if each is independently checkable.
- If the interview reveals the ask is actually a one-line fix in disguise, say so and skip the rest of the ceremony — this skill exists to prevent wasted implementation effort, not to guarantee its own steps always run in full.
