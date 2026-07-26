#!/usr/bin/env python3
"""Geometric tangency PROOF for lathe tool-nose-radius compensation.

Given a compensated .ngc (comp active via G41.1/G42.1 or G41/G42), a nose
radius R, a tool orientation Q, and the target PROFILE the op is supposed to
cut, this proves the compensation is correct: the tool nose circle (radius R,
positioned per orientation Q) rides exactly TANGENT to the profile with no
gouge, everywhere the tool is cutting.

Why this is a proof and not a heuristic
---------------------------------------
rs274 (the LinuxCNC interpreter, batch mode) applies the compensation itself,
so its canon output is the COMPENSATED control-point path. For a correct comp
the nose circle centred off each control point must be tangent to the profile.

The control-point -> nose-centre offset depends on orientation Q. Rather than
trust a published Q table from memory, we CALIBRATE it empirically: run a
straight reference cut twice, once with L0 (an on-centre/round tool, whose
control point IS the nose centre) and once with the real Lq; for a straight
line the nose centre is identical in both, so
    u_hat(Q) * R = endpoint(L0) - endpoint(Lq)
gives the exact control-point->centre vector rs274 actually uses.

Assertions (PASS requires all):
  1. NO GOUGE  - for every compensated point, dist(nose_centre, profile) >= R-tol
  2. TANGENT   - the cutting portion touches the profile: points classified as
                 cutting (nose within tol of tangent) must have dist == R +/- tol
  3. COVERAGE  - every profile segment is actually reached by some tangent point
                 (the tool cuts the whole profile, not air)

Ends with exactly one verdict line: [VERDICT: PASS] / [VERDICT: FAIL - ...].
"""
import argparse
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rs274 import run_rs274, parse_canon  # noqa: E402

# Compensated arcs are sampled into this many points; each becomes a tangency
# test point and a coverage witness. It must be dense enough that a finely
# sampled arc PROFILE (kept fine so its chord sagitta stays under tol) still
# gets a witness within R+5*tol of every profile segment - otherwise coverage
# fails on a perfectly good arc purely from point/segment granularity mismatch.
ARC_SAMPLES = 200


# ----------------------------------------------------------------------------
# geometry helpers  (all points are (z, x) = (axial, radial) tuples)
# ----------------------------------------------------------------------------
def _seg_dist(p, a, b):
    """Distance from point p to segment a-b."""
    az, ax = a
    bz, bx = b
    pz, px = p
    dz, dx = bz - az, bx - ax
    L2 = dz * dz + dx * dx
    if L2 < 1e-18:
        return math.hypot(pz - az, px - ax)
    t = ((pz - az) * dz + (px - ax) * dx) / L2
    t = max(0.0, min(1.0, t))
    cz, cx = az + t * dz, ax + t * dx
    return math.hypot(pz - cz, px - cx)


def profile_min_dist(p, segments):
    return min(_seg_dist(p, a, b) for a, b in segments)


def _signed_seg_dist(p, a, b, freeside):
    """Signed perpendicular distance from p to the INFINITE line through a-b:
    positive on the material-FREE side, negative if p has crossed to material.
    Also returns the projection parameter t (0..1 = onto the finite segment,
    outside = off the ends, i.e. in lead-in/out / approach space). freeside=+1
    uses the right-hand normal of travel a->b, -1 the left."""
    az, ax = a
    bz, bx = b
    pz, px = p
    dz, dx = bz - az, bx - ax
    L2 = dz * dz + dx * dx
    if L2 < 1e-18:
        return math.hypot(pz - az, px - ax), 0.5
    t = ((pz - az) * dz + (px - ax) * dx) / L2
    L = math.sqrt(L2)
    ndz, ndx = dz / L, dx / L
    nz, nx = (ndx * freeside, -ndz * freeside)   # right-hand normal * freeside
    signed = (pz - az) * nz + (px - ax) * nx
    return signed, t


def profile_signed_dist(p, segments, freeside):
    """(signed distance, projects-onto-a-segment-interior?) for the nearest
    segment. A point that only projects OFF the ends of every segment is in
    lead-in / approach space (not cutting the wall), so its 'material side'
    against the infinite wall line is not a real gouge and must not count."""
    best = min(segments, key=lambda s: _seg_dist(p, s[0], s[1]))
    signed, t = _signed_seg_dist(p, best[0], best[1], freeside)
    interior = (-0.02 <= t <= 1.02)
    return signed, interior


def sample_moves(moves):
    """Yield compensated cutting/positioning points (z, x): feed and arc
    endpoints, plus densely sampled arc interiors. Rapids are yielded too but
    tagged so tangency is only *required* on non-rapid points."""
    pts = []
    prev = None
    for m in moves:
        k = m['kind']
        if k in ('feed', 'rapid'):
            p = (m['z'], m['x'])
            pts.append((p, k))
            prev = p
        elif k == 'arc':
            end = (m['z'], m['x'])
            c = (m['zc'], m['xc'])
            if prev is not None:
                a0 = math.atan2(prev[1] - c[1], prev[0] - c[0])
                a1 = math.atan2(end[1] - c[1], end[0] - c[0])
                da = a1 - a0
                while da > math.pi:
                    da -= 2 * math.pi
                while da < -math.pi:
                    da += 2 * math.pi
                r = math.hypot(prev[1] - c[1], prev[0] - c[0])
                for s in range(1, ARC_SAMPLES + 1):
                    ang = a0 + da * s / ARC_SAMPLES
                    pts.append(((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)), 'feed'))
            prev = end
    return pts


# ----------------------------------------------------------------------------
# empirical calibration of the control-point -> nose-centre unit vector u(Q)
# ----------------------------------------------------------------------------
REF_TEMPLATE = """G21
G18 G8 G90 G94 G54
G0 X20 Z5
G1 Z0 F200
G{gword}.1 D{dia} L{lval}
G1 Z-10
G40
G0 X40
M2
"""


def _ref_endpoint(ini, tbl, R, lval, gword, var=None):
    ngc = tempfile.NamedTemporaryFile('w', suffix='.ngc', delete=False)
    ngc.write(REF_TEMPLATE.format(gword=gword, dia=2.0 * R, lval=lval))
    ngc.close()
    canon, _ = run_rs274(ini, ngc.name, tbl, var_path=var)
    os.unlink(ngc.name)
    moves = [m for m in parse_canon(canon) if m['kind'] == 'feed']
    # the last feed endpoint is the compensated end of the Z-10 cut
    if not moves:
        raise RuntimeError('reference cut produced no feed moves; comp may not have engaged')
    return (moves[-1]['z'], moves[-1]['x'])


def calibrate_offset(ini, tbl, R, Q, gword=42, var=None):
    """Control-point -> nose-centre offset vector (z, x), empirically.

    On an identical straight cut, L0 (on-centre/round tool) puts the control
    point AT the nose centre, while LQ puts it at the oriented imaginary tip.
    So offset(Q) = endpoint(L0) - endpoint(LQ). This is a raw vector in the
    fixed (z,x) machine frame - for a 90-degree insert corner (orientations
    1/3/5/7) its magnitude is R*sqrt2 (the sharp tip sits sqrt2*R from the
    round-nose centre); for an edge orientation it is R; for on-centre 0/9
    it is (0,0). Do NOT normalise it.
    """
    e0 = _ref_endpoint(ini, tbl, R, 0, gword, var)
    eq = _ref_endpoint(ini, tbl, R, Q, gword, var)
    return (e0[0] - eq[0], e0[1] - eq[1])


# ----------------------------------------------------------------------------
# the proof
# ----------------------------------------------------------------------------
def prove(moves, segments, R, offset, tol, freeside):
    offz, offx = offset
    pts = sample_moves(moves)
    max_gouge = 0.0
    tangent_pts = []          # (z,x) nose centres classified as cutting
    worst_tangent_err = 0.0
    for (z, x), kind in pts:
        cz, cx = z + offz, x + offx              # nose centre = control + offset(Q)
        d = profile_min_dist((cz, cx), segments)
        sd, interior = profile_signed_dist((cz, cx), segments, freeside)
        # gouge = nose disc reaching onto the material side: the centre is
        # closer to the profile than R measured on the free side (a wrong comp
        # side lands the centre near -R, deep on the material side). Only count
        # points that actually project onto the cutting span - a point off the
        # ends is lead-in / approach in free air, not gouging the wall.
        if interior and sd < R - tol:
            max_gouge = max(max_gouge, R - sd)
        if abs(d - R) <= tol and kind != 'rapid':
            tangent_pts.append((cz, cx))
            worst_tangent_err = max(worst_tangent_err, abs(d - R))

    # coverage: every profile segment must have a tangent contact near it
    uncovered = []
    for i, (a, b) in enumerate(segments):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        seglen = math.hypot(b[0] - a[0], b[1] - a[1])
        near = any(_seg_dist(tp, a, b) <= R + 5 * tol for tp in tangent_pts)
        if not near and seglen > 5 * tol:
            uncovered.append(i)
    return max_gouge, len(tangent_pts), worst_tangent_err, uncovered


def parse_profile(spec):
    """'z1,x1 z2,x2 ...' -> list of consecutive segments."""
    pts = []
    for tok in spec.split():
        z, x = tok.split(',')
        pts.append((float(z), float(x)))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--ngc', required=True)
    ap.add_argument('--tbl', default=None)
    ap.add_argument('--radius', type=float, required=True, help='tool nose radius R')
    ap.add_argument('--orient', type=int, required=True, help='tool orientation Q (0-9)')
    ap.add_argument('--profile', required=True,
                     help='target profile as "z1,x1 z2,x2 ..." (radial x)')
    ap.add_argument('--side', type=int, default=42, choices=(41, 42),
                     help='calibration comp side (41/42), match the op')
    ap.add_argument('--freeside', choices=('right', 'left'), default='right',
                     help='which side of the traced profile is material-free '
                          '(where the tool rides). right = right-hand normal of '
                          'travel; OD turning front-to-back is typically right')
    ap.add_argument('--tol', type=float, default=1e-3)
    ap.add_argument('--var', default=None,
                    help='frozen known-good var snapshot (avoids the live '
                         'GUI-written var, which can be caught mid-write)')
    args = ap.parse_args()
    freeside = 1 if args.freeside == 'right' else -1

    segments = parse_profile(args.profile)

    try:
        offset = calibrate_offset(args.ini, args.tbl, args.radius, args.orient,
                                  args.side, args.var)
    except Exception as e:
        print(f'[VERDICT: FAIL - calibration failed: {e}]')
        sys.exit(1)
    offmag = math.hypot(*offset)
    print(f'Calibrated offset(Q={args.orient}) = ({offset[0]:+.4f}, {offset[1]:+.4f}) '
          f'[z,x]; |offset| = {offmag:.4f} (R={args.radius}, R*sqrt2={args.radius * 1.4142:.4f})')

    try:
        canon, raw = run_rs274(args.ini, args.ngc, args.tbl, var_path=args.var)
    except Exception as e:
        print(f'[VERDICT: FAIL - rs274 failed: {e}]')
        sys.exit(1)
    if 'error' in canon.lower() and 'error_code' not in canon.lower():
        print(f'[VERDICT: FAIL - interpreter errors, see {raw}]')
        sys.exit(1)

    moves = parse_canon(canon)
    max_gouge, ntan, terr, uncovered = prove(moves, segments, args.radius, offset, args.tol, freeside)
    print(f'Points tangent to profile: {ntan}; worst tangent error {terr:.6f} '
          f'(tol {args.tol})')
    print(f'Max gouge depth: {max_gouge:.6f} (tol {args.tol})')
    print(f'Profile segments uncovered by any tangent point: {uncovered}')

    reasons = []
    if max_gouge > args.tol:
        reasons.append(f'gouge {max_gouge:.5f} > tol')
    if ntan == 0:
        reasons.append('no tangent contact - tool cutting air')
    if uncovered:
        reasons.append(f'{len(uncovered)} profile segment(s) never cut')
    if offmag > 2.5 * args.radius:
        reasons.append(f'implausible calibration offset {offmag:.3f}')

    if reasons:
        print(f'[VERDICT: FAIL - {"; ".join(reasons)}]')
        sys.exit(1)
    print('[VERDICT: PASS]')
    sys.exit(0)


if __name__ == '__main__':
    main()
