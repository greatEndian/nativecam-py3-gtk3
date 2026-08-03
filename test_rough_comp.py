#!/usr/bin/env python3
# coding: utf-8
"""Compensated roughing does not cut past the stock the pre-finish needs.

Standalone, like the other test_*.py here - run it directly, no pytest.

Roughing levels stop against the stop table. UNCOMPENSATED, that table stops the
imaginary tool tip on the pre-finish contour - so the nose, which trails the tip
by up to its own radius, carries on and cuts past it. Compensated, the table
carries the nose and the NOSE stops there instead.

That is a falsifiable statement, and it is what this measures: sweep the real
nose circle along the roughing moves only, and ask how far past the pre-finish
contour the surface ends up.

WHY THE METRIC IS ONE-SIDED. An earlier attempt compared roughing against the
FINAL profile and reported 5.0452 mm on Off - the known-good baseline - because
it was measuring the region behind the boss that the back angle cannot reach and
that roughing correctly leaves standing. A metric that fails the baseline is not
a metric. Counting only OVERCUT - surface below the target - fixes that at the
root: an unreachable stretch leaves material ABOVE the target and contributes
exactly zero, so no exclusion window has to be guessed at.

The pre-finish target is the programmed contour offset outward by the Offset per
side, and the programmed contour is taken from an OFF-mode run whose last finish
pass carries no offset at all - the same non-circular trick test_comp_overlay
uses.
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
NOSE, ORIENT, F_OFF = 0.4, 2, 0.508
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def radius_span(pts, z):
    """(min, max) radius of a (z, radius) polyline at Z, or None.

    Both ends matter. Where a profile has a NEAR-VERTICAL segment - an end
    face, a shoulder - there is no single radius at that Z, and comparing a
    swept surface against the outer one there reports the whole height of the
    wall as an overcut. Measured: 4.7405 mm at Z-69.4 on testing_15_2, in every
    mode including Off, which is the end wall and not a fault.
    """
    lo = hi = None
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        if min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9 and abs(z1 - z0) > 1e-9:
            r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
            lo = r if lo is None else min(lo, r)
            hi = r if hi is None else max(hi, r)
    return None if lo is None else (lo, hi)


def radius_at(pts, z, flat=0.5):
    """The radius at Z, or None where the profile is not single-valued."""
    sp = radius_span(pts, z)
    if sp is None or sp[1] - sp[0] > flat:
        return None
    return sp[1]


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    import lathe_sections as ls
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='rough_comp_')
    try:
        def gen(mode):
            out = os.path.join(d, 'm%d.ngc' % mode)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            PROJECT, '--out', out, '--config-copy',
                            '--set', 'polyline:param_n_comp=%d' % mode],
                           capture_output=True, text=True)
            if not os.path.isfile(out):
                return None
            tp = P.parse_program(out, INI)
            return None if tp.error else tp

        runs = {m: gen(m) for m in (0, 1, 2)}
        check('all three modes generate and run', all(runs.values()),
              str({m: (t is None) for m, t in runs.items()}))
        if not all(runs.values()):
            return

        def phase(tp, rough):
            out = []
            for m in tp.moves:
                if m.op != 'Lathe Polyline':
                    continue
                fin = P.FINISH in m.subs or P.PREFINISH in m.subs
                if rough and not fin and m.kind != 'rapid':
                    out.append(m)
                elif not rough and P.FINISH in m.subs and m.kind == 'feed':
                    out.append(m)
            return out

        # the programmed contour: Off's finish pass applies no offset at all
        fin = phase(runs[0], False)
        prog = [(m.a[2], m.a[0]) for m in fin]
        prog.append((fin[-1].b[2], fin[-1].b[0]))
        check('the programmed contour has enough points', len(prog) > 5,
              '%d' % len(prog))
        if len(prog) <= 5:
            return

        # the pre-finish target: that contour offset outward by the allowance,
        # by the same construction the stop table itself uses
        target = ls.entry_contour(prog, F_OFF, 0)
        check('the pre-finish target stands off the profile',
              abs((radius_at(target, -10.0) or 0)
                  - (radius_at(prog, -10.0) or 0) - F_OFF) < 0.02,
              'offset is not %.3f at Z-10' % F_OFF)

        worst = {}
        for mode, label in ((0, 'Off'), (1, 'Native'), (2, 'In CAM')):
            rgh = phase(runs[mode], True)
            zs = [p for m in rgh for p in (m.a[2], m.b[2])]
            z0, z1 = min(zs) - 2, max(zs) + 2
            f = P.StockField(z0, z1, 0.0, 60.0,
                             P.StockField.columns_for(z0, z1, NOSE))
            dv = P.nose_offset(ORIENT)
            for m in rgh:
                f.cut_move(m.a, m.b, NOSE, dv)
            over, where, n = 0.0, None, 0
            z = max(p[0] for p in target)
            while z > min(p[0] for p in target):
                t = radius_at(target, z)
                if t is not None:
                    i = max(0, min(f.n - 1, int((z - f.z0) / f.dz)))
                    cut = t - f.outer[i]          # positive = cut BELOW target
                    n += 1
                    if cut > over:
                        over, where = cut, z
                z -= 0.1
            worst[label] = over
            print('   %-8s overcut past the pre-finish contour: %.4f mm%s '
                  '(%d samples)'
                  % (label, over, (' at Z%.1f' % where) if where else '', n))

        # THE PROOF, both halves. The uncompensated case must overcut by
        # something of the order of the nose, or there was nothing to fix and
        # the compensated result proves nothing.
        # The threshold is the MARGIN between the modes, not an absolute size.
        # A first version demanded Off exceed half the nose radius, which was a
        # guess and not a bound: the overcut an uncompensated stop leaves is
        # R*(1-cos) of the local surface angle, so on a 13 degree ramp it is
        # 0.0102 mm and only a steep wall approaches R. Measured here it is
        # 0.1116, which is real, far above the field's quantisation, and less
        # than the guessed threshold - the assertion was wrong, not the code.
        gain = worst['Off'] - max(worst['Native'], worst['In CAM'])
        check('uncompensated roughing DOES cut past the pre-finish contour, '
              'measurably', gain > 0.03,
              'compensation only removes %.4f mm, which is too close to the '
              'noise for the passes below to mean anything' % gain)
        for label in ('Native', 'In CAM'):
            check('%s roughing cuts materially less past it' % label,
                  worst[label] < worst['Off'] * 0.75,
                  'overcuts %.4f mm against Off %.4f - compensation is not '
                  'holding the nose off the pre-finish stock'
                  % (worst[label], worst['Off']))
        check('and the two compensated modes agree',
              abs(worst['Native'] - worst['In CAM']) < 0.02,
              '%.4f vs %.4f' % (worst['Native'], worst['In CAM']))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Compensated roughing leaves the pre-finish its stock.')


if __name__ == '__main__':
    main()
