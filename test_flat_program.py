#!/usr/bin/env python3
# coding: utf-8
"""The flat program is the same motion as ncam.ngc, and it loads.

Standalone, like the other test_*.py here - run it directly, no pytest.

ncam.ngc is O-word calls and expressions. The Send dropdown can hand LinuxCNC
the FLAT program instead - the interpreter's own output, every subroutine and
expression already gone - which is what a control that cannot handle O-words
needs. That is only safe if it is the same motion, so this asserts it.

NOT BY COMPARING MOVE LISTS INDEX BY INDEX. flatten_canon drops zero-length
moves, so the two lists are different lengths - 253 against 241 here - and
zipping them reports a 69.89 mm discrepancy that is pure index drift. The
comparison that means something is over quantities that do not care about
ordering or about moves that go nowhere: the number of non-zero feeds, the
total feed length, and the SET of feed endpoints.

Two properties of the flat file are stated in its own header and both were
verified rather than assumed:

- work offsets are NOT baked in. Setting G54 Z to 12.0 in a scratch var file
  leaves the canon output byte-identical, so it runs under the same G54 the
  original was written for.
- cutter compensation IS applied - the coordinates are tool control points -
  so it must not be run with G41/G42 active as well.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECT = 'testing_15_2.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def stats(tp):
    f = [m for m in tp.moves if m.kind == 'feed']
    nz = [m for m in f
          if math.dist((m.a[0], m.a[2]), (m.b[0], m.b[2])) > 1e-9]
    length = sum(math.dist((m.a[0], m.a[2]), (m.b[0], m.b[2])) for m in f)
    ends = {(round(m.b[2], 4), round(m.b[0], 4)) for m in f}
    return len(nz), length, ends, len([m for m in tp.moves
                                       if m.kind == 'rapid'])


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    # the action exists, on the class that owns it, and the dropdown wires it
    import ncam                                            # noqa: F401
    from ncam_app_actions import NCamAppActionsMixin as M
    import inspect
    check('the Send dropdown has a flat-G-code action',
          hasattr(M, 'action_send_flat'))
    src = inspect.getsource(M.create_send_mode_menu)
    check('   and the dropdown actually calls it',
          'self.action_send_flat' in src,
          'the action exists but nothing invokes it')
    check('   with its own filename, not ncam.ngc',
          ncam.FLAT_FILE != ncam.GENERATED_FILE,
          'the flat program would overwrite the O-word one')

    d = tempfile.mkdtemp(prefix='flat_')
    try:
        out = os.path.join(d, 'p.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        PROJECT, '--out', out, '--config-copy',
                        '--set', 'polyline:param_n_comp=2'],
                       capture_output=True, text=True)
        if not os.path.isfile(out):
            check('the project generates', False)
            return
        tp = P.parse_program(out, INI)
        check('the original parses and yields a flat listing',
              not tp.error and tp.flat.strip().count('\n') > 50,
              'error %s, %d lines' % (tp.error, tp.flat.count('\n')))
        if tp.error or not tp.flat.strip():
            return

        flat = os.path.join(d, 'ncam-flat.ngc')
        open(flat, 'w').write(tp.flat)
        tp2 = P.parse_program(flat, INI)
        check('the flat program LOADS - the interpreter accepts it',
              not tp2.error, str(tp2.error))
        if tp2.error:
            return

        a, b = stats(tp), stats(tp2)
        check('the same number of cutting moves', a[0] == b[0],
              '%d against %d' % (a[0], b[0]))
        check('the same total feed length', abs(a[1] - b[1]) < 1e-4,
              '%.4f against %.4f mm' % (a[1], b[1]))
        check('the same rapids', a[3] == b[3], '%d against %d' % (a[3], b[3]))
        check('and every feed endpoint is in both',
              a[2] == b[2],
              '%d only in the original, %d only in the flat'
              % (len(a[2] - b[2]), len(b[2] - a[2])))

        # it must be a program, not a listing: the words a control needs
        head = tp.flat[:4000]
        for word, why in (('G18', 'plane'), ('G7', 'diameter mode'),
                          ('M6', 'tool change'), ('M3', 'spindle')):
            check('   the flat program states its %s' % why,
                  word in head, 'no %s in the first 4000 characters' % word)
        check('   and it ends', 'M2' in tp.flat[-2000:],
              'no M2 - the control would run off the end')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The flat program loads and is the same motion.')


if __name__ == '__main__':
    main()
