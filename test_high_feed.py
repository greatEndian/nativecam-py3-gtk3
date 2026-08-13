#!/usr/bin/env python3
# coding: utf-8
"""Positioning moves can be posted as G1, without a cut ever inheriting the rate.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 23 of `POLYLINE-GAPS.md`. The reference package: *"Specifies when rapid
movements should be output as true rapids (G0) and when they should be output as
high feedrate movements (G1)"*, six choices, *"usually set to avoid collisions at
rapids on machines which perform 'dogleg' movements at rapid."*

THE DOGLEG REASON DOES NOT APPLY HERE, and the tooltip says so rather than
implying a safety benefit this cannot deliver. Measured on testing_15_5: 148
positioning moves, 99 radial, 49 axial, and **0 moving both axes**. A
single-axis G0 is a straight line on every control, so there is nothing here to
dogleg - on LinuxCNC or anywhere else. Three of the six choices - preserve all,
preserve axial and radial, preserve single-axis - are therefore the same thing
on this output, and are offered only so a setting carries its meaning across
from the package it was copied from. What earns its place is posting the moves
as G1 where G0 positions faster or harder than wanted near a fixture.

THE RISK IS THE MODAL FEED, not the geometry. F is modal, so a G1 issued at the
high feed leaves it set, and lathe_level_pass has a path where the level cut
takes whatever F was last set - with the profile-angle approach off, nothing
names a feed between the positioning move and the cut. A leak there would run a
CUT at positioning speed. So `hf_move` puts the caller's feed back, and the case
below counts high-feed moves against converted moves: equal means no leak, and
any excess is a cut running at the wrong rate.

THE FIRST ASSERTION IS THE ONE THAT MATTERS: the default preserves every rapid
and must be byte-identical, because a feature that quietly re-posts every
existing project's rapids as feeds is worse than one that is missing.
"""
import hashlib
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
PROJECT = 'testing_15_5.xml'
HF = 800.0
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build(sets):
    d = tempfile.mkdtemp(prefix='hf_')
    out = os.path.join(d, 'o.ngc')
    cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
           '--out', out, '--config-copy']
    for kv in sets:
        cmd += ['--set', kv]
    subprocess.run(cmd, capture_output=True, text=True)
    return d, (out if os.path.isfile(out) else None)


def moves(sets):
    """-> (count, hash, rapids, radial rapids, axial rapids) or None."""
    import ncam_preview as P
    d, out = build(sets)
    try:
        if out is None:
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline']
        key = [(m.kind, round(m.a[0], 4), round(m.a[2], 4),
                round(m.b[0], 4), round(m.b[2], 4)) for m in mv]
        rap = [m for m in mv if m.kind == 'rapid']
        return (len(mv),
                hashlib.sha1(repr(key).encode()).hexdigest()[:12],
                len(rap),
                sum(1 for m in rap if abs(m.b[0] - m.a[0]) > 1e-6),
                sum(1 for m in rap if abs(m.b[2] - m.a[2]) > 1e-6))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def high_feed_cuts(sets):
    """How many interpreted feed moves run at the high rate, or None."""
    d, out = build(sets)
    try:
        if out is None:
            return None
        r = subprocess.run(['rs274', '-g', '-b', '-i', INI, out],
                           capture_output=True, text=True,
                           cwd=os.path.dirname(INI), timeout=400)
        feed, hi = None, 0
        for ln in r.stdout.splitlines():
            m = re.search(r'SET_FEED_RATE\(([-0-9.]+)\)', ln)
            if m:
                feed = float(m.group(1))
                continue
            if 'STRAIGHT_FEED' in ln or 'ARC_FEED' in ln:
                if feed is not None and abs(feed - HF) < 1e-6:
                    hi += 1
        return hi
    except Exception:
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    base = moves([])
    check('the project generates with the default mode', base is not None)
    if base is None:
        sys.exit(1)
    n0, h0, r0, x0, z0 = base
    print('      default  %d moves, %s, %d rapids (%d radial, %d axial)'
          % (n0, h0, r0, x0, z0))

    # THE FACT THE FEATURE IS SHAPED AROUND, asserted rather than assumed:
    # nothing this operation emits moves both axes at rapid, so nothing doglegs.
    check('no positioning move travels both axes', x0 + z0 == r0,
          '%d radial + %d axial != %d rapids, so some move both and the '
          'dogleg case IS live here' % (x0, z0, r0))

    def same(mode, label):
        r = moves(['polyline:param_hf_mode=%d' % mode,
                   'polyline:param_hf_feed=%s' % HF])
        check('   %s is byte-identical to the default' % label,
              r is not None and r[1] == h0 and r[2] == r0,
              'hash %s against %s' % (r[1] if r else '?', h0))

    # a rate alone must not convert anything - the mode is what asks for it
    idle = moves(['polyline:param_hf_feed=%s' % HF])
    check('a high feedrate with the default mode changes NOTHING',
          idle is not None and idle[1] == h0,
          'setting only the rate re-posted the program')
    same(0, 'preserve all')
    same(1, 'preserve axial and radial')
    same(4, 'preserve single-axis')

    # the three that do something
    for mode, label, keep_x, keep_z in ((2, 'preserve axial only', 0, z0),
                                        (3, 'preserve radial only', x0, 0),
                                        (5, 'always high feed', 0, 0)):
        r = moves(['polyline:param_hf_mode=%d' % mode,
                   'polyline:param_hf_feed=%s' % HF])
        if r is None:
            check('%s generates' % label, False)
            continue
        n, _h, rap, xr, zr = r
        print('      %-22s %d rapids left (%d radial, %d axial)'
              % (label, rap, xr, zr))
        check('%s converts what it says' % label,
              xr <= keep_x + 4 and zr <= keep_z + 4
              and (keep_x or xr < x0) and (keep_z or zr < z0),
              'radial %d (keep %d), axial %d (keep %d)'
              % (xr, keep_x, zr, keep_z))
        # THE GEOMETRY MAY NOT MOVE - a G1 rapid goes where the G0 went
        check('   %s moves the tool to the same places' % label, n == n0,
              '%d moves against %d' % (n, n0))
        # AND NO CUT MAY INHERIT THE RATE
        hi = high_feed_cuts(['polyline:param_hf_mode=%d' % mode,
                             'polyline:param_hf_feed=%s' % HF])
        conv = r0 - rap
        check('   %s leaks the rate into no cut' % label, hi == conv,
              '%s moves run at the high feed for %d converted - the modal '
              'feed is leaking into cuts' % (hi, conv))

    # always high feed must leave nothing behind
    allhf = moves(['polyline:param_hf_mode=5',
                   'polyline:param_hf_feed=%s' % HF])
    check('always high feed leaves NO rapid in the operation',
          allhf is not None and allhf[2] == 0,
          '%d rapids remain' % (allhf[2] if allhf else -1))

    # a mode with no rate must stay on true rapids - G1 F0 stops the machine
    norate = moves(['polyline:param_hf_mode=5'])
    check('a mode with no rate set stays on true rapids',
          norate is not None and norate[1] == h0,
          'converted without a feed, which would post G1 F0')

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Positioning posts as asked, and no cut inherits the rate.')


if __name__ == '__main__':
    main()
