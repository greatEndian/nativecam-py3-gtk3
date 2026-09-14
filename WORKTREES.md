# Isolating parallel worker sessions with `git worktree`

greatEndian runs several Sonnet sessions in separate terminals against this
one working tree. That has cost real work three times (see "Why this
exists" in `SONNET-PROMPT-WORKTREES.md`, kept for the record). This doc and
`worker_worktree.py` are the mitigation: one worktree, one branch, per
worker session, so each session's `git status`/`git add` only ever sees its
own files.

**Read this before running the script.** In particular: a worktree does NOT
make the sim/`rs274` lane safe for concurrent use — see "What breaks" below.

## Quick reference

```bash
# create a worktree + branch for one worker (default base: liveTooling)
python3 worker_worktree.py create <name> [--base <branch-or-commit>]

# a worktree has NO configs/sim/*/ncam_demo/ncam/ directory yet - see below.
# only needed if that worker will load a sim config at all:
python3 worker_worktree.py link-sim <name>

# what's currently checked out
python3 worker_worktree.py list

# tear down: removes the worktree AND its branch (merge first if you want
# the work kept - see "Merging a worker's branch back")
python3 worker_worktree.py remove <name> [--keep-branch]
```

Worktrees live at `~/nativecam-worktrees/<name>` — **outside this repo**, so
they never show up in `git status` here, and a worker's own `git add -A`
inside its own worktree can only ever add files that physically exist in
that worktree's own directory. That is the actual fix for incident 1 (the
2026-09-13 cross-session sweep): it is not "remember to pass explicit
paths", it is "the other session's in-flight file is not even present on
disk here to be swept."

Branches are named `worker/<name>` by `create`, purely so they are easy to
spot in `git branch -a` and do not collide with real feature-branch names.

## What each worktree needs to actually work

### The non-sim lane: works out of the box

`git worktree add` gives a worktree a full checkout of every TRACKED file —
`lathe_sections.py`, every `test_*.py`, `cam_map.py`, `ncam*.py`, `cfg/`,
`lib/`. Verified in this session: `python3 test_vkb.py` and `python3
cam_map.py` both ran and exited 0 inside a fresh worktree with nothing else
done to it. Any worker whose whole job is Python-level (unit tests against
`lathe_sections.py`, `cam_map.py`'s static checks, flake8) needs nothing
beyond `create`.

### The sim lane: **breaks**, and needs `link-sim` to even start

The embedded sim configs' own `ncam/` directory (`configs/sim/*/ncam_demo/
ncam/`, holding the `cfg`/`lib`/`graphics` symlinks `CLAUDE.md` describes) is
listed in `.gitignore` (line 218: `configs/sim/*/ncam_demo/ncam/`). Verified
directly: a fresh worktree's `configs/sim/axis/ncam_demo/` contains only the
seven tracked `.ini`/`README` files — **no `ncam/` directory at all.**

Nothing in the current codebase recreates it automatically. Reading
`ncam.py`'s startup path (`require_ini_items`, `update_user_tree`,
`require_ncam_lib`) shows why that matters:

1. `NCAM_DIR` is resolved from the ini's own `[DISPLAY]NCAM_DIR` value,
   relative to **the ini file's own directory** — inside the worktree, that
   is the worktree's own `configs/sim/axis/ncam_demo/ncam`, not the main
   tree's.
2. `update_user_tree` (called when `SYS_DIR != NCAM_DIR`, which it always is
   here) creates that directory and populates `catalogs/`+`my-stuff/` in it
   — but its `fromdirs` list is only `[CATALOGS_DIR, CUSTOM_DIR]`. It never
   touches `cfg`/`lib`/`graphics`.
3. `require_ncam_lib` then checks the ini's `[RS274NGC]SUBROUTINE_PATH`
   resolves to a real, existing directory under `NCAM_DIR/lib`. It does not
   exist yet, so this fails outright — before `rs274` or anything else runs.

**So a worktree breaks the sim path by default: `ncam.py` (and therefore
`rs274` runs through it) will not even start against a worktree's own sim
config.** This is exactly the failure mode `analysis/057` describes from the
other direction — that incident was `gen_project.py --repo <worktree>`
being pointed at the **main tree's** shared ini while a worktree existed,
which let `NCam`'s own startup re-point the **live** config's symlinks into
the worktree (because `SYS_DIR` — `os.path.dirname(os.path.realpath(
ncam.py))` — resolved inside the worktree once `ncam.py` ran from there).
Two different failures, same root cause: the symlink farm is manual,
untracked, and not worktree-aware.

`worker_worktree.py link-sim <name>` is the fix for the first failure: it
creates `ncam/{cfg,lib,graphics}` inside the **named worktree only**,
pointed at **that worktree's own** `cfg`/`lib`/`graphics` — never at the
main tree, and it refuses to touch anything that already exists and is not
exactly the expected symlink. Verified in this session: ran it against a
throwaway worktree, confirmed with `readlink` that all three symlinks point
inside that worktree (not the main repo), and that a second run reports
`already correct` rather than re-linking.

**What was NOT verified, on instruction — do not read more into this than
is here:** whether `ncam.py`/`rs274` actually runs end-to-end once
`link-sim` has been used. This session was explicitly told not to run
`rs274` or generate projects (another session may own that machine time).
So the fix above is grounded in reading `ncam.py`'s own startup code plus
confirming the symlinks land correctly — not in a green `rs274` run through
a worktree. **Treat the sim lane in a worktree as unproven, not as fixed,
until someone runs it for real.** The honest, immediately-usable summary:
worktrees suit the non-`rs274` lanes without qualification; they suit the
`rs274` lane only after `link-sim`, and even then unverified end-to-end.

## Merging a worker's branch back

From the main tree (not from inside the worktree):

```bash
git merge worker/<name>          # or: git merge --no-ff worker/<name>
```

Verified in this session: created a worktree, committed a trivial file on
its branch, merged that branch into a scratch integration branch (not
`liveTooling` — this doc's own dry run had no work worth keeping), confirmed
the file arrived, then deleted the scratch branch, deleted the worker
branch, and removed the worktree. `git worktree list` and `git status
--short` on `liveTooling` were unchanged before and after.

### `analysis/NNN` collisions at merge time — branch-per-worker does NOT solve this on its own

The obvious answer, already in use, is a hand-assigned number range per
worker (this doc's own commit used `270`-`279`). **Branch-per-worker does
not make that unnecessary.** Two workers on two different branches, each
picking `analysis/200-something.md` with a different slug, merge into
`liveTooling` **without any conflict at all** — git only conflicts on the
same path, and the two files have different names. The 2026-09-13 incident
(`analysis/130` claimed twice) would reproduce exactly the same way across
two worktrees as it did in one shared tree; nothing about file-level
isolation touches the fact that the NUMBER, not the file, is what collided.
The range convention is still the whole mitigation. Worktrees change
*where* two workers' files live while they work, not whether their chosen
numbers agree.

What worktrees DO fix outright is incident 1's mechanism (an accidental
bulk-add sweeping another session's *uncommitted* file) — because that
requires the file to be visible in the same working directory, which
worktrees make structurally impossible.

## What is still shared, and therefore still serialised

**The machine itself.** File and branch isolation do not give two `rs274`
processes their own CPU, disk, or LinuxCNC lock file — `analysis/134`
already measured this: two sessions competing for the machine produced
false `FAIL`s on healthy drivers (`test_sub_spans.py` timed out, an
unrelated driver returned rc=1), not because the code was wrong but because
the machine was loaded. A worktree does not change this at all: two workers
each in their own worktree, each running `rs274` at the same moment, still
contend for the same CPU and the same LinuxCNC lock the sim configs use.
`run_tests.py`'s retry-once mitigation (from `SONNET-PROMPT-WORKTREES.md`'s
own non-interference rule 2) is about REPORTING this correctly, not about
preventing the contention — that would need actual serialisation (a lock
file, a queue, or simply "only one session runs rs274 at a time"), which is
outside this deliverable's scope and not attempted here.

## `lathe_sections.py` is a single-writer resource

Confirmed by reading the recent history, not assumed: every one of the last
18 commits touching Python geometry code in this project has touched
`lathe_sections.py` (`git log --oneline -18 -- lathe_sections.py`, all named
`feat(lathe)`/`fix(lathe)`/`refactor(lathe)`/`perf(lathe)`), and
`offset_contour` is confirmed still at line 4220 as the prompt states.
Nearly every geometry task in this project — the roughing ladder, the
section machinery, the contour offsets — edits this one file.

**File isolation via worktrees does not allow two geometry workers to edit
it concurrently in any meaningful sense.** Each worktree can happily hold
its own uncommitted edit to its own copy of `lathe_sections.py` — git does
not stop that — but the moment either tries to merge back, or the moment a
second worker's edit needs to build on the first's (which describes nearly
every geometry task in this project's own history: the ladder head, the
floor stages, the ramp direction table, tip comp, all built on each other
in sequence, not in parallel), the file-level isolation stops helping and
becomes exactly two branches racing to touch the same lines. Worktrees make
that collision **visible as a merge conflict instead of silent** (the real,
concrete improvement over today's shared-tree editing, where two sessions'
uncommitted edits to the same file simply overwrite each other on disk with
no signal at all) — they do not make the file safe to edit from two
sessions at once. Sequencing geometry work on `lathe_sections.py` — one
active writer, others queued or working on genuinely disjoint files (new
`test_*.py` files, as every recent unit-test worker in this project has
done) — remains a human/scheduling decision, not something this tooling
resolves.

## Cheap gates only, inside a worktree

Nothing about a worktree changes which gates are safe to run concurrently.
The same rule as the shared tree applies: `flake8`, `cam_map.py`,
`test_cam_map.py`, and any pure-Python `test_*.py` that never invokes
`rs274` are safe to run in as many worktrees at once as there are CPUs to
spare. `test_project_sweep.py`, `test_motion_fingerprint.py`,
`test_surface_equality.py`, `test_all_projects.py`, and anything under
`.claude/skills/lathe-gcode-verify/scripts/` are not — see the previous
section.
