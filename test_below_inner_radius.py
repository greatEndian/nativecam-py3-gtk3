#!/usr/bin/env python3
# coding: utf-8
"""A face can run on past its End diameter, and by default does not.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 13 of `POLYLINE-GAPS.md`. The reference package: *"an adjustment to a Face
or Part cut to position the tool nose past the Inner Radius position. Use this
to cut past the Centreline of the part."*

WHY IT IS NEEDED. Facing to centre with a round nose leaves a pip. The nose is a
circle, so when its centre reaches the axis the cutting edge has not yet swept
the last of the material and a small cone stands on the axis. Carrying on past
by about the nose radius removes it.

WHY FACING AND NOT THE POLYLINE. The polyline's End diameter is the final
diameter of a TURNING region and reaches poly_lathe_mill as `final_radius`;
running a turning pass past the spindle axis is not a thing. The pip is left by a
FACE. The reference also names Part cuts - there is no parting operation in this
codebase yet, so it inherits this parameter when it is built. See analysis/037.

THE FIRST ASSERTION IS THE ONE THAT MATTERS: at 0 the program must be
byte-identical. Measured when this was written - the whole move list of
testing_15_5 hashes the same with the feature present and with it stashed away,
484 moves either way.

WHAT IS ASSERTED IS THE SURFACE, NOT THE PARAMETER. The distance is checked by
reading how far the facing moves actually reach in X, because a unit test on the
arithmetic would have passed the version that scaled the radial distance wrongly
- that is exactly how the tangential extension's diameter/radius bug survived
its unit cases in bd50c55.
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
PROJECT = 'testing_15_5.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(sets):
    """-> (facing feed count, how far the face reaches in X, all moves)."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='bir_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
               '--out', out, '--config-copy']
        for kv in sets:
            cmd += ['--set', kv]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        fac = [m for m in tp.moves
               if m.op and 'acing' in m.op and m.kind != 'rapid']
        if not fac:
            return None
        xs = [q for m in fac for q in (m.a[0], m.b[0])]
        moves = [(round(m.a[0], 4), round(m.a[2], 4),
                  round(m.b[0], 4), round(m.b[2], 4), m.kind)
                 for m in tp.moves]
        return {'n': len(fac), 'reach': round(min(xs), 4), 'moves': moves}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    off = run([])
    check('the project generates with the feature at its default', off)
    if not off:
        sys.exit(1)
    print('      default        %d facing feeds, reaching X%.4f'
          % (off['n'], off['reach']))

    zero = run(['facing:param_below_ir=0.0'])
    check('an explicit 0 is IDENTICAL to the default, move for move',
          zero is not None and zero['moves'] == off['moves'],
          'the feature moves a program that asked for nothing')

    # the face must reach exactly that much further, in the direction it was
    # already cutting - this project faces to the centreline, so past it
    for dist in (1.0, 2.0):
        on = run(['facing:param_below_ir=%s' % dist])
        check('a distance of %.1f runs the face exactly that far past the end'
              % dist,
              on is not None
              and abs((off['reach'] - on['reach']) - dist) < 1e-3,
              'reaches X%.4f against X%.4f, a difference of %.4f not %.1f'
              % (on['reach'] if on else 0.0, off['reach'],
                 (off['reach'] - on['reach']) if on else 0.0, dist))
        if on:
            print('      below_ir %.1f    %d facing feeds, reaching X%.4f'
                  % (dist, on['n'], on['reach']))
            # it lengthens the cut; it does not add passes
            check('   and it does not add or remove a pass',
                  on['n'] == off['n'],
                  '%d facing feeds against %d' % (on['n'], off['n']))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The face runs past centre by the distance asked for, and only then.')


if __name__ == '__main__':
    main()
