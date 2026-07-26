---
name: gotchas-update
description: "Use right after fixing a bug that wasn't obvious from reading the code (a silent failure, a wrong assumption, a footgun in LinuxCNC/GTK3/rs274 behavior). Drafts a concise lesson and appends it to md_files/LEARNINGS-LOG.md - the log this project already keeps for exactly this - after showing you the draft. Does NOT auto-edit CLAUDE.md unattended; that file is shared, tracked, and load-bearing, so changes to it go through normal review, not a heuristic auto-append."
---

# /gotchas-update

Capture a lesson so the next session doesn't rediscover it the hard way.

## Steps

1. Identify the actual lesson from what just happened in this conversation: symptom observed → root cause → the fix or the rule that avoids it. Not a changelog entry ("fixed X") — a gotcha ("if you do X, Y silently breaks, because Z").
2. Draft a 2-4 line entry in the style already used in `md_files/LEARNINGS-LOG.md` (read a couple of existing entries first to match tone/format — don't invent a new format).
3. Show the user the exact drafted text and ask for confirmation before writing (a bad or overly-narrow lesson permanently written into the log is worse than no lesson — false generalizations compound across sessions).
4. On confirmation, append to `md_files/LEARNINGS-LOG.md`.
5. Only if the lesson is about something broadly load-bearing and likely to recur on *every* future session (the class of thing already in CLAUDE.md's "LinuxCNC G-code rules" or "Lathe coordinate conventions" sections, not a one-off) — separately ask whether it should also become a one-line addition to CLAUDE.md. Never write to CLAUDE.md without that explicit, separate confirmation; it's a shared, git-tracked file every session reads first, so a bad or duplicate entry there has a much larger blast radius than one in the local, untracked learnings log.

## Gotchas & Edge Cases

- `md_files/` is `.gitignore`d (explicitly local, not committed) — this is *why* it's the safe default append target instead of `CLAUDE.md`. Don't "fix" this by pointing the skill at CLAUDE.md directly.
- Don't log a lesson that's really just "I made a typo" or "I forgot to run the linter" — those aren't gotchas about the *system*, they're not going to recur in a way a future session benefits from reading. Only log things where the codebase/tooling behavior itself was non-obvious or surprising.
- If the same gotcha already exists in the log (even worded differently), don't duplicate it — point it out to the user instead.
