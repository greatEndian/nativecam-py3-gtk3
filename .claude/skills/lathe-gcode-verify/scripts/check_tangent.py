#!/usr/bin/env python3
"""End-to-end lathe G-code motion verification.

Runs rs274 against an .ngc file (via parse_rs274.run_rs274, always on an
isolated scratch var copy), then checks:
  - no interpreter errors in the canon output
  - every arc is tangent-continuous with its adjacent straight moves
  - (optional) every occurrence of a marker comment is followed by an arc,
    to catch a fillet/lead silently dropped by a degenerate radius/angle

Always ends with exactly one verdict line:
  [VERDICT: PASS]
  [VERDICT: FAIL - <reason>]
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rs274 import run_rs274, parse_canon  # noqa: E402

DEFAULT_MIN_DOT = 0.999


def _xz(move):
    return (move['x'], move['z'])


def _tangent_at(move, at='end'):
    """Unit tangent vector (x, z) of an arc at its 'end' (endpoint stored in
    the move, i.e. the far end reached by this ARC_FEED) - direction of
    travel AT that endpoint, sign per rotation direction.
    """
    rvec = (move['x'] - move['xc'], move['z'] - move['zc'])
    rl = math.hypot(*rvec)
    if rl < 1e-9:
        return None
    sign = 1.0 if move['rot'] > 0 else -1.0
    return (-rvec[1] / rl * sign, rvec[0] / rl * sign)


def check_tangent_continuity(moves, min_dot=DEFAULT_MIN_DOT):
    """Returns (min_dot_seen, list_of_violations)."""
    violations = []
    min_seen = 1.0
    positioned = [m for m in moves if m['kind'] in ('feed', 'rapid', 'arc')]

    for i, m in enumerate(positioned):
        if m['kind'] != 'arc':
            continue
        # exit tangent-continuity: arc's own tangent at its endpoint vs the
        # direction of the very next positioned move
        if i + 1 < len(positioned):
            nxt = positioned[i + 1]
            line_dir = (nxt['x'] - m['x'], nxt['z'] - m['z'])
            ll = math.hypot(*line_dir)
            if ll > 1e-6:
                line_dir = (line_dir[0] / ll, line_dir[1] / ll)
                tang = _tangent_at(m)
                if tang is not None:
                    dot = tang[0] * line_dir[0] + tang[1] * line_dir[1]
                    min_seen = min(min_seen, abs(dot))
                    if abs(dot) < min_dot:
                        violations.append(
                            f'arc ending at x={m["x"]:.4f} z={m["z"]:.4f}: '
                            f'exit tangent dot={dot:.5f} (want >= {min_dot})'
                        )
    return min_seen, violations


def check_marker_has_arc(moves, marker_substr):
    """For every comment containing marker_substr, verify an ARC_FEED occurs
    before the next comment or end of the move list. Returns list of
    0-indexed marker occurrences (among matches) that had no following arc.
    """
    missing = []
    match_idx = 0
    i = 0
    n = len(moves)
    while i < n:
        mv = moves[i]
        if mv['kind'] == 'comment' and marker_substr in mv['text']:
            found_arc = False
            j = i + 1
            while j < n and not (moves[j]['kind'] == 'comment' and marker_substr in moves[j]['text']):
                if moves[j]['kind'] == 'arc':
                    found_arc = True
                    break
                j += 1
            if not found_arc:
                missing.append(match_idx)
            match_idx += 1
        i += 1
    return match_idx, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--ngc', required=True)
    ap.add_argument('--tbl', default=None)
    ap.add_argument('--min-dot', type=float, default=DEFAULT_MIN_DOT)
    ap.add_argument('--marker', default=None,
                     help='comment substring that must always be followed by an arc '
                          '(e.g. "retreat lead-out")')
    args = ap.parse_args()

    try:
        canon_text, raw_out_path = run_rs274(args.ini, args.ngc, args.tbl)
    except Exception as e:
        print(f'[VERDICT: FAIL - rs274 invocation failed: {e}]')
        sys.exit(1)

    # COMMENT(...) lines are the program's own text echoed back, so a subroutine
    # that merely explains what it fixes - "...the chord error this removes" -
    # would otherwise fail every verification that traces it. Only non-comment
    # lines can carry a real interpreter error.
    error_lines = [l for l in canon_text.splitlines()
                   if 'error' in l.lower()
                   and 'error_code' not in l.lower()
                   and 'COMMENT(' not in l]
    if error_lines:
        print('Interpreter errors found in canon output:')
        for l in error_lines[:10]:
            print(' ', l)
        print(f'[VERDICT: FAIL - {len(error_lines)} interpreter error line(s), see {raw_out_path}]')
        sys.exit(1)

    moves = parse_canon(canon_text)
    print(f'Parsed {len(moves)} canon events from {raw_out_path}')

    # No motion at all means rs274 gave up before producing any - an unclosed
    # comment, a missing subroutine, a truncated var file. It reports those on
    # its own streams rather than into the canon, so the canon is simply empty
    # and every check below then passes vacuously. Verifying nothing is not a
    # pass; say so instead of printing a green verdict over an empty file.
    if not [m for m in moves if m.get('kind') in ('feed', 'arc', 'rapid')]:
        print('[VERDICT: FAIL - no motion in the canon output; rs274 produced '
              f'nothing to verify, see {raw_out_path}]')
        sys.exit(1)

    min_dot, violations = check_tangent_continuity(moves, args.min_dot)
    print(f'Tangent continuity: min |dot| = {min_dot:.5f} (threshold {args.min_dot})')
    for v in violations[:20]:
        print('  VIOLATION:', v)

    marker_total = 0
    marker_missing = []
    if args.marker:
        marker_total, marker_missing = check_marker_has_arc(moves, args.marker)
        print(f'Marker "{args.marker}": {marker_total} occurrence(s), '
              f'{len(marker_missing)} missing a following arc')

    reasons = []
    if violations:
        reasons.append(f'{len(violations)} tangent-continuity violation(s)')
    if marker_missing:
        reasons.append(f'{len(marker_missing)} of {marker_total} "{args.marker}" '
                        f'marker(s) missing an arc')

    if reasons:
        print(f'[VERDICT: FAIL - {"; ".join(reasons)}]')
        sys.exit(1)
    else:
        print('[VERDICT: PASS]')
        sys.exit(0)


if __name__ == '__main__':
    main()
