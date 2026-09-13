# 230 — a suite runner that does not lie under load

## What was asked

Build `run_tests.py`, a driver-suite runner that closes the gap `analysis/134`
found: the sweep reports `rc=1`/`rc=124` for drivers that are provably fine in
isolation, and each of the four times that has happened it was treated as a
one-off instead of what it is — a property of the instrument. Requirements:
retry a failing driver once and report the retry outcome distinctly, a
generous per-driver timeout reported as its own bucket, always-serial
execution, `test_rough_ends.py` reportable as a known-expected failure without
reddening the run, and validation against fake drivers — never the real suite.

## What was built

`run_tests.py` (repo root): discovers `test_*.py` siblings by default, or runs
exactly the driver paths given on the command line. Every driver is run with
`subprocess.run`, one at a time, never overlapped. A non-zero, non-timeout
exit gets exactly one retry before it is reported; the six-bucket verdict is
PASS / PASSED ON RETRY / FAILED / TIMEOUT / KNOWN FAIL / SKIPPED, and the exit
code is non-zero only for FAILED or TIMEOUT — a pass-on-retry or a
known-expected failure leaves the run green. `test_run_tests.py` is its test.

## The five fake-driver cases, and what each proved

Built in a scratch temp dir (`test_run_tests.py`, `main()`), never against the
real suite:

| fake driver | shape | proves |
|---|---|---|
| `always_pass.py` | exit 0 | a clean driver is reported PASS and run exactly once — no wasted retry on a driver that never needed one |
| `always_fail.py` | exit 1, always | a driver that fails **twice** is reported FAILED, ran exactly twice (the retry did fire), and is a genuine result — this is the bucket that must turn the run red |
| `flaky_once.py` | exit 1 first call, exit 0 second (via a marker file left behind after the first run) | this is the whole point: a driver that fails once and then passes is reported PASSED ON RETRY, not PASS and not FAILED — and the run it's in still exits 0. This is exactly the shape `test_sub_spans.py` and `test_x_continuity.py` had in `analysis/134` |
| `slow_driver.py` | sleeps 5s, runner given `--timeout 2` | reported TIMEOUT, a bucket of its own, and — checked explicitly — ran **once**, not twice: retrying a timeout would silently double the wall-clock cost of the slowest driver in the suite for no signal gained, so `classify()` never retries a `TimeoutExpired` |
| `known_expected_fail.py` | exit 1, always, named via `--known-fail` | reported KNOWN FAIL rather than FAILED, still retried once like any other failure (so a known-fail that starts passing would show up as PASSED ON RETRY / PASS, not get silently swallowed), and does not redden the run |

Two aggregate runs then checked the exit code itself, not just the labels:
the clean set (`always_pass` + `flaky_once` + `known_expected_fail`) exits
**0**; the dirty set (`always_fail` + `slow_driver`) exits **1**. 14 checks
total, all passing (`python3 test_run_tests.py`).

A sixth, bonus check (not one of the required five, added because it was
cheap): auto-discovery with no explicit arguments must SKIP a
`test_project_sweep.py`-named file rather than run it. Proven against a copy
of `run_tests.py` placed inside the scratch dir alongside a stub
`test_project_sweep.py` that would fail the run if it were ever executed — the
run still exits 0, so the stub never ran.

## The timeout chosen, and why

**600 seconds per attempt**, default. Drivers this runner is meant to run
(anything not in `AUTO_EXCLUDE`) call `rs274` internally with their own
sub-timeouts: `test_peck.py` 300s, `test_high_feed.py` 400s, `test_pane_layout.py`
/ parse_rs274.py 120s. 600s is comfortably above the largest of those single
internal calls (400s) with room for process-launch and interpreter-import
overhead on a *contended* machine — the exact condition `analysis/134`
documents test_sub_spans failing under, at whatever the old sweep's limit was
(not recorded, and not reconstructed here since the point is to be generous
enough that it stops mattering). It is a CLI flag (`--timeout`), not a
constant, so a genuinely slower driver doesn't need a code change.

## What the suite taught while building this

**Auto-discovery has to key off the runner's own file location, not the
caller's working directory.** `HERE = os.path.dirname(os.path.abspath(__file__))`
means "every test_*.py in this directory" always means the repo the runner
lives in, regardless of `cwd`. That is the right behaviour for the tool, but
it made the first draft of the bonus auto-discovery check dangerous: it ran
the *real* `run_tests.py` with no arguments from a scratch `cwd`, which
auto-discovered and started running this repo's real `test_*.py` files —
including `test_air_leads.py`, which was caught running for about a minute
(48% CPU) before being killed. No `rs274`/`linuxcnc` process or lock file
resulted (checked immediately after), and no file outside the scratch dir was
touched, but it was exactly the class of interference `CLAUDE.md`'s
non-interference rules exist to prevent, self-inflicted by the validation
harness for the tool meant to prevent it. Fixed by copying `run_tests.py`
itself into the scratch dir for that one check, so its own `__file__`
resolves inside the sandbox. Recorded here rather than quietly patched over,
per the standing rule to record failed attempts too.

**Why `AUTO_EXCLUDE` is a hardcoded set and not a CLI flag with an empty
default.** `test_project_sweep.py`, `test_motion_fingerprint.py`,
`test_surface_equality.py`, `test_all_projects.py` are the same four names
`CLAUDE.md` already separates out as "whole-catalogue sweeps" (`README`/
Commands section) — they are not part of "the driver sweep" `analysis/126` and
`analysis/134` are about, they regenerate the entire project catalogue and
drive `rs274` repeatedly, minutes not seconds. Excluding them from
no-argument auto-discovery encodes a distinction the repo already draws, not
an arbitrary rule for today's session; naming one explicitly on the command
line still runs it, because at that point it's a deliberate choice, not a
default that silently pulls in a 10-minute `rs274`-heavy run.

**A timeout must never be retried.** The retry exists to catch a load
artifact — a driver that failed because the machine was momentarily busy,
which a fast second attempt reveals. A driver that used its *entire* generous
budget and still didn't finish gains nothing from a second attempt except
another full timeout's worth of wall-clock cost; `classify()` returns TIMEOUT
on the first `TimeoutExpired` without retrying, and this is checked explicitly
(`slow_driver` ran exactly once, not twice).

## Verification run (cheap drivers only, per the gates)

```
running test_vkb.py                      PASS             (0.2s)
running test_coord_mapping.py            PASS             (0.2s)
running test_lathe_validation.py         PASS             (0.0s)
running test_cam_map.py                  PASS             (1.6s)
running test_geometry_primitives.py      PASS             (0.0s)

SUMMARY: 5 run, 0 skipped
  passed:          5
  ...
```
rc=0. The full suite was never pointed at — another session may own `rs274`
right now, and a runner tested only on a quiet machine proves nothing about
the behaviour it exists for; the fake-driver harness above is what actually
proves the classification logic.

## Still unknown

- The real, historical per-driver timeout the original ad hoc sweep used
  (whatever produced `test_sub_spans.py`'s `rc=124` in `analysis/134`) was
  never recorded and could not be reconstructed here — 600s is a reasoned
  default, not a measured replacement for that number.
- Whether any driver outside the five cheap ones needs *more* than 600s per
  attempt on a genuinely loaded machine is unmeasured; `--timeout` exists
  precisely so that doesn't require a code change if it turns out to.
