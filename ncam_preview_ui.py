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
from gi.repository import Gdk            # noqa: E402
from gi.repository import GLib            # noqa: E402

import ncam_preview                        # noqa: E402


class PreviewPane(object):
    """Owns the notebook, the drawing area and the last parsed toolpath."""

    # playback multipliers. Slow speeds matter more than fast ones here: the
    # point of watching is usually one corner or one plunge, not the whole part.
    # 0.01x to 10x. The slow end is where the value is: at 0.01x the whole
    # path takes about 13 minutes, which is what you want when watching one
    # corner being formed. Stops are spaced roughly 1-2-5 per decade so the
    # list stays short enough to pick from.
    SPEEDS = [('0.01x', 0.01), ('0.02x', 0.02), ('0.05x', 0.05),
              ('0.1x', 0.1), ('0.2x', 0.2), ('0.5x', 0.5),
              ('1x', 1.0), ('2x', 2.0), ('5x', 5.0), ('10x', 10.0)]
    TICK_MS = 40
    BASE_STEP = 0.005          # fraction of the path per tick at 1x

    def __init__(self, ini_path=None, plane='ZX', stock_cb=None,
                 profile_cb=None):
        self.ini_path = ini_path
        self.plane = plane
        # returns (a_min, a_max, b_min, b_max) for the stock, or None. A
        # callback rather than a value so the pane never holds a stale copy of
        # a Workpiece the operator has since edited.
        self.stock_cb = stock_cb
        # the finished profile, for Comparison colouring. A callback for the
        # same reason stock_cb is one: it must never be a stale copy of a
        # feature the operator has since edited.
        self.profile_cb = profile_cb
        self.colorize = 'plain'
        self.leftover = 0.0
        self.tolerance = 0.01
        self.toolpath = ncam_preview.Toolpath()
        self._last_status = ''
        self._busy = False
        self._pending = None

        self.widget = gtk.Notebook()
        self.widget.set_scrollable(True)

        self.view = ncam_preview.View()
        self.area = gtk.DrawingArea()
        self.area.connect('draw', self._on_draw)
        # GTK3 does not deliver these to a DrawingArea unless they are asked
        # for explicitly - the same omission the treeviews had to fix for the
        # scroll wheel
        self.area.add_events(Gdk.EventMask.SCROLL_MASK
                             | Gdk.EventMask.SMOOTH_SCROLL_MASK
                             | Gdk.EventMask.BUTTON_PRESS_MASK
                             | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.area.connect('scroll-event', self._on_scroll)
        self.area.connect('button-press-event', self._on_button)
        self.area.connect('motion-notify-event', self._on_motion)
        self._drag = None
        self.widget.append_page(self.area, gtk.Label(label=_('Plot')))

        self.buffer = gtk.TextBuffer()
        view = gtk.TextView.new_with_buffer(self.buffer)
        view.set_editable(False)          # ncam.ngc is generated; edits would
        view.set_monospace(True)          # be lost on the next Regenerate
        scroll = gtk.ScrolledWindow()
        scroll.add(view)
        self.widget.append_page(scroll, gtk.Label(label=_('G-code')))

        # --- simulation controls ------------------------------------------
        # Play walks the toolpath; the slider scrubs it. Parameterised by
        # DISTANCE along the path, because the canon dump carries no feed
        # rates and a time-accurate run would be inventing them.
        self.sim_t = 0.0
        self.sim_running = False
        self._sim_source = None
        self._acc = None
        self._total = 0.0
        self.nose_r = 0.0
        self.orient = 0
        self.cl_deg = None
        self.included_deg = None
        self._field = None
        self._field_upto = -1

        self.play_btn = gtk.Button()
        self.play_btn.set_image(gtk.Image.new_from_icon_name(
            'media-playback-start', gtk.IconSize.BUTTON))
        self.play_btn.set_tooltip_text(_('Run the tool along the toolpath'))
        self.play_btn.connect('clicked', self._on_play)

        # Stop is not Pause. Pause leaves the tool and the cut material where
        # they are; Stop rewinds to bar stock, which is the only way back to an
        # uncut part without regenerating.
        self.stop_btn = gtk.Button()
        self.stop_btn.set_image(gtk.Image.new_from_icon_name(
            'media-playback-stop', gtk.IconSize.BUTTON))
        self.stop_btn.set_tooltip_text(_('Stop and rewind to uncut stock'))
        self.stop_btn.connect('clicked', self._on_stop)

        self.speed = 1.0
        self.speed_combo = gtk.ComboBoxText()
        for label, mult in self.SPEEDS:
            self.speed_combo.append(str(mult), label)
        self.speed_combo.set_active_id('1.0')
        self.speed_combo.set_tooltip_text(
            _('Playback speed. The whole path takes about 8 seconds at 1x, '
              'whatever its length.'))
        self.speed_combo.connect('changed', self._on_speed)

        self.sim_scale = gtk.Scale.new_with_range(
            gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.001)
        self.sim_scale.set_draw_value(False)
        self.sim_scale.connect('value-changed', self._on_scrub)

        self.sim_box = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=4)
        self.sim_box.pack_start(self.play_btn, False, False, 0)
        self.sim_box.pack_start(self.stop_btn, False, False, 0)
        self.sim_box.pack_start(self.sim_scale, True, True, 0)
        self.sim_box.pack_start(self.speed_combo, False, False, 0)

        # --- stock colouring ----------------------------------------------
        self.color_combo = gtk.ComboBoxText()
        self.color_combo.append('plain', _('Stock'))
        self.color_combo.append('comparison', _('Comparison'))
        self.color_combo.append('operation', _('By operation'))
        self.color_combo.append('tool', _('By tool'))
        self.color_combo.set_active_id('plain')
        self.color_combo.set_tooltip_text(
            _('Comparison colours the remaining material against the finished '
              'profile: blue where stock is still standing proud, green where '
              'it is on size, red where it has been cut past the part.'))
        self.color_combo.connect('changed', self._on_colorize)

        self.leftover_entry = gtk.Entry()
        self.leftover_entry.set_width_chars(6)
        self.leftover_entry.set_text('0.00')
        self.leftover_entry.set_tooltip_text(
            _('Stock deliberately left ON the part. Excess and gouges are '
              'measured from that surface; 0 measures from the part itself.'))
        self.leftover_entry.connect('changed', self._on_cmp_value)

        self.tol_entry = gtk.Entry()
        self.tol_entry.set_width_chars(6)
        self.tol_entry.set_text('0.01')
        self.tol_entry.set_tooltip_text(
            _('Band either side of the expected surface. Outside it, material '
              'counts as excess or gouged.'))
        self.tol_entry.connect('changed', self._on_cmp_value)

        # --- toolpath display ---------------------------------------------
        self.mode = ncam_preview.MODE_ALL
        self.mode_combo = gtk.ComboBoxText()
        for mid, label in ((ncam_preview.MODE_ALL, _('All toolpaths')),
                           (ncam_preview.MODE_BEHIND, _('Behind')),
                           (ncam_preview.MODE_AHEAD, _('Ahead')),
                           (ncam_preview.MODE_OPERATION, _('Operation')),
                           (ncam_preview.MODE_TAIL, _('Tail'))):
            self.mode_combo.append(mid, label)
        self.mode_combo.set_active_id(ncam_preview.MODE_ALL)
        self.mode_combo.set_tooltip_text(
            _('Which of the toolpath is drawn, relative to where the tool has '
              'reached: everything, only what is behind it, only what is '
              'ahead, only the current operation, or a short trail.'))
        self.mode_combo.connect('changed', self._on_mode)

        # Cutting moves and leads are what you look at; links and connections
        # are usually noise, so they start hidden - the reference panel makes
        # the same choice.
        self.cat_btns = {}
        self.tp_box = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=2)
        self.tp_box.pack_start(self.mode_combo, False, False, 0)
        for cat, label, on, tip in (
                (ncam_preview.CUT, _('Cut'), True, _('Cutting moves')),
                (ncam_preview.LEAD, _('Lead'), True,
                 _('Lead moves - the entry to, and exit from, a cut. Inferred '
                   'from where a feed sits next to a rapid, not marked in the '
                   'G-code.')),
                (ncam_preview.LINK, _('Link'), False,
                 _('Link moves - rapids within one operation')),
                (ncam_preview.CONNECT, _('Conn'), False,
                 _('Connection moves - rapids between operations'))):
            b = gtk.ToggleButton(label=label)
            b.set_active(on)
            b.set_tooltip_text(tip)
            b.connect('toggled', self._on_cat)
            self.cat_btns[cat] = b
            self.tp_box.pack_start(b, False, False, 0)
        self.points_btn = gtk.ToggleButton(label=_('Pts'))
        self.points_btn.set_tooltip_text(
            _('Mark where each move starts and ends - useful on a path made of '
              'many small segments.'))
        self.points_btn.connect('toggled', lambda _b: self.area.queue_draw())
        self.tp_box.pack_start(self.points_btn, False, False, 0)

        self.cmp_box = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=4)
        self.cmp_box.pack_start(self.color_combo, False, False, 0)
        self.cmp_box.pack_start(gtk.Label(label=_('Leave')), False, False, 0)
        self.cmp_box.pack_start(self.leftover_entry, False, False, 0)
        self.cmp_box.pack_start(gtk.Label(label=_('Tol')), False, False, 0)
        self.cmp_box.pack_start(self.tol_entry, False, False, 0)

        self.status = gtk.Label()
        self.status.set_halign(gtk.Align.START)
        self.status.set_ellipsize(3)      # PANGO_ELLIPSIZE_END

        self.box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        self.box.pack_start(self.widget, True, True, 0)
        self.box.pack_start(self.sim_box, False, False, 0)
        self.box.pack_start(self.tp_box, False, False, 0)
        self.box.pack_start(self.cmp_box, False, False, 0)
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
        self._acc = None          # lengths belong to the old path
        self._reset_field()
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
        # base text and displayed text are kept apart: _show_zoom appends a
        # zoom suffix, and writing that back would compound it on every scroll
        self._last_status = text
        self._render_status()

    def _render_status(self):
        text = self._last_status
        if not self.view.fitted:
            text = '%s  -  zoom %.0f%%, double-click to fit' % (
                text, self.view.scale * 100.0)
        self.status.set_markup('<small>%s</small>'
                               % GLib.markup_escape_text(text))

    # -- simulation ---------------------------------------------------------
    def set_tool(self, nose_r, orient, cl_deg=None, included_deg=None):
        """Nose radius, orientation and the real insert angles.

        nose_r/orient come from ncam.tip_comp_inputs(), the same source the
        G-code compensates with. cl_deg/included_deg come from the tool table's
        I and J, so the drawn insert is the one in the turret rather than a
        generic wedge.
        """
        self.nose_r, self.orient = nose_r or 0.0, orient or 0
        self.cl_deg, self.included_deg = cl_deg, included_deg
        self._reset_field()
        self.area.queue_draw()

    def _nose_dir(self):
        # the RAW lathe_shapes offset, not a unit vector - see nose_offset()
        return ncam_preview.nose_offset(self.orient)

    def _reset_field(self):
        self._field = None
        self._field_upto = -1

    def _stock_field(self):
        """The material, cut back to wherever the simulation has reached.

        Rebuilt from the stock whenever the scrub goes BACKWARDS, because
        removal only subtracts - you cannot put metal back by replaying fewer
        moves. Going forwards just applies the moves not yet applied, so
        dragging the slider along stays cheap.
        """
        if self.toolpath.empty or self.sim_t <= 0.0:
            return None
        stock = None
        if self.stock_cb is not None:
            try:
                stock = self.stock_cb()
            except Exception:
                stock = None
        if not stock:
            return None
        if self._acc is None:
            self._acc, self._total = ncam_preview.path_lengths(self.toolpath)
        _pos, idx, _k = ncam_preview.position_at(self.toolpath, self.sim_t,
                                                 self._acc, self._total)
        if self._field is None or idx <= self._field_upto:
            a0, a1, b0, b1 = stock
            cols = ncam_preview.StockField.columns_for(a0, a1, self.nose_r)
            self._field = ncam_preview.StockField(a0, a1, b0, b1, cols)
            self._field_upto = -1

        # Moves BEFORE the current one are applied whole, once each.
        for i in range(self._field_upto + 1, idx):
            mv = self.toolpath.moves[i]
            if mv.kind == 'feed':    # rapids do not cut
                self._field.cut_move(mv.a, mv.b, self.nose_r, self._nose_dir())
        self._field_upto = idx - 1

        # The CURRENT move is cut only as far as the tool has actually reached.
        # Applying it whole made an entire pass of material vanish the instant
        # the tool arrived at it, instead of being eaten progressively behind
        # the nose - the tool appeared to be following a cut somebody else had
        # already made. Re-cutting this partial every frame is safe: removal
        # takes a minimum, so cutting the same metal twice changes nothing.
        cur = self.toolpath.moves[idx]
        if cur.kind == 'feed':
            self._field.cut_move(cur.a, _pos, self.nose_r, self._nose_dir())
        return self._field

    def _on_play(self, _btn):
        self.sim_running = not self.sim_running
        if self.sim_running:
            if self.sim_t >= 0.999:
                self.sim_t = 0.0        # replay rather than sit at the end
                self._reset_field()
            self._sim_source = GLib.timeout_add(self.TICK_MS, self._sim_tick)
        else:
            self._stop_sim()
        self._sync_play_icon()

    def _on_stop(self, _btn):
        """Rewind to uncut stock."""
        self._stop_sim()
        self.sim_t = 0.0
        self._reset_field()
        self.sim_scale.set_value(0.0)
        self._sync_play_icon()
        self.area.queue_draw()

    def _on_mode(self, combo):
        self.mode = combo.get_active_id() or ncam_preview.MODE_ALL
        self.area.queue_draw()

    def _on_cat(self, _btn):
        self.area.queue_draw()

    def _shown_cats(self):
        return {c for c, b in self.cat_btns.items() if b.get_active()}

    def _move_colour(self):
        """Per-move colour for the By operation / By tool modes."""
        if self.colorize == 'operation':
            order = self.toolpath.operations
            return lambda m: ncam_preview.palette_colour(m.op, order)
        if self.colorize == 'tool':
            order = self.toolpath.tools
            return lambda m: ncam_preview.palette_colour(m.tool, order)
        return None

    def _on_colorize(self, combo):
        self.colorize = combo.get_active_id() or 'plain'
        self.area.queue_draw()

    def _on_cmp_value(self, _entry):
        def num(entry, fallback):
            try:
                return float(entry.get_text().replace(',', '.'))
            except ValueError:
                return fallback          # mid-typing; keep the last good value
        self.leftover = num(self.leftover_entry, self.leftover)
        self.tolerance = max(num(self.tol_entry, self.tolerance), 0.0)
        if self.colorize == 'comparison':
            self.area.queue_draw()

    def _classes(self, field):
        """Per-column comparison classes, or None for a plain fill."""
        if field is None or self.colorize != 'comparison':
            return None
        pts = None
        if self.profile_cb is not None:
            try:
                pts = self.profile_cb()
            except Exception:
                pts = None
        if not pts or len(pts) < 2:
            # nothing to compare against - a project with no profile feature.
            # Say so rather than silently drawing a plain fill that looks like
            # a part which is entirely in tolerance.
            self._set_status(_('Comparison needs a profile feature '
                               '(a Lathe Polyline) to compare against'))
            return None
        return ncam_preview.compare_field(field, pts, self.leftover,
                                          self.tolerance)

    def _on_speed(self, combo):
        sid = combo.get_active_id()
        if sid:
            self.speed = float(sid)

    def _stop_sim(self):
        self.sim_running = False
        if self._sim_source is not None:
            GLib.source_remove(self._sim_source)
            self._sim_source = None

    def _sync_play_icon(self):
        self.play_btn.set_image(gtk.Image.new_from_icon_name(
            'media-playback-pause' if self.sim_running
            else 'media-playback-start', gtk.IconSize.BUTTON))
        self.play_btn.show_all()

    def _sim_tick(self):
        # ~8 s for the whole path at 1x regardless of length, so a long program
        # is still watchable and a short one is not over before it is seen
        self.sim_t = min(1.0, self.sim_t + self.BASE_STEP * self.speed)
        self.sim_scale.set_value(self.sim_t)
        if self.sim_t >= 1.0:
            self._stop_sim()
            self._sync_play_icon()
            return False
        return True

    def _on_scrub(self, scale):
        v = scale.get_value()
        if abs(v - self.sim_t) > 1e-9:
            self.sim_t = v
            self.area.queue_draw()
        else:
            self.area.queue_draw()

    def _tool_state(self):
        if self.toolpath.empty or self.sim_t <= 0.0:
            return None
        if self._acc is None:
            self._acc, self._total = ncam_preview.path_lengths(self.toolpath)
        pos, _i, _k = ncam_preview.position_at(self.toolpath, self.sim_t,
                                               self._acc, self._total)
        return {'pos': pos, 'nose_r': self.nose_r, 'orient': self.orient,
                'cl_deg': self.cl_deg, 'included_deg': self.included_deg}

    # -- zoom and pan -------------------------------------------------------
    def _on_scroll(self, area, ev):
        d = ev.direction
        if d == Gdk.ScrollDirection.SMOOTH:
            # a touchpad reports fractions; the sign is what matters
            step = -ev.delta_y
        elif d == Gdk.ScrollDirection.UP:
            step = 1.0
        elif d == Gdk.ScrollDirection.DOWN:
            step = -1.0
        else:
            return False
        if abs(step) < 1e-6:
            return False
        alloc = area.get_allocation()
        self.view.zoom_at(1.15 ** step, ev.x, ev.y, alloc.width, alloc.height)
        area.queue_draw()
        self._show_zoom()
        return True

    def _on_button(self, area, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            # double click re-fits, so there is always a way back from a lost
            # view without hunting for a button
            self.view.reset()
            area.queue_draw()
            self._show_zoom()
            return True
        self._drag = (ev.x, ev.y)
        return True

    def _on_motion(self, area, ev):
        if self._drag is None:
            return False
        self.view.pan(ev.x - self._drag[0], ev.y - self._drag[1])
        self._drag = (ev.x, ev.y)
        area.queue_draw()
        return True

    def _show_zoom(self):
        self._render_status()

    # -- drawing ------------------------------------------------------------
    def _on_draw(self, area, cr):
        alloc = area.get_allocation()
        stock = None
        if self.stock_cb is not None:
            try:
                stock = self.stock_cb()
            except Exception:
                stock = None
        fld = self._stock_field()
        idx = None
        if self.sim_t > 0.0 and not self.toolpath.empty:
            if self._acc is None:
                self._acc, self._total = ncam_preview.path_lengths(self.toolpath)
            _p, idx, _k = ncam_preview.position_at(self.toolpath, self.sim_t,
                                                   self._acc, self._total)
        moves = ncam_preview.visible_moves(self.toolpath, self.mode, idx,
                                           self._shown_cats())
        ncam_preview.draw_toolpath(cr, alloc.width, alloc.height,
                                   self.toolpath, self.plane, stock,
                                   view=self.view, tool=self._tool_state(),
                                   field=fld, classes=self._classes(fld),
                                   moves=moves, move_colour=self._move_colour(),
                                   points=self.points_btn.get_active())
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
        self.preview_pane = PreviewPane(ini, plane, self._preview_stock,
                                       self._preview_profile)

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

    def _preview_profile(self):
        """The finished profile as (z, diameter), or None.

        Straight from lathe_sections.resolve_points on the polyline feature -
        the very function the G-code is generated from - so the surface the
        simulation is judged against is the part itself, not a second
        description of it that could drift.

        Only a polyline defines a whole profile; the parametric ops each cut one
        wall. Returning None for those is honest, and the caller says so rather
        than drawing everything as in-tolerance.
        """
        try:
            f = self._find_feature('polyline')
            if f is None:
                return None
            import lathe_sections
            pts = lathe_sections.resolve_points(f)
            return pts if pts and len(pts) >= 2 else None
        except Exception:
            return None

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
