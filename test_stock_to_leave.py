#!/usr/bin/env python3
# coding: utf-8
"""Stock to leave is two numbers: radial on the diameters, axial on the walls.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 15 of `POLYLINE-GAPS.md`. We held ONE allowance, perpendicular to the whole
profile, so there was no way to leave more on a wall than on a diameter - which
is ordinary when the faces are finished by a different tool or a different pass.

THE RULE, and why it is not a guess. Displace the surface by the vector
(nz * off_z, nr * off_x): a diameter has normal (0, 1) and moves off_x
radially, a wall has normal (1, 0) and moves off_z axially. The perpendicular
distance that produces is its projection on the normal,

    d = nz^2 * off_z + nr^2 * off_x

which is off_x on a diameter, off_z on a wall, and their mean at 45 degrees -
the interpolation the reference package describes in as many words.

WHAT IS ASSERTED

1. THE ISOTROPIC PATH IS UNTOUCHED. Both offsetters, called with one allowance
   or with the same number twice, return identical lists. This is the assertion
   that matters most: every saved project keeps its toolpath to the last bit,
   and the new parameter defaults off.

2. THE BLEND IS RIGHT AT THE THREE NORMALS that can be checked by hand.

3. IT REACHES THE CONTOUR. On a real profile with a diameter and a wall, the
   diameter is offset by the radial value and the wall by the axial one -
   measured off the returned contour, not off the rule.

4. AND IT REACHES THE MACHINE. The generated program's stop table moves when
   the axial value changes, and does not when only the switch is off.
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
TOL = 1e-9
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def radius_at(pts, z):
    """Outermost radius of a (z, radius) polyline at Z, or None."""
    best = None
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        if min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9 and abs(z1 - z0) > 1e-9:
            r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
            best = r if best is None else max(best, r)
    return best


def main():
    import lathe_sections as L

    # 1. THE ISOTROPIC PATH IS UNTOUCHED
    prof = [(0.0, 38.0), (-1.0, 40.0), (-20.0, 40.0), (-20.0, 50.0),
            (-30.0, 50.0), (-35.0, 60.0), (-50.0, 60.0)]
    rad = [(z, x / 2.0) for z, x in prof]
    check('offset_contour is unchanged when the two allowances are equal',
          L.offset_contour(prof, 0.4, 2, 1, 0.508)
          == L.offset_contour(prof, 0.4, 2, 1, 0.508, 0.508))
    check('entry_contour is unchanged when the two allowances are equal',
          L.entry_contour(rad, 0.508, 0, 0.4, 2)
          == L.entry_contour(rad, 0.508, 0, 0.4, 2, 0.508))
    check('   and with no nose either',
          L.entry_contour(rad, 0.3, 0) == L.entry_contour(rad, 0.3, 0, 0.0, 0, 0.3))

    # 2. THE BLEND, at the normals that can be checked by hand
    f = L.stock_at_normal
    check('a diameter gets the radial value', abs(f(0.0, 1.0, 0.5, 0.1) - 0.5) < TOL)
    check('a wall gets the axial value', abs(f(1.0, 0.0, 0.5, 0.1) - 0.1) < TOL)
    r2 = 2 ** -0.5
    check('45 degrees gets their mean', abs(f(r2, r2, 0.5, 0.1) - 0.3) < 1e-9,
          '%.6f' % f(r2, r2, 0.5, 0.1))
    check('and one value answers every normal when they are equal',
          all(abs(f(nz, (1 - nz * nz) ** 0.5, 0.5, 0.5) - 0.5) < TOL
              for nz in (0.0, 0.3, 0.7, 1.0)))

    # 3. IT REACHES THE CONTOUR - measured off the result, not the rule
    iso = L.entry_contour(rad, 0.5, 0)
    ani = L.entry_contour(rad, 0.5, 0, 0.0, 0, 0.1)
    check('the diameter still carries the radial allowance',
          abs(radius_at(ani, -10.0) - (20.0 + 0.5)) < 1e-6,
          'got %.4f' % (radius_at(ani, -10.0) or 0))
    check('   and the isotropic contour agrees there',
          abs(radius_at(iso, -10.0) - radius_at(ani, -10.0)) < 1e-6)
    # MEASURE THE PERPENDICULAR DISTANCE, not a shift in Z. A wall's contour
    # moves TOWARD it and a 45 degree surface's Z shift is the perpendicular
    # distance times cos 45 - two sign-and-trig traps that both read as
    # failures when the real numbers were right. The allowance is a
    # perpendicular distance by definition, so measure that.
    def dist_to(c, pz, pr):
        best = None
        for (z0, r0), (z1, r1) in zip(c, c[1:]):
            dz, dr = z1 - z0, r1 - r0
            n2 = dz * dz + dr * dr
            t = 0.0 if n2 < 1e-12 else max(0.0, min(
                1.0, ((pz - z0) * dz + (pr - r0) * dr) / n2))
            d = ((z0 + t * dz - pz) ** 2 + (r0 + t * dr - pr) ** 2) ** 0.5
            best = d if best is None else min(best, d)
        return best

    for what, (pz, pr), want in (
            ('the diameter', (-10.0, 20.0), 0.5),
            ('the wall', (-20.0, 22.5), 0.1),
            ('the 45 degree chamfer', (-0.5, 19.5), 0.3)):
        got = dist_to(ani, pz, pr)
        check('%s is left %.1f' % (what, want), abs(got - want) < 0.01,
              'measured %.4f from the surface at Z%.1f r%.1f' % (got, pz, pr))

    # 4. AND IT REACHES THE MACHINE
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    else:
        d = tempfile.mkdtemp(prefix='stock2leave_')
        try:
            def gen(tag, sets):
                out = os.path.join(d, tag + '.ngc')
                cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
                       '--out', out, '--config-copy']
                for kv in sets:
                    cmd += ['--set', kv]
                subprocess.run(cmd, capture_output=True, text=True)
                if not os.path.isfile(out):
                    return None
                txt = open(out).read()
                return [float(x) for x in
                        re.findall(r'#4[45]\d\d = (-?[\d.]+)', txt)]

            # AND ROUGHING HONOURS IT, which is the assertion this file did
            # not have. It measured a 45 degree chamfer, 0.3008 against 0.3,
            # and I read that as proof - but on a slope the level scan stops
            # on the scalar and the STOP table then extends it forward onto
            # the anisotropic contour, so the right number came out for the
            # wrong reason. A WALL with an axial value far larger than the
            # radial one needs the stop pulled BACK, which the stop table can
            # never do. greatEndian set Z to 2.000 against X 0.508 and
            # roughing stopped at 0.762 - fin_off + prefin_off, the scalar.
            def wall_gap(sets):
                out = os.path.join(d, 'wall.ngc')
                cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
                       '--out', out, '--config-copy']
                for kv in sets:
                    cmd += ['--set', kv]
                subprocess.run(cmd, capture_output=True, text=True)
                if not os.path.isfile(out):
                    return None
                import ncam_preview as P
                tp = P.parse_program(out, INI)
                if tp.error:
                    return None
                lv = [m for m in tp.moves
                      if m.op == 'Lathe Polyline' and not m.subs
                      and m.kind == 'feed' and abs(m.b[0] - m.a[0]) < 1e-6
                      and abs(m.b[2] - m.a[2]) > 1e-6 and m.b[2] < -60.0]
                return min(m.b[2] for m in lv) + 70.4 if lv else None

            iso = wall_gap(['polyline:param_n_comp=2'])
            ani = wall_gap(['polyline:param_n_comp=2',
                            'polyline:param_f_off=0.508',
                            'polyline:param_f_off_sep=1',
                            'polyline:param_f_off_z=2.0'])
            # THE ALLOWANCE ROUGHING LEAVES IS fin + prefin, ON EVERY AXIS.
            #
            # These expected 2.000 and 0.508 - the FINISH offset alone - which
            # encoded a real fault as correct. The stop contour carried
            # `stock_pair` while the floor contour carried `fin + prefin`, so
            # the pre-finish allowance existed on the diameters and not on the
            # walls: a level was allowed to stop ON the pre-finish surface in
            # Z, and the pre-finish pass reached a boss face or a wall with
            # nothing to cut. greatEndian, 2026-08-12: "prefinish offset has to
            # be constant in the each axis so the tool will have some material
            # to cut and not create chattering" - a rubbing pass chatters and
            # leaves a worse surface than the one it was sent to improve.
            #
            # So both numbers gain the 0.254 pre-finish offset this project
            # carries, and the ISOTROPIC one is the tighter test of the two:
            # it is the case where a radial-only allowance looks right.
            PF = 0.254
            check('roughing leaves the AXIAL allowance on a wall, plus the '
                  'pre-finish',
                  ani is not None and abs(ani - (2.0 + PF)) < 0.05,
                  'the deepest level stops %.4f from the Z-70.4 wall, expected '
                  '%.4f - the axial value plus the pre-finish allowance'
                  % (ani if ani is not None else -1, 2.0 + PF))
            check('   and the isotropic case leaves it too',
                  iso is not None and abs(iso - (0.508 + PF)) < 0.05,
                  'stops %.4f, expected %.4f - a stop on the finish offset '
                  'alone leaves the pre-finish pass nothing to cut in Z'
                  % (iso if iso is not None else -1, 0.508 + PF))

            base = gen('base', [])
            offb = gen('sep_off', ['polyline:param_f_off_z=0.1'])
            on = gen('sep_on', ['polyline:param_f_off_sep=1',
                                'polyline:param_f_off_z=0.1'])
            check('the project generates all three ways',
                  base and offb and on)
            if base and offb and on:
                check('the switch OFF changes nothing, whatever Z holds',
                      base == offb,
                      '%d values differ' % sum(1 for a, b in zip(base, offb)
                                               if abs(a - b) > 1e-9))
                check('the switch ON moves the stop contour', base != on,
                      'the table is identical - the axial value never '
                      'reached the machine')
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for x in FAILED:
            print('   -', x)
        sys.exit(1)
    print('Radial on the diameters, axial on the walls, blended between.')


if __name__ == '__main__':
    main()
