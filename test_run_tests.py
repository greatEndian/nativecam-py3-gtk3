#!/usr/bin/env python3
# coding: utf-8
"""Validates run_tests.py against five deliberately-built fake drivers.

Standalone, like the other test_*.py here - run it directly, no pytest.

CLAUDE.md: "validate the instrument before trusting it - a broken probe costs
more than no probe." run_tests.py is itself a probe for every other probe in
this repo, so it is validated here against fakes with a KNOWN correct verdict,
never against the real suite - see analysis/230 for why (another session may
own rs274 while this runs).

Builds, in a scratch temp dir:
  always_pass.py           - exits 0 every time
  always_fail.py           - exits 1 every time (a genuine failure)
  flaky_once.py            - exits 1 the first time, 0 the second (the load
                              artifact analysis/134 is about)
  slow_driver.py            - sleeps past the timeout it is given
  known_expected_fail.py    - exits 1 every time, but is named on --known-fail
                              (stands in for test_rough_ends.py)

Then runs run_tests.py twice: once over the three that should leave a clean
run (pass / pass-on-retry / known-fail), asserting exit 0, and once over the
two genuine problems (fail-twice / timeout), asserting exit 1 - and checks
each driver's own retry count, not just the label printed for it.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, 'run_tests.py')

failures = []


def check(name, ok, detail=''):
    print(('PASS' if ok else 'FAIL'), name, '' if ok else ('-> ' + detail))
    if not ok:
        failures.append(name)


def write(path, body):
    with open(path, 'w') as f:
        f.write(body)


def counter_bump(path):
    return (
        "import os\n"
        "c = %r\n"
        "n = int(open(c).read()) + 1 if os.path.exists(c) else 1\n"
        "open(c, 'w').write(str(n))\n" % path
    )


def read_count(path):
    if not os.path.exists(path):
        return 0
    return int(open(path).read())


def main():
    work = tempfile.mkdtemp(prefix='run_tests_selftest_')

    cnt_pass = os.path.join(work, 'pass.count')
    cnt_fail = os.path.join(work, 'fail.count')
    cnt_flaky = os.path.join(work, 'flaky.count')
    cnt_slow = os.path.join(work, 'slow.count')
    cnt_known = os.path.join(work, 'known.count')
    flaky_marker = os.path.join(work, 'flaky.marker')

    p_pass = os.path.join(work, 'always_pass.py')
    p_fail = os.path.join(work, 'always_fail.py')
    p_flaky = os.path.join(work, 'flaky_once.py')
    p_slow = os.path.join(work, 'slow_driver.py')
    p_known = os.path.join(work, 'known_expected_fail.py')

    write(p_pass, counter_bump(cnt_pass) + "raise SystemExit(0)\n")
    write(p_fail, counter_bump(cnt_fail) + "raise SystemExit(1)\n")
    write(p_known, counter_bump(cnt_known) + "raise SystemExit(1)\n")
    write(p_slow, counter_bump(cnt_slow) + "import time\ntime.sleep(5)\nraise SystemExit(0)\n")
    write(p_flaky, counter_bump(cnt_flaky) + (
        "import os\n"
        "marker = %r\n"
        "if os.path.exists(marker):\n"
        "    raise SystemExit(0)\n"
        "open(marker, 'w').close()\n"
        "raise SystemExit(1)\n" % flaky_marker
    ))

    # Run A: the clean set - pass, pass-on-retry, known-fail. Must exit 0.
    ra = subprocess.run(
        [sys.executable, RUNNER, p_pass, p_flaky, p_known,
         '--timeout', '5', '--known-fail', 'known_expected_fail.py'],
        capture_output=True, text=True)

    check('clean run exits 0', ra.returncode == 0,
          'rc=%d\n%s' % (ra.returncode, ra.stdout[-800:]))
    check('always_pass classified PASS',
          bool(re.search(r'always_pass\.py\s+PASS\b', ra.stdout)), ra.stdout)
    check('always_pass ran once', read_count(cnt_pass) == 1,
          'ran %d times' % read_count(cnt_pass))
    check('flaky_once classified PASSED ON RETRY',
          'flaky_once.py' in ra.stdout and 'PASSED ON RETRY' in ra.stdout, ra.stdout)
    check('flaky_once ran exactly twice (the retry)', read_count(cnt_flaky) == 2,
          'ran %d times' % read_count(cnt_flaky))
    check('known_expected_fail classified KNOWN FAIL',
          bool(re.search(r'known_expected_fail\.py\s+KNOWN FAIL', ra.stdout)), ra.stdout)
    check('known_expected_fail ran twice (retried like any other failure)',
          read_count(cnt_known) == 2, 'ran %d times' % read_count(cnt_known))

    # Run B: the dirty set - fails twice, and a real timeout. Must exit 1.
    rb = subprocess.run(
        [sys.executable, RUNNER, p_fail, p_slow, '--timeout', '2'],
        capture_output=True, text=True)

    check('dirty run exits 1 (genuine failure present)', rb.returncode == 1,
          'rc=%d\n%s' % (rb.returncode, rb.stdout[-800:]))
    check('always_fail classified FAILED',
          bool(re.search(r'always_fail\.py\s+FAILED\b', rb.stdout)), rb.stdout)
    check('always_fail ran exactly twice (one retry, still failed)',
          read_count(cnt_fail) == 2, 'ran %d times' % read_count(cnt_fail))
    check('slow_driver classified TIMEOUT',
          bool(re.search(r'slow_driver\.py\s+TIMEOUT\b', rb.stdout)), rb.stdout)
    check('slow_driver ran exactly once (no retry burns another timeout)',
          read_count(cnt_slow) == 1, 'ran %d times' % read_count(cnt_slow))

    # Bonus: auto-discovery skips the whole-catalogue sweeps by name, without
    # running them, when no drivers are named explicitly on the command line.
    # run_tests.py discovers siblings of ITS OWN file, not the caller's cwd -
    # so this must run a COPY of the runner placed inside the scratch dir,
    # never the real one (that would auto-discover and run this repo's real,
    # possibly rs274-driving, test_*.py files - exactly what must not happen).
    runner_copy = os.path.join(work, 'run_tests.py')
    with open(RUNNER) as f:
        write(runner_copy, f.read())
    sweep_stub = os.path.join(work, 'test_project_sweep.py')
    write(sweep_stub, "raise SystemExit(1)\n")  # would fail the run if executed
    ordinary = os.path.join(work, 'test_ordinary.py')
    write(ordinary, "raise SystemExit(0)\n")
    rc_auto = subprocess.run([sys.executable, runner_copy], cwd=work,
                              capture_output=True, text=True)
    check('auto-discovery reports the sweep SKIPPED, not run',
          'test_project_sweep.py' in rc_auto.stdout
          and re.search(r'skipped:\s+1\s+test_project_sweep\.py', rc_auto.stdout) is not None,
          rc_auto.stdout)
    check('auto-discovery run still exits 0 (the stub sweep never ran)',
          rc_auto.returncode == 0, 'rc=%d\n%s' % (rc_auto.returncode, rc_auto.stdout[-800:]))

    if failures:
        print('\n%d check(s) FAILED: %s' % (len(failures), ', '.join(failures)))
        sys.exit(1)
    print('\nAll run_tests.py self-checks passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
