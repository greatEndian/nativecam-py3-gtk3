#!/usr/bin/env python3
# coding: utf-8
"""The preview pane: a plot of the generated toolpath, and the G-code itself.

The parsing and the Cairo drawing live in ncam_preview.py, which imports no GTK
and no ncam and is tested headlessly. This file is only the widget around them.

Why a Notebook rather than a real side-by-side: the panel is embedded as a
narrow tab inside AXIS, and there is not enough width there for a G-code view
BESIDE a plot without squeezing both into uselessness. Tabs give the same two
views at full width each. The pane is built here in Python rather than in Glade
specifically so it can later be popped into its own window, where side-by-side
would fit, without rebuilding any of it.

The interpreter runs in a subprocess and takes on the order of two seconds on a
real project, so it runs on a worker thread and the result is handed back to the
GTK thread with GLib.idle_add. Doing it inline would freeze the panel - inside
AXIS, on a machine that may be cutting - every time Regenerate is pressed.
"""
import os
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk      # noqa: E402
from gi.repository import GLib            # noqa: E402

import ncam_preview                        # noqa: E402


class PreviewPane(object):
    """Owns the notebook, the drawing area and the last parsed toolpath."""

    def __init__(self, ini_path=None, plane='ZX', stock_cb=None):
        self.ini_path = ini_path
        self.plane = plane
        # returns (a_min, a_max, b_min, b_max) for the stock, or None. A
        # callback rather than a value so the pane never holds a stale copy of
        # a Workpiece the operator has since edited.
        self.stock_cb = stock_cb
        self.toolpath = ncam_preview.Toolpath()
        self._busy = False
        self._pending = None

        self.widget = gtk.Notebook()
        self.widget.set_scrollable(True)

        self.area = gtk.DrawingArea()
        self.area.connect('draw', self._on_draw)
        self.widget.append_page(self.area, gtk.Label(label=_('Plot')))

        self.buffer = gtk.TextBuffer()
        view = gtk.TextView.new_with_buffer(self.buffer)
        view.set_editable(False)          # ncam.ngc is generated; edits would
        view.set_monospace(True)          # be lost on the next Regenerate
        scroll = gtk.ScrolledWindow()
        scroll.add(view)
        self.widget.append_page(scroll, gtk.Label(label=_('G-code')))

        self.status = gtk.Label()
        self.status.set_halign(gtk.Align.START)
        self.status.set_ellipsize(3)      # PANGO_ELLIPSIZE_END

        self.box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        self.box.pack_start(self.widget, True, True, 0)
        self.box.pack_start(self.status, False, False, 2)
        self.box.show_all()

    # -- refreshing ---------------------------------------------------------
    def refresh(self, fname=None):
        """Re-parse and redraw. Safe to call from the GTK thread."""
        if fname is None:
            return
        self._load_text(fname)
        if self._busy:
            # a second Regenerate while one is still parsing: keep the newest
            # request and drop the rest, rather than queueing interpreter runs
            self._pending = fname
            return
        self._busy = True
        self._set_status(_('Reading toolpath...'))
        t = threading.Thread(target=self._worker, args=(fname,), daemon=True)
        t.start()

    def _worker(self, fname):
        tp = ncam_preview.parse_program(fname, self.ini_path)
        GLib.idle_add(self._done, tp)

    def _done(self, tp):
        self.toolpath = tp
        self._busy = False
        if tp.error:
            self._set_status(_('Preview: %s') % tp.error)
        else:
            self._set_status(_('%(f)d cutting moves, %(r)d rapids')
                             % {'f': len(tp.feeds), 'r': len(tp.rapids)})
        self.area.queue_draw()
        nxt, self._pending = self._pending, None
        if nxt:
            self.refresh(nxt)
        return False

    def _load_text(self, fname):
        try:
            with open(fname, errors='replace') as f:
                self.buffer.set_text(f.read())
        except OSError as e:
            self.buffer.set_text(str(e))

    def _set_status(self, text):
        self.status.set_markup('<small>%s</small>' % GLib.markup_escape_text(text))

    # -- drawing ------------------------------------------------------------
    def _on_draw(self, area, cr):
        alloc = area.get_allocation()
        stock = None
        if self.stock_cb is not None:
            try:
                stock = self.stock_cb()
            except Exception:
                stock = None
        ncam_preview.draw_toolpath(cr, alloc.width, alloc.height,
                                   self.toolpath, self.plane, stock)
        return False


class NCamPreviewMixin(object):
    """Builds the preview pane and hangs it under the existing panel."""

    def create_preview_pane(self):
        """Slot a draggable plot pane in under the existing tree/params area.

        The Glade tree is  MainBox > vbox4 > hpaned1 > ncam_pane > ...  so the
        preview goes in a new vertical Paned that takes hpaned1's place inside
        its own parent. Looked up through get_parent() rather than by the name
        vbox4, so a Glade reshuffle moves it rather than breaking it.
        """
        top = getattr(self, 'feature_Hpane', None)
        if top is None:
            return None
        parent = top.get_parent()
        if parent is None:
            return None

        ini = getattr(self, 'ini_file', None) or os.getenv('INI_FILE_NAME')
        plane = 'ZX' if getattr(self, 'catalog_dir', '') == 'lathe' else 'XY'
        self.preview_pane = PreviewPane(ini, plane, self._preview_stock)

        paned = gtk.Paned(orientation=gtk.Orientation.VERTICAL)
        self.preview_paned = paned

        expand = True
        fill = True
        if isinstance(parent, gtk.Box):
            expand, fill, _pad, _ptype = parent.query_child_packing(top)
        parent.remove(top)
        paned.pack1(top, True, False)
        paned.pack2(self.preview_pane.box, False, True)
        if isinstance(parent, gtk.Box):
            parent.pack_start(paned, expand, fill, 0)
        else:
            parent.add(paned)
        paned.show_all()
        return paned

    def _preview_stock(self):
        """The Workpiece extents in the plotted axes, or None.

        Read live from the feature tree rather than cached, so the outline
        cannot disagree with a Workpiece the operator just edited.
        """
        try:
            f = self._find_feature('workpiece')
            if f is None:
                return None

            def val(name, default=0.0):
                p = f.get_param(name)
                return float(p.get_ngc_value()) if p is not None else default

            # cfg/lathe/material.cfg: OD/ID are DIAMETERS, Z is the Z of the
            # tip - the begin position - and L is the length running back from
            # it. The plot works in radius, like canon does.
            od, idia = val('param_od'), val('param_id')
            z, length = val('param_z'), val('param_l')
            return (z - abs(length), z, idia / 2.0, od / 2.0)
        except Exception:
            return None

    def _find_feature(self, ftype, parent=None):
        store = getattr(self, 'treestore', None)
        if store is None:
            return None
        it = store.iter_children(parent)
        while it is not None:
            f = store.get_value(it, 0)
            if f.get_attr('type') == ftype:
                return f
            got = self._find_feature(ftype, it)
            if got is not None:
                return got
            it = store.iter_next(it)
        return None
