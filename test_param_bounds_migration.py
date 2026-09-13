#!/usr/bin/env python3
# coding: utf-8
"""A cfg must be able to CHANGE a parameter's minimum or maximum on an
existing project - narrowing AND widening - without touching the saved
VALUE, and without doing either silently when the carried-over value no
longer fits the new range.

Standalone, like the other test_*.py here - run it directly, no pytest.

Regression for analysis/043 / analysis/220. `update_features` used to copy a
saved project's own minimum_value/maximum_value straight back over whatever
the current cfg declared - a cfg author could therefore never tighten OR
widen a range on any project that already existed; the change only ever
reached brand-new features. `analysis/043` found this narrowing
`PARAM_BACK_CLEAR` on `cfg/lathe/tool-change.cfg`: cfg 1.23 declared
0.01..10.0, every existing project kept its stale -45.0..45.0.

Exercises the REAL migration path, `NCam.update_features`, against the REAL
`cfg/lathe/tool-change.cfg` and the exact parameter analysis/043 found this
on - a fabricated minimal <feature> stands in for the old, stored copy a
real project would carry, the same way `test_flank_envelope.py` and
`test_rough_overlay.py` already exercise this same method.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lxml import etree                          # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def saved_feature(min_v, max_v, value):
    """A minimal fabricated 'saved project' <feature> for tool_change,
    carrying only param_back_clear - version deliberately far below the real
    cfg's, so migration always triggers regardless of what version
    tool-change.cfg is at when this runs. Everything else in the real cfg's
    own param list is simply left at its fresh default, which is the normal
    case for a project saved before some other parameter existed.
    """
    xml = etree.Element('feature', type='tool_change',
                        src='lathe/tool-change.cfg', version='0.01',
                        id='tool_change_001')
    etree.SubElement(xml, 'param', call='#param_back_clear', type='float',
                     path='0:0', value=str(value), minimum_value=str(min_v),
                     maximum_value=str(max_v))
    return xml


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ini = os.path.join(here, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
    if not os.path.isfile(ini):
        print('SKIP  no demo config to run the real migration path against')
        return

    src = open(os.path.join(here, 'cfg', 'lathe', 'tool-change.cfg')).read()
    check('setup: tool-change.cfg is still the project analysis/043 found '
          'this on',
          'minimum_value = 0.01' in src and 'maximum_value = 10.0' in src,
          'the real cfg bounds have moved; this test targets stale numbers')

    scratch = tempfile.mkdtemp(prefix='param_bounds_')
    try:
        dst = os.path.join(scratch, 'ncam_demo')
        shutil.copytree(os.path.dirname(ini), dst, symlinks=True)
        sys.argv = ['ncam.py', '-i', os.path.join(dst, 'lathe-mm.ini'),
                    '-c', 'lathe']
        import ncam

        def migrate(feature_xml):
            app = ncam.NCam()
            project = etree.Element(ncam.XML_TAG)
            project.append(feature_xml)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = app.update_features(project)
            p = out.find(".//feature[@type='tool_change']"
                          "/param[@call='#param_back_clear']")
            return p, buf.getvalue()

        # 1 - NARROWING, analysis/043's own worked example: saved -45..45,
        # cfg 0.01..10.0, value 2.0 (inside both) - the cfg's tighter range
        # must win and the value must be untouched
        p, out = migrate(saved_feature(-45.0, 45.0, 2.0))
        check('narrowing: the cfg bound wins, not the stale saved one',
              p.get('minimum_value') == '0.01' and p.get('maximum_value') == '10.0',
              'got %s..%s' % (p.get('minimum_value'), p.get('maximum_value')))
        check('narrowing: the saved VALUE survives untouched',
              p.get('value') == '2.0', 'got %s' % p.get('value'))
        check('narrowing: no out-of-range notice when the value already '
              'fits (negative control for check 3 below)',
              'outside the' not in out, out)

        # 2 - WIDENING, the reverse direction, proven separately rather than
        # assumed from the narrowing case
        p, out = migrate(saved_feature(1.0, 5.0, 3.0))
        check('widening: the cfg bound wins here too',
              p.get('minimum_value') == '0.01' and p.get('maximum_value') == '10.0',
              'got %s..%s' % (p.get('minimum_value'), p.get('maximum_value')))
        check('widening: the saved VALUE survives untouched',
              p.get('value') == '3.0', 'got %s' % p.get('value'))

        # 3 - a saved value the new (narrower) bound no longer contains:
        # must NOT be clamped, and must NOT be silent
        p, out = migrate(saved_feature(-45.0, 45.0, -20.0))
        check('out-of-range: the value is kept exactly as saved, not clamped',
              p.get('value') == '-20.0', 'got %s' % p.get('value'))
        check("out-of-range: the bound still moves to the cfg's own range",
              p.get('minimum_value') == '0.01' and p.get('maximum_value') == '10.0',
              'got %s..%s' % (p.get('minimum_value'), p.get('maximum_value')))
        check('out-of-range: a visible notice is printed, not silence',
              'outside the' in out and '0.01' in out and '10.0' in out, out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Bounds migrate to the cfg; the value never does.')


if __name__ == '__main__':
    main()
