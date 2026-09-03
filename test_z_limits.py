#!/usr/bin/env python3
# coding: utf-8
"""A Z limit bounds the ROUGHING too, not just the contours.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG THIS EXISTS FOR

The Z limits trim the PROFILE, and every table built from it - finish,
pre-finish, entry, stop - inherits the trim. The roughing window did not:
`poly_lathe_mill` takes its extents from the RECORD ARRAY, which is built from
the raw polyline items and has never seen the trim.

A roughing level that does not cross the trimmed profile then had nothing to
stop it. Measured on testing_15_5 with End Z -40: six roughing FEED moves ran
the full bar, one of them **Z-0.4000 to Z-70.8000 at a constant X34.4371** -
30 mm of stock the limit was set to protect. The finishing passes stopped
correctly, so only half the program was wrong.

**It is a safety bug, not a cosmetic one.** A back limit is what you set to
keep the tool out of a chuck, a steady, or a second setup, and it was being
obeyed by the passes you can see in the plot and ignored by the roughing.

WHY IT SURVIVED: testing_15_2 obeys the same limit, because there every level
crosses the profile before reaching it and the window end never bites. One
project honoured the limit and one did not, which reads like a project quirk
until both are measured side by side. So both are measured here.

WHAT IS ASSERTED

1. THE LIMIT BITES, on the project that ignored it. Nothing reaches past it -
   and 15_5 now stops at the same Z as 15_2, which is the corroboration that
   the number is right and not merely smaller.
2. THE FRONT LIMIT BITES TOO. The same window, the other end.
3. NO LIMIT CHANGES NOTHING. `_pl_lim_on` is 0 and the clamp is skipped, so
   every project that sets no limit keeps the toolpath it has - asserted
   against the recorded baselines, not against itself.
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

# from analysis/071 and 072 - the motion of these projects with no limit set
BASELINE = {'testing_15_9.xml': ('6cf361a8b8f5', 1575),
            'testing_15_2.xml': ('e2744cbb6ff0', 327),
            'testing_15_5.xml': ('128ebb273ba5', 458)}


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(project, sets, tag, d):
    out = os.path.join(d, tag + '.ngc')
    cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
           '--out', out, '--config-copy']
    for kv in sets:
        cmd += ['--set', kv]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(out):
        return None
    import ncam_preview as P
    tp = P.parse_program(out, INI)
    if tp.error:
        return None
    mv = [m for m in tp.moves if m.op == 'Lathe Polyline']
    if not mv:
        return None
    key = ['%.5f %.5f %.5f %.5f %s' % (m.a[2], m.a[0], m.b[2], m.b[0], m.kind)
           for m in mv]
    # A LIMIT BOUNDS THE CUTTING, NOT THE TRAVEL. The tool still has to reach
    # its start point through air, so a rapid in front of a Front Z limit is
    # correct and expected - measuring every move made this test fail on a
    # rapid at Z0.0 while the feeds all began correctly at Z-20.4.
    fd = [m for m in mv if m.kind == 'feed']
    return dict(zmin=min(min(m.a[2], m.b[2]) for m in mv),
                fzmin=min(min(m.a[2], m.b[2]) for m in fd) if fd else None,
                fzmax=max(max(m.a[2], m.b[2]) for m in fd) if fd else None,
                n=len(mv),
                h=hashlib.md5('\n'.join(key).encode()).hexdigest()[:12])


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    d = tempfile.mkdtemp(prefix='zlim_')
    try:
        # 1. THE BACK LIMIT BITES, on both projects, at the same Z
        stops = {}
        for project in ('testing_15_5.xml', 'testing_15_2.xml'):
            r = run(project, ['polyline:param_e_z_on=1',
                              'polyline:param_e_z=-40'],
                    project[:-4] + '_ez', d)
            check('%s generates with End Z -40' % project, r is not None)
            if r is None:
                continue
            stops[project] = r['fzmin']
            # the lead-out and the nose take it a little past the trim; a whole
            # millimetre of slack is far tighter than the 30 mm this is about
            check('   %s: nothing runs past the End Z limit' % project,
                  r['zmin'] > -41.0,
                  'reaches Z%.4f against a -40 limit' % r['zmin'])
            check('   %s: and no CUT does either' % project,
                  r['fzmin'] is not None and r['fzmin'] > -41.0,
                  'a feed reaches Z%.4f' % r['fzmin'])
        if len(stops) == 2:
            a, b = stops.values()
            check('   and both projects stop at the same Z',
                  abs(a - b) < 1e-3,
                  '%.4f against %.4f' % (a, b))

        # 2. THE FRONT LIMIT BITES
        r = run('testing_15_5.xml', ['polyline:param_fr_z_on=1',
                                     'polyline:param_fr_z=-20'],
                'fz', d)
        check('testing_15_5 generates with Front Z -20', r is not None)
        if r is not None:
            check('   and nothing CUTS in front of the Front Z limit',
                  r['fzmax'] is not None and r['fzmax'] < -19.0,
                  'a feed reaches Z%.4f against a -20 limit' % r['fzmax'])

        # 3. NO LIMIT, NO CHANGE - against the recorded baselines
        for project, (want_h, want_n) in BASELINE.items():
            r = run(project, [], project[:-4] + '_base', d)
            check('%s generates with no limit' % project, r is not None)
            if r is None:
                continue
            check('   %s: no limit leaves the toolpath exactly as it was'
                  % project, r['h'] == want_h and r['n'] == want_n,
                  '%s/%d against the recorded %s/%d'
                  % (r['h'], r['n'], want_h, want_n))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('A Z limit bounds the roughing, and no limit changes nothing.')


if __name__ == '__main__':
    main()
