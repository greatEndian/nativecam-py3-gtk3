#!/usr/bin/env python3
# coding: utf-8
"""Every lathe operation offers nose compensation, and defaults to CNC-side.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian ruled on 2026-08-13: *"Comp: CNC-side or CAM-side as default ... CNC
side"*. That is Native LinuxCNC, `param_n_comp` = 1 - the interpreter does the
compensation with G41.1/G42.1 and no geometry of ours is in the path.

Six of the seven already agreed; `facing` alone shipped `value = 0` while its own
tooltip said *"the default"* was Native. This file exists so that disagreement
cannot come back, on any of them.

WHAT A CHANGED DEFAULT DOES AND DOES NOT DO. A cfg default is read when a
feature is ADDED. A saved project stores its own value per parameter and keeps
it through migration, so changing the default moves nothing that already exists.
Measured on the three demo projects, hashing the move list before and after:
identical, b849fd15881b / 7de894acaec9 / d5d3b06f1ee0 - while testing_15_5's
stored Facing still reads 0 and its Polyline still reads 2.

That is the honest scope of the ruling, and it is asserted below rather than
left as a footnote: an operator wanting Native on an EXISTING feature has to set
it there. The alternative - forcing stored values to follow the cfg - is a much
larger change, since a saved value is the operator's own choice and overriding
it silently would be worse than the mismatch.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CFG = os.path.join(HERE, 'cfg', 'lathe')
PROJECTS = os.path.join(HERE, 'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects')
NATIVE = '1'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def comp_block(path):
    """The [PARAM_N_COMP] block of a cfg, or None if it has no comp at all."""
    s = open(path).read()
    m = re.search(r'^\[PARAM_N_COMP\](.*?)(?=^\[)', s, re.S | re.M)
    return m.group(1) if m else None


def field(block, name):
    m = re.search(r'^%s = (.*)$' % name, block, re.M)
    return m.group(1).strip() if m else None


def main():
    ops = sorted(f for f in os.listdir(CFG) if f.endswith('.cfg'))
    have = [(f, comp_block(os.path.join(CFG, f))) for f in ops]
    have = [(f, b) for f, b in have if b is not None]
    check('the lathe operations with a comp parameter were found',
          len(have) >= 7, 'only %d' % len(have))

    for fname, block in have:
        val = field(block, 'value')
        check('%-16s defaults to Native LinuxCNC' % fname[:-4],
              val == NATIVE,
              'value = %s - greatEndian ruled CNC-side on 2026-08-13' % val)

    # the choices themselves must stay: the ruling was about the DEFAULT, not
    # about removing In CAM, which is the only mode that survives a concave
    # corner smaller than the nose
    for fname, block in have:
        opts = field(block, 'options') or ''
        check('   %-13s still offers all three modes' % fname[:-4],
              'Native LinuxCNC=1' in opts and 'In CAM=2' in opts
              and 'Off=0' in opts, opts)

    # AND THE SCOPE OF THE RULING. A saved project keeps its own value, so the
    # default cannot have rewritten one. testing_15_5 is the witness: its
    # Facing was saved Off and its Polyline In CAM, and both must still read
    # that way - if this ever fails, a default has started overriding an
    # operator's stored choice.
    proj = os.path.join(PROJECTS, 'testing_15_5.xml')
    if not os.path.isfile(proj):
        print('SKIP  testing_15_5 not present for the stored-value check')
    else:
        import xml.etree.ElementTree as ET
        stored = {}
        for feat in ET.parse(proj).getroot().iter():
            if feat.tag in ('subroutine', 'feature'):
                for el in feat.iter('param'):
                    if (el.get('name') or '') == 'Tool nose comp':
                        stored[feat.get('name') or '?'] = el.get('value')
        check('a saved project keeps its own comp values, whatever the default',
              stored.get('Facing') == '0' and stored.get('Lathe Polyline') == '2',
              repr(stored))
        print('      testing_15_5 stores %s' % stored)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('CNC-side is the default everywhere, and no stored choice was moved.')


if __name__ == '__main__':
    main()
