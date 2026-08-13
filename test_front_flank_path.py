#!/usr/bin/env python3
# coding: utf-8
"""The finishing contour can be kept out of the leading flank's shadow.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 1 of `POLYLINE-GAPS.md`, the TOOLPATH half. `test_front_flank` covers the
warning; this covers what happens when the operator acts on it.

WHAT IT DOES. `Respect tool front angle` adds the leading flank to the same
wedge dilation the trailing flank already drives, so `finish_profile` returns a
contour that does not enter regions the front of the insert cannot reach. Every
contour, section window, ladder and table derives from `finish_profile`, so this
is the choke point of the whole operation - getting the trailing-flank version
of it right cost five stacked faults (`analysis/032`).

OFF BY DEFAULT, AND THAT IS THE FIRST ASSERTION. Switching it on changes the
part: the path stops attempting shapes the tool cannot make. That is the honest
part and also a DIFFERENT part from the one every saved project has been
producing, so it cannot arrive unasked. `Respect tool back angle` has had its
own switch since it was built, for the same reason.

WHY THE ENVELOPE IS BUILT WITH BOTH FLANKS AT ONCE rather than merging two
finished ones. A merge resamples two piecewise-linear curves onto a union of
breakpoints and manufactures corners tighter than the nose; the interpreter
refuses those outright - measured, `Straight feed in concave corner cannot be
reached by the tool without gouging` on testing_15_5. Built together, the
candidate-Z generation, the outer bound and the collinearity pruning all see
both flanks and the result is one coherent contour. THAT is why the last check
here generates and runs a program rather than only inspecting geometry: the
failure this guards against is one only the interpreter can see.
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
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(project, on=None):
    """-> (move count, hash of the whole move list) or (None, reason)."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='ffp_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
               '--out', out, '--config-copy']
        if on is not None:
            cmd += ['--set', 'polyline:param_front_flank=%d' % on]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None, 'did not generate'
        tp = P.parse_program(out, INI)
        if tp.error:
            return None, str(tp.error)[:70]
        h = hashlib.sha256()
        for m in tp.moves:
            h.update(('%s|%s|%.6f,%.6f,%.6f|%.6f,%.6f,%.6f\n'
                      % (m.op, m.kind, m.a[0], m.a[1], m.a[2],
                         m.b[0], m.b[1], m.b[2])).encode())
        return (len(tp.moves), h.hexdigest()[:12]), None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    import lathe_sections as L

    # ---- the envelope takes both flanks, and each keeps its own reach ----
    steep = [(0.0, 20.0), (-10.0, 20.0), (-10.2, 60.0), (-30.0, 60.0)]
    back_only = L.flank_envelope(steep, 75.0, 0)
    both = L.flank_envelope(steep, 75.0, 0, 0.0, 0.0, 15.0)
    check('adding the leading flank changes the envelope',
          both != back_only,
          'the front angle is being ignored where it should constrain')

    check('   and a front angle of 0 - an absent column - changes nothing',
          L.flank_envelope(steep, 75.0, 0, 0.0, 0.0, 0.0) == back_only,
          'a blank tool-table column is being read as a real 0 degree tool')
    check('   nor does None', L.flank_envelope(steep, 75.0, 0, 0.0, 0.0,
                                               None) == back_only)

    # the combined envelope must still be a sane contour: single-valued in Z
    # and ordered, because everything downstream walks it as a polyline
    zs = [z for z, _x in both]
    check('the combined envelope stays ordered in Z',
          zs == sorted(zs) or zs == sorted(zs, reverse=True),
          'a contour that doubles back cannot be walked')

    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
    elif not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
    else:
        # ---- THE ONE THAT MATTERS: the default must not move anything ----
        for proj in ('testing_15_2.xml', 'testing_15_5.xml'):
            a, ea = run(proj)                 # as saved
            b, eb = run(proj, 0)              # explicitly off
            check('%s is untouched by default' % proj[:-4],
                  a is not None and b is not None and a == b,
                  'as saved %s, explicitly off %s' % (a or ea, b or eb))
            if a:
                print('      %-18s %d moves  %s' % (proj[:-4], a[0], a[1]))

        # ---- switched on, it changes the part - and still runs -----------
        for proj in ('testing_15_2.xml', 'testing_15_5.xml'):
            off, _e = run(proj, 0)
            on, eon = run(proj, 1)
            check('%s still generates and runs with the front flank on'
                  % proj[:-4], on is not None,
                  'the combined envelope produced a contour the interpreter '
                  'refuses: %s' % eon)
            if on and off:
                check('   %s the path changes when it is asked for'
                      % proj[:-4], on != off,
                      'the switch does nothing at all')
                print('      %-18s off %d moves -> on %d moves'
                      % (proj[:-4], off[0], on[0]))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The leading flank shapes the path only when it is asked to.')


if __name__ == '__main__':
    main()
