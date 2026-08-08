#!/usr/bin/env python3
# coding: utf-8
"""Every profile-angle ramp arrives at the same angle, from the stock side.

Standalone, like the other test_*.py here - run it directly, no pytest.

The ramp is the short approach that lets a roughing level arrive PARALLEL to
the surface it is about to run along, instead of driving in at 45 degrees. It
had three sources of its angle - the crossing that set the pass's start, the
nearest crossing, and a Python table - and nothing asserted which one fires
where. Two faults got through in one day because of that, both found by
greatEndian in the GUI rather than here:

  * the ramp behind the boss came out 2.9656 long against its neighbours'
    2.2004, because it copied the short shallow scrap of fillet the pass
    happened to START on;
  * then 8.9734, because the crossing it preferred landed on the near-FLAT
    top of the boss, slope 0.0566;
  * and on the front passes a ramp was armed pointing INTO the part, so the
    lead-in dived to the next pass's level and climbed back out - the doubled
    lead-in.

WHAT IS ASSERTED

1. ONE ANGLE. Every ramp in a program has the same slope. That is the whole of
   greatEndian's criterion - "has to have same parameters as each other one, no
   extra length" - and it is the property all three faults broke.

2. SHORTER IS ALLOWED, LONGER IS NOT. A pass too short to fit a full ramp gets
   a proportionally shortened one at the same angle, which is deliberate. So
   the bound is on length, not on equality.

3. A RAMP NEVER STARTS INSIDE THE CUT. Its whole purpose is to come in through
   material that has already gone, so it must begin on the stock side of the
   level it is entering. This is the doubled lead-in, stated directly.

Not circular: the angle is not compared against the table Python emitted, only
against the OTHER ramps in the same program, read back out of rs274. A table
that changed every ramp together would still have to keep them equal.
"""
import collections
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = ('testing_15_5.xml', 'testing_15_4.xml', 'testing_15_2.xml')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def ramps(mv):
    """(index, dz, dr) of every ramp - a feed shallower than 45 degrees.

    A lead-in is 45 degrees by construction, so |dz| over |dr| tells the two
    apart with no angle assumed: 1.5 is well clear of both the lead-in's 1.0
    and the shallowest ramp seen on any of these projects, 4.3.
    """
    out = []
    for i, m in enumerate(mv):
        if m.kind != 'feed':
            continue
        dz, dr = abs(m.b[2] - m.a[2]), abs(m.b[0] - m.a[0])
        if dr > 1e-6 and dz > dr * 1.5:
            out.append((i, dz, dr))
    return out


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='ramps_')
    total = 0
    try:
        for project in PROJECTS:
            for sect in (1, 0):
                tag = '%s sect=%d' % (project[:-4], sect)
                out = os.path.join(d, '%s_%d.ngc' % (project[:-4], sect))
                subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                                project, '--out', out, '--config-copy', '--set',
                                'polyline:param_sectioning=%d' % sect],
                               capture_output=True, text=True)
                if not os.path.isfile(out):
                    check('%s generates' % tag, False)
                    continue
                tp = P.parse_program(out, INI)
                check('%s runs' % tag, not tp.error, str(tp.error)[:120])
                if tp.error:
                    continue
                mv = [m for m in tp.moves
                      if m.op == 'Lathe Polyline' and not m.subs]
                rs = ramps(mv)
                check('%s has ramps at all' % tag, len(rs) > 2,
                      '%d - nothing to compare' % len(rs))
                if len(rs) <= 2:
                    continue
                total += len(rs)

                # 1. ONE ANGLE
                slopes = [round(dr / dz, 3) for _i, dz, dr in rs]
                spread = max(slopes) - min(slopes)
                check('%s every ramp arrives at the same angle' % tag,
                      spread < 0.002,
                      'slopes %s' % dict(collections.Counter(slopes)))

                # 2. SHORTER IS ALLOWED, LONGER IS NOT
                lens = [round(dz, 4) for _i, dz, _dr in rs]
                full = max(collections.Counter(lens).items(),
                           key=lambda kv: kv[1])[0]
                over = [x for x in lens if x > full + 1e-3]
                check('   %s and none is longer than the standard one' % tag,
                      not over,
                      'standard %.4f, but %s' % (full, sorted(set(over))))

                # 3. A RAMP NEVER STARTS INSIDE THE CUT
                inside = []
                for i, _dz, _dr in rs:
                    nxt = None
                    for m in mv[i + 1:i + 3]:
                        if m.kind == 'feed' and abs(m.b[0] - m.a[0]) < 1e-6 \
                                and abs(m.b[2] - m.a[2]) > 1e-6:
                            nxt = m
                            break
                    if nxt is None:
                        continue
                    # OD: the stock side is the larger radius
                    if mv[i].a[0] < nxt.a[0] - 1e-4:
                        inside.append((mv[i].a[0], nxt.a[0]))
                check('   %s and none starts inside the level it enters' % tag,
                      not inside,
                      'a ramp starts at r%.4f to enter r%.4f - it dives into '
                      'the part and climbs back out'
                      % inside[0] if inside else '')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    print('%d ramps checked' % total)
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every ramp arrives at one angle, from the stock side.')


if __name__ == '__main__':
    main()
