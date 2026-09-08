#!/usr/bin/env python3
# coding: utf-8
"""The roughing stop surface and the finishing contour are ONE surface.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHY THIS EXISTS. lathe_sections builds the back-angle envelope twice: once for
the FLANK table (`_pl_env_*`, 3600), which roughing stops against, and once for
the FINISH contour table (`_pl_fc_*`, 4000), which the contour passes trace.
The comment above the flank call says what the relationship has to be -

    "Cleaned exactly as the finishing contour is, and for the same reason.
     Roughing stops against THIS surface while the contour passes follow the
     cleaned one; if the two differ, roughing eats into the pre-finish
     allowance at every sawtooth valley. One surface, both users."

- and for a long time they did differ, because `_min_segment`'s `protect`
argument was passed at the finishing call site and not at the flank one. The
invariant lived only in that comment, and nothing checked it. This does.

WHAT IS ASSERTED

Every point of the finishing contour appears in the flank envelope. Containment,
not set equality: the envelope may legitimately carry points the contour does
not, and does.

It is deliberately a check on the SHIPPED TABLES, read back out of the generated
program, rather than on the functions that build them. The bug was a missing
argument at one call site - both functions were correct - so a unit test on
either would have passed while the program went out wrong.

WHAT IT COST WHEN IT WAS WRONG, measured on testing_13_arc_first (analysis/116):
the envelope dropped three corners the contour kept - 0.0186, 0.6270 and 0.9338
mm - leaving `Z-50.9261 R27.0614 -> Z-69.9998 R28.0000`, a 19 mm phantom ramp
where the part is a flat R28 cylinder. Roughing ran 8.96 mm past the corner and
cut 0.49 mm into a finished surface.

WHAT IS NOT COVERED

The stop contour (`_pl_stop_*`, 4400) is a third table and a different surface -
the pre-finish contour - so it is not compared here.

The two envelopes are not built from identical inputs: the finishing one also
takes a front-flank angle and uses `fin_dir` where the flank one uses
`rough_dir`. Containment holds across the whole catalogue regardless, and it is
the documented intent, so it is asserted straight. Should a front-flank project
ever break it, that is the intent no longer holding and worth being told about,
which is exactly what this will say.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = os.path.join(HERE,
                        'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects')
ENV_BASE, FC_BASE = 3600, 4000
QUANT = 4

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def table(src, count_name, base):
    """One point table as [(z, x)], straight out of the generated program."""
    m = [x for x in re.finditer(r'#<%s>\s*=\s*(\d+)' % count_name, src)]
    if not m:
        return []
    # the defaults block assigns every global first, so it is the LAST
    # assignment that carries the value this program actually runs with
    n = int(m[-1].group(1))
    v = {int(x.group(1)): float(x.group(2))
         for x in re.finditer(r'^#(\d+) = ([-0-9.]+)', src, re.M)}
    pts = [(v.get(base + 2 * k), v.get(base + 2 * k + 1)) for k in range(n)]
    return [p for p in pts if p[0] is not None and p[1] is not None]


def missing(env, fc):
    """Points of fc that are not vertices of env."""
    have = set((round(z, QUANT), round(x, QUANT)) for z, x in env)
    return [p for p in fc if (round(p[0], QUANT), round(p[1], QUANT)) not in have]


def self_check():
    """The comparator must be able to FAIL. A gate that cannot is not a gate,
    and two vacuous passes in this project's history were only found later."""
    env = [(0.0, 8.0), (-1.0, 9.0), (-2.0, 9.0)]
    fc = list(env)
    ok_empty = not missing(env, fc)
    dropped = missing([env[0], env[2]], fc)
    check('the comparator reports an identical pair as contained', ok_empty,
          'it flagged points that are present')
    check('the comparator catches a dropped point',
          len(dropped) == 1 and abs(dropped[0][0] + 1.0) < 1e-9,
          'a point removed from the envelope was not reported')


def main():
    self_check()
    if not os.path.isdir(PROJECTS):
        print('NO PROJECT DIRECTORY - nothing was compared')
        return 1
    work = tempfile.mkdtemp(prefix='surface_eq_')
    compared = both = 0
    for pr in sorted(f for f in os.listdir(PROJECTS) if f.endswith('.xml')):
        out = os.path.join(work, pr[:-4] + '.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project', pr,
                        '--out', out, '--config-copy'],
                       capture_output=True, text=True, timeout=900)
        if not os.path.isfile(out):
            continue
        src = open(out).read()
        env = table(src, '_pl_env_count', ENV_BASE)
        fc = table(src, '_pl_fc_n', FC_BASE)
        compared += 1
        if not env or not fc:
            continue
        both += 1
        miss = missing(env, fc)
        if miss:
            check('%s: the flank envelope holds every finishing point' % pr,
                  False,
                  '%d of %d missing, e.g. Z%.4f R%.4f - roughing stops against '
                  'a surface the finishing pass does not follow'
                  % (len(miss), len(fc), miss[0][0], miss[0][1]))
    # A zero count is the failure mode this project has actually shipped twice:
    # 30 configurations reporting PASS over 0 answers. Never pass on nothing.
    check('projects were generated at all', compared > 0,
          'nothing generated - the sweep measured nothing')
    check('projects carrying both tables were compared', both > 0,
          'no project produced a flank AND a finishing table, so the '
          'containment was never actually tested')
    print('\n%d projects generated, %d with both tables compared' % (compared, both))
    if FAILED:
        print('\nFAILED: %d\n   -  %s' % (len(FAILED), '\n   -  '.join(FAILED)))
        return 1
    print('One surface, both users.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
