# 027 — A map of what touches what, and what it found

2026-08-10, branch `liveTooling`, from `4ef1acb`.

## Why

greatEndian, after the anisotropic stock to leave took four rounds:

> *"learn the active CAM framework what touches what and which change will
> introduce dependency … lets create own graphify for it"*

`graphify` maps the Python and does it well. This system's hard part is not
Python: it is the chain from a `.cfg` parameter, through a Python builder, into
a numbered-parameter window, out to an `.ngc` subroutine that walks it. Nothing
could see that chain, so every change was scoped from memory — and every one of
the four misses was a link in it.

## `cam_map.py`

Extraction: cfg parameters and their readers, global named parameters
(defined / assigned / read), parameter-window constants against the literals
the O-code hard-codes, and subroutine definitions against call sites.

Seven static checks, each here because it would have caught a bug this project
actually had. `--map` writes `CAM-MAP.md`, 621 lines: per parameter, global,
table and subroutine, **who writes it and who reads it**.

## What it found on its first run

Four things, none of which anyone had noticed.

**1. `CAM_TOP` was wrong, and it was a live hazard.** `poly_add_item.ngc` uses
**#4984–#4999** as scratch on every machine. The In-CAM offset table was
declared `CAM_BASE 4600 … CAM_TOP 5000` — so it was permitted to grow into
slots the very subroutine that builds the record array overwrites. The worst
real usage measured is 290 slots, reaching 4890, so nothing had been corrupted;
the declared cap was simply wrong and the overflow check would have passed
while the data was clobbered. `CAM_TOP` is now **4984**.

**2. Six dangling `order =` names**, in four files: `cfg/plasma/circle.cfg`
(nine), `cfg/mill/sel-reamer.cfg` (`h3`), `cfg/mill/taper-hole.cfg` (`h1`), and
`cfg/mill/sel-thread-mill.cfg` (`teeth`, where the section is
`[PARAM_CUT_TEETH]` — so that parameter does not appear in the tree at all).
The same class as the `e_z` found by accident the day before. All pre-existing,
all outside the lathe work, so they are listed in `ORDER_KNOWN` rather than
fixed blind — a **new** one still fails.

**3. 90 parameters and 2 globals defined and never read.** Reported, never
failed: some are deliberate (`multi_x` is documented as inert). It is a list to
read, not a gate.

**4. Two faults in the checker itself**, caught by its own negative controls —
see below.

## The checks, and the bug each exists for

| check | the bug |
|---|---|
| windows do not overlap | — |
| every literal in `lib/` lands in a declared window | a table reference pointing nowhere |
| the hard-coded literals match `lathe_sections` | the floor table moved 3300 → 3380 in Python and `poly_lathe_mill` kept reading 3300 — **twice** |
| no window reaches over a slot the O-code writes | `CAM_TOP` above, found by this check |
| every `#<_pl_*>` read has a default | LinuxCNC's load-time *"Named parameter not defined"* |
| every `order =` name has a parameter | the dangling `e_z`, and the five above |
| every subroutine called is defined | — |

## `test_cam_map.py` — and why it mattered

Each check is driven with a **known-bad copy** of the tree and must report the
failure. On the first run **two of the five did not fire**, and both were the
test's fault, not the checker's:

- the window case selected its check by the word *"literal"*, which two check
  names contain — it picked the wrong one, which passed;
- the global case wrote `#<_pl_zzz> = [#<_pl_zzz> + 1]`, which **assigns** the
  global, and the check deliberately allows that (it is how `_pl_ph1_front_cut`
  works). The bad case had to read without assigning.

Two checks that would have shipped believed-working. There is also an assertion
that a window fault trips **only** the window check, so a red report says where
to look.

## Extraction faults it exposed in itself

- `;` line comments were not stripped, so commented-out `o<parallel> CALL`
  lines counted as calls to a missing subroutine;
- `order =` names were compared case-sensitively, so `probe-stock.cfg`'s `H5`
  read as dangling against `[PARAM_H5]`.

Both fixed before any finding was believed.

## Still open

- **C3 from the plan is not built**: checking each emitter's worst-case table
  size against its window needs generation, and belongs behind a flag. It is
  the check that would have caught the floor contour needing 226 slots with 200
  free — which is still only caught by a WARNING comment nobody reads.
- The map is generated, not live. Nothing regenerates it, and a stale
  `CAM-MAP.md` is worse than none. It should be regenerated whenever the checks
  run, or checked into CI.
