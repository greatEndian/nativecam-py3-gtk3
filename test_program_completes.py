#!/usr/bin/env python3
# coding: utf-8
"""A run that stopped part way is refused, not measured.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG THIS EXISTS FOR

`rs274` returns every move it made before it stopped, and those moves are all
perfectly valid. So a check that counts moves, or measures geometry, cannot
tell a finished program from a truncated one - it measures the fragment and
reports whatever it finds. Two real faults sat green behind exactly that:
`openPoints.md`, *"A test that passes on an aborted program is not passing.
Neither test_behind_boss_ladder nor test_ladder checks that rs274 reached the
end of the file; both take whatever moves were emitted before it stopped."*

Measured here: truncating a real program two-thirds of the way through still
yields **14 moves**, against 341 for the whole one. Every geometric assertion in
this suite would have run happily on those 14.

THE FIX IS IN ONE PLACE. `parse_program` now records whether `PROGRAM_END` was
reached, and sets `error` when it was not. All 29 test files already refuse to
measure an errored run, so they are protected without each having to remember a
second check, and a test written tomorrow inherits it.

WHY THE END MARKER AND NOT THE ERROR MESSAGE. Some aborts leave no message at
all - a truncated var file stops the interpreter at `T<n> M6` in silence, which
is recorded in the lathe-gcode-verify skill. Testing for the absence of an
error would miss exactly those. The end marker is positive evidence.

WHAT IS ASSERTED

1. A whole program reports completed, with no error.
2. A TRUNCATED one is refused - and still emits moves, which is the whole
   point: without that, this test would prove nothing that a move count did
   not already prove.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='complete_')
    try:
        whole = os.path.join(d, 'whole.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        'testing_15_2.xml', '--out', whole, '--config-copy'],
                       capture_output=True, text=True)
        check('the reference program generates', os.path.isfile(whole))
        if not os.path.isfile(whole):
            return

        tp = P.parse_program(whole, INI)
        check('a whole program reports completed', tp.completed)
        check('   and carries no error', tp.error is None, str(tp.error)[:90])
        check('   and has moves to measure', len(tp.moves) > 100,
              '%d moves' % len(tp.moves))
        n_whole = len(tp.moves)

        # 2. TRUNCATE IT. A bad named parameter two-thirds of the way in stops
        # the interpreter there; everything before it still runs.
        lines = open(whole).read().split('\n')
        cut = int(len(lines) * 0.66)
        bad = os.path.join(d, 'truncated.ngc')
        open(bad, 'w').write('\n'.join(
            lines[:cut] + ['G1 X#<_no_such_parameter_at_all>'] + lines[cut:]))

        tt = P.parse_program(bad, INI)
        check('a truncated program is NOT reported completed',
              not tt.completed)
        check('   and is refused through error, so every existing test '
              'refuses it too', tt.error is not None)
        check('   and it DID emit moves - which is why a move count '
              'cannot catch this', len(tt.moves) > 0,
              'no moves emitted, so this proves nothing a move count did not')
        check('   and far fewer than the whole program',
              0 < len(tt.moves) < n_whole,
              '%d against %d' % (len(tt.moves), n_whole))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('An aborted program is refused instead of measured.')


if __name__ == '__main__':
    main()
