#!/usr/bin/env python3
# coding: utf-8
"""No roughing level may cut through a feature standing above it.

Standalone, like the other test_*.py here - run it directly, no pytest.

A roughing level is a straight cut at one radius. Where the part rises above
that radius - a boss, a shoulder - the level has to stop, and resume on the far
side; that is what the disjoint-interval handling exists for. A level that
sweeps straight through such a feature is a crash, not a finish defect.

WHAT LET IT HAPPEN, and why nothing else caught it: lathe_level_pass overrides
its own z_start from the entry-contour crossing, which is deliberately allowed
to sit BEHIND the interval start - that backward reach is the room the
profile-angle ramp needs, and on testing_15_2 it is 1.8127 mm on every level.
It had no upper bound. With the pre-finish pass switched OFF the nearest
qualifying crossing sat 24.03, 25.32 and 28.08 mm back, on the far side of the
boss, and the level swept 45.7 mm through a boss peaking 2.77 mm above it.

The section windows, the resume scan and the CALL arguments were all correct
and all three were measured before the cause was found. test_rough_comp saw
nothing: its metric is one-sided overcut past the pre-finish contour, and a
level ploughing through a boss is not overcut of that surface at all.

THE PRE-FINISH SWITCH IS PART OF THE TEST. The fault only appeared with it off,
and every saved project has it on - so a check that does not toggle it would
have passed throughout.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECT = 'testing_15_2.xml'
FC_BASE, FC_TOP = 4000, 4200
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def contour(path):
    """The reachable contour the program carries, as (z, radius)."""
    vals = {}
    for ln in open(path):
        m = re.match(r'#(\d+) = (-?[\d.]+)\s*$', ln.strip())
        if m and FC_BASE <= int(m.group(1)) < FC_TOP:
            vals[int(m.group(1))] = float(m.group(2))
    pts, i = [], FC_BASE
    while i in vals and i + 1 in vals:
        pts.append((vals[i], vals[i + 1]))
        i += 2
    return pts


def peak_between(pts, z0, z1):
    """The highest contour radius strictly inside (z1, z0), or None."""
    lo, hi = min(z0, z1), max(z0, z1)
    inside = [r for z, r in pts if lo + 1e-6 < z < hi - 1e-6]
    return max(inside) if inside else None


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='through_')
    try:
        for pf in (1, 0):
            label = 'pre-finish %s' % ('ON' if pf else 'OFF')
            out = os.path.join(d, 'pf%d.ngc' % pf)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            PROJECT, '--out', out, '--config-copy',
                            '--set', 'polyline:param_n_comp=1',
                            '--set', 'polyline:param_pf_on=%d' % pf],
                           capture_output=True, text=True)
            if not os.path.isfile(out):
                check('%s generates' % label, False)
                continue
            fc = contour(out)
            tp = P.parse_program(out, INI)
            check('%s: the program carries a reachable contour' % label,
                  len(fc) > 5 and not tp.error,
                  '%d points, error %s' % (len(fc), tp.error))
            if not fc or tp.error:
                continue
            rgh = [m for m in tp.moves if m.op == 'Lathe Polyline'
                   and not m.subs and m.kind == 'feed']
            cuts = [(m.a[0], m.a[2], m.b[2]) for m in rgh
                    if abs(m.b[0] - m.a[0]) < 1e-6 and m.b[2] < m.a[2] - 1e-6]
            through = []
            for r, z0, z1 in cuts:
                pk = peak_between(fc, z0, z1)
                if pk is not None and pk > r + 0.01:
                    through.append((r, z0, z1, pk - r))
            check('%s: no level cuts through a feature above it' % label,
                  not through,
                  '%d of %d cuts do - worst r%.4f from Z%.4f to Z%.4f, '
                  '%.4f mm into a feature standing above it'
                  % ((len(through), len(cuts)) + through[0][:3]
                     + (through[0][3],)) if through else '')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('No roughing level ploughs through a feature standing above it.')


if __name__ == '__main__':
    main()
