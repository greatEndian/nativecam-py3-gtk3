#!/usr/bin/env python3
"""Run rs274 against an .ngc file and parse its canon output into a move list.

Always runs against a scratch copy of the var file - never the live one
passed in. A crashed/interrupted rs274 run can permanently corrupt real
machine coordinate offsets (lathe.var), so this is not optional.
"""
import argparse
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def _find_ini_value(ini_path, section, key):
    parser = configparser.ConfigParser(strict=False)
    with open(ini_path) as f:
        text = f.read()
    parser.read_string(text)
    return parser.get(section, key, fallback=None)


def _resolve_var_path(ini_path, var_arg):
    if var_arg:
        return var_arg
    ini_dir = os.path.dirname(os.path.abspath(ini_path))
    param_file = _find_ini_value(ini_path, 'RS274NGC', 'PARAMETER_FILE') \
        or _find_ini_value(ini_path, 'EMC', 'PARAMETER_FILE')
    if not param_file:
        raise SystemExit('Could not find PARAMETER_FILE in ini - pass --var explicitly')
    return os.path.join(ini_dir, param_file)


def _resolve_tbl_path(ini_path, tbl_arg):
    if tbl_arg:
        return tbl_arg
    ini_dir = os.path.dirname(os.path.abspath(ini_path))
    tool_file = _find_ini_value(ini_path, 'EMCIO', 'TOOL_TABLE')
    if not tool_file:
        return None
    return os.path.join(ini_dir, tool_file)


def run_rs274(ini_path, ngc_path, tbl_path=None, scratch_dir=None, var_path=None):
    """Run rs274 in batch mode against ngc_path, on an isolated scratch copy
    of a var file. Returns the raw canon output text.

    var_path lets the caller point at a FROZEN, known-good var (a one-time
    snapshot) instead of the ini's live var. The live lathe.var is written by
    the running GUI, so copying it can catch a truncated mid-write file that
    aborts rs274 early - a frozen copy removes that flakiness while still
    honouring the 'never touch the live var' rule.
    """
    # rs274 must run with cwd = the ini's own directory (SUBROUTINE_PATH and
    # other ini entries are relative to it) - so any relative ngc/output path
    # must be absolutized against the CALLER's cwd first, before that switch.
    ini_path = os.path.abspath(ini_path)
    ngc_path = os.path.abspath(ngc_path)

    real_var = os.path.abspath(var_path) if var_path else _resolve_var_path(ini_path, None)
    tbl_path = _resolve_tbl_path(ini_path, tbl_path)

    scratch_dir = scratch_dir or tempfile.mkdtemp(prefix='lathe_gcode_verify_')
    scratch_var = os.path.join(scratch_dir, 'scratch.var')
    shutil.copy(real_var, scratch_var)

    out_path = os.path.join(scratch_dir, 'rs274_canon.out')
    cmd = ['rs274', '-i', ini_path, '-v', scratch_var, '-b', '-g']
    if tbl_path and os.path.exists(tbl_path):
        cmd += ['-t', tbl_path]
    cmd += [ngc_path, out_path]

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(ini_path)),
                             capture_output=True, text=True, timeout=120)
    if not os.path.exists(out_path):
        raise RuntimeError(
            f'rs274 produced no output file. stdout:\n{result.stdout}\nstderr:\n{result.stderr}'
        )
    with open(out_path) as f:
        canon_text = f.read()
    return canon_text, out_path


def parse_canon(canon_text):
    """Parse rs274 -g canon dump into a flat move list.

    Each entry is a dict: {'kind': 'feed'|'rapid'|'arc'|'comment', ...}
    Lathe (G18) convention: canon's first axis is X, third is Z.
    """
    moves = []
    for line in canon_text.splitlines():
        m = re.search(r'STRAIGHT_FEED\(([^)]*)\)', line)
        if m:
            v = [float(x) for x in m.group(1).split(',')]
            moves.append({'kind': 'feed', 'x': v[0], 'z': v[2]})
            continue
        m = re.search(r'STRAIGHT_TRAVERSE\(([^)]*)\)', line)
        if m:
            v = [float(x) for x in m.group(1).split(',')]
            moves.append({'kind': 'rapid', 'x': v[0], 'z': v[2]})
            continue
        m = re.search(r'ARC_FEED\(([^)]*)\)', line)
        if m:
            v = [float(x) for x in m.group(1).split(',')]
            # ARC_FEED(line, first_end, second_end, first_axis_center,
            #           second_axis_center, rotation, axis_end_point, ...)
            # In G18: first_end=Z, second_end=X, centers likewise.
            moves.append({
                'kind': 'arc',
                'z': v[0], 'x': v[1],
                'zc': v[2], 'xc': v[3],
                'rot': v[4],
            })
            continue
        m = re.search(r'COMMENT\("([^"]*)"\)', line)
        if m:
            moves.append({'kind': 'comment', 'text': m.group(1)})
            continue
    return moves


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--ngc', required=True)
    ap.add_argument('--tbl', default=None)
    ap.add_argument('--out', default=None, help='write parsed move list as JSON here')
    args = ap.parse_args()

    canon_text, raw_out_path = run_rs274(args.ini, args.ngc, args.tbl)
    moves = parse_canon(canon_text)

    if 'ERROR' in canon_text.upper() and 'error' not in ('',):
        pass  # surfaced via moves/verdict layer, not here

    payload = {'raw_canon_file': raw_out_path, 'move_count': len(moves), 'moves': moves}
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(payload, f, indent=2)
    else:
        json.dump(payload, sys.stdout, indent=2)


if __name__ == '__main__':
    main()
