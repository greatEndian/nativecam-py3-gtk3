#!/usr/bin/env python3
# coding: utf-8
"""Where a profile doubles back under itself, said as a property of the shape.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, 2026-08-13, on gaps 7 and 11 (Machine Undercuts / Groove
Suppression): *"here we will use knowledge from cutting behind the boss element
or Xlevel of segmeng -1 is less than Xactive or Xsegment - 2"*.

That rule, in our terms: walking in cut order, a region is re-entrant where an
earlier segment's radius lies below the running maximum - the profile has come
back up, so what lies between is a pocket reachable only from outside.

WHAT THIS IS NOT. It is not a second detector beside a working one. The
disjoint-interval machinery already acts on exactly this knowledge; `reentrant_spans`
states it as a property of the profile so code can ask WHERE the pockets are
without re-deriving it from a scan's state. The cross-check below is what makes
that claim checkable rather than asserted: on testing_15_5 the rule reports
Z-34.4..-69.6, and that is the span whose roughing arrives as disjoint intervals
- a figure established over several days of work on that exact geometry.

AND IT IS DELIBERATELY NOT A WARNING. Every 15_x and 9_x demo project has a
pocket, because that is what those parts are. Telling an operator "this profile
is re-entrant" would fire on nearly every job and train them to ignore it - the
same trap the leading-flank survey was held back from. What an operator needs to
know is whether the tool can REACH, and the two flank warnings already say that.
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
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def generate(project):
    """-> (floor contour points in radius, roughing level moves) or None."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='reent_')
    try:
        out = os.path.join(d, 'o.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project', project,
                        '--out', out, '--config-copy'],
                       capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        s = open(out).read()
        v = {}
        for q in re.finditer(r'#(\d{4}) = (-?[0-9.]+)', s):
            v[int(q.group(1))] = float(q.group(2))
        m = re.findall(r'#<_pl_flc_n>\s*=\s*(\d+)\s*$', s, re.M)
        if not m:
            return None
        n = max(int(x) for x in m)
        pts = [(v.get(3700 + i * 2), v.get(3700 + i * 2 + 1)) for i in range(n)]
        pts = [p for p in pts if None not in p]
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid']
        lv = [m for m in mv if abs(m.b[0] - m.a[0]) < 1e-6
              and abs(m.b[2] - m.a[2]) > 1e-6]
        return pts, lv
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    import lathe_sections as L

    # --- the rule, on shapes whose answer is known ------------------------
    rising = [(0.0, 20.0), (-10.0, 20.0), (-20.0, 30.0), (-30.0, 30.0)]
    check('a profile that only rises has no pocket',
          L.reentrant_spans(rising) == [], repr(L.reentrant_spans(rising)))

    falling = [(0.0, 30.0), (-10.0, 30.0), (-20.0, 20.0), (-30.0, 20.0)]
    check('   nor does one that only falls', L.reentrant_spans(falling) == [],
          'a step DOWN is cut from outside and is not a pocket: %r'
          % L.reentrant_spans(falling))

    groove = [(0.0, 30.0), (-10.0, 30.0), (-10.1, 20.0), (-14.0, 20.0),
              (-14.1, 30.0), (-25.0, 30.0)]
    g = L.reentrant_spans(groove)
    check('a groove is one pocket, of the right depth',
          len(g) == 1 and abs(g[0][2] - 10.0) < 1e-6, repr(g))
    check('   spanning the groove and not the whole part',
          len(g) == 1 and g[0][0] <= -10.0 and g[0][1] >= -14.2, repr(g))

    two = groove + [(-30.0, 22.0), (-34.0, 22.0), (-34.1, 30.0), (-40.0, 30.0)]
    check('two grooves are two pockets', len(L.reentrant_spans(two)) == 2,
          repr(L.reentrant_spans(two)))

    check('a profile too short to double back is empty',
          L.reentrant_spans([(0.0, 20.0), (-5.0, 20.0)]) == [])

    # --- THE CROSS-CHECK: does the rule agree with the machinery? ---------
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        got = generate('testing_15_5.xml')
        check('testing_15_5 generates', got is not None)
        if got is not None:
            pts, lv = got
            spans = L.reentrant_spans(pts)
            check('the rule finds the pocket behind the boss', len(spans) == 1,
                  repr(spans))
            if spans:
                z0, z1, depth = spans[0]
                print('      pocket Z%.1f..%.1f, %.2f mm deep' % (z0, z1, depth))
                # every level cut lying wholly inside the pocket is a pass that
                # could only be reached as a DISJOINT interval - if the rule
                # named the wrong span there would be none
                inside = [m for m in lv
                          if max(m.a[2], m.b[2]) < z0 - 0.5
                          and min(m.a[2], m.b[2]) > z1 - 0.5]
                check('   and roughing does arrive there as separate passes',
                      len(inside) > 5,
                      'only %d level cuts inside the span the rule named - the '
                      'rule and the machinery disagree about where the pocket '
                      'is' % len(inside))
                print('      %d roughing passes lie inside it' % len(inside))

        flat = generate('testing_2.xml')
        if flat is not None:
            check('   while a plain profile reports no pocket at all',
                  L.reentrant_spans(flat[0]) == [],
                  repr(L.reentrant_spans(flat[0])))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The rule names the pockets, and agrees with what roughing does.')


if __name__ == '__main__':
    main()
