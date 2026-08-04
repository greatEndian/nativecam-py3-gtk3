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
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk      # noqa: E402
from gi.repository import Gdk            # noqa: E402
from gi.repository import GLib            # noqa: E402

import ncam_preview                        # noqa: E402


def _trace(what):
    """One line to stderr, flushed, naming a UI callback as it runs.

    A FREEZE leaves no traceback - the process is alive and stuck, so there is
    nothing to raise and nothing to catch. What it does leave is whatever was
    already flushed, so the last line printed names the callback that did not
    return. That is the only evidence a hang gives up, and it costs a handful
    of lines per session because only the coarse callbacks are traced, never
    the per-frame tick.

    greatEndian hit Stop and had to kill AXIS - no traceback, and the stop path
    audits as cheap: sim_t 0 short-circuits the field rebuild, rs274 runs on a
    worker thread with -b and a 120 s timeout, and parse_program measures at
    1.76 s / 17 MB on the live program. Reading found nothing, so the next
    occurrence has to say where itself.

    Set NCAM_NO_TRACE=1 to silence it.
    """
    if os.getenv('NCAM_NO_TRACE'):
        return
    try:
        sys.stderr.write('[ncam-preview] %s\n' % what)
        sys.stderr.flush()
    except Exception:
        pass


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
                 profile_cb=None, soft_cb=None, comp_cb=None,
                 comp_mode_cb=None):
        self.ini_path = ini_path
        self.plane = plane
        # from the ini's own limit, in mm/min. MAX_LINEAR_VELOCITY is per
        # SECOND there, and taking it for per-minute makes every rapid sixty
        # times too slow - which is most of the total on a short part.
        self.rapid = ncam_preview.rapid_rate(ini_path)
        # returns (a_min, a_max, b_min, b_max) for the stock, or None. A
        # callback rather than a value so the pane never holds a stale copy of
        # a Workpiece the operator has since edited.
        self.stock_cb = stock_cb
        # the finished profile, for Comparison colouring. A callback for the
        # same reason stock_cb is one: it must never be a stale copy of a
        # feature the operator has since edited.
        self.profile_cb = profile_cb
        self.soft_cb = soft_cb
        # where the tool CONTROL POINT should travel once compensation is
        # applied. A callback like the others, so it follows the operator's
        # edits without anything having to remember to refresh it.
        self.comp_cb = comp_cb
        self.comp_mode_cb = comp_mode_cb
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
        # no blinking cursor: it is a frame-clock tick callback on a page that
        # is usually not the visible tab, and there is nothing to type into
        view.set_cursor_visible(False)
        scroll = gtk.ScrolledWindow()
        scroll.add(view)
        self.widget.append_page(scroll, gtk.Label(label=_('G-code')))

        # ncam.ngc is O-word calls and expressions: true, but it does not say
        # where the tool goes. This third page is the same program after the
        # interpreter has had it - every subroutine, loop and expression gone,
        # every number a number the machine moves to. It costs no width: the
        # notebook is scrollable, so another tab does not widen the pane.
        self.flat_buffer = gtk.TextBuffer()
        flat_view = gtk.TextView.new_with_buffer(self.flat_buffer)
        flat_view.set_editable(False)
        flat_view.set_monospace(True)
        flat_view.set_cursor_visible(False)
        flat_scroll = gtk.ScrolledWindow()
        flat_scroll.add(flat_view)
        self.widget.append_page(flat_scroll, gtk.Label(label=_('Flat')))

        # Info follows the tool as it plays; Statistics is per program and is
        # rebuilt only when one is parsed.
        self.info_rows = {}
        info_grid = gtk.Grid(row_spacing=2, column_spacing=8, margin=6)
        for r, (key, label) in enumerate((
                ('pos', _('Position')), ('move', _('Movement')),
                ('op', _('Operation')), ('tool', _('Tool')),
                ('feed', _('Feed')), ('spindle', _('Spindle')),
                ('rate', _('Actual rate')), ('at', _('At move')))):
            name = gtk.Label(label=label)
            name.set_halign(gtk.Align.START)
            val = gtk.Label(label='-')
            val.set_halign(gtk.Align.START)
            info_grid.attach(name, 0, r, 1, 1)
            info_grid.attach(val, 1, r, 1, 1)
            self.info_rows[key] = val
        info_scroll = gtk.ScrolledWindow()
        info_scroll.add(info_grid)
        self.widget.append_page(info_scroll, gtk.Label(label=_('Info')))

        self.stats_buffer = gtk.TextBuffer()
        stats_view = gtk.TextView.new_with_buffer(self.stats_buffer)
        stats_view.set_editable(False)
        stats_view.set_monospace(True)
        stats_view.set_cursor_visible(False)
        stats_scroll = gtk.ScrolledWindow()
        stats_scroll.add(stats_view)
        self.widget.append_page(stats_scroll, gtk.Label(label=_('Stats')))

        # --- simulation controls ------------------------------------------
        # Play walks the toolpath; the slider scrubs it. Parameterised by
        # DISTANCE along the path rather than by time - the playback is for
        # watching a corner form, not for running in real time. The Statistics
        # page does the time arithmetic, where being right matters.
        self.sim_t = 0.0
        self.sim_running = False
        self._sim_source = None
        self._acc = None
        self._total = 0.0
        self.nose_r = 0.0
        self.orient = 0
        self.cl_deg = None
        self.included_deg = None
        self.front_deg = None
        self.back_deg = None
        self.flank_len = 0.0
        self.shank_h = 0.0
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

        # --- toolpath display, in a menu rather than a row of buttons -------
        # As three rows of controls this pane demanded 522 px of minimum width.
        # The panel opens at 400 and the operator drags it narrower, so the
        # right-hand controls were off the edge - and a control you cannot see
        # is a control that does not exist. Wrapping them was tried first: GTK3
        # has no wrap box, and a FlowBox lays out in UNIFORM columns sized to
        # its widest child, so at 400 px it stacked one cluster per line and
        # spent 208 px of height to save nothing.
        #
        # A menu costs one button of width and none of height, and unlike a
        # Popover it is its own X window - so it is not clipped by the panel it
        # is embedded in, which is the whole problem being solved here.
        self.mode = ncam_preview.MODE_ALL
        self.disp_menu = gtk.Menu()
        self.mode_items = {}
        group = []
        for mid, label, tip in (
                (ncam_preview.MODE_ALL, _('All toolpaths'),
                 _('The whole toolpath, wherever the tool has reached')),
                (ncam_preview.MODE_BEHIND, _('Behind'),
                 _('Only what the tool has already traversed')),
                (ncam_preview.MODE_AHEAD, _('Ahead'),
                 _('Only what the tool has yet to traverse')),
                (ncam_preview.MODE_OPERATION, _('Operation'),
                 _('Only the operation the tool is in')),
                (ncam_preview.MODE_TAIL, _('Tail'),
                 _('A short trail behind the tool'))):
            it = gtk.RadioMenuItem.new_with_label(group, label)
            group = it.get_group()
            it.set_tooltip_text(tip)
            it.set_active(mid == ncam_preview.MODE_ALL)
            it.connect('toggled', self._on_mode, mid)
            self.mode_items[mid] = it
        mode_sub = gtk.Menu()
        for mid in (ncam_preview.MODE_ALL, ncam_preview.MODE_BEHIND,
                    ncam_preview.MODE_AHEAD, ncam_preview.MODE_OPERATION,
                    ncam_preview.MODE_TAIL):
            mode_sub.append(self.mode_items[mid])
        mode_item = gtk.MenuItem(label=_('Show'))
        mode_item.set_submenu(mode_sub)
        self.disp_menu.append(mode_item)
        self.disp_menu.append(gtk.SeparatorMenuItem())

        # Cutting moves and leads are what you look at; links and connections
        # are usually noise, so they start hidden - the reference panel makes
        # the same choice.
        self.cat_btns = {}
        for cat, label, on, tip in (
                (ncam_preview.CUT, _('Cutting moves'), True,
                 _('The cuts themselves')),
                (ncam_preview.LEAD, _('Lead moves'), True,
                 _('The entry to, and exit from, a cut. Inferred from where a '
                   'feed sits next to a rapid, not marked in the G-code.')),
                (ncam_preview.LINK, _('Link moves'), False,
                 _('Rapids within one operation')),
                (ncam_preview.CONNECT, _('Connection moves'), False,
                 _('Rapids between operations'))):
            b = gtk.CheckMenuItem(label=label)
            b.set_active(on)
            b.set_tooltip_text(tip)
            b.connect('toggled', self._on_cat)
            self.cat_btns[cat] = b
            self.disp_menu.append(b)
        self.disp_menu.append(gtk.SeparatorMenuItem())

        self.contour_btn = gtk.CheckMenuItem(label=_('Contour'))
        self.contour_btn.set_active(True)
        self.contour_btn.set_tooltip_text(
            _('Show the drawn contour and the one the tool can actually reach. '
              'Where the tool back angle shadows part of the profile the two '
              'separate, and the gap is material that cannot be cut with this '
              'tool. Where everything is reachable they coincide.'))
        self.contour_btn.connect('toggled', self._on_contour)
        self.disp_menu.append(self.contour_btn)

        self.points_btn = gtk.CheckMenuItem(label=_('Points'))
        self.points_btn.set_tooltip_text(
            _('Mark where each move starts and ends - useful on a path made of '
              'many small segments.'))
        self.points_btn.connect('toggled', lambda _b: self.area.queue_draw())
        self.disp_menu.append(self.points_btn)
        self.disp_menu.append(gtk.SeparatorMenuItem())

        self.col_items = {}
        group = []
        for cid, label, tip in (
                ('plain', _('Stock'), _('One colour for the material')),
                ('comparison', _('Comparison'),
                 _('Colour the remaining material against the finished '
                   'profile: blue where stock still stands proud, green where '
                   'it is on size, red where it has been cut past the part.')),
                ('operation', _('By operation'),
                 _('A colour per feature, from the markers NativeCAM writes')),
                ('tool', _('By tool'), _('A colour per tool number'))):
            it = gtk.RadioMenuItem.new_with_label(group, label)
            group = it.get_group()
            it.set_tooltip_text(tip)
            it.set_active(cid == 'plain')
            it.connect('toggled', self._on_colorize, cid)
            self.col_items[cid] = it
        col_sub = gtk.Menu()
        for cid in ('plain', 'comparison', 'operation', 'tool'):
            col_sub.append(self.col_items[cid])
        col_item = gtk.MenuItem(label=_('Colour'))
        col_item.set_submenu(col_sub)
        self.disp_menu.append(col_item)
        self.disp_menu.show_all()

        self.disp_btn = gtk.MenuButton(label=_('Display'))
        self.disp_btn.set_popup(self.disp_menu)
        self.disp_btn.set_tooltip_text(
            _('What is drawn: which part of the toolpath, which kinds of move, '
              'the contour overlays, and how the material is coloured.'))
        self.sim_box.pack_start(self.disp_btn, False, False, 0)

        # Leave/Tol belong to Comparison and mean nothing in the other three
        # colourings, so they are only in the pane when that one is chosen -
        # the reference panel marks them "Comparison only" for the same reason.
        # That keeps the steady-state chrome to one row and the status line.
        self.cmp_box = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=4)
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
        self.box.pack_start(self.cmp_box, False, False, 0)
        self.box.pack_start(self.status, False, False, 2)
        # A GLib timeout is owned by the main loop, not by the widget, so a
        # running simulation keeps firing after the panel is torn down and
        # calls set_value/queue_draw on dead widgets. Embedded in AXIS that
        # surfaces as a burst of
        #   gdk_frame_clock_end_updating: assertion GDK_IS_FRAME_CLOCK failed
        # followed by an X BadWindow, and it takes LinuxCNC down with it.
        self.box.connect('destroy', lambda _w: self._stop_sim())
        self.box.show_all()
        # after show_all, so the row's own children get shown once and only the
        # row itself is toggled from here on. Both halves are needed: without
        # no_show_all a later show_all from whatever the pane is packed into
        # brings the row back, and without the show_all above the row would
        # come back empty. set_visible still works through no_show_all - it is
        # only show_all that skips the widget.
        self.cmp_box.set_no_show_all(True)
        self.cmp_box.hide()

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
        _trace('refresh start')
        self._busy = True
        self._set_status(_('Reading toolpath...'))
        t = threading.Thread(target=self._worker, args=(fname,), daemon=True)
        t.start()

    def _worker(self, fname):
        tp = ncam_preview.parse_program(fname, self.ini_path)
        GLib.idle_add(self._done, tp)

    def _done(self, tp):
        _trace('done')
        # the interpreter runs on a worker thread and hands the result back
        # with idle_add, so the panel can be gone by the time it lands.
        #
        # THE LIVENESS TEST IS THE WINDOW, AND ONLY THE WINDOW. It used to be
        # ANDed with `self._acc is not None`, which is a cached path-length
        # array and says nothing about whether the panel is alive - and it is
        # set to None four lines below, so on the first result after any
        # refresh the guard could not fire at all. A parse that finished after
        # the pane went away then ran on through set_text/_render_stats/
        # _render_info, touching widgets that no longer exist.
        if self.area.get_window() is None:
            self._busy = False
            return False
        self.toolpath = tp
        self._acc = None          # lengths belong to the old path
        self._reset_field()
        self._busy = False
        self.flat_buffer.set_text(
            tp.flat or _('(no flattened listing - the interpreter run failed)'))
        self._render_stats()
        self._render_info()
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

    def _render_stats(self):
        """The Statistics page - one program, not one position."""
        tp = self.toolpath
        if tp.empty:
            self.stats_buffer.set_text(_('Nothing parsed yet.'))
            return
        st = ncam_preview.statistics(tp, self.rapid)
        L = []
        L.append(_('Machining time  %s') % ncam_preview.fmt_time(st['time']))
        L.append(_('  cutting       %s') % ncam_preview.fmt_time(st['cut_time']))
        L.append(_('  rapid         %s') % ncam_preview.fmt_time(st['rapid_time']))
        L.append('')
        L.append(_('Distance        %.1f mm') % st['dist'])
        L.append(_('  cutting       %.1f mm') % st['cut_dist'])
        L.append(_('  rapid         %.1f mm') % st['rapid_dist'])
        L.append('')
        L.append(_('Moves           %d') % st['moves'])
        L.append(_('Operations      %d') % len(st['ops']))
        L.append(_('Tools           %s')
                 % (', '.join('T%d' % t for t in st['tools']) or '-'))
        L.append(_('Rapid rate      %(v).0f mm/min (%(src)s)')
                 % {'v': self.rapid,
                    'src': _('from the ini') if self.ini_path
                    else _('no ini - assumed')})
        if st['unknown']:
            # never folded into the total: a time that quietly drops the moves
            # it could not work out reads exactly like a complete one
            L.append('')
            L.append(_('%d move(s) have no workable rate and are NOT in the '
                       'time above - a feed per revolution with no spindle '
                       'speed does not give a speed.') % st['unknown'])
        L.append('')
        L.append(_('Per operation'))
        for row in st['per_op']:
            L.append('  %-22s %9.1f mm  %8s  %5.1f%%'
                     % (row['name'][:22], row['dist'],
                        ncam_preview.fmt_time(row['time']), row['share']))
        self.stats_buffer.set_text('\n'.join(L))

    def _render_info(self):
        """The Info page - where the tool is now, and under what."""
        idx, point = None, None
        if self.sim_t > 0.0 and not self.toolpath.empty:
            if self._acc is None:
                self._acc, self._total = ncam_preview.path_lengths(self.toolpath)
            point, idx, _k = ncam_preview.position_at(
                self.toolpath, self.sim_t, self._acc, self._total)
        nfo = ncam_preview.info_at(self.toolpath, idx, point, self.rapid)
        if nfo is None:
            for val in self.info_rows.values():
                val.set_text('-')
            return
        move = nfo['kind'] + ((', ' + nfo['cat']) if nfo['cat'] else '')
        op = nfo['op'] or '-'
        if nfo['phase']:
            op = '%s / %s' % (op, nfo['phase'])
        if nfo['feed']:
            feed = (_('%.4g mm/rev') if nfo['fmode'] == 'rev'
                    else _('%.4g mm/min')) % nfo['feed']
        else:
            feed = '-'
        text = {
            'pos': 'X%.4g  Z%.4g' % (nfo['x'], nfo['z']),
            'move': move,
            'op': op,
            'tool': ('T%d' % nfo['tool']) if nfo['tool'] is not None else '-',
            'feed': feed,
            'spindle': ('%.0f rpm' % nfo['rpm']) if nfo['rpm'] else '-',
            'rate': ('%.0f mm/min' % nfo['rate']) if nfo['rate'] else _('unknown'),
            'at': '%d / %d' % (nfo['index'] + 1, nfo['moves']),
        }
        for key, val in self.info_rows.items():
            val.set_text(text.get(key, '-'))

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
        markup = '<small>%s</small>' % GLib.markup_escape_text(text)
        legend = self._legend()
        if legend:
            markup += '  <small>%s</small>' % legend
        self.status.set_markup(markup)

    def _legend(self):
        """Pango markup naming the colours currently on the plot.

        In the status line rather than a row of its own: a legend is the kind
        of thing that quietly costs another 34 px of a pane that had none to
        spare, and it is only worth showing while there is something in the
        picture it explains.
        """
        def swatch(rgb, label):
            return '<span foreground="#%02x%02x%02x">■</span> %s' % (
                int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255),
                GLib.markup_escape_text(label))

        col = ncam_preview.COL
        if self.colorize == 'comparison':
            cmp_col = ncam_preview.CMP_COL
            parts = [swatch(cmp_col[ncam_preview.EXCESS], _('proud')),
                     swatch(cmp_col[ncam_preview.IN_TOL], _('on size')),
                     swatch(cmp_col[ncam_preview.GOUGE], _('gouged'))]
        elif self.colorize in ('operation', 'tool'):
            return ''                     # a colour per key; no fixed legend
        else:
            # only the phases this program actually contains: a legend naming
            # a colour that is nowhere on the plot is worse than none
            names = {ncam_preview.PREFINISH: (col['prefinish'], _('pre-finish')),
                     ncam_preview.FINISH: (col['finish'], _('finish'))}
            found = ncam_preview.phases_in(self.toolpath.moves)
            parts = [swatch(col['feed'], _('rough'))] if found else []
            parts += [swatch(*names[p]) for p in found if p in names]
        if self.contour_btn.get_active() and self.soft_cb is not None:
            parts.append(swatch(col['soft'], _('reachable')))
        # the compensated path, and WHICH MODE produced it. The mode is the
        # part that answers the question: a polyline with nose comp off has no
        # compensation in its path at all, and every saved test project had it
        # off, which is what "we see uncompensated" turned out to mean.
        if self.contour_btn.get_active() and self.comp_mode_cb is not None:
            mode = self._comp_mode()
            if mode:
                parts.append(swatch(col['comp'], _('comp: %s') % mode))
        return '   '.join(parts)

    # -- simulation ---------------------------------------------------------
    def set_tool(self, nose_r, orient, cl_deg=None, included_deg=None,
                 front_deg=None, back_deg=None, flank_len=0.0,
                 shank_h=0.0):
        """Nose radius, orientation, the real insert angles, and the flank.

        nose_r/orient come from ncam.tip_comp_inputs(), the same source the
        G-code compensates with. cl_deg/included_deg/front_deg/back_deg come
        from the tool table's I and J, so the drawn insert is the one in the
        turret rather than a generic wedge. flank_len comes from the Tool
        Change - it is the one dimension the tool table has no column for.
        """
        self.nose_r, self.orient = nose_r or 0.0, orient or 0
        self.cl_deg, self.included_deg = cl_deg, included_deg
        self.front_deg, self.back_deg = front_deg, back_deg
        self.flank_len = flank_len or 0.0
        self.shank_h = shank_h or 0.0
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
        _trace('play')
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
        _trace('stop')
        self._stop_sim()
        self.sim_t = 0.0
        self._reset_field()
        self.sim_scale.set_value(0.0)
        self._sync_play_icon()
        self.area.queue_draw()
        self._render_info()
        _trace('stop done')

    def _on_mode(self, item, mid):
        # a radio group fires twice per change - once for the item losing the
        # selection and once for the item gaining it. Acting on both would set
        # the mode to whichever fired last, which is not the one clicked.
        if not item.get_active():
            return
        self.mode = mid
        self.area.queue_draw()

    def _on_cat(self, _btn):
        self.area.queue_draw()

    def _on_contour(self, _btn):
        self._render_status()             # the legend follows the overlay
        self.area.queue_draw()

    def _shown_cats(self):
        return {c for c, b in self.cat_btns.items() if b.get_active()}

    def _contour(self, cb):
        if cb is None or not self.contour_btn.get_active():
            return None
        try:
            return cb()
        except Exception:
            return None

    COMP_MODES = {0: 'off', 1: 'CNC', 2: 'CAM'}

    def _comp_mode(self):
        """'CNC' / 'CAM' / 'off' for the polyline, or None when there is none.

        Read live rather than cached: the operator changes it on the feature
        and the legend has to follow, the same reason every contour here is a
        callback.
        """
        try:
            return self.COMP_MODES.get(int(self.comp_mode_cb()))
        except Exception:
            return None

    def _move_colour(self):
        """Per-move colour for the By operation / By tool modes."""
        if self.colorize == 'operation':
            order = self.toolpath.operations
            return lambda m: ncam_preview.palette_colour(m.op, order)
        if self.colorize == 'tool':
            order = self.toolpath.tools
            return lambda m: ncam_preview.palette_colour(m.tool, order)
        # plain: the pre-finish contour pass in its own colour, so it reads
        # apart from the roughing levels and the finish pass around it. No
        # marker, no change - a program without one draws exactly as before.
        if ncam_preview.has_phase(self.toolpath.moves):
            return ncam_preview.phase_colour
        return None

    def _on_colorize(self, item, cid):
        if not item.get_active():
            return                        # the deselect half of the pair
        self.colorize = cid
        self.cmp_box.set_visible(cid == 'comparison')
        self._render_status()
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
        # belt as well as braces: between the timeout being scheduled and it
        # firing, the panel can have gone away
        if self.area.get_window() is None:
            self._sim_source = None
            return False
        # ~8 s for the whole path at 1x regardless of length, so a long program
        # is still watchable and a short one is not over before it is seen
        self.sim_t = min(1.0, self.sim_t + self.BASE_STEP * self.speed)
        self.sim_scale.set_value(self.sim_t)     # which redraws and re-informs
        if self.sim_t >= 1.0:
            # Returning False is what removes this source, so the id must be
            # dropped WITHOUT calling GLib.source_remove on it - removing a
            # source from inside its own dispatch and then returning False
            # takes it away twice. It normally only logs, but it is a real
            # double free of a source being dispatched and there is no reason
            # to keep it.
            self.sim_running = False
            self._sim_source = None
            self._sync_play_icon()
            return False
        return True

    def _on_scrub(self, scale):
        v = scale.get_value()
        if abs(v - self.sim_t) > 1e-9:
            self.sim_t = v
        self.area.queue_draw()
        self._render_info()

    def _tool_state(self):
        if self.toolpath.empty or self.sim_t <= 0.0:
            return None
        if self._acc is None:
            self._acc, self._total = ncam_preview.path_lengths(self.toolpath)
        pos, _i, _k = ncam_preview.position_at(self.toolpath, self.sim_t,
                                               self._acc, self._total)
        return {'pos': pos, 'nose_r': self.nose_r, 'orient': self.orient,
                'cl_deg': self.cl_deg, 'included_deg': self.included_deg,
                'front_deg': self.front_deg, 'back_deg': self.back_deg,
                'flank_len': self.flank_len, 'shank_h': self.shank_h}

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
                                   points=self.points_btn.get_active(),
                                   hard=self._contour(self.profile_cb),
                                   soft=self._contour(self.soft_cb),
                                   comp=self._contour(self.comp_cb))
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
                                       self._preview_profile,
                                       self._preview_soft_profile,
                                       self._preview_comp_profile,
                                       self._preview_comp_mode)

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

    def _preview_soft_profile(self):
        """The reachable contour, or None when the drawn one is reachable."""
        try:
            f = self._find_feature('polyline')
            if f is None:
                return None
            import lathe_sections
            import ncam
            # every argument the GENERATED code passes, including the flank
            # length. Dropping it made the drawn contour an infinite-flank one
            # while the passes used the real insert, so the picture disagreed
            # with the program it was drawn from - the two must come out of
            # the same call with the same inputs or neither can be trusted.
            pts, soft = lathe_sections.finish_profile(
                f, ncam.TOOL_TABLE.get_back_angle(), ncam.tip_comp_inputs()[0],
                ncam.TOOL_TABLE.get_flank_len(),
                ncam.TOOL_TABLE.get_back_clear())
            return pts if soft else None
        except Exception:
            return None

    def _preview_comp_mode(self):
        """The polyline's Tool nose comp setting as 0/1/2, or None."""
        f = self._find_feature('polyline')
        if f is None:
            return None
        p = f.get_param('param_n_comp')
        return None if p is None else int(float(p.get_ngc_value()))

    def _preview_comp_profile(self):
        """Where the tool CONTROL POINT travels once compensation is applied.

        The same offset the machine gets: lathe_sections.offset_contour, which
        is what In CAM mode already emits, at the nose radius and the side the
        pass compensates to. Drawing it beside the programmed profile makes
        the compensation visible instead of implied - and drawing it beside
        the ACTUAL toolpath makes it a check, since the two should coincide.

        Returns None when compensation is OFF, deliberately. A line lying
        exactly on the profile would say a compensation is happening that is
        not; nothing is the honest picture. It follows the contour the passes
        follow - the reachable one where the back angle constrains it, the
        drawn one otherwise - because that is what the finish pass traces.
        """
        try:
            mode = self._preview_comp_mode()
            if mode not in (1, 2):
                return None
            import lathe_sections
            import ncam
            f = self._find_feature('polyline')
            if f is None:
                return None
            nose_r, orient = ncam.tip_comp_inputs()
            if nose_r <= 0 or not 0 < int(orient) < 10:
                return None
            pts, _soft = lathe_sections.finish_profile(
                f, ncam.TOOL_TABLE.get_back_angle(), 0.0,
                ncam.TOOL_TABLE.get_flank_len(),
                ncam.TOOL_TABLE.get_back_clear())
            if not pts or len(pts) < 2:
                return None
            # a bore has its material on the other side, the same inversion
            # build_cam_comp_gcode makes
            sp = f.get_param('param_side')
            side = -1 if (sp is not None
                          and int(float(sp.get_ngc_value())) == 1) else 1
            out = lathe_sections.offset_contour(pts, nose_r, int(orient), side)
            return out if out and len(out) >= 2 else None
        except Exception:
            return None

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
