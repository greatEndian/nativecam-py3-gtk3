#!/usr/bin/env python3
# coding: utf-8
"""z_limit_span against the two silent gaps openPoints.md records: a Z limit
that falls outside the profile entirely, and Z limits that leave too little
to machine.

Standalone, like the other test_*.py here - run it directly, no pytest.
No rs274 needed - this is pure Python, checked the same way test_sections.py
checks lathe_sections' own resolvers, with stand-in Feature/Parameter objects
just complete enough for resolve_points/z_limit_abs to run.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_sections as LS  # noqa: E402
import z_limit_span as ZS  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


# --- stand-ins, same shape as test_sections.py's --------------------------
class P(object):
    def __init__(self, v):
        self.v = v

    def get_ngc_value(self):
        return self.v


class Child(object):
    def __init__(self, kind, **params):
        self.kind = kind
        self.params = params

    def get_attr(self, a):
        return self.kind if a == 'type' else None

    def get_param(self, n):
        return P(self.params[n]) if n in self.params else None


class Poly(Child):
    """A polyline feature with two items - resolve_points never returns the
    Start Z/Start diameter origin as a point (see its own docstring), only
    the items - so with end_z=-50.0 the PROFILE ITSELF runs from its
    midpoint, Z-25.0, to Z-50.0. Long enough (25 mm) that a limit can sit
    inside it, outside it, or squeeze it thin.

    Z limits default OFF, both datums 0 (absolute), no X datum/contact-point
    shift - only what outside_profile_problems/too_little_problem read.
    """
    def __init__(self, end_z=-50.0, fr_on=0, fr_z=0.0, fr_dat=0,
                 e_on=0, e_z=0.0, e_dat=0, ext_fr=0.0, ext_bk=0.0):
        Child.__init__(
            self, 'polyline',
            param_b_z='0.0', param_b_x='40.0', param_b_x_dat='0',
            param_e_x='10.0', param_e_x_dat='0', param_x_limit='0',
            param_side='0',
            param_fr_z_on=str(fr_on), param_fr_z=str(fr_z),
            param_fr_z_dat=str(fr_dat),
            param_e_z_on=str(e_on), param_e_z=str(e_z),
            param_e_z_dat=str(e_dat),
            param_ext_fr=str(ext_fr), param_ext_bk=str(ext_bk))
        mid_z = end_z / 2.0
        self.child_features = [
            Child('poly-line-to', param_act='1', param_type='1',
                  param_x=str(25.0), param_z=str(mid_z),
                  param_m_style='0', param_m_r='0.0'),
            Child('poly-line-to', param_act='1', param_type='1',
                  param_x=str(10.0), param_z=str(end_z),
                  param_m_style='0', param_m_r='0.0')]


def main():
    # reset every module-level datum global, same as ncam_project_io.to_gcode
    # does at the start of every build - a stale value from another test
    # module run in the same process must not leak in here
    LS.WORKPIECE_FACE_Z = None
    LS.WORKPIECE_OD = None
    LS.WORKPIECE_ID = None

    # 1. NO LIMITS AT ALL - neither check has anything to say, whatever the
    #    tool geometry is, because there is nothing here for a Z limit to do
    poly = Poly()
    check('no limits: outside_profile_problems is empty',
          ZS.outside_profile_problems(poly) == [])
    check('no limits: too_little_problem is None, even with a large tool',
          ZS.too_little_problem(poly, rough_cut=2.0, nose_r=2.0) is None)

    # 2. A LIMIT OUTSIDE THE PROFILE - the profile itself runs Z-25 to Z-50
    #    (see Poly's own docstring - the origin is never a point)
    poly = Poly(end_z=-50.0, fr_on=1, fr_z=5.0)
    probs = ZS.outside_profile_problems(poly)
    check('Front Z beyond the drawn end: one problem reported',
          len(probs) == 1, 'got %r' % probs)
    if probs:
        check('   names Front Z, the typed value and the true range',
              'Front Z' in probs[0] and '5.000' in probs[0]
              and 'Z-25.000' in probs[0] and 'Z-50.000' in probs[0],
              probs[0])

    poly = Poly(end_z=-50.0, e_on=1, e_z=-100.0)
    probs = ZS.outside_profile_problems(poly)
    check('End Z beyond the drawn end: one problem reported',
          len(probs) == 1, 'got %r' % probs)
    if probs:
        check('   names End Z and the typed value',
              'End Z' in probs[0] and '-100.000' in probs[0], probs[0])

    # 3. A LIMIT INSIDE THE RAW PROFILE BUT PUSHED OUTSIDE BY THE OTHER ONE'S
    #    OWN TRIM - the case a check against the raw profile alone would miss.
    #    Front Z -40 is inside Z-25..-50 and trims the profile down to
    #    -40..-50. End Z -20 is inside the RAW range but now outside the
    #    trimmed one.
    poly = Poly(end_z=-50.0, fr_on=1, fr_z=-40.0, e_on=1, e_z=-20.0)
    probs = ZS.outside_profile_problems(poly)
    check('End Z inside the raw profile but outside the front-trimmed one: '
          'still caught', len(probs) == 1, 'got %r' % probs)
    if probs:
        check('   reports the FRONT-TRIMMED range, not the raw one',
              'End Z' in probs[0] and 'Z-50.000' in probs[0]
              and 'Z-40.000' in probs[0], probs[0])

    # 4. A FINE LIMIT - inside the profile, nothing to say
    poly = Poly(end_z=-50.0, e_on=1, e_z=-30.0)
    check('a limit well inside the profile: no outside-profile problem',
          ZS.outside_profile_problems(poly) == [])
    check('   and no too-little problem either, with a modest tool',
          ZS.too_little_problem(poly, rough_cut=0.5, nose_r=0.4) is None)

    # 5. TOO LITTLE TO MACHINE - the profile runs Z-25 to Z-50; End Z -26.0
    #    is inside it and leaves only Z-26 to Z-25, 1.0 mm. Threshold with
    #    rough_cut=0.508, nose_r=0.4 (real testing_15_5 tool numbers,
    #    analysis/250) is 2*0.4 + 0.508 = 1.308, so 1.0 mm is short of it
    poly = Poly(end_z=-50.0, e_on=1, e_z=-26.0)
    msg = ZS.too_little_problem(poly, rough_cut=0.508, nose_r=0.4)
    check('End Z -26 against a 1.308 mm need: fires', msg is not None, msg)
    if msg:
        check('   states the span, the range and the threshold',
              '1.000' in msg and 'Z-26.000' in msg and 'Z-25.000' in msg
              and '1.308' in msg, msg)

    # 6. A LOOSER LIMIT LEAVING 2.0 mm - no longer too little
    poly = Poly(end_z=-50.0, e_on=1, e_z=-27.0)
    check('End Z -27 against the same 1.308 mm need: does not fire',
          ZS.too_little_problem(poly, rough_cut=0.508, nose_r=0.4) is None)

    # 7. NEITHER TOOL NUMBER KNOWN (0.0, 0.0) - the check is a no-op, not a
    #    false positive against a tool that has not been chosen yet
    poly = Poly(end_z=-50.0, e_on=1, e_z=-1.0)
    check('unknown tool geometry (0, 0): too-little never fires',
          ZS.too_little_problem(poly, rough_cut=0.0, nose_r=0.0) is None)

    # 8. min_machinable_span itself - the two terms combine, doubled nose
    check('min_machinable_span combines 2*nose_r and rough_cut',
          abs(ZS.min_machinable_span(0.508, 0.4) - 1.308) < 1e-9)
    check('   and is 0 when neither is known',
          ZS.min_machinable_span(0.0, 0.0) == 0.0)

    # 9. THE DATUM NOTE - a Front Z measured from the workpiece face resolves
    #    to a different absolute Z than the operator typed, and the message
    #    says so rather than only showing the typed value
    LS.WORKPIECE_FACE_Z = 100.0
    poly = Poly(end_z=-50.0, fr_on=1, fr_z=200.0, fr_dat=1)
    probs = ZS.outside_profile_problems(poly)
    check('a datum-front limit that resolves outside the profile: caught',
          len(probs) == 1, 'got %r' % probs)
    if probs:
        check('   shows both the typed value and the resolved absolute Z',
              '200.000' in probs[0] and 'Z-100.000' in probs[0], probs[0])
    LS.WORKPIECE_FACE_Z = None

    # 10. z_limit_problems combines both checks
    poly = Poly(end_z=-50.0, e_on=1, e_z=-100.0)
    check('z_limit_problems reports the outside-profile case too',
          len(ZS.z_limit_problems(poly, 0.508, 0.4)) == 1)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('a Z limit outside the profile, and one leaving too little, are '
          'both caught.')


if __name__ == '__main__':
    main()
