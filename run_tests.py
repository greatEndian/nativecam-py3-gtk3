#!/usr/bin/env python3
# coding: utf-8
"""Suite runner that makes a reported FAIL trustworthy.

Standalone, like the drivers it runs - no pytest.

WHY THIS EXISTS. analysis/134: a 74-driver sweep reported test_sub_spans.py
(rc=124) and test_x_continuity.py (rc=1) as failures; re-run alone, with
nothing else contending for rs274, both exit 0. That is the FOURTH time
concurrency has corrupted a measurement in this project, each time treated as
a one-off scheduling mistake. It is not one: the sweep is an instrument that
returns false FAILs under load, and that is a property of the instrument, not
of the drivers it runs.

WHAT THIS DOES ABOUT IT
  - runs drivers ONE AT A TIME, always - never two at once, so the suite
    itself never becomes the load that corrupts its own measurement;
  - gives a driver that exits non-zero ONE retry before it is reported, and
    reports a pass-on-retry distinctly from a driver that failed both times -
    the retry outcome is itself the signal that the first run was loaded, not
    a verdict on the driver;
  - gives every attempt a generous per-driver timeout (default 600s - see
    analysis/230 for why that number) and reports a timeout as a TIMEOUT, a
    third bucket, never folded into FAILED;
  - lets a known-expected failure (test_rough_ends.py, awaiting greatEndian's
    tip-vs-cut ruling - CLAUDE.md) be reported as KNOWN FAIL, distinctly from
    both PASS and FAILED, without turning the run red.

Exit non-zero only when a driver failed twice with no known-fail excuse, or
timed out - a genuine result, not a load artifact.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# The whole-catalogue sweeps CLAUDE.md itself separates from "the drivers" -
# each one regenerates every project and drives rs274 repeatedly, minutes not
# seconds, and analysis/134 records the sweep returning false FAILs under load
# from exactly this kind of contention. Auto-discovery (no args given) skips
# them; naming one explicitly on the command line still runs it - that is a
# deliberate choice by whoever typed the name, not a default.
AUTO_EXCLUDE = {
    'test_project_sweep.py',
    'test_motion_fingerprint.py',
    'test_surface_equality.py',
    'test_all_projects.py',
}

DEFAULT_TIMEOUT = 600.0
DEFAULT_KNOWN_FAIL = {'test_rough_ends.py'}

PASS, PASSED_ON_RETRY, FAILED, TIMEOUT, KNOWN_FAIL, SKIPPED = (
    'PASS', 'PASSED ON RETRY', 'FAILED', 'TIMEOUT', 'KNOWN FAIL', 'SKIPPED')


def tracked_state():
    """`git status --porcelain` for TRACKED files, as a set, or None.

    None means "cannot tell" (not a git tree, git missing) and disables the
    check rather than inventing a verdict. Untracked files are excluded with
    -uno: a driver writing a scratch file into the tree is untidy, not the
    fault this guards against.
    """
    try:
        r = subprocess.run(['git', 'status', '--porcelain', '-uno'],
                           cwd=HERE, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode:
        return None
    return set(ln for ln in r.stdout.splitlines() if ln.strip())


def discover(script_dir):
    names = sorted(f for f in os.listdir(script_dir)
                    if f.startswith('test_') and f.endswith('.py'))
    keep = [n for n in names if n not in AUTO_EXCLUDE]
    skipped = [n for n in names if n in AUTO_EXCLUDE]
    return keep, skipped


def run_once(path, timeout):
    """Returns (rc_or_None, elapsed, output_tail). rc is None on timeout."""
    start = time.time()
    try:
        r = subprocess.run([sys.executable, path], cwd=os.path.dirname(path) or '.',
                            capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - start
        tail = (r.stderr or r.stdout or '')[-300:].replace('\n', ' ')
        return r.returncode, elapsed, tail
    except subprocess.TimeoutExpired:
        return None, time.time() - start, ''
    except OSError as e:
        return -1, time.time() - start, str(e)


def classify(name, path, timeout, known_fail):
    rc1, t1, tail1 = run_once(path, timeout)
    if rc1 is None:
        return TIMEOUT, [t1], ''
    if rc1 == 0:
        return PASS, [t1], ''
    rc2, t2, tail2 = run_once(path, timeout)
    if rc2 is None:
        return TIMEOUT, [t1, t2], ''
    if rc2 == 0:
        return PASSED_ON_RETRY, [t1, t2], ''
    if name in known_fail:
        return KNOWN_FAIL, [t1, t2], tail2
    return FAILED, [t1, t2], tail2


def fmt_times(times):
    return ' + '.join('%.1fs' % t for t in times)


def main():
    p = argparse.ArgumentParser(
        prog='run_tests.py',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('drivers', nargs='*', metavar='test_*.py',
                   help='specific driver files to run (any path, including '
                        'one from AUTO_EXCLUDE - naming it is your choice). '
                        'Default: every test_*.py in this directory except '
                        'the whole-catalogue sweeps (see AUTO_EXCLUDE), which '
                        'are then reported SKIPPED instead of run.')
    p.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                    help='seconds allowed per attempt, per driver '
                         '(default %(default)s)')
    p.add_argument('--known-fail', action='append', metavar='NAME',
                    help='driver basename to report as KNOWN FAIL instead of '
                         'FAILED when it fails twice (repeatable). Default: '
                         + ', '.join(sorted(DEFAULT_KNOWN_FAIL)))
    args = p.parse_args()

    known_fail = set(args.known_fail) if args.known_fail else set(DEFAULT_KNOWN_FAIL)

    if args.drivers:
        paths = args.drivers
        skipped = []
    else:
        names, skipped = discover(HERE)
        paths = [os.path.join(HERE, n) for n in names]

    results = []
    dirtied = []
    for path in paths:
        name = os.path.basename(path)
        print('running %-32s' % name, end=' ', flush=True)
        before = tracked_state()
        kind, times, tail = classify(name, path, args.timeout, known_fail)
        after = tracked_state()
        results.append((name, kind, times, tail))
        # A driver must not modify a TRACKED file. Compared as sets, so a tree
        # that was already dirty before the run is not blamed on the driver -
        # only paths this driver newly touched count. Earned 2026-09-16: a
        # committed harness wrote into cfg/lathe/facing.cfg on every run
        # because NCam's own startup re-symlinked its "scratch" copy back at
        # the repo (analysis/212), and nothing in the suite noticed.
        new_dirt = sorted(after - before) if (before is not None
                                              and after is not None) else []
        if new_dirt:
            dirtied.append((name, new_dirt))
        suffix = (' - %s' % tail) if kind == FAILED and tail else ''
        if new_dirt:
            suffix += '  [DIRTIED TRACKED: %s]' % ', '.join(
                d.strip() for d in new_dirt)
        print('%-16s (%s)%s' % (kind, fmt_times(times), suffix))

    print()
    print('SUMMARY: %d run, %d skipped' % (len(results), len(skipped)))
    buckets = {PASS: [], PASSED_ON_RETRY: [], FAILED: [], TIMEOUT: [], KNOWN_FAIL: []}
    for name, kind, times, tail in results:
        buckets[kind].append(name)
    print('  passed:          %d' % len(buckets[PASS]))
    print('  passed on retry: %d  %s' % (len(buckets[PASSED_ON_RETRY]),
          ' '.join(buckets[PASSED_ON_RETRY])))
    print('  failed (twice):  %d  %s' % (len(buckets[FAILED]),
          ' '.join(buckets[FAILED])))
    print('  timed out:       %d  %s' % (len(buckets[TIMEOUT]),
          ' '.join(buckets[TIMEOUT])))
    print('  known fail:      %d  %s' % (len(buckets[KNOWN_FAIL]),
          ' '.join(buckets[KNOWN_FAIL])))
    print('  skipped:         %d  %s' % (len(skipped), ' '.join(skipped)))
    print('  dirtied tree:    %d  %s' % (len(dirtied),
          ' '.join(n for n, _ in dirtied)))

    if dirtied:
        print()
        print('A DRIVER MODIFIED A TRACKED FILE. A test that edits the repo is '
              'not testing an isolated copy, whatever it reports:')
        for name, paths_ in dirtied:
            for d in paths_:
                print('    %-28s %s' % (name, d.strip()))

    if buckets[PASSED_ON_RETRY]:
        print()
        print('NOTE: a pass-on-retry is not a clean bill of health - it means '
              'the FIRST attempt failed. If this run shared the machine with '
              'anything else, that is the load artifact analysis/134 '
              'describes, not a fixed bug.')

    exit_code = 1 if (buckets[FAILED] or buckets[TIMEOUT] or dirtied) else 0
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
