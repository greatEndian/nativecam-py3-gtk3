#!/usr/bin/env python3
# coding: utf-8
"""An End Z stops the operation short of where the polyline ends.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 8 of `POLYLINE-GAPS.md`. We had a Start Z and nothing at the back, so an
operation always ran to the end of the drawn profile - no way to machine this
much of a part and leave the rest for another setup or a tool that can reach
past a chuck.

The trim happens once, in `resolve_points`, to the profile every builder reads.
The contours, the section windows, the floor ladder and the entry and stop
tables are all derived from those points, so trimming there is what keeps them
agreeing with each other.

THE ASSERTION THAT MATTERS IS THE FIRST ONE. This feature can only be safe if
a project without it is untouched, and the obvious design was not: using 0.0 as
"no limit" looks harmless until a profile starts at a POSITIVE Z, which
testing_15_2 does - it begins at Z+1.0. 0.0 then falls inside the profile and
trimmed the part down to its first millimetre: **29 roughing levels became 2**,
and the program still generated and still ran. Nothing but a move count would
have caught it. Hence the explicit switch, and hence this test asserting that
with the switch off the program is identical whatever End Z holds.
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
PROJECT = 'testing_15_2.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def main():
    import lathe_sections as L

    prof = [(0.0, 38.0), (-1.0, 40.0), (-20.0, 40.0), (-20.0, 50.0),
            (-30.0, 50.0)]

    check('a limit outside the profile does nothing',
          L.trim_to_end_z(prof, -40.0) == prof
          and L.trim_to_end_z(prof, 5.0) == prof)
    check('a limit inside it trims, and interpolates the last point',
          L.trim_to_end_z(prof, -10.0)
          == [(0.0, 38.0), (-1.0, 40.0), (-10.0, 40.0)])
    check('   the trimmed profile ends exactly ON the limit',
          abs(L.trim_to_end_z(prof, -25.0)[-1][0] + 25.0) < 1e-9,
          'ends at %.4f' % L.trim_to_end_z(prof, -25.0)[-1][0])
    check('a limit at a wall keeps the wall foot and drops the wall',
          L.trim_to_end_z(prof, -20.0)[-1] == (-20.0, 40.0))
    check('a profile that would be left with one point is not trimmed',
          L.trim_to_end_z(prof, 0.5) == prof)

    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        import ncam_preview as P
        d = tempfile.mkdtemp(prefix='end_z_')
        try:
            def run(tag, sets):
                out = os.path.join(d, tag + '.ngc')
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
                mv = [m for m in tp.moves if m.op == 'Lathe Polyline']
                lv = [m for m in mv if not m.subs and m.kind == 'feed'
                      and abs(m.b[0] - m.a[0]) < 1e-6
                      and abs(m.b[2] - m.a[2]) > 1e-6]
                zs = [q for m in mv for q in (m.a[2], m.b[2])]
                return {'moves': [(round(m.a[0], 4), round(m.a[2], 4),
                                   round(m.b[2], 4)) for m in mv],
                        'levels': len(lv), 'reach': min(zs)}

            off = run('off', [])
            off_v = run('off_v', ['polyline:param_e_z=-40.0'])
            on = run('on', ['polyline:param_e_z_on=1',
                            'polyline:param_e_z=-40.0'])
            check('the project generates all three ways',
                  off and off_v and on)
            if off and off_v and on:
                # THE ONE THAT MATTERS
                check('the switch OFF is identical whatever End Z holds',
                      off['moves'] == off_v['moves'],
                      'the profile is being trimmed with the switch off - a '
                      'saved project would silently lose part of its part')
                print('      off: %d levels, reaches Z%.3f'
                      % (off['levels'], off['reach']))
                print('      on:  %d levels, reaches Z%.3f'
                      % (on['levels'], on['reach']))
                check('the switch ON stops the operation short',
                      on['reach'] > off['reach'] + 10.0,
                      'reaches Z%.3f against Z%.3f' % (on['reach'],
                                                       off['reach']))
                check('   and it does less work, not more',
                      on['levels'] < off['levels'],
                      '%d levels against %d - trimming the part should not '
                      'add passes' % (on['levels'], off['levels']))
                # the untrimmed run must still be the whole part: this is what
                # went wrong, and a bare "off == off_v" would not have seen it
                check('   and the untrimmed run still machines the whole part',
                      off['levels'] > 20 and off['reach'] < -60.0,
                      'only %d levels reaching Z%.3f - the profile is being '
                      'trimmed when nothing asked for it'
                      % (off['levels'], off['reach']))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for x in FAILED:
            print('   -', x)
        sys.exit(1)
    print('End Z trims the profile, and only when it is switched on.')


if __name__ == '__main__':
    main()
