#!/usr/bin/env python3
# coding: utf-8
"""Checks the preview pane's controls fit, and still do what they did.

Standalone, like the other test_*.py here - run it directly, no pytest.

The pane is embedded as a tab inside AXIS, in a panel that opens at 400 px and
gets dragged narrower. Laid out as three rows of buttons it demanded 522 px of
MINIMUM width, so the right-hand controls were simply outside the panel - and a
control that cannot be seen is a control that does not exist. GTK does not
complain about that; it just clips. So the width is asserted here, with the
number the panel actually opens at.

The controls then moved into a menu, which is where the second half of this
test comes from: a menu item is easy to wire up and easy to leave inert, and
nothing on screen says which. Every option is exercised through the item the
operator clicks, not by setting the attribute behind it.
"""
import os
import sys

sys.argv = ['ncam.py', '-c', 'lathe']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi                                             # noqa: E402
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk                  # noqa: E402

FAILED = []

# the width the panel opens at - ncam_ui_chrome falls back to 400 when it has
# no remembered width, and the operator drags it narrower than that
PANEL_W = 400

# what the pane demanded before the controls moved into a menu. Kept as a
# number rather than a memory: without it "281" means nothing.
WAS = 522


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def pump():
    while gtk.events_pending():
        gtk.main_iteration()


def main():
    if not gtk.init_check([])[0]:
        print('SKIP  no display')
        return

    import ncam                                       # noqa: F401
    import ncam_preview
    from ncam_preview_ui import PreviewPane

    p = PreviewPane(ini_path=None, soft_cb=lambda: [(0.0, 0.0), (1.0, 1.0)])
    win = gtk.OffscreenWindow()
    win.add(p.box)
    # the show_all the panel does around the pane, not the one inside it: a
    # row hidden in __init__ comes straight back out under this unless it is
    # marked no_show_all, and that is exactly what happened the first time
    win.show_all()
    pump()

    # --- 1. it fits ---------------------------------------------------------
    w = p.box.get_preferred_width().minimum_width
    check('the pane fits the panel it is embedded in',
          w <= PANEL_W, '%d px minimum, panel opens at %d (was %d)'
          % (w, PANEL_W, WAS))
    check('and leaves room to drag the panel narrower',
          w <= 320, '%d px minimum' % w)

    # --- 2. the steady state is one row of controls ------------------------
    check('Leave/Tol are not in the pane outside Comparison',
          not p.cmp_box.get_visible(),
          'they mean nothing in the other colourings and cost a whole row')
    h_plain = p.box.get_preferred_height().minimum_height

    # --- 3. every option is actually in the menu ---------------------------
    labels = []

    def collect(menu):
        for it in menu.get_children():
            if isinstance(it, gtk.SeparatorMenuItem):
                continue
            labels.append(it.get_label())
            sub = it.get_submenu()
            if sub is not None:
                collect(sub)
    collect(p.disp_menu)
    want = ['Show', 'All toolpaths', 'Behind', 'Ahead', 'Operation', 'Tail',
            'Cutting moves', 'Lead moves', 'Link moves', 'Connection moves',
            'Contour', 'Points', 'Colour', 'Stock', 'Comparison',
            'By operation', 'By tool']
    missing = [x for x in want if x not in labels]
    check('every display option is in the menu', not missing, str(missing))

    # --- 4. the defaults are the ones the pane always had ------------------
    check('cutting moves and leads start shown, links and connections hidden',
          p._shown_cats() == {ncam_preview.CUT, ncam_preview.LEAD},
          str(sorted(p._shown_cats())))
    check('the contour overlay starts on', p.contour_btn.get_active())
    check('points start off', not p.points_btn.get_active())
    check('the mode starts at All', p.mode == ncam_preview.MODE_ALL, p.mode)
    check('the colouring starts plain', p.colorize == 'plain', p.colorize)

    # --- 5. the items are wired, and fire ONCE -----------------------------
    # A radio group emits toggled twice per change, once for the item losing
    # the selection. Acting on both sets the value from whichever fired last,
    # which is not the one clicked - so this walks every item and reads back.
    for mid in (ncam_preview.MODE_BEHIND, ncam_preview.MODE_AHEAD,
                ncam_preview.MODE_OPERATION, ncam_preview.MODE_TAIL,
                ncam_preview.MODE_ALL):
        p.mode_items[mid].set_active(True)
        pump()
        check('picking %s selects it' % mid, p.mode == mid,
              'mode is %s' % p.mode)

    for cat in (ncam_preview.LINK, ncam_preview.CONNECT):
        p.cat_btns[cat].set_active(True)
    pump()
    check('the category items reach the filter',
          p._shown_cats() == {ncam_preview.CUT, ncam_preview.LEAD,
                              ncam_preview.LINK, ncam_preview.CONNECT},
          str(sorted(p._shown_cats())))
    for cat in (ncam_preview.LINK, ncam_preview.CONNECT):
        p.cat_btns[cat].set_active(False)
    pump()

    p.contour_btn.set_active(False)
    pump()
    check('turning the contour off reaches the drawing code',
          p._contour(lambda: [(0.0, 0.0)]) is None)
    p.contour_btn.set_active(True)
    pump()

    for cid in ('comparison', 'operation', 'tool', 'plain'):
        p.col_items[cid].set_active(True)
        pump()
        check('picking the %s colouring selects it' % cid,
              p.colorize == cid, 'colorize is %s' % p.colorize)

    # --- 6. Leave/Tol come back, with their contents ------------------------
    p.col_items['comparison'].set_active(True)
    pump()
    check('Comparison brings the Leave/Tol row back',
          p.cmp_box.get_visible())
    check('and brings it back populated, not as an empty strip',
          all(c.get_visible() for c in p.cmp_box.get_children()),
          'a no_show_all container whose children were never shown')
    check('which is the only time the pane is taller',
          p.box.get_preferred_height().minimum_height > h_plain,
          'the row is not actually taking any space')
    check('the pane still fits with that row out',
          p.box.get_preferred_width().minimum_width <= PANEL_W,
          '%d px' % p.box.get_preferred_width().minimum_width)

    p.leftover_entry.set_text('0.25')
    p.tol_entry.set_text('0.05')
    pump()
    check('the entries reach the comparison values',
          abs(p.leftover - 0.25) < 1e-9 and abs(p.tolerance - 0.05) < 1e-9,
          'leftover %s tolerance %s' % (p.leftover, p.tolerance))
    p.leftover_entry.set_text('nonsense')
    pump()
    check('a half-typed number keeps the last good value',
          abs(p.leftover - 0.25) < 1e-9, str(p.leftover))

    # --- 7. the legend names the colours that are on the plot --------------
    # It lives in the status line precisely so it does not become row number
    # two, so it has to be right about which colours are showing.
    check('Comparison is legended with its three classes',
          all(k in p._legend() for k in ('proud', 'on size', 'gouged')),
          p._legend())
    p.col_items['tool'].set_active(True)
    pump()
    check('a per-key colouring gets no fixed legend', p._legend() == '',
          p._legend())

    p.col_items['plain'].set_active(True)
    pump()
    check('plain with no pre-finish in the path legends only the overlay',
          'pre-finish' not in p._legend() and 'reachable' in p._legend(),
          p._legend())

    tp = ncam_preview.Toolpath()
    tp.moves = [ncam_preview.Move('feed', (0.0, 0.0, 0.0), (0.0, 0.0, -1.0),
                                  'Lathe Polyline', 1, ncam_preview.CUT,
                                  (ncam_preview.PREFINISH,))]
    p.toolpath = tp
    check('a path WITH a pre-finish pass legends it',
          'pre-finish' in p._legend(), p._legend())

    p.contour_btn.set_active(False)
    pump()
    check('and the overlay drops out of the legend when it is turned off',
          'reachable' not in p._legend(), p._legend())

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Preview pane fits and its controls are wired.')


if __name__ == '__main__':
    main()
