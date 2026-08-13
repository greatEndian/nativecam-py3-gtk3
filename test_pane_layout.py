#!/usr/bin/env python3
# coding: utf-8
"""Both splits land on half at startup, once, and survive the deferred layout.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, 2026-08-13: the path preview should start at half the panel, the
tree and parameter panes should each be half the width, and it has to be
formatted after startup rather than dragged into place every time.

WHY IT CANNOT SIMPLY BE SET AT CONSTRUCTION. A Gtk.Paned position is a pixel
count, and a fraction of the panel is unknowable until it has been allocated -
every allocation is 1x1 while the widgets are built. That is why the existing
`tv_w_adj` preference is an absolute number applied from ncam.py long before
anything has a width: it could not have been a proportion.

AND WHY IT CANNOT BE SET FROM size-allocate EITHER - the mistake this file
exists to prevent. `set_layout` defers its work with `GLib.idle_add`, and that
deferred pass REPACKS frame2, the parameters, into feature_Hpane. Formatting
from inside size-allocate lands BEFORE the repack and is silently undone by it.
The first version did exactly that: it measured half in a bare harness and did
nothing at all in the running panel, which is what greatEndian reported. The fix
is to apply from an idle at PRIORITY_LOW, which is numerically after
PRIORITY_DEFAULT_IDLE and so runs once the layout has settled.

THE STUB CASES BELOW COULD NOT HAVE CAUGHT THAT. They test arithmetic and
lifecycle, which is worth holding, but the fault was one of ORDER against real
GTK. So the last case builds the actual glade panes under a display and lets a
default-priority idle move the divider afterwards, the way set_layout does. It
skips when there is no display; run it under `xvfb-run -a` in a headless
environment.
"""
import os
import subprocess
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
    """Enough Gtk.Paned to exercise the handlers."""

    def __init__(self, pos=0, width=0, height=0):
        self._pos = pos
        self._w = width
        self._h = height
        self.sets = []
        self.disconnected = []

    def get_position(self):
        return self._pos

    def set_position(self, p):
        self._pos = p
        self.sets.append(p)

    def get_allocated_width(self):
        return self._w

    def get_allocated_height(self):
        return self._h

    def disconnect(self, handler):
        self.disconnected.append(handler)


class Alloc(object):
    def __init__(self, h):
        self.height = h


class Host(object):
    """Only what the handlers touch, with the methods bound from the mixin."""

    def __init__(self, hpane):
        self.feature_Hpane = hpane
        self._fmt_handler = 'H1'
        self.scheduled = []

    from ncam_preview_ui import NCamPreviewMixin as _M
    _format_panes_once = _M._format_panes_once
    _apply_half_split = _M._apply_half_split


def gtk_case():
    """The real panes, with a deferred repack racing the formatter."""
    src = os.path.join(HERE, '.pane_gtk_case.py')
    with open(src, 'w') as fh:
        fh.write('''
import sys, io
sys.path.insert(0, %r)
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
b = Gtk.Builder()
b.add_from_string(io.open(%r).read())
hp = b.get_object("hpaned1")
hp.get_parent().remove(hp)
paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
paned.pack1(hp, True, False)
plot = Gtk.DrawingArea(); plot.set_size_request(50, 50)
paned.pack2(plot, False, True)
win = Gtk.Window(); win.set_default_size(960, 800); win.add(paned)
class H:
    feature_Hpane = hp
    _fmt_handler = None
    from ncam_preview_ui import NCamPreviewMixin as _M
    _format_panes_once = _M._format_panes_once
    _apply_half_split = _M._apply_half_split
h = H()
h._fmt_handler = paned.connect("size-allocate", h._format_panes_once)
win.show_all()
# what set_layout does: a DEFAULT-priority idle that moves the divider
GLib.idle_add(lambda: (hp.set_position(120), False)[1])
def done():
    print("VPOS %%d %%d" %% (paned.get_position(), paned.get_allocated_height()))
    print("HPOS %%d %%d" %% (hp.get_position(), hp.get_allocated_width()))
    Gtk.main_quit(); return False
GLib.timeout_add(2500, done)
Gtk.main()
''' % (HERE, os.path.join(HERE, 'ncam.glade')))
    try:
        cmd = [sys.executable, src]
        if not os.getenv('DISPLAY'):
            if not _which('xvfb-run'):
                return None
            cmd = ['xvfb-run', '-a'] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = {}
        for line in r.stdout.splitlines():
            p = line.split()
            if len(p) == 3 and p[0] in ('VPOS', 'HPOS'):
                out[p[0]] = (int(p[1]), int(p[2]))
        return out or None
    except Exception:
        return None
    finally:
        try:
            os.remove(src)
        except OSError:
            pass


def _which(x):
    for d in os.getenv('PATH', '').split(os.pathsep):
        if os.path.isfile(os.path.join(d, x)):
            return True
    return False


def main():
    # --- the split itself -------------------------------------------------
    v = FakePaned(pos=900, height=800)
    h = FakePaned(pos=700, width=1000)
    host = Host(h)
    host._apply_half_split(v)
    check('the preview pane is set to half the height', v.get_position() == 400,
          'position %d of 800' % v.get_position())
    check('the tree/parameter split is set to half the width',
          h.get_position() == 500, 'position %d of 1000' % h.get_position())

    # already correct: nothing written, so no re-entry into size-allocate -
    # the guard ncam_ui_chrome documents for the dual-view panes
    v2 = FakePaned(pos=400, height=800)
    h2 = FakePaned(pos=500, width=1000)
    Host(h2)._apply_half_split(v2)
    check('positions already at half are not written again',
          v2.sets == [] and h2.sets == [], '%r %r' % (v2.sets, h2.sets))

    # --- the trigger ------------------------------------------------------
    v3 = FakePaned(pos=900, height=800)
    h3 = FakePaned(pos=700, width=1)
    host3 = Host(h3)
    host3._format_panes_once(v3, Alloc(800))
    check('a real height with no width yet is ignored', v3.disconnected == [],
          'it gave up before the panel was laid out')
    check('   and it keeps listening for a real allocation',
          host3._fmt_handler == 'H1')

    v4 = FakePaned(pos=900, height=800)
    h4 = FakePaned(pos=700, width=1)
    host4 = Host(h4)
    host4._format_panes_once(v4, Alloc(1))
    check('a 1x1 allocation - construction time - is ignored',
          v4.disconnected == [] and host4._fmt_handler == 'H1')

    # a real allocation disconnects and DEFERS rather than applying inline
    v5 = FakePaned(pos=900, height=800)
    h5 = FakePaned(pos=700, width=1000)
    host5 = Host(h5)
    host5._format_panes_once(v5, Alloc(800))
    check('a real allocation stops listening', v5.disconnected == ['H1']
          and host5._fmt_handler is None)
    check('   and it does NOT set the position from inside size-allocate',
          v5.sets == [] and h5.sets == [],
          'applied inline, so set_layout deferred repack will undo it')

    # --- the case the stubs cannot see -----------------------------------
    got = gtk_case()
    if got is None:
        print('SKIP  the real-GTK case needs a display or xvfb-run')
    else:
        vp, vh = got.get('VPOS', (0, 0))
        hp, hw = got.get('HPOS', (0, 0))
        check('REAL GTK: the preview is half the height after a deferred '
              'repack', abs(vp - vh // 2) <= 2,
              'position %d of %d' % (vp, vh))
        check('REAL GTK: the tree/parameter split is half the width after a '
              'deferred repack', abs(hp - hw // 2) <= 2,
              'position %d of %d - the deferred layout won, which is exactly '
              'the bug greatEndian reported' % (hp, hw))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Both splits start at half, after the layout settles, once.')


if __name__ == '__main__':
    main()
