#!/usr/bin/env python3
"""One-command proof that a generated lathe program's tool-tip compensation is
correct - a thin front-end over check_nose_tangent.py that fills in the tool
nose radius, orientation, target profile, comp side and free side for you.

It resolves everything it can automatically:
  - the tool table from the ini ([EMCIO] TOOL_TABLE)
  - the nose radius (= tool D/2) and orientation Q for the tool - taken from the
    tool actually loaded by the program's `T<n> M6`, or an explicit --tool
  - the target profile / comp side / free side from the op preset + its params

Then it runs the geometric tangency proof (nose circle rides the profile,
no gouge) and prints one verdict line.

Examples
--------
  # an OD taper: large dia 60, small dia 40, start Z 0, 45 degrees
  prove_tip_comp.py --ini lathe-mm.ini --ngc ncam.ngc \\
      --op taper_od --large-dia 60 --small-dia 40 --start-z 0 --angle 45

  # anything else: give the profile / side / free side yourself
  prove_tip_comp.py --ini lathe-mm.ini --ngc ncam.ngc --op raw \\
      --tool 2 --profile "0,20 -10,30" --side 42 --freeside right
"""
import argparse
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rs274 import run_rs274, parse_canon, _resolve_tbl_path  # noqa: E402
from check_nose_tangent import calibrate_offset, prove, parse_profile  # noqa: E402


# ----------------------------------------------------------------------------
# tool table lookup:  T<n> -> (nose radius = D/2, orientation Q)
# ----------------------------------------------------------------------------
def read_tool(tbl_path, tool_num):
    with open(tbl_path) as f:
        for line in f:
            row = line.split(';')[0]
            toks = row.split()
            fields = {t[0]: t[1:] for t in toks if len(t) > 1}
            if fields.get('T') == str(tool_num):
                dia = float(fields.get('D', '0') or '0')
                q = int(float(fields.get('Q', '0') or '0'))
                return dia / 2.0, q
    raise SystemExit(f'tool T{tool_num} not found in {tbl_path}')


def tool_from_ngc(ngc_path):
    """First tool loaded by a `T<n> M6` (or `T<n> ... M6`) in the program."""
    txt = open(ngc_path).read()
    m = re.search(r'\bT(\d+)\b[^\n]*\bM6\b', txt) or re.search(r'\bM6\b[^\n]*\bT(\d+)\b', txt)
    return int(m.group(1)) if m else None


# ----------------------------------------------------------------------------
# op presets: build (profile segments, comp side, free side) from op params
# radial x throughout (canon units); diameters are halved to radius.
# ----------------------------------------------------------------------------
def taper_profile(large_dia, small_dia, start_z, angle, od=True):
    """Reproduce the sub's finish wall: from (start_z, small_r) to (end_z, large_r).

    OD taper.ngc:   end_z = start_z - (large_r - small_r) * tan(90 - angle)
    ID taper_id.ngc uses TAN[angle - 90] = -TAN[90 - angle], so its wall
    deepens the OTHER way: end_z = start_z + (large_r - small_r) * tan(90 - angle).
    Both subs pick the comp side as: 42 when start_z < end_z else 41 (OD's rule
    inverted for ID). Free side tracks the side (proven by the tangency check):
    side 42 -> right-hand-normal free side, side 41 -> left."""
    large_r, small_r = large_dia / 2.0, small_dia / 2.0
    span = (large_r - small_r) * math.tan(math.radians(90 - angle))
    end_z = (start_z - span) if od else (start_z + span)
    segs = [((start_z, small_r), (end_z, large_r))]
    if od:
        # OD follows the turning convention: cutting toward -Z (start_z>end_z) = 42
        side = 42 if start_z > end_z else 41
    else:
        # ID inverts it (material is outside the bore)
        side = 42 if start_z < end_z else 41
    freeside = 'right' if side == 42 else 'left'
    return segs, side, freeside


def boring_profile(bore_dia, start_z, end_z):
    """boring.ngc finish wall: a straight bore at radius bore_dia/2 from
    start_z to end_z. Material is outside the bore; side inverts OD turning
    (41 default, 42 when start_z<end_z), free side tracks the side."""
    r = bore_dia / 2.0
    segs = [((start_z, r), (end_z, r))]
    side = 42 if start_z < end_z else 41
    freeside = 'right' if side == 42 else 'left'
    return segs, side, freeside


def facing_profile(begin_dia, end_dia, start_z, end_z):
    """facing.ngc finish face: the plane at Z=end_z spanning begin_r..end_r.
    z_factor = 1 (side 42) when start_z>end_z, else side 41; free side tracks
    the side. (The compensated finish skips the lead-in/out arcs.)"""
    br, er = begin_dia / 2.0, end_dia / 2.0
    segs = [((end_z, br), (end_z, er))]
    side = 42 if start_z > end_z else 41
    freeside = 'right' if side == 42 else 'left'
    return segs, side, freeside


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--ngc', required=True)
    ap.add_argument('--tbl', default=None, help='override tool table (else from ini)')
    ap.add_argument('--tool', type=int, default=None,
                     help='tool number (else auto-read from the program T<n> M6)')
    ap.add_argument('--op', required=True,
                     choices=('taper_od', 'taper_id', 'boring', 'facing', 'raw'),
                     help='op preset that fixes the profile/side/free side; '
                          '"raw" = give --profile/--side/--freeside yourself')
    # taper preset params
    ap.add_argument('--large-dia', type=float)
    ap.add_argument('--small-dia', type=float)
    ap.add_argument('--start-z', type=float)
    ap.add_argument('--end-z', type=float)
    ap.add_argument('--angle', type=float)
    # raw overrides
    ap.add_argument('--profile')
    ap.add_argument('--side', type=int, choices=(41, 42))
    ap.add_argument('--freeside', choices=('right', 'left'))
    ap.add_argument('--tol', type=float, default=1e-3)
    ap.add_argument('--var', default=None,
                     help='frozen known-good var snapshot (avoids the live '
                          'GUI-written var, which can be caught mid-write)')
    args = ap.parse_args()

    tbl = args.tbl or _resolve_tbl_path(os.path.abspath(args.ini), None)
    if not tbl or not os.path.exists(tbl):
        print(f'[VERDICT: FAIL - tool table not found ({tbl})]')
        sys.exit(1)

    tool_num = args.tool if args.tool is not None else tool_from_ngc(args.ngc)
    if tool_num is None:
        print('[VERDICT: FAIL - no --tool and no T<n> M6 found in the program]')
        sys.exit(1)
    R, Q = read_tool(tbl, tool_num)
    print(f'Tool T{tool_num}: nose radius R={R:.4f}, orientation Q={Q}')

    if args.op in ('taper_od', 'taper_id'):
        missing = [k for k in ('large_dia', 'small_dia', 'start_z', 'angle')
                   if getattr(args, k) is None]
        if missing:
            print(f'[VERDICT: FAIL - {args.op} needs --{" --".join(m.replace("_", "-") for m in missing)}]')
            sys.exit(1)
        segments, side, freeside = taper_profile(
            args.large_dia, args.small_dia, args.start_z, args.angle,
            od=(args.op == 'taper_od'))
    elif args.op == 'boring':
        if args.small_dia is None or args.start_z is None or args.end_z is None:
            print('[VERDICT: FAIL - boring needs --small-dia (bore dia) --start-z --end-z]')
            sys.exit(1)
        segments, side, freeside = boring_profile(args.small_dia, args.start_z, args.end_z)
    elif args.op == 'facing':
        missing = [k for k in ('large_dia', 'small_dia', 'start_z', 'end_z')
                   if getattr(args, k) is None]
        if missing:
            print(f'[VERDICT: FAIL - facing needs --{" --".join(m.replace("_", "-") for m in missing)}]')
            sys.exit(1)
        segments, side, freeside = facing_profile(
            args.large_dia, args.small_dia, args.start_z, args.end_z)
    else:
        if not (args.profile and args.side and args.freeside):
            print('[VERDICT: FAIL - --op raw needs --profile --side --freeside]')
            sys.exit(1)
        segments = parse_profile(args.profile)
        side, freeside = args.side, args.freeside

    freesign = 1 if freeside == 'right' else -1
    prof_str = ' '.join(f'{z:.4f},{x:.4f}' for z, x in
                        [segments[0][0]] + [s[1] for s in segments])
    print(f'Profile: {prof_str}   side G{side}.1   free={freeside}')

    if R <= 0:
        print('[VERDICT: FAIL - tool has zero nose radius (D=0); nothing to compensate]')
        sys.exit(1)

    try:
        offset = calibrate_offset(args.ini, tbl, R, Q, side, args.var)
    except Exception as e:
        print(f'[VERDICT: FAIL - calibration failed: {e}]')
        sys.exit(1)
    print(f'Calibrated offset(Q={Q}) = ({offset[0]:+.4f}, {offset[1]:+.4f}) [z,x]; '
          f'|offset|={math.hypot(*offset):.4f}')

    try:
        canon, raw = run_rs274(args.ini, args.ngc, tbl, var_path=args.var)
    except Exception as e:
        print(f'[VERDICT: FAIL - rs274 failed: {e}]')
        sys.exit(1)
    if 'error' in canon.lower() and 'error_code' not in canon.lower():
        print(f'[VERDICT: FAIL - interpreter errors, see {raw}]')
        sys.exit(1)

    moves = parse_canon(canon)
    max_gouge, ntan, terr, uncovered = prove(moves, segments, R, offset, args.tol, freesign)
    print(f'Tangent points: {ntan}; worst tangent err {terr:.6f}; '
          f'max gouge {max_gouge:.6f}; uncovered segs {uncovered} (tol {args.tol})')

    reasons = []
    if max_gouge > args.tol:
        reasons.append(f'gouge {max_gouge:.5f} > tol')
    if ntan == 0:
        reasons.append('no tangent contact - tool cutting air (comp off or wrong tool?)')
    if uncovered:
        reasons.append(f'{len(uncovered)} profile segment(s) never cut')
    if reasons:
        print(f'[VERDICT: FAIL - {"; ".join(reasons)}]')
        sys.exit(1)
    print('[VERDICT: PASS]')
    sys.exit(0)


if __name__ == '__main__':
    main()
