#!/usr/bin/env python3
# coding: utf-8
"""Checks the tool flank shadow in lathe_sections.py.

Standalone, like the other test_*.py here - run it directly, no pytest. Pure
geometry, so it needs no rs274 and runs instantly.

The property under test is the one photo/spaceBehindIssue_0.png shows going
wrong: behind a raised boss the reachable floor is not the profile, it is a
ramp leaving the boss corner at the tool's flank angle. Getting the sign or the
trig wrong here does not crash anything - it silently either gouges the boss or
leaves a step of uncut material - so every case checks a computed number, not
just that a list came back.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lathe_sections as ls  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def at(env, z):
    """Envelope radius at a Z, by interpolation."""
    return ls._interpolate_x(env, z)


def main():
    # --- the angles the tool table actually carries -------------------------
    # every demo tool's I/J bisect to its CL angle; that is the consistency
    # check that says the two flanks and the orientation are one set
    for i, j, cl in ((105, 165, 135), (15, 75, 45), (285, 345, 315), (195, 255, 225)):
        check('I%d J%d bisects to CL %d' % (i, j, cl), abs((i + j) / 2.0 - cl) < 1e-9)

    # --- the limiting flank -------------------------------------------------
    # BACK is the trailing flank and the one that fouls a wall already driven
    # past, so it is the column this uses. T2 is J75.
    check('a back flank facing out gives a ray', len(ls.flank_directions(75)) == 1)
    check('a back flank facing inward gives none', len(ls.flank_directions(255)) == 0)

    # --- the shape itself ---------------------------------------------------
    # a boss at r20 from Z0 to Z-10, then a valley floor at r10 out to Z-40
    prof = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 10.0), (-40.0, 10.0)]

    # prof is in DIAMETERS, so a D20 boss over a D10 floor is 5 mm of radius.
    # A 45 degree flank rises 1 mm of radius per 1 mm of Z, so it takes 5 mm to
    # come back down to the floor - not 10.
    env = ls.flank_envelope(prof, 45.0)
    check('at the boss the envelope is the boss', abs(at(env, -10.0) - 20.0) < 0.05,
          'r%.3f' % at(env, -10.0))
    for dz, want in ((2.0, 16.0), (5.0, 10.0), (8.0, 10.0), (15.0, 10.0)):
        got = at(env, -10.0 - dz)
        check('%4.1f mm behind the boss the 45 deg flank allows r%.1f' % (dz, want),
              abs(got - want) < 0.06, 'got r%.3f' % got)

    # never below the true profile, anywhere
    below = [(z, r) for z, r in env
             if (ls._interpolate_x(prof, z) or 0) - r > 1e-6]
    check('the envelope never dips below the profile', not below, str(below[:3]))

    # --- the angle actually changes the ramp --------------------------------
    # a steeper flank gets closer to the boss: 75 degrees rises at tan(75), so
    # it recovers the floor in 10/tan(75) = 2.68 mm instead of 10
    env75 = ls.flank_envelope(prof, 75.0)
    reach = 5.0 / math.tan(math.radians(75.0))
    check('a 75 deg flank recovers the floor in %.2f mm' % reach,
          abs(at(env75, -10.0 - reach) - 10.0) < 0.06,
          'r%.3f at Z%.3f' % (at(env75, -10.0 - reach), -10.0 - reach))
    check('the steeper flank is never more restrictive than the shallow one',
          all(at(env75, z) <= at(env, z) + 1e-6 for z, _ in env75))

    # --- a vertical flank constrains nothing --------------------------------
    envv = ls.flank_envelope(prof, 90.0)
    check('a vertical flank leaves the profile alone', envv == prof, str(envv[:3]))

    # --- both sides bind at once, which is why travel direction drops out ---
    # a valley between two bosses: each wall casts its own ramp inward
    vee = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 8.0), (-30.0, 8.0),
           (-30.0, 20.0), (-40.0, 20.0)]
    envb = ls.flank_envelope(vee, 45.0)
    # 4 mm past a 12 mm wall on a 1:1 flank the tool is still 12 - 4 = 8 above
    # the floor, i.e. r16 - that is the whole point of the shadow
    check('the near wall ramps in at the flank angle',
          abs(at(envb, -14.0) - 12.0) < 0.06, 'D%.3f' % at(envb, -14.0))
    # only the back flank binds, so the far wall - which the tool drives away
    # from, not past - casts no shadow of its own
    check('the far wall casts no shadow, only the near one does',
          abs(at(envb, -26.0) - 8.0) < 0.06, 'r%.3f at Z-26' % at(envb, -26.0))
    check('6 mm past the near wall the floor is reached',
          abs(at(envb, -16.0) - 8.0) < 0.06, 'D%.3f' % at(envb, -16.0))

    # a narrow valley cannot be reached to the bottom at all
    narrow = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 8.0), (-14.0, 8.0),
              (-14.0, 20.0), (-24.0, 20.0)]
    envn = ls.flank_envelope(narrow, 45.0)
    check('a valley narrower than the shadow cannot be bottomed out',
          at(envn, -12.0) > 8.0 + 0.5,
          'deepest reachable D%.3f against a true floor of D8' % at(envn, -12.0))

    # the result is breakpoints, not a sampled curve - it has to fit in a
    # record array, and every point costs eight numbered parameters
    check('the envelope stays compact', len(env) <= 8, '%d points' % len(env))

    # --- degenerate input is handled, not crashed ---------------------------
    check('an empty profile returns empty', ls.flank_envelope([], 45.0) == [])
    check('a single point is returned unchanged',
          ls.flank_envelope([(0.0, 10.0)], 45.0) == [(0.0, 10.0)])

    # --- the emitted ramp must measure the tool's own back angle ------------
    # points are diameters and a flank slope is rise-in-radius per unit Z; if
    # that is not accounted for the ramp comes out at half the angle, which is
    # exactly what testing_15_0 showed - a 75 degree tool ramping at 61.8
    for ang in (75.0, 60.0, 45.0, 30.0):
        e = sorted(ls.flank_envelope([(0.0, 40.0), (-10.0, 40.0),
                                      (-10.0, 20.0), (-40.0, 20.0)], ang))
        got = None
        for (z0, r0), (z1, r1) in zip(e, e[1:]):
            if abs(z1 - z0) > 1e-9 and abs(r1 - r0) > 1e-9:
                got = math.degrees(math.atan(abs((r1 - r0) / 2.0 / (z1 - z0))))
        check('a %.0f deg back angle ramps at %.0f deg' % (ang, ang),
              got is not None and abs(got - ang) < 0.01,
              'measured %.2f deg' % got if got else 'no ramp found')

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All flank envelope tests passed.')


if __name__ == '__main__':
    main()
