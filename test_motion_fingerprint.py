#!/usr/bin/env python3
# coding: utf-8
"""Every lathe project's motion, as one sha1 per project. A tool, not a gate.

Standalone, like the other test_*.py here - run it directly, no pytest.

    python3 test_motion_fingerprint.py --write before.txt   # record
    ...make a change...
    python3 test_motion_fingerprint.py --baseline before.txt

WHY. A change that is meant to move nothing has to be shown to move nothing, on
every project rather than the six a hand-picked gate sweeps. This was the
primary check behind analysis/115-118 - it is what said "43 of 46 identical, and
the only three that changed are the three that were broken" - and it caught a
stale baseline that had produced a false "all 36 differ".

It is deliberately NOT in the suite: it takes ~10 minutes and needs a baseline
recorded from the tree you are comparing against, which is a decision, not a
constant. Record it before you start, not after.

The fingerprint covers kind, both endpoints and the move's category. It does
not cover feed, speed or comments - a change that alters only those is invisible
here, by design.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = os.path.join(HERE,
                        'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects')


def fingerprint():
    import ncam_preview as P
    work = tempfile.mkdtemp(prefix='fingerprint_')
    rows = {}
    for pr in sorted(f for f in os.listdir(PROJECTS) if f.endswith('.xml')):
        out = os.path.join(work, pr[:-4] + '.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project', pr,
                        '--out', out, '--config-copy'],
                       capture_output=True, text=True, timeout=900)
        if not os.path.isfile(out):
            rows[pr] = ('NOGEN', '-')
            continue
        tp = P.parse_program(out, INI)
        h = hashlib.sha1()
        for m in tp.moves:
            h.update(('%s %.5f %.5f %.5f %.5f %s\n'
                      % (m.kind, m.a[0], m.a[2], m.b[0], m.b[2],
                         m.cat)).encode())
        rows[pr] = (str(len(tp.moves)), h.hexdigest()[:12])
        print('%-34s %8s %s' % (pr, rows[pr][0], rows[pr][1]), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', help='record the fingerprint to this file')
    ap.add_argument('--baseline', help='compare against a recorded fingerprint')
    args = ap.parse_args()
    if not os.path.isdir(PROJECTS):
        print('NO PROJECT DIRECTORY - nothing was measured')
        return 1
    rows = fingerprint()
    if not rows:
        print('NO PROJECTS FOUND - the sweep measured nothing')
        return 1
    if args.write:
        with open(args.write, 'w') as fh:
            for pr in sorted(rows):
                fh.write('%s %s %s\n' % (pr, rows[pr][0], rows[pr][1]))
        print('\nwrote %d projects to %s' % (len(rows), args.write))
        return 0
    if not args.baseline:
        print('\n%d projects. Pass --write to record or --baseline to compare.'
              % len(rows))
        return 0
    base = {}
    for line in open(args.baseline):
        f = line.split()
        if len(f) >= 3:
            base[f[0]] = (f[1], f[2])
    # A baseline that predates the tree is the failure this has already had:
    # before.txt was five commits stale once and produced a false "all differ".
    missing = [p for p in rows if p not in base]
    changed = [p for p in sorted(rows) if p in base and base[p] != rows[p]]
    for pr in changed:
        print('CHANGED %-34s %s -> %s' % (pr, base[pr], rows[pr]))
    print('\n%d identical, %d changed, %d not in the baseline, of %d'
          % (len(rows) - len(changed) - len(missing), len(changed),
             len(missing), len(rows)))
    return 1 if changed or missing else 0


if __name__ == '__main__':
    sys.exit(main())
