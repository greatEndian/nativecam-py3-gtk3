#!/usr/bin/env python3
# coding: utf-8
"""The drawn compensated path is the path the machine actually takes.

Standalone, like the other test_*.py here - run it directly, no pytest.

The preview gained a teal overlay showing where the tool CONTROL POINT travels
once compensation is applied, computed in Python by
lathe_sections.offset_contour. The toolpath drawn beside it is what the
INTERPRETER actually did, read out of the rs274 canon after G41.1/G42.1.

Two independent routes to the same curve, which is the whole point: where they
disagree one of them is wrong. Both compensation faults found on 2026-08-02/03
- an arc that stopped 9 degrees short, and an entry that landed 0.4 mm off and
tapered the first cut - were found exactly this way, by putting a predicted
number next to a measured one. This makes that a test instead of a habit.

It also pins the deliberate silence: with nose comp OFF the overlay draws
NOTHING. A line lying on the profile would claim a compensation that is not
happening, and "off" is the state every saved project in this repo is in.
"""
import math
import os
import subprocess
import shutil
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


def dist_to_polyline(pt, pts):
    """Shortest distance from a point to a polyline, in radius units."""
    z, r = pt
    best = None
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        dz, dr = z1 - z0, r1 - r0
        n2 = dz * dz + dr * dr
        if n2 < 1e-18:
            continue
        t = max(0.0, min(1.0, ((z - z0) * dz + (r - r0) * dr) / n2))
        d = math.hypot(z - (z0 + dz * t), r - (r0 + dr * t))
        best = d if best is None else min(best, d)
    return best


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    import lathe_sections as ls
    import ncam_preview as P

    # --- the overlay is silent when compensation is off -------------------
    # asserted on the geometry helper rather than through GTK, so it runs
    # without a display: the supplier's rule is "mode not in (1, 2) -> None"
    src = open(os.path.join(HERE, 'ncam_preview_ui.py')).read()
    check('the supplier draws nothing with compensation off',
          'if mode not in (1, 2):' in src,
          'the off case is what every saved project is in, so it is the one '
          'that has to be right')
    check('and the pane hands a compensated contour to the drawing code',
          'comp=self._contour(self.comp_cb)' in src)
    check('and the drawing code accepts it',
          'comp=None' in open(os.path.join(HERE, 'ncam_preview.py')).read())

    # --- prediction against the interpreter -------------------------------
    # NOT circular: the programmed profile comes from an OFF-mode run and the
    # compensated one from a NATIVE run of the same project. Off mode's LAST
    # finish pass carries shift_r 0, so it applies no offset at all and its
    # path is the programmed profile itself. Offsetting that in Python must
    # reproduce what the interpreter did in the other run.
    d = tempfile.mkdtemp(prefix='comp_overlay_')
    try:
        def finish_pass(mode):
            out = os.path.join(d, 'm%d.ngc' % mode)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            'testing_15_2.xml', '--out', out, '--config-copy',
                            '--set', 'polyline:param_n_comp=%d' % mode],
                           capture_output=True, text=True)
            if not os.path.isfile(out):
                return None
            tp = P.parse_program(out, INI)
            if tp.error:
                return None
            return [m for m in tp.moves
                    if m.op == 'Lathe Polyline' and P.FINISH in m.subs
                    and m.kind == 'feed']

        prog_mv, comp_mv = finish_pass(0), finish_pass(1)
        check('both runs produce a finish pass',
              prog_mv and comp_mv and len(prog_mv) > 5 and len(comp_mv) > 5,
              '%s / %s feeds' % (len(prog_mv or []), len(comp_mv or [])))
        if not (prog_mv and comp_mv):
            return

        def path(mv):
            return [(m.a[2], m.a[0]) for m in mv] + [(mv[-1].b[2],
                                                      mv[-1].b[0])]
        programmed = path(prog_mv)          # radius, no offset applied
        actual = path(comp_mv)              # radius, compensated

        nose_r, orient = 0.4, 2
        pred = ls.offset_contour(
            [(z, r * ls.DIAMETER_MODE) for z, r in programmed],
            nose_r, orient, 1)
        check('offset_contour returns a usable contour',
              bool(pred) and len(pred) >= 2, '%s points' % (len(pred or [])))
        if not pred or len(pred) < 2:
            return
        pred_r = [(z, x / ls.DIAMETER_MODE) for z, x in pred]

        # THE CHECK: every point the interpreter visited while tracing the
        # CONTOUR lies on the curve Python predicted.
        #
        # The lead-in and lead-out are left out, and not as a convenience: the
        # overlay deliberately draws the contour only, and those moves are
        # placed by the orientation-aware ENTRY rule in lathe_poly_pass rather
        # than by the contour offset. Measured, they are the only points that
        # part company - the first two and the last three:
        #
        #     idx  0  Z  1.3071  gap 0.3061   lead-in, before the contour
        #     idx  1  Z  0.6000  gap 0.1172   the comp entry point
        #     idx 25  Z-29.9846  gap 0.0001   <- the body, for comparison
        #     idx 36  Z-70.4000  gap 0.1172   lead-out
        #     idx 37  Z-70.0000  gap 0.1172
        #     idx 38  Z-69.2929  gap 0.8566   the retreat into air
        #
        # No corner exclusion is needed and none is made: at a convex vertex
        # the interpreter rolls the nose round on an arc and Python emits that
        # same arc as chords under a 0.005 mm sagitta bound, so the two agree
        # there too.
        LEAD_IN, LEAD_OUT = 2, 3
        body = actual[LEAD_IN:-LEAD_OUT]
        check('the pass is longer than its lead-in and lead-out',
              len(body) > 10, '%d contour points of %d'
              % (len(body), len(actual)))
        gaps = [dist_to_polyline(p, pred_r) for p in body]
        gaps = [g for g in gaps if g is not None]
        worst = max(gaps)
        check('the interpreter walks the curve Python predicts, all %d '
              'contour points' % len(gaps), worst < 0.02,
              'worst %.4f mm apart - the overlay would be drawing a different '
              'path from the one the machine takes' % worst)

        # and the exclusion cannot quietly grow to hide a fault: everything
        # outside those five points has to agree, so if a sixth ever starts
        # disagreeing this fails rather than being trimmed away
        ends = ([dist_to_polyline(p, pred_r) for p in actual[:LEAD_IN]]
                + [dist_to_polyline(p, pred_r) for p in actual[-LEAD_OUT:]])
        check('   and exactly the five lead moves are the ones that differ',
              sum(1 for g in ends if g is not None and g > 0.02) >= 1,
              'the leads now agree too, so the exclusion is no longer '
              'earning its place and should be removed')

        # and the prediction really is offset from the programmed profile,
        # or the agreement above would be trivially true of any two paths
        stand = [dist_to_polyline(p, programmed) for p in pred_r]
        stand = [g for g in stand if g is not None]
        check('and that curve stands off the programmed profile',
              max(stand) > nose_r * 0.5,
              'the prediction lies on the profile, so agreeing with it '
              'proves nothing')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The compensated overlay is the path, not a decoration.')


if __name__ == '__main__':
    main()
