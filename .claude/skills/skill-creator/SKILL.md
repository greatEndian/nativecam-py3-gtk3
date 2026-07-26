---
name: skill-creator
description: "Use when asked to turn a plain-English SOP, workflow description, or 'install a skill for X' request into a real .claude/skills/<name>/SKILL.md. Encodes the checks that prevented this project's skill set from becoming duplicated, ungrounded, or full of nonfunctional config across the session that built it."
---

# /skill-creator

Turning a request into a skill file is not just formatting Markdown with YAML frontmatter — most of the value is in NOT creating a skill when one already exists, and in grounding the content in this repo's actual code instead of a generic template. This project's 6 skills (`gotchas-update`, `init-custom`, `lathe-gcode-verify`, `plan-and-test`, `security-audit`, `spec-builder`, `verifier`) were each checked against the steps below; several *requested* skills (`plan-feature`, `verify-build`, `compound-learnings`, `verify-scope`) were declined as exact duplicates of ones already installed.

## Steps

1. **Check for an existing overlapping skill first.** `ls .claude/skills/` and read each `description:` frontmatter line — if the new request's job is already covered (even under a different proposed name), extend the existing skill instead of creating a near-duplicate. A second skill doing the same job splits future edits across two files and creates ambiguity about which to invoke.
2. **Verify the actual frontmatter schema — don't assume a field works because it sounds plausible.** Check a real installed skill (e.g. the vendored `graphify` at `~/.claude/skills/graphify/SKILL.md`) for what fields it actually uses. `name:` and `description:` are confirmed real; a `model:`/`context:` field for per-skill model routing is **not** part of the SKILL.md schema (that's an `.claude/agents/*.md` subagent feature) — never add it just because an instruction asks for it, it would be inert, misleading decoration.
3. **Ground every claim in the actual codebase**, not a generic template: read the real files the skill will operate on (a `.cfg` example, the actual test scripts, real `git log`/`grep` output) before writing instructions that reference them. A skill that describes a plausible-sounding but wrong file layout or command is worse than no skill.
4. **Write the file**, `.claude/skills/<kebab-case-name>/SKILL.md`:
   - Frontmatter: `name` (matches directory), `description` (specific enough that the *right* trigger conditions are obvious — "use when X, not for Y").
   - Body: `# /<name>` header, a short "why this exists" if the motivation isn't obvious from the description, then `## Steps`.
   - Decide whether a hard `[VERDICT: PASS]`/`[VERDICT: FAIL - reason]` gate belongs at the end — only for skills whose job is verification/completion-gating (like `verifier`, `security-audit`); a planning or logging skill (`spec-builder`, `gotchas-update`) doesn't need one, it ends in a decision or a written artifact instead.
   - Always add a `## Gotchas & Edge Cases` section — the sharp edges found while building/testing the skill's own scripts (if any) belong here, not just codebase gotchas.
5. **If the skill needs a helper script**, put it under `.claude/scripts/` (shared, reusable) rather than embedding non-trivial logic inline in the SKILL.md — and actually run it against real project data before calling the skill done, the way `parse_rs274.py`/`check_tangent.py`/`find_latest.py`/`compress_output.py` were each tested against a real log/`.ngc` file, not just written and assumed correct.
6. **Decide the log target for anything persistence-related** — this project already has two: `md_files/LEARNINGS-LOG.md` (git-ignored, human-readable, the actual append target per `CLAUDE.md`) and Claude's own cross-session memory (`project`/`feedback`/`user`/`reference` typed entries). Don't invent a third (e.g. a `.claude/*.json` snapshot) without a concrete reason the existing two don't cover — check both before proposing a new one.

## Gotchas & Edge Cases

- A request phrased as "install skill X" is sometimes better satisfied by extending an existing skill's `## Steps` — don't create the file just because a name was given if the job already exists under a different name.
- Don't fabricate acceptance-sounding frontmatter or settings.json hook wiring for functionality you haven't verified actually exists in this Claude Code version — say so and stop at the boundary of what's confirmed, rather than writing config that looks right but does nothing (or, worse, silently breaks something if it's a global hook).
- A skill's `description:` is what triggers it — vague ("use for code stuff") means it either never fires or fires on the wrong things. Write it as a triggering condition, not a summary.
