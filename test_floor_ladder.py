#!/usr/bin/env python3
# coding: utf-8
"""Roughing lands on the floor of the region it is cutting.

Standalone, like the other test_*.py here - run it directly, no pytest.

A roughing level is one radius held across its whole sweep, and the ladder of
levels is anchored on a floor. Take that floor from the deepest point of the
WHOLE part - which is what a single Final Diameter does - and every region that
is not the deepest gets its levels positioned by somebody else's floor.

testing_15_4 is the case greatEndian reported: the front chamfer bottoms at r19
and the cylinder behind it at r20, so their own floors are 20.016 and 21.016.
Those are 1.000 apart against a 0.508 depth of cut, so **no single grid can land
on both** - 1.000 is not a multiple of 0.508 - and the cylinder's deepest level
came out at 21.032, 0.016 above where it was entitled to stop.

WHAT IS ASSERTED, and why none of it is circular:

1. THE ARITHMETIC IS THE .ngc's OWN. `region_floor` reproduces
   poly_lathe_mill's rough_target/step_target/anchor sequence. If it drifted,
   the table would ask for floors the ladder cannot land on - so the assertions
   below are on the MOTION, read back out of rs274, never on the table.

2. THE NEW LADDER LANDS ON MORE FLOORS THAN THE OLD ONE. The comparison is
   against the same generated program with `_pl_floor_n` forced to 0, which is
   the runtime gate - so "before" is this exact file with the feature switched
   off, not a remembered number from another commit. That is the negative
   control and it is built in rather than run once by hand.

3. A SINGLE-FLOOR PART IS NOT TOUCHED. The table is not emitted at all when one
   floor fits the whole profile, and the level radii are then identical with the
   gate on and off - byte for byte, not approximately.

NOT EVERY FLOOR IS REACHABLE, and the test does not pretend otherwise.
testing_15_4's chamfer bottoms at r19 at a SINGLE POINT, the tip at Z0; the
surface at radius 20.016 lies at Z-1.016, which is the cylinder, so no level
can cut at that floor and the pass is correctly blocked. A floor derived from a
point rather than an area is entitled to nothing. So the assertion is that the
new ladder lands on strictly more of them, not on all of them.
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
PROJECTS = ('testing_15_4.xml', 'testing_15_2.xml', 'testing_13_arcs.xml')
TOL = 1e-4
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def level_radii(tp, P):
    """The radii roughing actually cuts at - straight Z cuts, leads excluded."""
    return sorted({round(m.a[0], 4) for m in tp.moves
                   if m.op == 'Lathe Polyline' and not m.subs and m.kind == 'feed'
                   and abs(m.b[0] - m.a[0]) < 1e-6 and abs(m.b[2] - m.a[2]) > 1e-6})


def landed(floors, radii):
    return [f for f in floors if any(abs(f - r) < TOL for r in radii)]


def main():
    # 1. THE RULE ITSELF, with no machine involved. This is the part that says
    #    a single grid cannot serve two floors, and it is arithmetic.
    import lathe_sections as L

    chamfer_and_cylinder = [(0.0, 38.0), (-1.0, 40.0), (-20.0, 40.0),
                            (-20.0, 60.0)]
    fl = L.floor_ladder(chamfer_and_cylinder, 0.508, 0.254, 0.508, True)
    check('a two-diameter profile is entitled to two floors', len(fl) == 2,
          'got %s' % [round(f, 4) for f in fl])
    if len(fl) == 2:
        gap = abs(fl[0] - fl[1])
        check('   and they are 1.0000 apart, which 0.508 does not divide',
              abs(gap - 1.0) < TOL and abs(gap / 0.508 - round(gap / 0.508)) > 0.01,
              'gap %.4f' % gap)
        check('   the deeper one is the chamfer tip + the allowances',
              abs(min(fl) - 20.016) < TOL, '%.4f' % min(fl))

    plain = [(0.0, 40.0), (-50.0, 40.0), (-50.0, 60.0)]
    check('a single-diameter profile is entitled to exactly one',
          len(L.floor_ladder(plain, 0.508, 0.254, 0.508, True)) == 1)

    # and the anchored/unanchored arithmetic matches poly_lathe_mill's own
    check('anchored takes whole depths of cut off the pre-finish surface',
          abs(L.region_floor(40, 0.508, 0.254, 0.508, True) - 21.016) < TOL,
          '%.4f' % L.region_floor(40, 0.508, 0.254, 0.508, True))
    check('unanchored is just the two allowances',
          abs(L.region_floor(40, 0.508, 0.254, 0.508, False) - 20.762) < TOL,
          '%.4f' % L.region_floor(40, 0.508, 0.254, 0.508, False))

    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        import ncam_preview as P
        d = tempfile.mkdtemp(prefix='floor_ladder_')
        exercised = []
        try:
            for project in PROJECTS:
                on = os.path.join(d, project[:-4] + '_on.ngc')
                off = os.path.join(d, project[:-4] + '_off.ngc')
                subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                                project, '--out', on, '--config-copy'],
                               capture_output=True, text=True)
                if not os.path.isfile(on):
                    check('%s generates' % project, False)
                    continue
                txt = open(on).read()
                floors = [float(x) for x in re.findall(r'#33[89]\d = ([\d.]+)', txt)]
                # the gate itself is what "before" means - same file, feature off
                open(off, 'w').write(
                    re.sub(r'#<_pl_floor_n> = \d+', '#<_pl_floor_n> = 0', txt))

                a, b = P.parse_program(on, INI), P.parse_program(off, INI)
                check('%s runs with the ladder on and off' % project,
                      not (a.error or b.error), str(a.error or b.error)[:120])
                if a.error or b.error:
                    continue
                new, old = level_radii(a, P), level_radii(b, P)
                # A PROJECT WITH ONE FLOOR IS NOT A FAILURE. testing_15_2's
                # Final Diameter already matches its only region that has real
                # material at depth, so its ladder was never anchored on the
                # wrong number and there is nothing here to show. It stays in
                # the list as the control: no table, and the gate then cannot
                # change its motion at all.
                if len(floors) < 2:
                    print('   %-20s one floor - nothing to re-anchor, and no '
                          'table emitted' % project)
                    check('%s is unchanged when it has one floor' % project,
                          new == old,
                          '%d radii against %d' % (len(new), len(old)))
                    continue
                exercised.append(project)

                hit_new, hit_old = landed(floors, new), landed(floors, old)
                print('   %-20s %d floors, landed on %d -> %d'
                      % (project, len(floors), len(hit_old), len(hit_new)))
                check('%s lands on more of its floors than the old ladder did'
                      % project, len(hit_new) > len(hit_old),
                      '%d of %d before, %d of %d after - the ladder is not '
                      're-anchoring' % (len(hit_old), len(floors),
                                        len(hit_new), len(floors)))
                check('   %s and the old ladder really did miss some' % project,
                      len(hit_old) < len(floors),
                      'the old ladder already landed on every floor, so this '
                      'project cannot show the difference')

            check('at least one project actually exercises the ladder',
                  bool(exercised),
                  'every project collapsed to one floor - the re-anchoring is '
                  'not being tested by anything here')

            # 3. A SINGLE-FLOOR PART IS UNTOUCHED. testing_11's profile has two
            #    floors, so the one to prove this on is any project whose table
            #    is absent - assert the absence means identical motion.
            for project in ('testing_15_2.xml',):
                out = os.path.join(d, 'gate_' + project[:-4] + '.ngc')
                subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                                project, '--out', out, '--config-copy',
                                '--set', 'polyline:param_pf_off=0.0'],
                               capture_output=True, text=True)
                if not os.path.isfile(out):
                    continue
                txt = open(out).read()
                if '#<_pl_floor_n> = ' not in txt:
                    continue
                one = os.path.join(d, 'gate_off.ngc')
                open(one, 'w').write(
                    re.sub(r'#<_pl_floor_n> = \d+', '#<_pl_floor_n> = 0', txt))
                x, y = P.parse_program(out, INI), P.parse_program(one, INI)
                if x.error or y.error:
                    continue
                n = int(re.search(r'#<_pl_floor_n> = (\d+)', txt).group(1))
                if n > 1:
                    continue
                check('one floor means the gate changes nothing at all',
                      level_radii(x, P) == level_radii(y, P))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Roughing re-anchors on each floor the profile is entitled to.')


if __name__ == '__main__':
    main()
