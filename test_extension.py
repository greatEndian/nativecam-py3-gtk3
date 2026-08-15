#!/usr/bin/env python3
# coding: utf-8
"""A tangential extension runs the cut on along the profile's own direction.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 9 of `POLYLINE-GAPS.md`. The reference package: *"Creates a tangential
extension of the geometry from the Front limit"*, front and back each with their
own length.

ALONG THE TANGENT, NOT ALONG Z, and the difference is the whole feature. On a
taper, extending "by 2 mm" in Z moves the radius too and changes the shape;
along the segment's own direction the segment simply gets longer. On a vertical
wall the two readings could not be further apart - along Z it does nothing at
all, along the tangent it runs straight up the wall.

A LENGTH IS A LENGTH IN THE Z/RADIUS PLANE, which is the bug this file was
written after. `resolve_points` carries X as a DIAMETER, so taking the tangent
in (z, x) as given makes the radial half twice its true size. A 3.0 extension of
a wall moved the surface 1.5: measured, floor contour last point 35.1657 ->
36.6657 in radius. The unit cases below assert the length in the plane it is
actually measured in, so that cannot come back.

THE FRONT EXTENSION MOVES WHERE ROUGHING STARTS, not only where the contour
begins. Extending the profile alone would leave the levels sweeping from the old
place - the same trap the front Z limit hit, recorded in analysis/025 - so
`_pl_begin_z` carries the extension too, and the end-to-end case checks the
program's front-most cutting move, not the table.
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
PROJECT = 'testing_15_5.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(sets):
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='ext_')
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
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid']
        zs = [q for m in mv for q in (m.a[2], m.b[2])]
        xs = [q for m in mv for q in (m.a[0], m.b[0])]
        return {'n': len(mv), 'front': round(max(zs), 4),
                'back': round(min(zs), 4), 'maxx': round(max(xs), 4)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    import lathe_sections as L
    D = L.DIAMETER_MODE

    prof = [(0.0, 40.0), (-1.0, 44.0), (-20.0, 44.0), (-30.0, 52.0)]
    check('both lengths zero leaves the profile alone',
          L.extend_tangent(prof, 0.0, 0.0) == prof)
    check('a profile too short to have a tangent is returned untouched',
          L.extend_tangent([(0.0, 40.0)], 1.0, 1.0) == [(0.0, 40.0)])

    # the length is measured in the Z/RADIUS plane, on both ends
    e = L.extend_tangent(prof, 2.0, 3.0)
    df = math.hypot(e[0][0] - prof[0][0], (e[0][1] - prof[0][1]) / D)
    db = math.hypot(e[-1][0] - prof[-1][0], (e[-1][1] - prof[-1][1]) / D)
    check('the front runs on by exactly its length', abs(df - 2.0) < 1e-9,
          'moved %.4f, asked 2.0' % df)
    check('the back runs on by exactly its length', abs(db - 3.0) < 1e-9,
          'moved %.4f, asked 3.0' % db)
    check('   and only the end points move',
          e[1:-1] == prof[1:-1])

    # A VERTICAL WALL is where "along Z" and "along the tangent" disagree
    # completely, and where the diameter/radius bug showed itself.
    wall = [(0.0, 40.0), (-10.0, 40.0), (-10.0, 60.0)]
    w = L.extend_tangent(wall, 0.0, 3.0)
    check('a wall extends UP THE WALL, by its length in radius',
          abs((w[-1][1] - wall[-1][1]) / D - 3.0) < 1e-9,
          'radius moved %.4f, asked 3.0' % ((w[-1][1] - wall[-1][1]) / D))
    check('   and not along Z at all', abs(w[-1][0] - wall[-1][0]) < 1e-9)

    # a 45 degree taper: neither axis alone is the answer
    taper = [(0.0, 40.0), (-10.0, 60.0)]
    t = L.extend_tangent(taper, 0.0, 3.0)
    dz = t[-1][0] - taper[-1][0]
    dr = (t[-1][1] - taper[-1][1]) / D
    check('a taper runs on along ITS OWN direction',
          abs(math.hypot(dz, dr) - 3.0) < 1e-9 and abs(dz - (-dr)) < 1e-9,
          'dz %.4f, dr %.4f' % (dz, dr))

    # ---- and at the machine ---------------------------------------------
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        off = run([])
        check('the project generates with no extension', off is not None)
        if off is not None:
            print('      off        front Z%.4f  maxX %.4f'
                  % (off['front'], off['maxx']))
            fr = run(['polyline:param_ext_fr=3.0'])
            bk = run(['polyline:param_ext_bk=3.0'])
            # BY THE EXTENSION'S Z COMPONENT, NOT ITS LENGTH. This asserted a
            # shift of 3.0 and so encoded a bug: `_pl_begin_z` was adding the
            # raw tangent length, which starts the sweep further forward than
            # the profile actually reaches - 0.88 of air on this project - and
            # is the same confusion as measuring a length in diameters. This
            # profile's first segment is 45 degrees, so 3.0 along it is
            # 3.0/sqrt(2) = 2.1213 of Z, and that is what the cut may move.
            want = 3.0 / math.sqrt(2.0)
            check('a front extension moves where CUTTING starts, by its Z '
                  'component',
                  fr is not None
                  and abs(fr['front'] - off['front'] - want) < 1e-2,
                  'front-most cut Z%.4f against Z%.4f, a shift of %.4f where '
                  '%.4f was due'
                  % (fr['front'] if fr else 0.0, off['front'],
                     (fr['front'] - off['front']) if fr else 0.0, want))
            # this project ends in a wall, so the back extension shows in X
            check('a back extension runs on up the end wall',
                  bk is not None and abs(bk['maxx'] - off['maxx'] - 3.0) < 1e-3,
                  'maxX %.4f against %.4f'
                  % (bk['maxx'] if bk else 0.0, off['maxx']))
            check('   and neither one changes the other end',
                  fr is not None and bk is not None
                  and fr['maxx'] == off['maxx']
                  and bk['front'] == off['front'])

    # ---- and ROUGHING must follow it, not only the contour passes --------
    # greatEndian, 2026-08-15: it "works only in prefinish and finish and it
    # should work for the roughing too". Three things were wrong and each has
    # its own assertion below.
    if os.path.isfile(INI) and os.path.isfile(GEN) and shutil.which('rs274'):
        def rough_front(sets):
            import ncam_preview as P
            d = tempfile.mkdtemp(prefix='extr_')
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
                mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
                      and m.kind != 'rapid']
                rgh = [m for m in mv if not m.subs]
                con = [m for m in mv if m.subs]
                lv = [m for m in rgh if abs(m.b[0] - m.a[0]) < 1e-6
                      and abs(m.b[2] - m.a[2]) > 1e-6]
                rz = [q for m in rgh for q in (m.a[2], m.b[2])]
                cz = [q for m in con for q in (m.a[2], m.b[2])]
                return (round(max(rz), 4), round(max(cz), 4),
                        len({round(m.a[0], 4) for m in lv}))
            finally:
                shutil.rmtree(d, ignore_errors=True)

        a = rough_front([])
        b = rough_front(['polyline:param_ext_fr=3.0'])
        if a and b:
            print('      no extension  roughing front Z%.4f, %d levels'
                  % (a[0], a[2]))
            print('      front 3.0     roughing front Z%.4f, %d levels'
                  % (b[0], b[2]))
            # THE ONE THAT MATTERS: roughing must reach as far as the contour
            # passes do. It used to stop 1.28 short while they ran on out.
            check('ROUGHING reaches the extension, not just the contour passes',
                  abs(b[0] - b[1]) < 0.01,
                  'roughing front Z%.4f against the contour passes\' Z%.4f'
                  % (b[0], b[1]))
            check('   and the ladder gains levels to get there',
                  b[2] > a[2],
                  '%d levels against %d - the ladder is still bounded by '
                  'Begin X / End X and ignores the extended profile'
                  % (b[2], a[2]))
            check('   and it moves at all', b[0] > a[0] + 1.0,
                  'front Z%.4f against Z%.4f' % (b[0], a[0]))


    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The cut runs on along the profile, by the length asked for.')


if __name__ == '__main__':
    main()
