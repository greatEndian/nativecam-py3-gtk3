#!/usr/bin/env python3
# coding: utf-8
"""Checks the four preview-pane open points actually wired, not just built.

Standalone, like the other test_*.py here - run it directly, no pytest.

openPoints.md, 'Simulation - paused at your word': collision detection was
"built and tested but not wired to the pane" - ncam_preview.collisions() and
ncam_preview.py's own test_collisions.py / test_tool_silhouette.py passed
while nothing in ncam_preview_ui.py ever called it. This file checks the WIRE,
not the geometry underneath it - the geometry is what test_collisions.py
covers, and stays untouched here.

The one trap worth restating from test_collisions.py's own history: a
detector that reports the SAME hits regardless of program content passes any
test that only ever hands it a collision. Every section below that touches
PreviewPane's collision state runs a CLEAN program through the exact same
path and asserts zero - not just "did not crash".
"""
import math
import os
import sys

sys.argv = ['ncam.py', '-c', 'lathe']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi                                              # noqa: E402
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk                   # noqa: E402

import ncam_preview as P                                # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


# same fixture as test_collisions.py: a bar 60 mm long at radius 20, and a
# tool whose silhouette is small enough to reason about
STOCK = (-60.0, 0.0, 0.0, 20.0)
NOSE, ORIENT, FRONT, BACK, FLANK = 0.4, 2, 15.0, 75.0, 6.0


def path(moves):
    tp = P.Toolpath()
    tp.moves = [P.Move(kind, a, b, 'Turning', 1, None, ()) for kind, a, b in moves]
    return tp


CLEAN = path([
    ('rapid', (25.0, 0.0, 2.0), (25.0, 0.0, -50.0)),
    ('rapid', (25.0, 0.0, -50.0), (25.0, 0.0, 2.0)),
])
CRASH = path([
    ('rapid', (15.0, 0.0, 2.0), (15.0, 0.0, -50.0)),
])


def pump():
    while gtk.events_pending():
        gtk.main_iteration()


def main():
    if not gtk.init_check([])[0]:
        print('SKIP  no display')
        return

    import ncam                                        # noqa: F401

    # =========================================================================
    # 1/2 - collision detection wired to the pane, timeline marks, Stats line
    # =========================================================================
    from ncam_preview_ui import PreviewPane

    pane = PreviewPane(ini_path=None)
    win = gtk.OffscreenWindow()
    win.add(pane.box)
    win.show_all()
    pump()

    pane.stock_cb = lambda: STOCK
    pane.set_tool(NOSE, ORIENT, front_deg=FRONT, back_deg=BACK, flank_len=FLANK)

    marks = []
    real_add_mark = pane.sim_scale.add_mark

    def spy_add_mark(value, pos, markup):
        marks.append((value, markup))
        return real_add_mark(value, pos, markup)
    pane.sim_scale.add_mark = spy_add_mark

    def run(tp, checked, hits):
        marks.clear()
        pane._done(tp, checked, hits)
        pump()

    # --- not checked: no tool profile / no stock at all ---------------------
    pane_nt = PreviewPane(ini_path=None)
    win2 = gtk.OffscreenWindow()
    win2.add(pane_nt.box)
    win2.show_all()
    pump()
    checked = P.collisions_checked(CLEAN, None, 0.0)
    hits = P.collisions(CLEAN, None, 0.0) if checked else []
    pane_nt._done(CLEAN, checked, hits)
    pump()
    check('no tool/stock: reported as NOT CHECKED, not as clean',
          not pane_nt._collisions_checked and pane_nt._collisions == [],
          'checked=%s hits=%s' % (pane_nt._collisions_checked, pane_nt._collisions))
    check('the Stats line says so',
          'not checked' in pane_nt._verification_line(),
          pane_nt._verification_line())

    # --- clean program: the trap case - must report zero, not just run ------
    checked = P.collisions_checked(CLEAN, STOCK, NOSE)
    hits = P.collisions(CLEAN, STOCK, NOSE, ORIENT, FRONT, BACK, FLANK)
    check('sanity: the clean fixture really is clean', hits == [], hits[:1])
    run(CLEAN, checked, hits)
    check('a clean program reaches the pane as CHECKED and CLEAN',
          pane._collisions_checked and pane._collisions == [])
    check('Stats reports clean, not silence',
          'clean' in pane._verification_line().lower(),
          pane._verification_line())
    check('no timeline marks on a clean program', marks == [], marks)
    check('the status line does not mention a collision count',
          'collision' not in pane._last_status.lower(), pane._last_status)

    # --- crash program: a rapid driven straight into the bar ----------------
    checked = P.collisions_checked(CRASH, STOCK, NOSE)
    hits = P.collisions(CRASH, STOCK, NOSE, ORIENT, FRONT, BACK, FLANK)
    check('sanity: the crash fixture really does crash', len(hits) >= 1)
    run(CRASH, checked, hits)
    check('a colliding program reaches the pane as CHECKED with hits',
          pane._collisions_checked and len(pane._collisions) == len(hits),
          '%d vs %d' % (len(pane._collisions), len(hits)))
    check('Stats names the rapid hit and a depth',
          ('rapid into material' in pane._verification_line()
           and '%d collision' % len(hits) in pane._verification_line()),
          pane._verification_line())
    check('the timeline gets one mark per distinct position',
          len(marks) == len({round(c.at, 3) for c in hits}),
          '%d marks for %d hit(s)' % (len(marks), len(hits)))
    check('rapid hits are marked R',
          all(m == 'R' for _v, m in marks), marks)
    check('the status line surfaces the count',
          'collision' in pane._last_status.lower()
          and str(len(hits)) in pane._last_status, pane._last_status)

    # --- run the clean program again: marks must clear, not accumulate ------
    run(CLEAN, *([P.collisions_checked(CLEAN, STOCK, NOSE)]
                 + [P.collisions(CLEAN, STOCK, NOSE, ORIENT, FRONT, BACK, FLANK)]))
    check('marks from the previous (colliding) program do not survive '
          'a clean regenerate', marks == [], marks)

    # =========================================================================
    # 3 - Accuracy slider -> StockField.columns_for
    # =========================================================================
    lo = P.StockField.columns_for(-60.0, 0.0, 0.4, divisor=2.0)
    hi = P.StockField.columns_for(-60.0, 0.0, 0.4, divisor=24.0)
    default = P.StockField.columns_for(-60.0, 0.0, 0.4)
    check('a smaller divisor gives fewer columns (coarser, faster)',
          lo < default, '%d vs default %d' % (lo, default))
    check('a larger divisor gives more columns (finer, slower)',
          hi > default, '%d vs default %d' % (hi, default))
    check('the default divisor reproduces the pre-existing behaviour exactly',
          P.StockField.columns_for(-60.0, 0.0, 0.4, divisor=6.0) == default)
    check('a fresh pane\'s Accuracy slider starts at the old default divisor',
          abs(pane.accuracy_divisor - 6.0) < 1e-9, pane.accuracy_divisor)

    # moving the slider actually changes what _stock_field() would ask for
    pane.accuracy_scale.set_value(1.0)         # top of the range
    pump()
    check('dragging Accuracy to the top raises the divisor',
          pane.accuracy_divisor > 6.0, pane.accuracy_divisor)
    pane.accuracy_scale.set_value(0.0)         # bottom of the range
    pump()
    check('dragging Accuracy to the bottom lowers the divisor',
          pane.accuracy_divisor < 6.0, pane.accuracy_divisor)

    # =========================================================================
    # 4a - Programmed Point toggle
    # =========================================================================
    try:
        import cairo
    except ImportError:
        print('SKIP  cairo is not installed - cannot check the drawing')
    else:
        def render(show_point):
            W = H = 120
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
            cr = cairo.Context(surf)
            # orient=0, no cl_deg: tool_direction() is (0, 0), so draw_tool's
            # whole body branch is skipped and only the commanded-point cross
            # is at stake - isolating exactly what the toggle controls
            P.draw_tool(cr, (0.0, 0.0, 0.0), 'ZX', 1.0, 60.0, 60.0,
                       nose_r=0.0, orient=0, show_point=show_point)
            surf.flush()
            return bytes(surf.get_data())

        on, off = render(True), render(False)
        check('the Programmed Point cross actually changes the pixels',
              on != off)
        check('and draws nothing extra when off',
              off == render(False))

    check('the toggle defaults to on (unchanged behaviour for nobody '
          'touching it)', pane.show_point is True)

    # feed a position so _tool_state() has something to report
    pane.toolpath = CRASH
    pane.sim_t = 0.5
    pane._acc = None
    st = pane._tool_state()
    check('show_point is in the dict draw_toolpath reads',
          st is not None and st.get('show_point') is True, st)
    pane.point_btn.set_active(False)
    pump()
    check('unchecking Programmed point in the menu reaches the pane',
          pane.show_point is False)
    pane.sim_t = 0.0
    pane.toolpath = P.Toolpath()

    # =========================================================================
    # 4b - Regenerate on rewind as an option
    # =========================================================================
    check('Regenerate on rewind defaults to on (unchanged behaviour)',
          pane.regen_on_rewind is True)

    long_prog = path([
        ('feed', (25.0, 0.0, 2.0), (25.0, 0.0, -50.0)),
        ('feed', (25.0, 0.0, -50.0), (15.0, 0.0, -50.0)),
        ('feed', (15.0, 0.0, -50.0), (15.0, 0.0, 2.0)),
    ])
    pane.toolpath = long_prog
    pane.stock_cb = lambda: STOCK
    pane.nose_r = 1.0
    pane._acc = None
    pane._reset_field()

    pane.sim_t = 0.9
    f1 = pane._stock_field()
    upto_forward = pane._field_upto
    check('scrubbing forward builds a field', f1 is not None and upto_forward >= 0)

    # rewind with the option ON: full rebuild, field_upto resets low
    pane.sim_t = 0.1
    f2 = pane._stock_field()
    check('regen_on_rewind ON rebuilds on a backwards scrub (field_upto drops)',
          pane._field_upto < upto_forward, pane._field_upto)

    # go forward again, then rewind with the option OFF
    pane.sim_t = 0.9
    pane._stock_field()
    upto_forward2 = pane._field_upto
    pane.regen_btn.set_active(False)
    pump()
    check('unchecking Regenerate on rewind in the menu reaches the pane',
          pane.regen_on_rewind is False)
    field_before = pane._field
    pane.sim_t = 0.1
    pane._stock_field()
    check('regen_on_rewind OFF leaves the field object alone on a rewind '
          '(no rebuild)', pane._field is field_before)
    check('...and still moves field_upto back without rebuilding the field',
          pane._field_upto < upto_forward2)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Collision detection, timeline marks, the Stats verification line, '
          'the Accuracy slider and the two small toggles are all wired.')


if __name__ == '__main__':
    main()
