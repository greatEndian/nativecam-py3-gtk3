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

        # THE PROOF IS THE ABSOLUTE OVERCUT, not the gap between the modes.
        #
        # It used to be the gap - Off had to overcut at least 0.03 more than
        # the compensated modes, and each of those at most three quarters of
        # Off. That held while the ENTRY CONTOUR stood one roughing depth of
        # cut from the FINAL contour instead of from the floor: an
        # uncompensated level began cutting too far in and left 0.1115 past the
        # pre-finish contour, against 0.0503 compensated. Fixing the entry
        # (analysis/030) took Off to 0.0503 as well.
        #
        # So the gap is gone because the fault it measured is gone, and an
        # assertion keyed on it would now demand that roughing be BAD in the
        # uncompensated case. greatEndian, 2026-08-11: the fault was real -
        # merge it and rewrite the test.
        #
        # What actually matters is that no mode leaves the pre-finish more than
        # its own stock: the pre-finish surface is what the operator MEASURES
        # to dial in the finish compensation, so an overcut there is what
        # ruins that measurement.
        #
        # THE BOUND SITS BETWEEN THE TWO MEASURED STATES, which is what makes
        # it an assertion and not a rubber stamp: 0.1115 is what the broken
        # entry contour produced and must FAIL, 0.0503 is what the fixed one
        # produces and must PASS. 0.08 clears the good case by 0.0297 and
        # rejects the bad one by 0.0315. A first attempt used 0.0508 - one
        # tenth of the finish offset, which sounds principled - and left
        # 0.0005 of margin, an assertion that would flip on rounding.
        OVERCUT_MAX = 0.08
        for label in ('Off', 'Native', 'In CAM'):
            check('%-7s roughing does not cut past the pre-finish contour'
                  % label,
                  worst[label] <= OVERCUT_MAX,
                  'overcuts %.4f mm, more than the %.4f bound - roughing is '
                  'eating the stock the operator measures'
                  % (worst[label], OVERCUT_MAX))
        check('   and no mode is materially worse than another',
              max(worst.values()) - min(worst.values()) < 0.02,
              'Off %.4f, Native %.4f, In CAM %.4f'
              % (worst['Off'], worst['Native'], worst['In CAM']))
        check('and the two compensated modes agree',
              abs(worst['Native'] - worst['In CAM']) < 0.02,
              '%.4f vs %.4f' % (worst['Native'], worst['In CAM']))

        # AND EVERY LEVEL ACTUALLY REACHES THE PRE-FINISH IT STOPS AGAINST.
        # greatEndian, photo/leadOutIssue_1.png: the first roughing pass behind
        # the boss ended early, never touched the pre-finish, and rapided away.
        # Compensated only - Off was right. The stop contour carries the nose,
        # which shifts the WHOLE contour including its open ends, so the back
        # wall topped out at r29.6000 while the highest level sits at r29.6520:
        # that level never crossed the wall and stopped 0.5080 short.
        #
        # None of the checks above could see it. They measure how far roughing
        # cuts PAST the pre-finish; a level that stops early cuts less, which
        # reads as an improvement. Under-cutting needs its own assertion.
        for mode, label in ((0, 'Off'), (1, 'Native'), (2, 'In CAM')):
            tp = runs[mode]
            pf = [m for m in tp.moves if m.op == 'Lathe Polyline'
                  and P.PREFINISH in m.subs and m.kind == 'feed']
            if not pf:
                continue
            wall = min(m.b[2] for m in pf)
            rgh = [m for m in tp.moves if m.op == 'Lathe Polyline'
                   and not m.subs and m.kind == 'feed']
            lv = [(m.a[0], m.b[2]) for m in rgh
                  if abs(m.b[0] - m.a[0]) < 1e-6 and m.b[2] < m.a[2] - 1e-6]
            back = [(r, z) for r, z in lv if z < wall + 2.0]
            # A LEVEL MUST STOP THE PRE-FINISH ALLOWANCE SHORT OF THE WALL,
            # not ON it, which is what this asserted before.
            #
            # The stop contour carried the finish offset alone, so the Z end of
            # a level landed exactly on the pre-finish surface while the FLOOR
            # contour, which sets the radii, carried `fin + prefin`. The
            # allowance existed in X and not in Z, and against a boss face the
            # pre-finish pass arrived with nothing to cut. greatEndian,
            # 2026-08-12: "prefinish offset has to be constant in the each axis
            # so the tool will have some material to cut and not create
            # chattering."
            #
            # What this check was written for is UNCHANGED and still caught: a
            # level stopping a whole DEPTH OF CUT short, which the nose shifting
            # the stop contour's open end once produced - 0.5080 on
            # photo/leadOutIssue_1.png. So the bound is the pre-finish allowance
            # plus a margin, and it still rejects a depth of cut. The second
            # check is the new half: nothing may cut INTO that allowance.
            pf_allow = 0.254
            band = pf_allow + 0.06
            short = [(r, z) for r, z in back if z - wall > band]
            over = [(r, z) for r, z in back if z - wall < pf_allow - 0.06]
            check('%-7s every roughing level stops the pre-finish allowance '
                  'short of the wall' % label, not short,
                  'r%.4f stops at Z%.4f, %.4f short of the wall at Z%.4f - '
                  'more than the %.4f allowance, so a level is ending early'
                  % (short[0][0], short[0][1], short[0][1] - wall, wall,
                     pf_allow) if short else '')
            check('   %-7s and none of them cuts INTO that allowance' % label,
                  not over,
                  'r%.4f reaches Z%.4f, only %.4f from the wall - the '
                  'pre-finish pass has nothing to cut there'
                  % (over[0][0], over[0][1], over[0][1] - wall)
                  if over else '')

        # AND EVERY PASS BEHIND THE BOSS ARRIVES ALONG THE PROFILE ANGLE.
        # greatEndian: "the last pass lead in behind the boss segment has wrong
        # lead in .. if I select sectioning the lead in shape is right".
        #
        # The approach is three pieces - a straight lead-in, a no-op, then a
        # ramp at the contour's own angle onto the level - and the ramp is
        # capped so it is never longer than the cut it enters. That cap was
        # tested against the SCAN's stop, which the stop table then extends,
        # so the shortest pass lost its ramp and plunged in at 45 degrees.
        # Sectioning gave that region a longer window, the same cap passed,
        # and the shape came out right - which is exactly the comparison
        # greatEndian made.
        #
        # A ramp is told from the 45 degree lead-in by its shallowness: the
        # lead-in has |dz| == |dr|, a 13 degree ramp has |dz| over four times
        # |dr|. No angle is assumed - only that a ramp is not a 45 lead-in.
        for mode, label in ((0, 'Off'), (1, 'Native'), (2, 'In CAM')):
            rgh = [m for m in runs[mode].moves if m.op == 'Lathe Polyline'
                   and not m.subs]
            cuts = [i for i, m in enumerate(rgh)
                    if m.kind == 'feed' and abs(m.b[0] - m.a[0]) < 1e-6
                    and m.b[2] < m.a[2] - 1e-6 and m.a[2] < -40.0]
            plunged = []
            for i in cuts:
                ramp = False
                for m in rgh[max(0, i - 4):i]:
                    if m.kind != 'feed':
                        continue
                    dz, dr = abs(m.b[2] - m.a[2]), abs(m.b[0] - m.a[0])
                    if dr > 1e-6 and dz > dr * 1.5:
                        ramp = True
                if not ramp:
                    plunged.append((rgh[i].a[0], rgh[i].a[2]))
            check('%-7s every pass behind the boss ramps in, none plunges'
                  % label, not plunged,
                  '%d of %d plunge - first at r%.4f, Z%.4f'
                  % (len(plunged), len(cuts), plunged[0][0], plunged[0][1])
                  if plunged else '')
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
