#!/usr/bin/env python3
# coding: utf-8
"""Checks the collapsible side rail in ncam_ui_chrome.py.

Standalone, like the other test_*.py here - run it directly, no pytest.

The rail is the only way back once the panel is rolled away, so the property
that actually matters is that it survives a collapse. A test that only checked
main_box gets hidden would pass against code that hides the rail too and leaves
no way to restore the panel.
"""
import sys
import os

sys.argv = ['ncam.py', '-c', 'lathe']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ncam  # noqa: E402,F401
from ncam import gtk  # noqa: E402
from ncam_ui_chrome import NCamUIChromeMixin  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


class Panel(NCamUIChromeMixin, gtk.Box):
    """The real mixin on a stand-in for NCam - same widgets, same packing."""

    def __init__(self):
        gtk.Box.__init__(self, orientation=gtk.Orientation.VERTICAL)
        self.main_box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        self._resize_grip = gtk.EventBox()
        row = gtk.Box(orientation=gtk.Orientation.HORIZONTAL)
        row.pack_start(self.build_collapse_rail(), False, False, 0)
        row.pack_start(self._resize_grip, False, False, 0)
        row.pack_start(self.main_box, True, True, 0)
        self.pack_start(row, True, True, 0)
        self.show_all()


def main():
    p = Panel()
    check('starts expanded', not p._panel_collapsed)
    check('rail, grip and body all visible to begin with',
          p._collapse_rail.get_visible() and p._resize_grip.get_visible()
          and p.main_box.get_visible())

    p._panel_width = 420          # stands in for a real allocation
    p.toggle_panel()
    check('rolling away hides the body', not p.main_box.get_visible())
    check('rolling away hides the resize grip', not p._resize_grip.get_visible())
    check('THE RAIL SURVIVES - otherwise there is no way back',
          p._collapse_rail.get_visible())
    check('collapsed width is just the rail',
          p.get_size_request()[0] == p.COLLAPSE_RAIL_W,
          'got %s' % p.get_size_request()[0])

    p.toggle_panel()
    check('rolling out shows the body again', p.main_box.get_visible())
    check('rolling out shows the resize grip again', p._resize_grip.get_visible())
    check('the previous width is restored, not a default',
          p.get_size_request()[0] == 420, 'got %s' % p.get_size_request()[0])

    # the arrow has to say which way the panel will move, or the rail is a
    # mystery button
    p.toggle_panel()
    collapsed_icon = p._collapse_arrow.get_icon_name()[0]
    collapsed_tip = p._collapse_btn.get_tooltip_text()
    p.toggle_panel()
    expanded_icon = p._collapse_arrow.get_icon_name()[0]
    check('the arrow flips with the state',
          collapsed_icon != expanded_icon,
          'collapsed=%s expanded=%s' % (collapsed_icon, expanded_icon))
    check('the tooltip says what the click will do',
          bool(collapsed_tip) and collapsed_tip != p._collapse_btn.get_tooltip_text())

    # toggling twice must land exactly where it started, and asking for a state
    # already in force must not disturb the stored width
    before = p.get_size_request()[0]
    p.set_panel_collapsed(False)
    check('setting the state it is already in changes nothing',
          p.get_size_request()[0] == before and not p._panel_collapsed)

    # a collapse while already collapsed must not overwrite the saved width
    # with the rail width - that would strand the panel narrow forever
    p.set_panel_collapsed(True)
    p.set_panel_collapsed(True)
    p.set_panel_collapsed(False)
    check('a repeated collapse does not lose the remembered width',
          p.get_size_request()[0] == 420, 'got %s' % p.get_size_request()[0])

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All panel rail tests passed.')


if __name__ == '__main__':
    main()
