#!/usr/bin/env python3
"""Prove a polyline's In-CAM nose compensation puts the nose ON the profile.

prove_tip_comp.py covers the parametric ops, whose target wall is a formula it
can rebuild from a few numbers. A polyline's target is the profile the operator
drew, so this takes that profile from lathe_sections.resolve_points - the very
function the offset is computed from - rather than having it retyped as
--profile, where a typo silently moves the target the proof is measured against.

The proof itself is check_nose_tangent's, unchanged and mechanism-blind: put the
nose circle at every programmed control point and require it to ride the profile
without reaching into the material. Native compensation and In-CAM compensation
must both pass it - that is the whole point of having it.

The NEGATIVE CONTROL is not optional. A single profile line is tangent to the
nose circle from either side, so a proof with no free side declared passes a
path compensated the wrong way round just as happily. This runs both and
requires PASS on the correct side and FAIL on the flipped one; one without the
other proves nothing.

Usage:
  prove_cam_comp.py --ini <ini> --project testing_15_0.xml [--tol 0.002]
"""
import argparse
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rs274 import run_rs274, parse_canon, _resolve_tbl_path  # noqa: E402
from check_nose_tangent import calibrate_offset, sample_moves       # noqa: E402
from prove_tip_comp import read_tool, tool_from_ngc                 # noqa: E402

REPO = '/home/user/nativeCamDev'


# ----------------------------------------------------------------------------
# the gouge test, against the material REGION rather than segment by segment
#
# check_nose_tangent judges each point against its nearest single segment, using
# a signed distance off the segment's infinite line and calling the point
# "interior" while it projects within 2% of the segment's ends. That is right for
# the parametric ops, whose target is one wall. On a polyline it reports a false
# gouge at every convex corner: the nose legitimately rolls R*sqrt2 past the end
# of the segment it just finished, and on a 30 mm segment that is still inside
# the 2% window, where the distance to the extended line reads as zero. Tightening
# --tol cannot separate that from a real gouge, because the measured overlap is
# the full nose radius.
#
# So here the material is treated as what it is - the region under the profile -
# and the two questions asked directly: is the nose centre inside it, and is it
# at least R away from its boundary. Distances are clamped to the segments, so a
# point beyond a segment's end measures to the corner, which is the truth.
# ----------------------------------------------------------------------------
def _seg_dist_clamped(p, a, b):
    dz, dx = b[0] - a[0], b[1] - a[1]
    n2 = dz * dz + dx * dx
    if n2 < 1e-18:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dz + (p[1] - a[1]) * dx) / n2
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dz), p[1] - (a[1] + t * dx))


def profile_bound(z, segments, side):
    """The radius bounding the material at this Z, or None off the profile ends.

    Outside work (side +1): the material is under the profile, so the bound is
    the LARGEST radius reached at this Z - a vertical wall makes the profile
    multi-valued there and the outermost value is the one that bounds metal.
    Inside work (side -1): a bore's material is outside the profile instead, so
    the bound is the smallest radius. Getting this backwards would report a bore
    that is cut perfectly as buried in metal along its whole length.
    """
    best = None
    for a, b in segments:
        z0, z1 = min(a[0], b[0]), max(a[0], b[0])
        if not (z0 - 1e-9 <= z <= z1 + 1e-9):
            continue
        if abs(b[0] - a[0]) < 1e-12:
            r = max(a[1], b[1]) if side > 0 else min(a[1], b[1])
        else:
            t = (z - a[0]) / (b[0] - a[0])
            r = a[1] + t * (b[1] - a[1])
        if best is None:
            best = r
        else:
            best = max(best, r) if side > 0 else min(best, r)
    return best


def prove_region(points, segments, R, tol, side=1):
    """(max gouge, tangent point count, worst tangency error, uncovered segments)

    points is [(centre, kind)] with the nose centre already resolved.
    """
    max_gouge = 0.0
    worst_tangent = 0.0
    tangent_pts = []
    for (cz, cx), kind in points:
        dist = min(_seg_dist_clamped((cz, cx), a, b) for a, b in segments)
        bound = profile_bound(cz, segments, side)
        inside = bound is not None and (cx < bound - tol if side > 0
                                        else cx > bound + tol)
        if inside:
            # the centre itself is buried: the whole nose is in the material,
            # so the overlap is at least a radius however the distance reads
            max_gouge = max(max_gouge, R + dist)
        elif dist < R - tol:
            max_gouge = max(max_gouge, R - dist)
        if abs(dist - R) <= tol and kind != 'rapid':
            tangent_pts.append((cz, cx))
            worst_tangent = max(worst_tangent, abs(dist - R))

    uncovered = []
    for i, (a, b) in enumerate(segments):
        seglen = math.hypot(b[0] - a[0], b[1] - a[1])
        near = any(_seg_dist_clamped(tp, a, b) <= R + 5 * tol
                   for tp in tangent_pts)
        if not near and seglen > 5 * tol:
            uncovered.append(i)
    return max_gouge, len(tangent_pts), worst_tangent, uncovered


def generate(ini, project, out, overrides):
    """The project as G-code, via gen_project's own path so this proves what
    the GUI would produce rather than a hand-built file."""
    import subprocess
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        'gen_project.py'),
           '--ini', ini, '--project', project, '--out', out, '--config-copy']
    for k, v in overrides.items():
        cmd += ['--set', 'polyline:%s=%s' % (k, v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('generation failed:\n' + r.stdout + r.stderr)
    return out


def target_profile(ini, project, machine='lathe'):
    """The finished profile, as (z, radius) segments, straight from the feature.

    Runs in a subprocess: ncam is a GTK app that wants argv and an ini at import
    time, and this script has already been given a different pair.
    """
    import subprocess
    script = '''
import sys
sys.argv = ['ncam.py', '-i', %(ini)r, '-c', %(machine)r]
sys.path.insert(0, %(repo)r)
import ncam
from lxml import etree
import lathe_sections
app = ncam.NCam()
prj = %(prj)r
xml = app.update_features(etree.fromstring(open(prj).read().encode()))
app.treestore_from_xml(xml)
app.to_gcode()
f = None
for feat in app.get_features() if hasattr(app, 'get_features') else []:
    pass
def walk(it):
    while it is not None:
        yield it
        it = it.next_sibling if hasattr(it, 'next_sibling') else None
for row in app.treestore:
    pass
# the polyline feature, found the same way the cfg exec reaches it
def find(store, parent=None):
    it = store.iter_children(parent)
    while it is not None:
        f = store.get_value(it, 0)
        if f.get_attr('type') == 'polyline':
            return f
        r = find(store, it)
        if r is not None:
            return r
        it = store.iter_next(it)
    return None
feat = find(app.treestore)
pts = lathe_sections.resolve_points(feat)
sp = feat.get_param('param_side')
print('SIDE=%%s' %% (sp.get_ngc_value() if sp is not None else '0'))
print(' '.join('%%0.6f,%%0.6f' %% (z, x / 2.0) for z, x in pts))
''' % {'ini': ini, 'machine': machine, 'repo': REPO,
       'prj': os.path.join(os.path.dirname(ini), 'ncam', 'catalogs', machine,
                           'projects', project)}
    r = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    line = [ln for ln in r.stdout.splitlines() if ',' in ln]
    if not line:
        raise SystemExit('could not resolve the profile:\n' + r.stdout + r.stderr)
    side = 1
    for ln in r.stdout.splitlines():
        if ln.startswith('SIDE='):
            side = -1 if ln.strip().split('=')[1] == '1' else 1
    pts = []
    for tok in line[-1].split():
        z, x = tok.split(',')
        pts.append((float(z), float(x)))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)], side


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--project', required=True)
    ap.add_argument('--machine', default='lathe')
    ap.add_argument('--var', default=None)
    ap.add_argument('--tol', type=float, default=2e-3)
    ap.add_argument('--lead-margin', type=float, default=0.0,
                    help='mm at each end of the profile to treat as lead-in / '
                         'lead-out territory and report separately instead of '
                         'judging. 0 judges the whole path')
    ap.add_argument('--side', type=int, default=42, choices=(41, 42),
                    help='only selects which reference cut calibrates the '
                         'orientation offset; the offset itself is the same')
    args = ap.parse_args()

    ini = os.path.abspath(args.ini)
    tmp = tempfile.mkdtemp(prefix='prove_cam_')
    # finishing only, one pass, no pre-finish: the file then contains exactly
    # the pass under test, so uncompensated roughing cannot pollute the proof
    ngc = generate(ini, args.project, os.path.join(tmp, 'cam.ngc'),
                   {'param_n_comp': '2', 'param_op': '2',
                    'param_f_pass': '1', 'param_pf_on': '0'})

    segments, side = target_profile(ini, args.project, args.machine)
    print('profile: %d segments, from %s to %s, %s work'
          % (len(segments), segments[0][0], segments[-1][1],
             'outside' if side > 0 else 'inside'))

    tbl = _resolve_tbl_path(ini, None)
    tool = tool_from_ngc(ngc)
    if tool is None:
        raise SystemExit('no T<n> M6 in the program - nothing to prove against')
    R, Q = read_tool(tbl, tool)
    print('tool T%d: nose radius %.4f, orientation Q%d' % (tool, R, Q))
    if R <= 0:
        raise SystemExit('tool T%d has no D - the proof needs a nose radius' % tool)

    canon, _ = run_rs274(ini, ngc, None, var_path=args.var)
    moves = [m for m in parse_canon(canon) if m['kind'] != 'comment']
    if not moves:
        raise SystemExit('no motion parsed - check the ini and the program')
    offset = calibrate_offset(ini, None, R, Q, args.side, args.var)
    print('control point -> nose centre offset: (%.4f, %.4f), |.| = %.4f'
          % (offset[0], offset[1], (offset[0] ** 2 + offset[1] ** 2) ** 0.5))

    def centres(pts):
        return [((z + offset[0], x + offset[1]), kind) for (z, x), kind in pts]

    all_pts = centres(sample_moves(moves))
    # The lead-in and lead-out are separated out because they are a different
    # question. Their geometry is chosen by the lead parameters, not by the
    # compensation, and on ID work it is measurably worse under NATIVE
    # compensation than in CAM - so folding them in would report a pre-existing
    # lead problem as a fault in whichever mode is under test. --lead-margin
    # says how much of each end of the profile is lead territory; the contour
    # figure is the one that judges the compensation.
    zs = [c for a, b in segments for c in (a[0], b[0])]
    zlo, zhi = min(zs) + args.lead_margin, max(zs) - args.lead_margin
    mid_pts = [p for p in all_pts if zlo <= p[0][0] <= zhi]

    # Coverage is judged over the WHOLE path, always. It asks whether the tool
    # ever touched each part of the profile, and clipping the ends off the point
    # set would drop the contacts on the first and last segments and report them
    # as never cut - a failure invented by the window rather than found by it.
    wgouge, ntan, terr, uncovered = prove_region(all_pts, segments, R,
                                                 args.tol, side)
    gouge = prove_region(mid_pts, segments, R, args.tol, side)[0]
    ok = gouge <= args.tol and ntan > 0 and not uncovered
    if args.lead_margin > 0:
        print('  whole path     : gouge %.4f  (includes the lead-in/out, '
              'reported not judged)' % wgouge)
    print('  contour        : gouge %.4f, %d tangent points, worst tangency '
          'err %.5f, %d segment(s) uncovered -> %s'
          % (gouge, ntan, terr, len(uncovered), 'PASS' if ok else 'FAIL'))

    # NEGATIVE CONTROL: the same proof against the same profile offset to the
    # WRONG side. A proof that cannot fail is not a proof, and this is the
    # failure that actually happens - the side is inverted between OD and ID
    # work, so it is the one mistake this code is most likely to make.
    sys.path.insert(0, REPO)
    import lathe_sections
    prof_dia = [(segments[0][0][0], segments[0][0][1] * 2.0)]
    prof_dia += [(b[0], b[1] * 2.0) for a, b in segments]
    wrong = lathe_sections.offset_contour(prof_dia, R, Q, side=-side)
    w_pts = [((z, x / 2.0), 'feed') for z, x in wrong]
    wg, wn, wterr, wunc = prove_region(centres(w_pts), segments, R, args.tol,
                                       side)
    wrong_ok = wg <= args.tol and wn > 0 and not wunc
    print('  wrong-side ctrl: gouge %.4f, %d tangent points, worst tangency '
          'err %.5f, %d segment(s) uncovered -> %s'
          % (wg, wn, wterr, len(wunc), 'PASS' if wrong_ok else 'FAIL'))

    if ok and not wrong_ok:
        print('[VERDICT: PASS] the nose rides the profile, and the wrong-side '
              'control correctly fails')
        return 0
    if ok and wrong_ok:
        print('[VERDICT: FAIL - the wrong-side control passes too, so this '
              'proof is not discriminating and tells you nothing]')
        return 1
    print('[VERDICT: FAIL - the nose does not ride the profile]')
    return 1


if __name__ == '__main__':
    sys.exit(main())
