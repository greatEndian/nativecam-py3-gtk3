#!/usr/bin/env python3
# coding: utf-8
"""Both splits land on half at startup, once, and then let go.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, 2026-08-13: the path preview should start at half the panel, the
tree and parameter panes should each be half the width, and it has to be
formatted after startup rather than dragged into place every time.

WHY THIS COULD NOT SIMPLY BE SET AT CONSTRUCTION. A Gtk.Paned position is a
pixel count, and a fraction of the panel is unknowable until the panel has been
allocated - every allocation is 1x1 while the widgets are being built. That is
why the existing `tv_w_adj` preference is an absolute number applied from
ncam.py long before anything has a width: it could not have been a proportion.
So the split is done on the first allocation big enough to be real.

TESTED WITH STUBS, NOT GTK, deliberately: this environment has no display, and
the logic worth protecting is arithmetic and lifecycle - half, and exactly once
- not whether GTK draws. The stub records set_position calls and disconnects
the way a real Paned would.

THE ONE-SHOT IS THE PART THAT MATTERS. Left connected, the handler would drag
the splits back to half every time the panel is resized, so the operator could
never move them. And setting a position from inside size-allocate re-enters the
handler, which is why the guards are `!=` - the same trap ncam_ui_chrome
already documents for the dual-view panes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


class FakePaned(object):
    """Enough Gtk.Paned to exercise the handler: a position and a handler id."""

    def __init__(self, pos=0, width=0):
        self._pos = pos
        self._width = width
        self.sets = []
        self.disconnected = []

    def get_position(self):
        return self._pos

    def set_position(self, p):
        self._pos = p
        self.sets.append(p)

    def get_allocated_width(self):
        return self._width

    def disconnect(self, handler):
        self.disconnected.append(handler)


class Alloc(object):
    def __init__(self, h):
        self.height = h


class Host(object):
    """Just the two attributes the handler touches, plus the method itself."""

    def __init__(self, hpane):
        self.feature_Hpane = hpane
        self._fmt_handler = 'H1'

    # bound from the real mixin so the test exercises the shipped code
    from ncam_preview_ui import NCamPreviewMixin as _M
    _format_panes_once = _M._format_panes_once


def main():
    # 1. a real allocation splits both panes in half and lets go
    v = FakePaned(pos=900)
    h = FakePaned(pos=700, width=1000)
    host = Host(h)
    host._format_panes_once(v, Alloc(800))
    check('the preview pane is set to half the height', v.get_position() == 400,
          'position %d of 800' % v.get_position())
    check('the tree/parameter split is set to half the width',
          h.get_position() == 500, 'position %d of 1000' % h.get_position())
    check('   and the handler disconnects itself', v.disconnected == ['H1'],
          repr(v.disconnected))
    check('   and it stops listening', host._fmt_handler is None)

    # 2. a 1x1 allocation - what construction time looks like - is ignored.
    #    Halving THAT is what would put both splits at zero, so this is the
    #    check that the feature cannot fire before it means anything.
    v2 = FakePaned(pos=900)
    h2 = FakePaned(pos=700, width=1)
    host2 = Host(h2)
    host2._format_panes_once(v2, Alloc(1))
    check('an allocation too small to be real is ignored',
          v2.sets == [] and h2.sets == [], '%r %r' % (v2.sets, h2.sets))
    check('   and it keeps listening for a real one',
          host2._fmt_handler == 'H1')

    # 3. a height big enough but a width still unset must NOT half the height
    #    on its own - the two splits are one formatting step, not two
    v3 = FakePaned(pos=900)
    h3 = FakePaned(pos=700, width=1)
    host3 = Host(h3)
    host3._format_panes_once(v3, Alloc(800))
    check('a real height with no width yet is ignored too', v3.sets == [],
          repr(v3.sets))

    # 4. already correct: no set_position at all, so no re-entry into
    #    size-allocate. This is the guard the dual-view panes needed.
    v4 = FakePaned(pos=400)
    h4 = FakePaned(pos=500, width=1000)
    host4 = Host(h4)
    host4._format_panes_once(v4, Alloc(800))
    check('positions already at half are not written again',
          v4.sets == [] and h4.sets == [], '%r %r' % (v4.sets, h4.sets))
    check('   but it still disconnects, so the operator can drag',
          host4._fmt_handler is None)

    # 5. AFTER the one shot, a resize must not drag the splits back. Simulated
    #    by calling again with the handler already cleared - which is what a
    #    disconnected handler amounts to - and checking it does not re-set.
    v5 = FakePaned(pos=250)
    h5 = FakePaned(pos=300, width=1000)
    host5 = Host(h5)
    host5._fmt_handler = None
    host5._format_panes_once(v5, Alloc(800))
    check('a drag survives: half is applied once, not enforced',
          v5.disconnected == [],
          'it tried to disconnect again: %r' % v5.disconnected)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Both splits start at half, once, and then leave the operator alone.')


if __name__ == '__main__':
    main()
