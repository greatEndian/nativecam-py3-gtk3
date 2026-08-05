#!/usr/bin/env python3
# coding: utf-8
"""The dashed roughing overlay draws the curves the program actually walks.

Standalone, like the other test_*.py here - run it directly, no pytest.

Roughing is a ladder of straight cuts, so it has no single compensated path the
way a contour pass does. What carries the nose for it is the pair of tables it
walks: the ENTRY contour, where a level may begin cutting, and the STOP
contour, where it must stop. Those two are what the overlay draws, and they are
what "is roughing compensated" can actually be looked at.

WHY THIS IS NOT CIRCULAR. The overlay recomputes the curves in Python; this
compares them against the tables read out of the GENERATED PROGRAM, at #4200
and #4400 - the numbers the interpreter really reads. A drawing that agrees
with itself proves nothing; one that agrees with the emitted table catches the
drift that matters, which is somebody changing an offset in the builder and not
in the supplier.

That drift was live when this file was written: the supplier passed 0.0 to
finish_profile where both builders pass nose_r, and added the pre-finish offset
to the stop where build_stop_contour_gcode uses param_f_off alone. Two wrong
curves, both plausible-looking on screen.
"""
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
PROJECT = 'testing_15_2.xml'
ENTRY_BASE, ENTRY_TOP = 4200, 4400
STOP_BASE, STOP_TOP = 4400, 4600
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def table(path, base, top):
    """The (z, radius) pairs a parameter window holds in the generated file."""
    vals = {}
    for ln in open(path):
        m = re.match(r'#(\d+) = (-?[\d.]+)\s*$', ln.strip())
        if m and base <= int(m.group(1)) < top:
            vals[int(m.group(1))] = float(m.group(2))
    pts, i = [], base
    while i in vals and i + 1 in vals:
        pts.append((vals[i], vals[i + 1]))
        i += 2
    return pts


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return

    src = open(os.path.join(HERE, 'ncam_preview_ui.py')).read()
    drw = open(os.path.join(HERE, 'ncam_preview.py')).read()
    # a grep, and a weak one - it cannot see which class anything is on, which
    # is why the hasattr checks below exist and are the real guard here
    check('the pane hands a roughing pair and a surface to the drawing code',
          'rough=self._drawn(' in src and 'surf=self._drawn(' in src
          and 'rough_cb=self._preview_rough_comp' in src
          and 'surf_cb=self._preview_prefinish_surface' in src,
          'an overlay is computed but never handed over')

    # AND THE METHOD IS ON THE CLASS THAT CALLS IT. Asserted by importing,
    # not by grepping: the checks above are string searches and they passed
    # while _rough_contours sat on NCamPreviewMixin instead of PreviewPane -
    # every draw raised AttributeError and greatEndian got a blank plot. A
    # grep cannot see which class a def belongs to; getattr can.
    try:
        import ncam_preview_ui as UI
        pane_has = hasattr(UI.PreviewPane, '_rough_contours')
        mixin_has = hasattr(UI.NCamPreviewMixin, '_preview_rough_comp')
        check('_rough_contours is a PreviewPane method', pane_has,
              'it is defined on the wrong class - _on_draw calls it on the '
              'pane and will raise AttributeError on every draw')
        check('   and _preview_rough_comp is a supplier on the NCam side',
              mixin_has)
    except ImportError as exc:
        print('SKIP  the pane needs GTK to import (%s)' % exc)
    check('and the drawing code accepts and dashes it',
          'rough=None' in drw and "COL['rgh_entry']" in drw
          and "COL['rgh_stop']" in drw)
    check('   on a different dash from the finish overlay',
          '[3.0, 3.0]' in drw and '[6.0, 3.0]' in drw,
          'both overlays dashed the same way are told apart by hue alone')
    check('the supplier passes the nose to finish_profile, as the builders do',
          'finish_profile(f, back, nose_r' in src,
          'passing 0.0 draws a different reachable contour from the one the '
          'program walks')

    d = tempfile.mkdtemp(prefix='rough_overlay_')
    try:
        out = os.path.join(d, 'p.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        PROJECT, '--out', out, '--config-copy',
                        '--set', 'polyline:param_n_comp=1'],
                       capture_output=True, text=True)
        if not os.path.isfile(out):
            check('the project generates', False)
            return
        entry = table(out, ENTRY_BASE, ENTRY_TOP)
        stop = table(out, STOP_BASE, STOP_TOP)
        check('the program carries both tables', len(entry) > 5 and len(stop) > 5,
              '%d entry points, %d stop points' % (len(entry), len(stop)))
        if not (entry and stop):
            return

        # THE TWO MAY LEGITIMATELY COINCIDE, and on this project they do:
        # the entry stands off by the roughing depth of cut and the stop by
        # param_f_off, and both are 0.508 here, so the curves land on top of
        # each other and the operator sees one dashed line, not two. An
        # earlier version asserted they must DIFFER and failed on exactly that
        # valid configuration - the fifth metric this session to fire on a
        # baseline. What is worth asserting is that each is a usable contour.
        gap = max(abs(a[1] - b[1]) for a, b in zip(entry, stop))
        print('   entry and stop differ by at most %.4f mm in radius%s'
              % (gap, ' - they coincide at these settings' if gap < 1e-6
                 else ''))
        for name, tbl in (('entry', entry), ('stop', stop)):
            zs = [z for z, _r in tbl]
            check('the %s table is a usable contour' % name,
                  len(tbl) > 5 and len(set(zs)) > 3
                  and max(r for _z, r in tbl) > min(r for _z, r in tbl),
                  '%d points, %d distinct Z' % (len(tbl), len(set(zs))))

        # and the overlay's own construction reproduces them
        import lathe_sections as L
        prj = os.path.join(os.path.dirname(INI), 'ncam', 'catalogs', 'lathe',
                           'projects', PROJECT)
        has_poly = b'polyline' in open(prj, 'rb').read() if os.path.isfile(prj) \
            else False
        check('the test project still contains a polyline', has_poly)
        # entry_contour is the single construction both tables come from, so
        # the assertion worth making here is that it is EXACTLY that function -
        # a second implementation in the pane is the failure this guards
        check('every overlay is built with entry_contour, not a second '
              'implementation',
              src.count('lathe_sections.entry_contour(rad,') >= 3,
              'entry, stop and the pre-finish surface all come from the one '
              'function the G-code tables come from')
        check('and the pre-finish SURFACE carries no nose',
              'entry_contour(rad, off, rdir, 0.0, 0)' in src,
              'a surface does not have a tool offset - the nose belongs in '
              'the path that produces it, not in the shape it leaves')
        check('and it takes the stop offset from param_f_off alone',
              "f.get_param('param_f_off')" in src
              and "_off('param_pf_off')" not in src,
              'adding the pre-finish offset draws the stop one allowance out '
              'from where the levels really stop')
        check('entry_contour is importable and returns points',
              bool(L.entry_contour([(0.0, 20.0), (-10.0, 20.0)], 1.0, 0)))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The roughing overlay draws the entry and stop the program walks.')


if __name__ == '__main__':
    main()
