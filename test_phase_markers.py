#!/usr/bin/env python3
# coding: utf-8
"""Checks every lathe op brackets its finishing pass, by RUNNING each one.

Standalone, like the other test_*.py here - run it directly, no pytest.

The preview colours a pass by the marker the subroutine writes around it -
`(begin finish)` / `(end finish)`, and `(begin pre-finish)` on the polyline.
A marker is a comment, so nothing fails when one is missing, mistyped or
bracketing the wrong block: the pass simply draws in the roughing colour and
looks like roughing. That is the failure this file exists to catch, and it
cannot be caught by reading the .ngc - only by running it and looking at which
moves came out inside the bracket.

Most saved projects only use the polyline and facing, so the other five ops are
called DIRECTLY here: the generated program's defaults block is reused as a
preamble (every `#<_xxx>` global the subs read is defined in it) and one CALL is
spliced in after it. That is the same scratch technique the repo already uses
for motion checks.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ncam_preview as P                                   # noqa: E402

INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
GEN = os.path.join(HERE, '.claude', 'skills', 'lathe-gcode-verify', 'scripts',
                   'gen_project.py')
FAILED = []

# one CALL per op, with arguments that give it something to cut and at least
# one finishing pass. The numbers are not the point; a finishing pass count of
# 2 is - with 0 there would be no bracket to find and the test would pass
# against an op that never writes one.
CALLS = {
    'turning':   'o<turning> CALL [60] [50] [0] [-30] [2] [0] [0] [0]',
    'boring':    'o<boring> CALL [20] [30] [0] [-25] [2] [0] [0]',
    'taper':     'o<taper> CALL [60] [50] [0] [30] [2] [0] [0]',
    'taper_id':  'o<taper_id> CALL [20] [30] [0] [30] [2] [0] [0]',
    'radius_od': 'o<radius_od> CALL [50] [-10] [5] [1] [2]',
}


def check(name, cond, detail=''):
    # detail only on failure: most of these read as the accusation they are
    # there to make, which is nonsense printed next to a PASS
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def generate(out, project):
    r = subprocess.run([sys.executable, GEN, '--ini', INI, '--project', project,
                        '--out', out, '--config-copy'],
                       capture_output=True, text=True)
    return out if (r.returncode == 0 and os.path.isfile(out)) else None


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    d = tempfile.mkdtemp(prefix='phase_markers_')
    try:
        gen = generate(os.path.join(d, 'gen.ngc'), 'testing_15_2.xml')
        if gen is None:
            print('SKIP  could not generate the demo project')
            return

        # --- the two ops the demo project actually uses --------------------
        tp = P.parse_program(gen, INI)
        check('the demo project runs clean', tp.error is None, str(tp.error))
        by_op = {}
        for m in tp.moves:
            if m.kind == 'rapid':
                continue
            by_op.setdefault(m.op, {}).setdefault(m.subs, 0)
            by_op[m.op][m.subs] += 1

        def cuts(op, phase):
            return sum(n for subs, n in by_op.get(op, {}).items()
                       if (phase in subs if phase else not subs))

        check('facing brackets its finishing pass',
              cuts('Facing', P.FINISH) > 0,
              '%d finish cuts of %s' % (cuts('Facing', P.FINISH),
                                        by_op.get('Facing')))
        check('and still has roughing outside the bracket',
              cuts('Facing', None) > 0,
              'everything got marked as finish - the bracket is too wide')
        check('the polyline brackets its pre-finish pass',
              cuts('Lathe Polyline', P.PREFINISH) > 0)
        check('and its finishing passes',
              cuts('Lathe Polyline', P.FINISH) > 0)
        check('and keeps its roughing levels unmarked',
              cuts('Lathe Polyline', None) > 0)
        check('the two polyline phases do not overlap',
              not any(P.PREFINISH in s and P.FINISH in s
                      for s in by_op.get('Lathe Polyline', {})),
              'a move is inside both brackets at once')

        # --- the five ops no saved project exercises ------------------------
        with open(gen) as f:
            src = f.read().split('\n')
        try:
            head = src[:src.index('(begin Facing)')]
        except ValueError:
            print('SKIP  cannot find the defaults block to reuse')
            return
        for name, call in sorted(CALLS.items()):
            p = os.path.join(d, 'op_%s.ngc' % name)
            with open(p, 'w') as f:
                f.write('\n'.join(head)
                        + '\n(begin %s)\n\t%s\n(end %s)\nM2\n'
                        % (name, call, name))
            tpo = P.parse_program(p, INI)
            check('%s runs clean on its own' % name, tpo.error is None,
                  str(tpo.error))
            fin = [m for m in tpo.moves
                   if P.FINISH in m.subs and m.kind != 'rapid']
            rough = [m for m in tpo.moves if not m.subs and m.kind != 'rapid']
            check('%s brackets its finishing pass' % name, len(fin) > 0,
                  '%d cuts in the bracket, %d outside it'
                  % (len(fin), len(rough)))
            check('%s leaves its roughing outside the bracket' % name,
                  len(rough) > 0,
                  'the bracket swallowed the whole op')
            check('%s attributes the phase to the op, not above it' % name,
                  all(m.op == name for m in fin),
                  str({m.op for m in fin}))

        # --- a marker must colour something, or it is decoration ------------
        check('a finishing move is not drawn in the roughing colour',
              P.phase_colour(fin[0]) == P.COL['finish']
              and P.COL['finish'] != P.COL['feed'])
        check('and a roughing move still is',
              P.phase_colour(rough[0]) == P.COL['feed'])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every lathe op brackets its finishing pass.')


if __name__ == '__main__':
    main()
