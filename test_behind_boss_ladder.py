#!/usr/bin/env python3
# coding: utf-8
"""The roughing ladder behind a boss must taper out, not stop partway down.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, 2026-08-12: on testing_15_6 the last passes behind the boss are
missing, while testing_15_5 is right. The two projects have IDENTICAL geometry -
raw and reachable profiles match point for point - and differ only in
parameters, the significant one being the pre-finish offset: 0.254 mm on 15_5
against 1.000 mm on 15_6.

WHAT WENT WRONG. `resume_envelope`'s crossing test is strict at a segment's
lower end (`px >= lev > cx`), so a descending segment never yields a breakpoint
at its OWN bottom - it can only get one from a LATER segment that descends past
it. Behind a boss the back-angle shadow collapses the whole region into ONE long
taper, and nothing comes after it, so the envelope stopped partway down.

On testing_15_6 that taper is a single segment, Z-36.1330 X33.7997 to Z-68.8918
X26.2368. The envelope's lowest breakpoint was 27.2313 - a vertex radius from
elsewhere on the profile, crossing the taper at Z-64.5839 - and the two levels
below it, 27.1120 and 26.6040, fell outside the table. The walker's
out-of-range fallback returns the LAST breakpoint's Z, where the floor is
27.2313, so both levels were judged inside the part and cut nothing.

testing_15_5 escaped only by luck: its lowest breakpoint, 25.5146, happens to
sit near its own taper end at 25.2989, so the levels that fell outside had
nothing to cut anyway.

THE INVARIANT, and why it is this one. "Are levels 27.1120 and 26.6040 present"
needs those exact numbers and holds for one project. What holds everywhere is
that a ladder ENDS BY RUNNING OUT OF MATERIAL: the last, shortest pass behind
the boss must be shorter than one step of the ladder. If it is longer, the next
level down still had a real cut in front of it and the ladder was truncated -
which is exactly the shape of this bug, on any project and any offset.
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
BOSS_BACK = -33.5           # everything behind this is the region under test
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def behind_boss(project):
    """The behind-boss level cuts as [(radius, z_from, z_to)], deepest last."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='bbl_')
    try:
        out = os.path.join(d, 'o.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project', project,
                        '--out', out, '--config-copy',
                        '--set', 'polyline:param_sectioning=0'],
                       capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid']
        lv = [m for m in mv if abs(m.b[0] - m.a[0]) < 1e-6
              and abs(m.b[2] - m.a[2]) > 1e-6]
        beh = [(m.a[0], max(m.a[2], m.b[2]), min(m.a[2], m.b[2]))
               for m in lv if max(m.a[2], m.b[2]) < BOSS_BACK]
        return sorted(beh, key=lambda r: -r[0])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def unit_envelope():
    """resume_envelope must reach the bottom of the last descent."""
    import lathe_sections as L
    # a boss, then ONE long taper down - the shape the back-angle shadow makes
    contour = [(2.0, 20.0), (-10.0, 20.0), (-12.0, 34.0), (-14.0, 34.0),
               (-36.0, 33.8), (-68.0, 26.2), (-68.0, 35.0)]
    env = L.resume_envelope(contour, 1, lead_z=0.707, rough_cut=0.508)
    check('the envelope reaches the bottom of the last descent',
          bool(env) and abs(env[-1][0] - 26.2) < 1e-6,
          'lowest breakpoint is %.4f, the taper ends at 26.2000 - levels '
          'between the two get the walker out-of-range fallback and cut '
          'nothing' % (env[-1][0] if env else -1))
    check('   and its resume Z is the taper end, not an earlier crossing',
          bool(env) and abs(env[-1][1] - (-68.0)) < 1e-6,
          'Z%.4f, expected Z-68.0000' % (env[-1][1] if env else 0))
    check('   levels still descend and resume monotonically',
          all(env[i][0] > env[i + 1][0] and env[i + 1][1] <= env[i][1] + 1e-9
              for i in range(len(env) - 1)), repr(env))


def main():
    unit_envelope()

    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        for project in ('testing_15_5.xml', 'testing_15_6.xml'):
            beh = behind_boss(project)
            check('%s generates and cuts behind the boss' % project,
                  bool(beh) and len(beh) > 3,
                  '%s passes' % (len(beh) if beh else 'no'))
            if not beh or len(beh) < 3:
                continue
            steps = [abs(beh[i + 1][1] - beh[i][1]) for i in range(len(beh) - 1)]
            step = max(steps)
            last_len = abs(beh[-1][1] - beh[-1][2])
            print('      %s  %d passes, deepest r%.4f, last cut %.4f mm, '
                  'step %.4f' % (project, len(beh), beh[-1][0], last_len, step))

            # THE INVARIANT: the ladder ends by running out of material.
            check('   %s the ladder tapers out instead of stopping short'
                  % project, last_len < step,
                  'the last pass still cuts %.4f mm, more than the %.4f step - '
                  'the next level down had a real cut left and the ladder was '
                  'truncated' % (last_len, step))

            # and it is a LADDER - no level skipped in the middle
            rads = [r for r, _a, _b in beh]
            gaps = [rads[i] - rads[i + 1] for i in range(len(rads) - 1)]
            check('   %s no level is skipped inside the ladder' % project,
                  max(gaps) - min(gaps) < 1e-3,
                  'radius steps run %.4f .. %.4f' % (min(gaps), max(gaps)))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The behind-boss ladder runs out of material rather than stopping.')


if __name__ == '__main__':
    main()
