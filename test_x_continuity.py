#!/usr/bin/env python3
# coding: utf-8
"""No two roughing levels that cut the same ground may be more than one depth
of cut apart.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian's idea, 2026-08-12: remember the last X of a horizontal pass and
compare it with the next one; any step that is not one depth of cut is a missing
pass. This is that check, with one correction the measurements forced.

WHY NOT `step == doc`. With `Space passes from = Final contour` the ladder is
anchored on the floor, so the TOP step of a region is a remainder - 0.4682 and
0.4671 against a 0.5080 depth of cut on testing_15_6, both legitimate. Asserting
equality reports those as faults. What a missing pass actually does is make a
step BIGGER: the level that should have been there is absent and the next one
down takes its work, so the step doubles. Before the fix in analysis/036 the
step across the dome was 0.9363 = 2 x 0.4682, and every other step was under a
depth of cut. So the invariant is one-sided:

    no step DOWN to a level cutting the same ground may exceed one depth of cut

WHY "THE SAME GROUND" AND NOT SIMPLY THE NEXT LEVEL. A level is split into
disjoint intervals wherever a feature blocks it, and the ladder in front of a
dome is a different ladder from the one behind it - they interleave in X and
comparing them pairwise is meaningless. greatEndian's own framing was about
comparing across a region boundary, which is exactly the case that matters:
each pass is therefore matched against the next pass DOWN that overlaps it in
Z, so the region a pass belongs to is discovered from the geometry rather than
declared. That also covers the sectioned case he raised, where a section may
re-anchor its ladder instead of continuing the previous sequence - a re-anchor
that skips a pass shows up here as an over-large step, whatever caused it.

A pass with nothing below it overlapping is the deepest of its region and is
not a fault; `test_behind_boss_ladder` covers how a ladder is allowed to end.
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
PROJECTS = ('testing_15_5.xml', 'testing_15_6.xml')

# Two passes count as cutting the same ground when their Z spans overlap by at
# least this much. Small enough that a genuine neighbour always qualifies, large
# enough that two ladders merely touching at a feature edge do not.
MIN_OVERLAP = 1.0
TOL = 0.02
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def passes_of(project, sets=()):
    """-> (list of (X, zhi, zlo) level cuts, depth of cut) or (None, None)."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='xcont_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
               '--out', out, '--config-copy']
        for kv in sets:
            cmd += ['--set', kv]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None, None
        # the depth of cut the program itself used, not a guess
        txt = open(out).read()
        m = re.findall(r'#<_rough_cut>\s*=\s*([0-9.]+)', txt)
        doc = float(m[-1]) if m else None
        tp = P.parse_program(out, INI)
        if tp.error or doc is None:
            return None, None
        # ROUGHING ONLY. The pre-finish and finish passes are constant-X
        # feeds too, and sweeping them in makes the ladder look as if it has a
        # doubled step: on testing_15_6 they appear at X20.5080 (final 20.0 +
        # the 0.508 finish offset) and X20.0000, so the last roughing level at
        # X21.5240 seemed to be 1.0160 above its neighbour. They are not part
        # of the ladder. test_rough_comp separates them the same way.
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid' and not m.subs]
        lv = [m for m in mv if abs(m.b[0] - m.a[0]) < 1e-6
              and abs(m.b[2] - m.a[2]) > 1e-6]
        return [(m.a[0], max(m.a[2], m.b[2]), min(m.a[2], m.b[2]))
                for m in lv], doc
    finally:
        shutil.rmtree(d, ignore_errors=True)


def over_steps(cuts, doc, step_z=0.25):
    """Every place along Z where consecutive levels are more than doc apart.

    THE COMPARISON HAS TO BE POSITIONAL, not pass-to-pass. A first attempt
    matched each pass with the next one DOWN whose Z span overlapped it, and it
    could not see the very bug it was built for: on testing_15_6 the full-length
    pass at X34.5318 overlaps X34.0636 IN FRONT of the dome, so 34.0636 was
    taken as its neighbour and the gap BEHIND the dome - where 34.0636 does not
    cut at all and the next level is 33.5955, 0.9363 away - was never examined.
    It reported a worst step of 0.0000 on a program with a missing pass.

    So walk Z instead: at each station take the levels that actually cut there,
    sort them, and check consecutive gaps. A level absent over a stretch of the
    part shows up exactly where it is absent.
    """
    if not cuts:
        return []
    zhi = max(c[1] for c in cuts)
    zlo = min(c[2] for c in cuts)
    worst = {}
    z = zhi
    while z >= zlo:
        here = sorted((c[0] for c in cuts if c[2] - 1e-9 <= z <= c[1] + 1e-9),
                      reverse=True)
        for a, b in zip(here, here[1:]):
            if a - b > doc + TOL:
                key = (round(a, 4), round(b, 4))
                if key not in worst or z > worst[key][1]:
                    worst[key] = (a - b, z)
        z -= step_z
    return sorted(((a, b, gap, zz) for (a, b), (gap, zz) in worst.items()),
                  key=lambda r: -r[2])


def report(tag, cuts, doc):
    bad = over_steps(cuts, doc)
    print('      %-34s %3d passes, doc %.4f, worst gap %.4f'
          % (tag, len(cuts), doc, max([b[2] for b in bad], default=0.0)))
    for a, b, gap, zz in bad[:4]:
        print('         X%9.4f -> X%9.4f  gap %.4f  first seen at Z%.4f'
              % (a, b, gap, zz))
    return bad


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    # BOTH ROUGHING DIRECTIONS. Back to front had never been asked to pass
    # this - or anything else - and it did not: until analysis/054 it swept the
    # REVERSED record array and came out a different decomposition, 40 level
    # cuts against front to back's 45 on testing_15_6 with one in common. It
    # now emits the same cuts in the reverse order, so the same invariant has
    # to hold, and a regression that only shows up one way round is caught.
    for project in PROJECTS:
        for tag, sets in (('sect off f2b', ('polyline:param_sectioning=0',
                                            'polyline:param_dir=0')),
                          ('sect ON  f2b', ('polyline:param_sectioning=1',
                                            'polyline:param_dir=0')),
                          ('sect off b2f', ('polyline:param_sectioning=0',
                                            'polyline:param_dir=1')),
                          ('sect ON  b2f', ('polyline:param_sectioning=1',
                                            'polyline:param_dir=1')),
                          # BOTH DIRECTIONS, added 2026-08-18. Never generated
                          # here before, which is how it survived unimplemented:
                          # it was a strict SUBSET of front to back's cuts - 28
                          # of 44 on testing_15_6 - so the step down across the
                          # missing behind-boss levels was 7.49 mm where the
                          # depth of cut is 0.508. This check is precisely the
                          # one that would have said so. See analysis/060.
                          ('sect off alt', ('polyline:param_sectioning=0',
                                            'polyline:param_dir=2')),
                          ('sect ON  alt', ('polyline:param_sectioning=1',
                                            'polyline:param_dir=2'))):
            cuts, doc = passes_of(project, sets)
            check('%s %s generates' % (project, tag), cuts is not None)
            if cuts is None:
                continue
            bad = report('%s %s' % (project, tag), cuts, doc)
            check('   %s %s every step down is at most one depth of cut'
                  % (project, tag), not bad,
                  '%d gap(s) exceed %.4f - the largest is X%.4f to X%.4f, '
                  '%.4f at Z%.4f, which is a level that should be cutting '
                  'there and is not'
                  % (len(bad), doc, bad[0][0], bad[0][1], bad[0][2], bad[0][3])
                  if bad else '')

    # A CHECK THAT CANNOT FAIL PROVES NOTHING. Drop one level from the parsed
    # program - the measurement's input, so nothing generated is touched - and
    # the step across it must be reported.
    cuts, doc = passes_of('testing_15_6.xml', ('polyline:param_sectioning=0',
                                               'polyline:param_dir=0'))
    if cuts:
        behind = sorted([c for c in cuts if c[1] < -34.0], reverse=True)
        if len(behind) >= 3:
            victim = behind[1][0]
            thinned = [c for c in cuts if abs(c[0] - victim) > 1e-9]
            bad = over_steps(thinned, doc)
            print('      CONTROL testing_15_6 without X%.4f: %d over-step(s)%s'
                  % (victim, len(bad),
                     ', worst %.4f' % bad[0][2] if bad else ''))
            check('CONTROL: deleting the X%.4f pass is DETECTED' % victim,
                  bool(bad),
                  'removing a level did not produce an over-large step - the '
                  'check cannot see a missing pass')
        else:
            check('CONTROL: enough behind-feature passes to thin', False)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every roughing level is within one depth of cut of the one above it.')


if __name__ == '__main__':
    main()
