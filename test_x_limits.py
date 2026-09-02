#!/usr/bin/env python3
# coding: utf-8
"""The radial limits: a datum against the stock, and edge vs contact point.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHAT THESE ARE

Gaps 10 and 14 from `POLYLINE-GAPS.md`, the scan against a reference CAM
package's Profile Roughing operation.

  * **14** - a diameter limit was a number and nothing else. The reference
    gives each one a datum, but its datums point at solid geometry we do not
    have; OUR real object is the Workpiece, so Start/Final Diameter can now be
    an OFFSET from its Stock OD or Stock ID. Same vocabulary
    `cfg/lathe/facing.cfg` already uses, borrowed rather than reinvented.
  * **10** - every limit we have is on the CONTROL POINT, so a diameter could
    not say whether it meant where the cutting EDGE stops or where the nose
    TOUCHES. They differ by exactly the nose radius.

Both resolve in one place, `x_limit_abs`, because they are two adjustments to
the same number and applying them separately would let them disagree.

WHAT IS ASSERTED

1. THE ARITHMETIC, as units. Datum 0 is the value untouched; 1 and 2 offset
   from the published stock diameters; with no Workpiece both fall back to the
   value as written. Contact point shifts by one nose radius - in DIAMETER
   terms, so nose_r * DIAMETER_MODE - outward on OD and inward in a bore.

2. DEFAULTS CHANGE NOTHING. Datum 0 and Cutting edge are what these parameters
   have always meant, so the emitted limit must equal the project's own
   parameter to the last digit. Every saved project keeps the toolpath it has.

3. EACH SETTING ACTUALLY MOVES THE TOOLPATH. This is the one that matters and
   it is not decoration: the first working version shifted the emitted
   `_pl_b_x` from 70.0 to 70.8 and left the motion **byte-identical**, because
   the five internal consumers called the resolver with `nose_r` defaulted to
   0 and never saw the shift. A limit that resolves and changes nothing is
   the `Retract = Minimal` failure again - a setting that ships doing nothing.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_sections as ls  # noqa: E402

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


class FakeParam(object):
    def __init__(self, v):
        self.v = v

    def get_ngc_value(self):
        return self.v


class FakeFeature(object):
    """Only what x_limit_abs asks for - it takes a Feature and reads params."""

    def __init__(self, **kw):
        self.p = {k: FakeParam(v) for k, v in kw.items()}

    def get_param(self, name):
        return self.p.get(name)


def unit_tests():
    od, wid, nose = ls.WORKPIECE_OD, ls.WORKPIECE_ID, ls.TOOL_NOSE_R
    try:
        ls.WORKPIECE_OD, ls.WORKPIECE_ID, ls.TOOL_NOSE_R = 50.0, 20.0, 0.4
        dm = ls.DIAMETER_MODE

        f = FakeFeature(param_b_x=30.0, param_e_x=10.0)
        check('datum 0 leaves the value alone',
              ls.x_limit_abs(f, 'begin') == 30.0,
              str(ls.x_limit_abs(f, 'begin')))

        f = FakeFeature(param_b_x=0.0, param_b_x_dat=1.0)
        check('Stock OD with offset 0 is the bar itself',
              ls.x_limit_abs(f, 'begin') == 50.0)
        f = FakeFeature(param_b_x=-2.0, param_b_x_dat=1.0)
        check('   and a negative offset comes IN from the OD',
              ls.x_limit_abs(f, 'begin') == 48.0)
        f = FakeFeature(param_b_x=0.0, param_b_x_dat=2.0)
        check('Stock ID with offset 0 is the bore',
              ls.x_limit_abs(f, 'begin') == 20.0)

        # contact point: a DIAMETER moves by twice the radius
        f = FakeFeature(param_b_x=30.0, param_x_limit=1.0, param_side=0.0)
        check('contact point moves an OD limit OUT by one nose radius',
              abs(ls.x_limit_abs(f, 'begin') - (30.0 + 0.4 * dm)) < 1e-9,
              str(ls.x_limit_abs(f, 'begin')))
        f = FakeFeature(param_b_x=30.0, param_x_limit=1.0, param_side=1.0)
        check('   and an ID limit IN by the same, material being outboard',
              abs(ls.x_limit_abs(f, 'begin') - (30.0 - 0.4 * dm)) < 1e-9)
        f = FakeFeature(param_b_x=30.0, param_x_limit=1.0, param_side=0.0)
        check('   and an explicit 0 nose radius shifts nothing',
              ls.x_limit_abs(f, 'begin', 0.0) == 30.0)
        check('   and x_stock_ref ignores the tool reference entirely',
              ls.x_stock_ref(f, 'begin') == 30.0,
              str(ls.x_stock_ref(f, 'begin')))
        f = FakeFeature(param_b_x=-2.0, param_b_x_dat=1.0, param_x_limit=1.0,
                        param_side=0.0)
        check('   but x_stock_ref still takes the DATUM',
              ls.x_stock_ref(f, 'begin') == 48.0,
              str(ls.x_stock_ref(f, 'begin')))

        # no Workpiece - fall back to the value, and say so
        ls.WORKPIECE_OD = ls.WORKPIECE_ID = None
        f = FakeFeature(param_b_x=30.0, param_b_x_dat=1.0)
        check('with no Workpiece the datum falls back to the value',
              ls.x_limit_abs(f, 'begin') == 30.0)
        check('   and the program is told so',
              'WARNING' in ls.build_x_limit_note(f))
        f = FakeFeature(param_b_x=30.0)
        check('   and a plain value warns about nothing',
              ls.build_x_limit_note(f) == '')
    finally:
        ls.WORKPIECE_OD, ls.WORKPIECE_ID, ls.TOOL_NOSE_R = od, wid, nose


def run(project, sets, tag, d):
    out = os.path.join(d, tag + '.ngc')
    cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
           '--out', out, '--config-copy']
    for kv in sets:
        cmd += ['--set', kv]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(out):
        return None, None
    src = open(out).read()
    bx = re.findall(r'#<_pl_b_x> = ([-\d.]+)', src)
    import ncam_preview as P
    tp = P.parse_program(out, INI)
    if tp.error:
        return None, None
    mv = ['%.5f %.5f %.5f %.5f %s' % (m.a[2], m.a[0], m.b[2], m.b[0], m.kind)
          for m in tp.moves if m.op == 'Lathe Polyline']
    return (float(bx[-1]) if bx else None,
            hashlib.md5('\n'.join(mv).encode()).hexdigest()[:12])


def main():
    unit_tests()
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        d = tempfile.mkdtemp(prefix='xlim_')
        try:
            for project, own_bx in (('testing_15_9.xml', 70.0),
                                    ('testing_15_2.xml', 60.0)):
                base_bx, base_h = run(project, [], project[:-4] + '_b', d)
                check('%s generates' % project, base_bx is not None)
                if base_bx is None:
                    continue
                # 2. DEFAULTS CHANGE NOTHING
                check('   %s: the default limit is the parameter itself'
                      % project, abs(base_bx - own_bx) < 1e-6,
                      '%.4f against %.4f' % (base_bx, own_bx))
                # 3. EACH SETTING MOVES THE TOOLPATH
                # THE DATUM MOVES THE ORIGIN, THE TOOL REFERENCE DOES NOT.
                # greatEndian, 2026-09-02: "origin should stay put, only the
                # ladder bound moves". param_b_x is the Begin limit AND where
                # the profile starts; "start at the stock OD" has to carry the
                # origin with it, while "the limit means where the nose
                # touches" is about the cut alone. _pl_b_x is the origin, so
                # the two settings must show up differently in it.
                for label, sets, want_bx in (
                        ('datum Stock OD', ['polyline:param_b_x_dat=1'],
                         'moves'),
                        ('contact point', ['polyline:param_x_limit=1'],
                         'stays')):
                    bx, h = run(project, sets, project[:-4] + label[:5], d)
                    check('   %s: %s generates' % (project, label),
                          bx is not None)
                    if bx is None:
                        continue
                    if want_bx == 'stays':
                        check('   %s: %s leaves the ORIGIN where it was'
                              % (project, label), abs(bx - own_bx) < 1e-6,
                              'origin moved to %.4f - contact point must only '
                              'move the cut limit' % bx)
                    else:
                        check('   %s: %s moves the origin with it'
                              % (project, label), abs(bx - own_bx) > 1e-6,
                              'origin unchanged at %.4f' % bx)
                    # ...and both must reach the toolpath. A setting that
                    # resolves and changes no motion is the failure this test
                    # exists for - see the docstring.
                    check('   %s: %s MOVES the toolpath'
                          % (project, label), h != base_h,
                          'byte-identical motion - the limit resolves but '
                          'nothing consumes it')
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Radial limits carry a datum, and point where they say they point.')


if __name__ == '__main__':
    main()
