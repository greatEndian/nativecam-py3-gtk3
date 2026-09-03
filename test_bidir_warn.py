#!/usr/bin/env python3
# coding: utf-8
"""Both directions warns on a directional insert, and proceeds anyway.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHY THE WARNING EXISTS

Bi-directional roughing alternates the cutting direction every pass. That only
works with a neutral insert: an LH or RH tool rubs in the opposite direction,
which is why Sandvik had to build purpose-made all-directional geometries for
PrimeTurning rather than reuse ordinary ones. NativeCAM's `Both directions`
assumed a neutral tool and never checked, so with the demo T2 (Q2, an ordinary
right-hand OD insert) half the passes ran with the trailing flank leading.

greatEndian chose warn-and-proceed over refusing, 2026-09-01: a saved project
must keep generating, and the tool table cannot express every real holder - the
insert in the machine may be neutral even when Q says otherwise.

WHAT IS ASSERTED

1. IT FIRES where the insert cannot cut the direction asked for: `param_dir`
   = 2 with any directional insert, and a single direction that opposes the
   insert's own - Q2, which cuts toward -Z, roughed BACK TO FRONT.
2. IT STAYS QUIET otherwise - Q2 in its OWN direction, front to back, and a
   NEUTRAL insert in every direction. Assertion 2 is what stops this being a
   warning that always fires, which would be worth nothing.
   The truth table `wrong_way_dirs` produces, and which this pins:
       orient 2 (cuts -Z)   dir 0 quiet   dir 1 WARNS   dir 2 WARNS
       orient 9 (neutral)   dir 0 quiet   dir 1 quiet   dir 2 quiet
3. IT NEVER BLOCKS. Every one of the six combinations still produces a program.
   This is not decoration: msg_inv ends in Gtk.Dialog.run(), and before the
   headless guard added with this test, ANY validation message would hang a
   batch caller forever with no output but the print.

The neutral half runs from a scratch copy of the config whose tool table has
exactly one character changed, Q2 -> Q9, so the insert orientation is the only
variable between the two halves.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CFG = os.path.join(HERE, 'configs/sim/axis/ncam_demo')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
KEY_BOTH = 'Both directions alternates'
KEY_ONE = 'This tool cuts the other way'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def gen(cfgdir, direction, out):
    r = subprocess.run([sys.executable, GEN, '--ini',
                        os.path.join(cfgdir, 'lathe-mm.ini'),
                        '--project', 'testing_15_9.xml', '--out', out,
                        '--set', 'polyline:param_dir=%d' % direction],
                       capture_output=True, text=True)
    blob = (r.stdout or '') + (r.stderr or '')
    return (KEY_BOTH in blob or KEY_ONE in blob), os.path.isfile(out)


def main():
    if not (os.path.isdir(CFG) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    d = tempfile.mkdtemp(prefix='bidir_')
    neutral = os.path.join(d, 'neutral_cfg')
    try:
        shutil.copytree(CFG, neutral, symlinks=True)
        tbl = os.path.join(neutral, 'lathe_mm.tbl')
        txt = open(tbl).read()
        swapped = txt.replace('J75.000000  Q2', 'J75.000000  Q9')
        check('the tool table can be made neutral for the control',
              swapped != txt, 'T2 Q2 not found in ' + tbl)
        if swapped == txt:
            return
        open(tbl, 'w').write(swapped)

        # WIDENED 2026-09-03. The warning used to fire only for param_dir 2,
        # which was narrower than what the toolpath already believed:
        # _pl_ramp_face drops every ramp for a right-hand insert roughed BACK
        # TO FRONT, because the tool cannot cut that way - and the operator was
        # told nothing. The question is not "is the mode alternating" but "can
        # this insert cut the direction asked for", so Q2 now warns on 1 and 2
        # and stays quiet on 0, its own direction.
        for cfgdir, label, want in ((CFG, 'directional insert (Q2)',
                                     {2: True, 0: False, 1: True}),
                                    (neutral, 'neutral insert (Q9)',
                                     {2: False, 0: False, 1: False})):
            for direction in (2, 0, 1):
                way = {0: 'front to back', 1: 'back to front',
                       2: 'both directions'}[direction]
                out = os.path.join(d, '%s_%d.ngc' % (
                    os.path.basename(cfgdir), direction))
                fired, made = gen(cfgdir, direction, out)
                check('%s, %s: %s' % (label, way,
                                      'warns' if want[direction]
                                      else 'stays quiet'),
                      fired == want[direction],
                      'warning fired' if fired else 'no warning')
                # 3. IT NEVER BLOCKS
                check('   %s, %s: still generates a program' % (label, way),
                      made, 'no program produced - a dialog may be waiting')

        # ---- and with a REAL left-hand tool ---------------------------------
        # T13 was added to the demo tables on 2026-09-03: the left-hand twin of
        # T2, same 0.8 nose, orientation mirrored to Q1/CL135 AND its I/J
        # mirrored with it. The neutral half above runs on a scratch copy with
        # one character changed; T13 is loadable, so the mirrored path is
        # exercised by a tool a user could actually select.
        for direction, want in ((1, False), (0, True), (2, True)):
            way = {0: 'front to back', 1: 'back to front',
                   2: 'both directions'}[direction]
            out = os.path.join(d, 't13_%d.ngc' % direction)
            r = subprocess.run([sys.executable, GEN, '--ini',
                                os.path.join(CFG, 'lathe-mm.ini'),
                                '--project', 'testing_15_9.xml', '--out', out,
                                '--set', 'tool_change:param_dnum=13',
                                '--set', 'polyline:param_dir=%d' % direction],
                               capture_output=True, text=True)
            blob = (r.stdout or '') + (r.stderr or '')
            fired = (KEY_BOTH in blob or KEY_ONE in blob)
            check('T13, a real left-hand tool, %s: %s'
                  % (way, 'warns' if want else 'stays quiet'),
                  fired == want, 'warning fired' if fired else 'no warning')
            check('   T13 %s: still generates a program' % way,
                  os.path.isfile(out))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Both directions warns on a directional insert and proceeds.')


if __name__ == '__main__':
    main()
