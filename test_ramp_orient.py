#!/usr/bin/env python3
# coding: utf-8
"""A profile-angle ramp is armed only where the tool can cut that way.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG THIS EXISTS FOR

The ramp exists to arrive PARALLEL to a surface, which needs the tool to meet
that surface with its CUTTING edge. Nothing in the ramp path asked whether it
could: `entry_ramp_dirs` saw the profile alone, and `o<pa_side>` in
lathe_level_pass tests only that the approach comes from the stock side
RADIALLY - a different question, which never says which END the tool may
approach from. So a ramp was armed wherever the geometry allowed one, whichever
way the insert faced.

greatEndian, 2026-09-01, on the back-most section of testing_15_9 roughed back
to front: *"it should not be there there should be just the generic lead in/out
.. but there is the catch, if we have tool which is mirrored in the X axis and
if we have taper character part we have to create same behaviours"*.

WHAT IS ASSERTED, and why the pair is the point

The fix is `_pl_ramp_face`: +1 or -1 for the direction the insert cuts along Z,
0 for a facing or on-the-point tool with no axial preference. A ramp is armed
only where the pass TRAVELS that way.

  1. testing_15_9 with T2 (Q2, the ordinary right-hand OD tool, face -1)
     roughed BACK TO FRONT loses all 18 of its ramps - the reported case.
  2. FRONT TO BACK it keeps all 15 - the tool cuts that way, so nothing changes.
  3. The SAME PROJECT with the tool table's only difference being Q2 -> Q1 -
     the insert mirrored about the X axis, face +1 - gets all 18 ramps BACK
     when roughed back to front, and loses its 15 going front to back.

THE CONTROL IS THE SHIPPED PAIR, and that is a correction. When this test was
written, assertion 3 was the control: the mirrored insert got its 18 ramps back,
which is what stopped "0 ramps" being indistinguishable from "the ramps were
deleted". That is no longer true. Once `flank_sides` learned the insert too
(analysis/071) the mirrored tool's reachable envelope flips with it - the entry
contour on testing_15_9 halves, 40 segments to 20 - and no level arms a ramp on
it at all, so the mirrored half now reads 0 in both directions.

What still discriminates:

  * the SHIPPED pair, 0 back to front against 15 front to back. A blanket
    "delete the ramps" fails that immediately.
  * `_pl_ramp_face` itself, -1 shipped and +1 mirrored, asserted below.
  * `test_flank_envelope`'s wiring check, which requires the emitted flank
    table to MOVE when the insert is mirrored - that is what proves the
    orientation actually reaches the geometry rather than being dead code.

The mirrored zeros are recorded here as a measured consequence, not as
evidence. Whether a mirrored insert SHOULD lose every ramp on this part is
consistent with the tables and has not been independently proven - it is an
open point.

The two halves run from a scratch copy of the config whose tool table has
exactly one character changed, so nose radius, both flank angles and every
parameter are identical and the orientation is the only variable.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CFG = os.path.join(HERE, 'configs/sim/axis/ncam_demo')
INI = os.path.join(CFG, 'lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def ramps_of(ngc, ini):
    """Shallow feeds - the profile-angle ramps - in the ROUGHING passes.

    A lead-in is 45 degrees by construction, so |dz| over |dx| separates the
    two with no angle assumed. `not m.subs` keeps the finish contour out: its
    long shallow moves would otherwise count as ramps.
    """
    import ncam_preview as P
    tp = P.parse_program(ngc, ini)
    if tp.error:
        return None
    out = []
    for m in tp.moves:
        if m.op != 'Lathe Polyline' or m.subs or m.kind != 'feed':
            continue
        dz, dx = abs(m.b[2] - m.a[2]), abs(m.b[0] - m.a[0])
        if dx > 1e-6 and dz > dx * 1.5:
            out.append(m)
    return out


def run(cfgdir, direction, tag, d):
    ini = os.path.join(cfgdir, 'lathe-mm.ini')
    out = os.path.join(d, tag + '.ngc')
    subprocess.run([sys.executable, GEN, '--ini', ini, '--project',
                    'testing_15_9.xml', '--out', out,
                    '--set', 'polyline:param_dir=%d' % direction],
                   capture_output=True, text=True)
    if not os.path.isfile(out):
        return None, None
    face = re.findall(r'#<_pl_ramp_face> = ([-\d]+)', open(out).read())
    return ramps_of(out, ini), (int(face[-1]) if face else None)


def main():
    if not (os.path.isdir(CFG) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    d = tempfile.mkdtemp(prefix='rorient_')
    mirror = os.path.join(d, 'mirrored_cfg')
    try:
        # THE ONLY DIFFERENCE IS Q. Copied with symlinks preserved, because the
        # config's ncam/ directory links back into the repo and following those
        # would detach the copy from the cfg and lib being tested.
        shutil.copytree(CFG, mirror, symlinks=True)
        tbl = os.path.join(mirror, 'lathe_mm.tbl')
        txt = open(tbl).read()
        swapped = txt.replace('J75.000000  Q2', 'J75.000000  Q1')
        check('the tool table can be mirrored for the control',
              swapped != txt, 'T2 Q2 not found in ' + tbl)
        if swapped == txt:
            return
        open(tbl, 'w').write(swapped)

        for cfgdir, label, want_face, want in (
                (CFG, 'T2 as shipped (Q2)', -1, {1: 0, 0: 15}),
                (mirror, 'T2 mirrored to Q1', 1, {1: 0, 0: 0})):
            for direction in (1, 0):
                rs, face = run(cfgdir, direction, '%s_%d' % (
                    os.path.basename(cfgdir), direction), d)
                way = 'back to front' if direction == 1 else 'front to back'
                check('%s, %s: generates and runs' % (label, way),
                      rs is not None)
                if rs is None:
                    continue
                check('   %s, %s: the insert reports face %+d'
                      % (label, way, want_face),
                      face == want_face, 'got %s' % face)
                check('   %s, %s: %d ramps' % (label, way, want[direction]),
                      len(rs) == want[direction],
                      'got %d' % len(rs))
                if rs:
                    lens = [((m.b[2] - m.a[2]) ** 2
                             + (m.b[0] - m.a[0]) ** 2) ** 0.5 for m in rs]
                    check('   %s, %s: and they are all the standard length'
                          % (label, way),
                          max(lens) - min(lens) < 0.01,
                          '%.4f .. %.4f' % (min(lens), max(lens)))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The ramp follows the tool: armed only where the insert can cut.')


if __name__ == '__main__':
    main()
