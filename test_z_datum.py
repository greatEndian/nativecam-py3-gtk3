#!/usr/bin/env python3
# coding: utf-8
"""A Z limit can be measured from the workpiece face, not only in absolute Z.

Standalone, like the other test_*.py here - run it directly, no pytest.

The useful half of gaps 8 and 14. The reference package gives each Z limit a
datum, but its datums - Model front, Chuck front, Selection - point at solid
geometry we do not have. `POLYLINE-GAPS.md` says what survives the translation:
*"pointing at OUR OWN objects: the Workpiece's stock diameter and face Z"*.

HOW THE FACE REACHES GENERATION-TIME PYTHON, because it is not obvious and it
is the thing that had to be established before any of this could be designed:
a Feature holds only its own attributes and parameters - it has no
back-reference to the tree - and `lathe_sections` imports nothing from `ncam`
by design. So the face is PUSHED in: `to_gcode` already publishes the tool
change's values as it walks the tree, with the reason spelled out there
("features are processed in order, so by the time a later feature asks, the
nearest preceding tool change has spoken"), and the Workpiece is the first
feature of all. The same walk now sets `lathe_sections.WORKPIECE_FACE_Z`.

THE ASSERTION THAT MATTERS IS THE FIRST ONE: at the default datum the programs
must be identical. A datum is a way of SAYING where a limit is, not a change to
where it goes, and every saved project says it the old way.

THE SIGN. Datum 1 measures INTO the stock: the face is the origin and the value
is how far past it, so absolute Z is `face - value`. That is what makes the
number read the way a machinist says it - "40 from the face" - instead of as a
coordinate that happens to be negative.

testing_15_2 is used for the machine cases because it is the project `test_end_z`
established the limit numbers on - an absolute End Z of -40 reaches Z-40.6043 -
so the probe here is anchored to a figure already known to be right rather than
to one this file invented. (On testing_15_5 an End Z limit does not bite at all,
with or without this feature; that is pre-existing and not what this tests.)
"""
import hashlib
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


class P(object):
    """A parameter that answers get_ngc_value(), which is all this needs."""

    def __init__(self, v):
        self.v = v

    def get_ngc_value(self):
        return self.v


class F(object):
    def __init__(self, **kw):
        self.d = {k: P(v) for k, v in kw.items()}

    def get_param(self, n):
        return self.d.get(n)


def gen(sets):
    """-> (move count, hash of the path, back-most cutting Z) or None."""
    import ncam_preview as NP
    d = tempfile.mkdtemp(prefix='zdat_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
               '--out', out, '--config-copy']
        for kv in sets:
            cmd += ['--set', kv]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        tp = NP.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.kind != 'rapid']
        h = hashlib.sha1(repr([(round(m.a[0], 5), round(m.a[2], 5),
                                round(m.b[0], 5), round(m.b[2], 5))
                               for m in mv]).encode()).hexdigest()[:12]
        zs = [q for m in mv if m.op == 'Lathe Polyline' for q in (m.a[2], m.b[2])]
        return len(mv), h, (round(min(zs), 4) if zs else None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    import lathe_sections as L

    keep = L.WORKPIECE_FACE_Z
    try:
        L.WORKPIECE_FACE_Z = 0.0
        off = F(param_e_z_on=0, param_e_z=-40.0, param_e_z_dat=1)
        check('a limit whose switch is off resolves to nothing',
              L.z_limit_abs(off, 'end') is None)

        absol = F(param_e_z_on=1, param_e_z=-40.0, param_e_z_dat=0)
        check('datum Absolute is the value itself',
              L.z_limit_abs(absol, 'end') == -40.0)

        datum = F(param_e_z_on=1, param_e_z=40.0, param_e_z_dat=1)
        check('datum From-face is face minus the value',
              L.z_limit_abs(datum, 'end') == -40.0,
              'got %s with the face at 0.0' % L.z_limit_abs(datum, 'end'))

        L.WORKPIECE_FACE_Z = -10.0
        check('   and it FOLLOWS the face when the workpiece moves',
              L.z_limit_abs(datum, 'end') == -50.0,
              'got %s with the face at -10.0' % L.z_limit_abs(datum, 'end'))
        check('   while an absolute value does not',
              L.z_limit_abs(absol, 'end') == -40.0)

        # a project that predates the datum has no such parameter at all
        L.WORKPIECE_FACE_Z = -10.0
        old = F(param_e_z_on=1, param_e_z=-40.0)
        check('a project with no datum parameter is taken as absolute',
              L.z_limit_abs(old, 'end') == -40.0)

        L.WORKPIECE_FACE_Z = None
        check('with no Workpiece in the tree it falls back to absolute',
              L.z_limit_abs(datum, 'end') == 40.0,
              'the fallback must be the value as given, not a crash')
        check('   and the program is told so',
              'WARNING' in L.build_z_limit_note(datum))
        check('   but says nothing when no datum is asked for',
              L.build_z_limit_note(absol) == '')
    finally:
        L.WORKPIECE_FACE_Z = keep

    # ---- at the machine --------------------------------------------------
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        base = gen([])
        same = gen(['polyline:param_fr_z_dat=0', 'polyline:param_e_z_dat=0'])
        check('the project generates', base is not None and same is not None)
        if base and same:
            print('      default        %d moves, hash %s' % (base[0], base[1]))
            # THE ONE THAT MATTERS
            check('the default datum changes NOTHING - same program, move for '
                  'move', base[:2] == same[:2],
                  '%s against %s - a datum must not move a saved project'
                  % (str(same[:2]), str(base[:2])))

        a = gen(['polyline:param_e_z_on=1', 'polyline:param_e_z=-40.0'])
        d40 = gen(['polyline:param_e_z_on=1', 'polyline:param_e_z=40.0',
                   'polyline:param_e_z_dat=1'])
        moved = gen(['polyline:param_e_z_on=1', 'polyline:param_e_z=40.0',
                     'polyline:param_e_z_dat=1', 'workpiece:param_z=-10.0'])
        a_moved = gen(['polyline:param_e_z_on=1', 'polyline:param_e_z=-40.0',
                       'workpiece:param_z=-10.0'])
        if None in (a, d40, moved, a_moved):
            check('the datum cases generate', False)
        else:
            print('      absolute -40   back-most Z%.4f' % a[2])
            print('      datum face 40  back-most Z%.4f' % d40[2])
            print('      face at -10    back-most Z%.4f' % moved[2])
            check('a datum of 40 from the face IS an absolute -40',
                  d40[2] == a[2],
                  'Z%.4f against Z%.4f' % (d40[2], a[2]))
            check('   and moving the workpiece moves the limit with it',
                  abs(moved[2] - (a[2] - 10.0)) < 1e-3,
                  'Z%.4f, expected Z%.4f' % (moved[2], a[2] - 10.0))
            check('   while an absolute limit stays where it was put',
                  a_moved[2] == a[2],
                  'Z%.4f moved to Z%.4f - an absolute value followed the '
                  'workpiece, which it must never do' % (a[2], a_moved[2]))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('A Z limit can be said in absolute Z or from the face, and means the '
          'same thing.')


if __name__ == '__main__':
    main()
