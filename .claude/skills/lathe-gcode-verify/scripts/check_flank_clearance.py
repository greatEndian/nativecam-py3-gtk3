#!/usr/bin/env python3
"""Prove a roughing toolpath respects the tool's back flank, not just its tip.

The ordinary gouge proof asks "is the tool TIP inside the part?". That is the
wrong question for the flank shadow, because with the shadow on the tip is
never inside - what collides is the tool BODY, trailing behind the tip at the
back angle. A path can pass a tip-only proof and still drive the insert's heel
straight through a boss.

So this lays the back flank out from every cutting point and asks whether it
clears the material ahead of it:

    at a tip (zt, rt), the flank at Z = zt + d*side is at radius
        rt + d * tan(90 - BACK)
    and any profile point above that line, on the shadowed side, is metal the
    insert is sitting in.

Sampling follows the TRUE geometry of each move - an ARC_FEED is walked as an
arc, not as the chord across it - because the chord cuts inside a convex arc
and produces violations that are not real. That mistake has already cost this
project one full analysis.

Angles: BACK comes from the tool table's J column, measured off the
perpendicular, so the reachable ramp is at 90 - BACK from the Z axis. The side
follows the roughing direction: front to back shadows +Z, back to front -Z,
both directions takes both.

KNOWN LIMITATION, read before trusting a FAIL
---------------------------------------------
The flank shadow governs ROUGHING only. The pre-finish and finish contour
passes deliberately trace the true profile, including straight down a wall
face, so their flank is always inside the wall behind them and they will always
report a violation. That is not a path fault - it says the insert cannot finish
that wall, which is a tool choice, not something roughing can fix.

--on-profile skips tips sitting on the finished surface, but the pre-finish
pass runs at an offset and slips past it, so a whole-file run still fails on a
correct path. Until roughing can be isolated from the contour passes - by
bracketing the level loop with a marker comment, the way check_tangent uses
--marker - use --after to point this at a region you know is roughing, and read
a FAIL whose tip sits ON or just off the profile as the contour pass, not as a
defect.

Usage:
  check_flank_clearance.py --ini <ini> --ngc <ngc> --back 75 \
      --points "0,40 -20,40 -20,50 -50,50 -50,40 -80,40" [--dir 0] [--tol 0.01]

--points is the finished profile as "Z,diameter" pairs in program units.
Exits 0 with [VERDICT: PASS], or 1 with [VERDICT: FAIL - ...].
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rs274 import run_rs274, parse_canon      # noqa: E402


def walk(prev, m, steps=24):
    """Points along one move, following the real arc when it is one."""
    if m['kind'] == 'arc':
        cz, cx = m['zc'], m['xc']
        rad = math.hypot(prev[0] - cz, prev[1] - cx)
        a1 = math.atan2(prev[1] - cx, prev[0] - cz)
        a2 = math.atan2(m['x'] - cx, m['z'] - cz)
        if m['rot'] > 0:
            while a2 <= a1:
                a2 += 2 * math.pi
        else:
            while a2 >= a1:
                a2 -= 2 * math.pi
        return [(cz + rad * math.cos(a1 + (a2 - a1) * i / steps),
                 cx + rad * math.sin(a1 + (a2 - a1) * i / steps))
                for i in range(steps + 1)]
    return [(prev[0] + (m['z'] - prev[0]) * i / steps,
             prev[1] + (m['x'] - prev[1]) * i / steps) for i in range(steps + 1)]


def densify_profile(points, step=0.25):
    """The profile as closely spaced points, so a flank cannot slip between
    two widely separated vertices of a long slope."""
    out = []
    for (z0, r0), (z1, r1) in zip(points, points[1:]):
        n = max(int(abs(z1 - z0) / step), 1)
        for i in range(n):
            t = i / float(n)
            out.append((z0 + (z1 - z0) * t, r0 + (r1 - r0) * t))
    out.append(points[-1])
    return out


def _on_profile(prof, z, r, tol):
    for zp, rp in prof:
        if abs(zp - z) <= tol and abs(rp - r) <= tol:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--ngc', required=True)
    ap.add_argument('--tbl', default=None)
    ap.add_argument('--var', default=None)
    ap.add_argument('--points', required=True,
                    help='finished profile as "Z,diameter Z,diameter ..."')
    ap.add_argument('--back', type=float, required=True,
                    help='tool back angle, the tool table J column')
    ap.add_argument('--flank-len', type=float, default=0.0,
                    help='how far the flank extends along itself; 0 = infinite. '
                         'Must match the feature, or a correct finite-flank path '
                         'is judged against a tool longer than the real one')
    ap.add_argument('--dir', type=int, default=0,
                    help='0 front to back, 1 back to front, 2 both')
    ap.add_argument('--tol', type=float, default=0.01,
                    help='mm the flank may overlap before it counts')
    ap.add_argument('--on-profile', type=float, default=0.05,
                    help='ignore tips this close to the finished surface - the '
                         'contour passes are meant to touch it, and the shadow '
                         'governs roughing only')
    ap.add_argument('--after', default='roughing levels begin',
                    help='start looking after this comment appears')
    ap.add_argument('--until', default='roughing levels end',
                    help='stop at this comment. Together with --after these '
                         'bracket the roughing levels, which is the only part '
                         'the flank shadow governs - the contour passes trace '
                         'the profile by design and always show their flank in '
                         'the wall behind them')
    args = ap.parse_args()

    prof = []
    for tok in args.points.split():
        z, d = tok.split(',')
        prof.append((float(z), float(d) / 2.0))          # radius, as canon reports
    if len(prof) < 2:
        raise SystemExit('need at least two profile points')
    prof = densify_profile(prof)

    eff = 90.0 - args.back
    if eff <= 0 or eff >= 90:
        print('[VERDICT: PASS] back angle %.1f constrains nothing' % args.back)
        return 0
    slope = math.tan(math.radians(eff))
    reach = None
    if args.flank_len > 0:
        reach = args.flank_len * math.cos(math.radians(eff))
    sides = (-1,) if args.dir == 1 else ((1, -1) if args.dir == 2 else (1,))

    canon, _out = run_rs274(args.ini, args.ngc, args.tbl, var_path=args.var)
    lines = canon.splitlines()
    if args.after:
        try:
            lines = lines[next(i for i, ln in enumerate(lines) if args.after in ln):]
        except StopIteration:
            print('[VERDICT: FAIL - marker %r never appears]' % args.after)
            return 1
    if args.until:
        for i, ln in enumerate(lines):
            if args.until in ln:
                lines = lines[:i]
                break
    moves = [m for m in parse_canon('\n'.join(lines)) if m['kind'] != 'comment']
    if not moves:
        print('[VERDICT: FAIL - no motion parsed, check the ngc and ini]')
        return 1

    worst = (0.0, None)
    checked = 0
    prev = None
    for m in moves:
        if m['kind'] in ('feed', 'arc') and prev is not None:
            for zt, rt in walk(prev, m):
                # a tip sitting ON the finished surface is a contour pass, which
                # is supposed to touch the wall - the shadow governs roughing,
                # so judging those would report the part's own shape as a fault
                if _on_profile(prof, zt, rt, args.on_profile):
                    continue
                checked += 1
                for zp, rp in prof:
                    for side in sides:
                        d = (zp - zt) * side
                        if d <= 0:
                            continue
                        if reach is not None and d > reach:
                            continue    # past the end of the flank
                        # where the flank is, at that Z
                        flank_r = rt + d * slope
                        over = rp - flank_r
                        if over > worst[0]:
                            worst = (over, (zt, rt, zp, rp))
        if m['kind'] in ('feed', 'arc', 'rapid'):
            prev = (m['z'], m['x'])

    print('sampled %d cutting points against %d profile points' % (checked, len(prof)))
    print('back angle %.1f -> flank ramp %.1f deg from Z, slope %.4f, reach %s'
          % (args.back, eff, slope,
             'infinite' if reach is None else '%.3f mm' % reach))
    if worst[1] is None or worst[0] <= args.tol:
        print('deepest flank overlap: %.4f mm (tolerance %.4f)' % (worst[0], args.tol))
        print('[VERDICT: PASS]')
        return 0
    zt, rt, zp, rp = worst[1]
    print('deepest flank overlap: %.4f mm (tolerance %.4f)' % (worst[0], args.tol))
    print('  tip at Z%.3f r%.3f, flank buried in material at Z%.3f r%.3f'
          % (zt, rt, zp, rp))
    print('[VERDICT: FAIL - the back flank enters material by %.4f mm]' % worst[0])
    return 1


if __name__ == '__main__':
    sys.exit(main())
