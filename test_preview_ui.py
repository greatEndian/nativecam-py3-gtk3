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
from gi.repository import Gdk                          # noqa: E402

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

    # --- 6b. the Info and Statistics pages ---------------------------------
    # Fed a synthetic toolpath rather than a parsed one: what is under test
    # here is that the pages are wired to it, and 50 mm at 100 mm/min is 30 s
    # whether or not rs274 is on this machine.
    tp = ncam_preview.Toolpath()
    tp.moves = [ncam_preview.Move('feed', (10.0, 0.0, 0.0), (10.0, 0.0, -50.0),
                                  'Turning', 3, ncam_preview.CUT, (), 100.0,
                                  'min', None)]
    p._done(tp)
    pump()
    stats = p.stats_buffer.get_text(p.stats_buffer.get_start_iter(),
                                    p.stats_buffer.get_end_iter(), False)
    check('the Statistics page fills in', '0:30' in stats,
          'no hand-computed 30 s in: %s' % stats.splitlines()[:3])
    check('and names the operation it came from', 'Turning' in stats,
          stats)
    check('Info is blank until the tool is somewhere',
          p.info_rows['pos'].get_text() == '-',
          p.info_rows['pos'].get_text())
    p.sim_scale.set_value(0.5)
    pump()
    check('Info follows the tool once it moves',
          p.info_rows['pos'].get_text().startswith('X20'),
          'X should be a DIAMETER - twice the 10 in the move: %s'
          % p.info_rows['pos'].get_text())
    check('and names the operation, tool and feed there',
          p.info_rows['op'].get_text() == 'Turning'
          and p.info_rows['tool'].get_text() == 'T3'
          and 'mm/min' in p.info_rows['feed'].get_text(),
          '%s / %s / %s' % (p.info_rows['op'].get_text(),
                            p.info_rows['tool'].get_text(),
                            p.info_rows['feed'].get_text()))
    p.sim_scale.set_value(0.0)
    pump()

    # --- 6c. the simulation timer must not outlive the panel ---------------
    # A GLib timeout belongs to the main loop, not to the widget. A running
    # simulation kept firing after the panel was torn down and called
    # set_value/queue_draw on dead widgets; embedded in AXIS that came out as
    # a burst of "gdk_frame_clock_end_updating: assertion GDK_IS_FRAME_CLOCK
    # failed" and then an X BadWindow that took LinuxCNC down with it.
    p._done(tp)
    p._on_play(None)
    pump()
    check('play actually starts a timer',
          p.sim_running and p._sim_source is not None)
    win.destroy()
    pump()
    check('destroying the panel stops the timer',
          not p.sim_running and p._sim_source is None,
          'the timeout is still queued against destroyed widgets')
    check('and a tick that slipped through does nothing',
          p._sim_tick() is False,
          'it would touch widgets that no longer have a window')

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
    check('and does not legend a finish pass it does not contain',
          'finish' in p._legend() and '■</span> finish' not in p._legend(),
          p._legend())

    # facing has no pre-finish - the finishing pass is the only phase it has,
    # and it must still be named
    tp.moves = [ncam_preview.Move('feed', (0.0, 0.0, 0.0), (0.0, 0.0, -1.0),
                                  'Facing', 1, ncam_preview.CUT,
                                  (ncam_preview.FINISH,))]
    check('an op with only a finishing pass legends that',
          '■</span> finish' in p._legend()
          and 'pre-finish' not in p._legend(), p._legend())

    p.contour_btn.set_active(False)
    pump()
    check('and the overlay drops out of the legend when it is turned off',
          'reachable' not in p._legend(), p._legend())

    # --- the plot's own scroll mask, on the GdkWindow that reads it -------
    # greatEndian, 2026-08-25: scroll-to-zoom only worked while the wheel was
    # held DOWN. That is the signature of a missing SCROLL_MASK and of nothing
    # else - a button press takes an implicit pointer grab, and a grab routes
    # scroll to the grab window whatever its mask says, which is why the zoom
    # itself behaved perfectly once held.
    #
    # add_events sets the WIDGET mask, which GTK copies onto the GdkWindow
    # when that window is created and only then; a widget already realized
    # when the mask is added keeps its old window mask. This pane is
    # reparented into a Paned after the panel exists, which is exactly that
    # case, so the mask is re-applied at realize.
    #
    # THE CONTROL IS THE POINT. Asserting the bits are present on a
    # freshly-built pane proves nothing - add_events alone would pass that.
    # So the fault is reproduced first by stripping the bits off the live
    # window, and only then is the handler asked to put them back.
    # A FRESH PANE IN ITS OWN WINDOW: the panel `p` lives in was destroyed by
    # the timer check above, so its drawing area no longer has a GdkWindow to
    # read a mask from.
    p2 = PreviewPane(ini_path=None, soft_cb=lambda: [(0.0, 0.0), (1.0, 1.0)])
    win2 = gtk.OffscreenWindow()
    win2.add(p2.box)
    win2.show_all()
    pump()
    gw = p2.area.get_window()
    check('the plot has a window to carry the mask', gw is not None)
    if gw is not None:
        want = int(Gdk.EventMask.SCROLL_MASK) | int(
            Gdk.EventMask.SMOOTH_SCROLL_MASK)
        check('the plot window carries the scroll masks',
              (int(gw.get_events()) & want) == want,
              'mask %d' % int(gw.get_events()))
        gw.set_events(Gdk.EventMask(int(gw.get_events()) & ~want))
        stripped = int(p2.area.get_window().get_events())
        check('   the control strips them, so the re-arm is not a no-op',
              (stripped & want) == 0, 'mask %d' % stripped)
        p2.area.emit('realize')
        rearmed = int(p2.area.get_window().get_events())
        check('   and realize puts exactly those bits back',
              (rearmed & want) == want, 'mask %d' % rearmed)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Preview pane fits and its controls are wired.')


if __name__ == '__main__':
    main()
