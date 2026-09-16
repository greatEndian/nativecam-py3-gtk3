#!/usr/bin/env python3
# coding: utf-8
"""A reader never sees a half-written file - and the check can prove it fails.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHAT THIS GUARDS. `analysis/213`: Regenerate rewrote `ncam.ngc` with a plain
`open(path, "w")`, which truncates at open() and then fills, while the
preview's rs274 was reading that same path. 2 of 165 preview parses died on
EOF mid-subroutine. `atomic_write.write_atomic` writes a temp file beside the
target and `os.replace`s it in.

THE INSTRUMENT IS VALIDATED BOTH WAYS. The race test runs the SAME reader
against a deliberately non-atomic writer (`_naive_write`, a copy of the old
code) and requires it to observe torn reads. A race test that cannot catch
the original bug proves nothing about the fix - `analysis/127` is this
project's own record of a gate that could not fail.
"""
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import atomic_write  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def _naive_write(path, text):
    """Exactly what write_ngc used to do - the negative control."""
    with open(path, 'w') as f:
        f.write(text)


# Two complete versions, big enough that filling the file is not instant.
VER_A = ('(version A)\n' + 'A' * 60 + '\n') * 6000 + 'M2\n'
VER_B = ('(version B)\n' + 'B' * 60 + '\n') * 6000 + 'M2\n'


def hammer(writer, path, seconds=1.5):
    """Alternate two complete versions while a reader reads. -> (reads, torn)"""
    stop = threading.Event()
    counts = {'reads': 0, 'torn': 0}

    def write_loop():
        i = 0
        while not stop.is_set():
            writer(path, VER_A if i % 2 else VER_B)
            i += 1

    def read_loop():
        while not stop.is_set():
            try:
                with open(path) as f:
                    got = f.read()
            except OSError:
                continue
            counts['reads'] += 1
            if got != VER_A and got != VER_B:
                counts['torn'] += 1

    writer(path, VER_A)
    threads = [threading.Thread(target=write_loop, daemon=True),
               threading.Thread(target=read_loop, daemon=True)]
    for t in threads:
        t.start()
    time.sleep(seconds)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    return counts['reads'], counts['torn']


def main():
    d = tempfile.mkdtemp(prefix='atomic_write_')
    try:
        # --- basics -------------------------------------------------------
        p = os.path.join(d, 'ncam.ngc')
        atomic_write.write_atomic(p, 'hello\nM2\n')
        check('the text arrives intact', open(p).read() == 'hello\nM2\n')
        atomic_write.write_atomic(p, 'replaced\nM2\n')
        check('a rewrite replaces the whole file',
              open(p).read() == 'replaced\nM2\n')

        os.chmod(p, 0o644)
        atomic_write.write_atomic(p, 'again\nM2\n')
        check('an existing file keeps its mode (644, not mkstemp 600)',
              (os.stat(p).st_mode & 0o777) == 0o644,
              'got %o' % (os.stat(p).st_mode & 0o777))

        leftovers = [n for n in os.listdir(d) if n != 'ncam.ngc']
        check('no temp files are left beside the target', not leftovers,
              'found %r' % (leftovers,))

        # a write into a directory that does not exist must raise, not litter
        try:
            atomic_write.write_atomic(os.path.join(d, 'nope', 'x.ngc'), 'x')
            raised = False
        except Exception:
            raised = True
        check('a failed write raises rather than half-succeeding', raised)

        # --- the race, negative control first ------------------------------
        ctl = os.path.join(d, 'control.ngc')
        reads, torn = hammer(_naive_write, ctl)
        print('      control (old non-atomic write): %d reads, %d torn' %
              (reads, torn))
        check('NEGATIVE CONTROL: the old write really does tear', torn > 0,
              'saw 0 torn in %d reads - the test cannot see the bug it '
              'guards, so a pass below would mean nothing' % reads)

        tgt = os.path.join(d, 'atomic.ngc')
        reads, torn = hammer(atomic_write.write_atomic, tgt)
        print('      atomic write:                   %d reads, %d torn' %
              (reads, torn))
        check('a reader never sees a torn file under write_atomic', torn == 0,
              '%d torn out of %d reads' % (torn, reads))
        check('the reader actually got to read (not a vacuous pass)',
              reads > 50, 'only %d reads' % reads)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('  -', f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
