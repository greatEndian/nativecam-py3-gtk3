# Task: isolate parallel worker sessions so they cannot corrupt each other

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first. Analysis range: **`analysis/270`–`279`**.

**You create new files only** — a setup script and a short doc. Do not edit
`lathe_sections.py`, `ncam*.py`, `lib/`, `cfg/`, or any existing `test_*.py`.
**Do not disturb the current working tree**: other sessions may be mid-edit in
it right now.

## Why this exists — three real incidents, not a hypothetical

greatEndian runs several Sonnet sessions in separate terminals against this one
working tree. It has cost real work:

1. **Cross-session file sweep, 2026-09-13.** A worker used a bulk `git add` and
   committed three of another session's in-flight files (`run_tests.py`,
   `test_run_tests.py`, `analysis/230`) inside `8c38722`; `1e08a93` was needed
   to untrack them. Nothing was lost, but only because it was noticed.
2. **Analysis-number collisions.** Two sessions both claimed `analysis/130`,
   costing two cleanup commits (`302e8be`, `58b69d7`) — the first of which was
   rename-only, so the content fix needed a second attempt. Numbers are now
   hand-assigned per session, which does not scale.
3. **False test failures under load**, `analysis/134`: two healthy drivers
   reported FAIL because sessions competed for the machine. `run_tests.py`
   mitigates the reporting; it does not stop the contention.

## What to build

A documented way to run N sessions without any of the three recurring. Use
`git worktree` — it is the tool for this and needs no new dependency.

Cover, concretely:

- **Creating and tearing down** a worker worktree, one command each. Where the
  worktrees live (outside the repo, so they never appear in `git status`).
- **What each worktree needs to actually work.** This is the substance — find
  it by reading, not by assuming. The embedded sim configs under
  `configs/sim/*/ncam_demo/` contain an `ncam/` directory of **symlinks back
  into the repo** (see `CLAUDE.md`). Determine what a worktree resolves those
  to, and whether `rs274` runs correctly from one. **If a worktree breaks the
  sim path, say so plainly — that is a finding, and it may mean worktrees suit
  only the non-`rs274` lanes.**
- **Merging a worker's branch back**, and what to do about `analysis/NNN`
  collisions at merge time. A number range per worktree is the obvious answer;
  check whether anything better falls out of branch-per-worker.
- **What is still shared and therefore still serialised**: the machine itself.
  Two `rs274` runs in parallel still contend no matter how isolated the files
  are, and `analysis/134` says that produces false failures. Say this out loud
  in the doc.

Also record the constraint discovered while planning this: **`lathe_sections.py`
is a single-writer resource.** Nearly every geometry task edits it —
`offset_contour` at line 4220, the roughing ladder, the section machinery — so
file isolation does not by itself allow two geometry workers at once; it only
makes the collision visible instead of silent.

## Verify it yourself

Actually create a worktree, run a **cheap** gate inside it
(`python3 test_vkb.py`, `python3 cam_map.py`), commit something trivial there,
merge it back, and tear it down. Report each step's real output. **Do not run
`rs274` or generate projects** — another session may own the machine.

A doc describing a workflow nobody executed is worth nothing here; this project
has been burned repeatedly by instructions that were never run.

## Gates

```bash
flake8 <your script> --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py
git worktree list          # must be clean when you are done
git status --short         # the main tree must be exactly as you found it
```

## Deliverable

The setup script and doc committed; `analysis/27N-...md` recording what you
actually ran, what a worktree does to the sim symlinks, what remains shared,
and the honest limits of the approach; then a report with every gate's exit
code.

## Non-interference rules

Other Claude sessions may work in this same git tree.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only. This is not hypothetical — on 2026-09-13 a worker's bulk `git
   add` swept three of another session's in-flight files into its commit
   (`8c38722`), and needed `1e08a93` to undo it.
2. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. `analysis/134` records that this suite returns **false FAILs under
   load**. Use `python3 run_tests.py <drivers>` — it re-runs a failing driver
   once and reports "passed on retry" separately.
3. **Do not push.** Local commits only — greatEndian's call.
4. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID (inside-diameter) work is **paused** by instruction.
5. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
