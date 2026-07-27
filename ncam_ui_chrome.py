import webbrowser

import ncam
from ncam import gtk, gdk, GLib, _, tv_select, XML_TAG


class NCamUIChromeMixin:
    def edit_menu_activate(self, *arg):
        txt = self.clipboard.wait_for_text()
        if txt:
            self.actionPaste.set_enabled(XML_TAG in txt)
        else:
            self.actionPaste.set_enabled(False)

        self.adt_mi.set_visible(self.selected_type in ['float', 'int'])
        self.art_mi.set_visible(self.selected_type == 'gcode')
        self.sep1.set_visible(self.selected_type in ['float', 'int', 'gcode'])


    def utilMenu_activate(self, *arg):
        if ncam.default_metric :
            self.mi_chunits.set_label(_("Change Units to Imperial"))
        else :
            self.mi_chunits.set_label(_("Change Units to Metric"))


    def view_menu_activate(self, *arg):
        self.agrp_mi.set_visible(self.selected_type in ["sub-header", "header"] and \
                                 self.actionDualView.get_active())
        self.aren_mi.set_visible(self.iter_selected_type == tv_select.feature)
        self.sep3.set_visible(self.agrp_mi.get_visible() or self.aren_mi.get_visible())

        self.d_menu.set_visible(self.selected_type == 'float')
        self.sep2.set_visible(self.selected_type == 'float')


    def action_lcncHome(self, *arg):
        webbrowser.open('http://www.linuxcnc.org')


    def action_lcncForum(self, *arg):
        webbrowser.open('http://www.linuxcnc.org/index.php/english/forum/40-subroutines-and-ngcgui')


    def action_youTube(self, *arg):
        webbrowser.open('https://www.youtube.com/channel/UCjOe4VxKL86HyVrshTmiUBQ')


    def action_youTrans(self, *arg):
#        webbrowser.open('https://www.youtube.com/channel/UCjOe4VxKL86HyVrshTmiUBQ')
        pass


    def _cancel_autorefresh_timer(self):
        tid = getattr(self, 'timeout', None)
        if tid is not None:
            try:
                GLib.source_remove(tid)
            except (TypeError, AttributeError, ValueError):
                pass
            self.timeout = None


    def _autorefresh_toggled(self, action):
        if not action.get_active():
            self._cancel_autorefresh_timer()
        self.autorefresh_call()


    def _toplevel_key_press(self, widget, event):
        """F2 anywhere in the panel starts editing the selected parameter value."""
        if gdk.keyval_name(event.keyval) != 'F2':
            return False
        tv = self.treeview
        if self.treeview2 is not None and self.treeview2.get_visible():
            tv = self.treeview2
        model, itr = tv.get_selection().get_selected()
        if itr is None:
            return False
        path = model.get_path(itr)
        tv.grab_focus()
        tv.set_cursor_on_cell(path, tv.get_column(1), None, True)
        return True


    def _grip_realize(self, widget):
        try:
            cursor = gdk.Cursor.new_from_name(widget.get_display(), 'ew-resize')
            widget.get_window().set_cursor(cursor)
        except Exception:
            pass


    def _grip_press(self, widget, event):
        if event.button == 1:
            self._grip_drag = (event.x_root, self.get_allocated_width())
            return True
        return False


    def _grip_release(self, widget, event):
        self._grip_drag = None
        return event.button == 1


    # width of the collapsed rail - just enough for the arrow and the label
    COLLAPSE_RAIL_W = 24

    def build_collapse_rail(self):
        """A thin vertical rail on the panel's own edge: an arrow that rolls
        NativeCAM out to the centre, and rolls it back out of the way again.

        The panel lives at the side of the host GUI, so when it is not being
        used it is only in the way of the backplot. Collapsing leaves this rail
        behind rather than the whole tree, and the rail keeps the arrow and the
        name so it is obvious what to click to get it back.
        """
        rail = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=2)
        rail.set_size_request(self.COLLAPSE_RAIL_W, -1)

        btn = gtk.Button()
        btn.set_relief(gtk.ReliefStyle.NONE)
        self._collapse_arrow = gtk.Image.new_from_icon_name(
            'pan-end-symbolic', gtk.IconSize.BUTTON)
        btn.add(self._collapse_arrow)
        btn.connect('clicked', self.toggle_panel)
        rail.pack_start(btn, False, False, 0)

        lbl = gtk.Label(label='NativeCAM')
        lbl.set_angle(270)
        rail.pack_start(lbl, False, False, 4)

        self._collapse_btn = btn
        self._collapse_rail = rail
        self._panel_collapsed = False
        self._panel_width = None
        self._update_collapse_button()
        return rail

    def _update_collapse_button(self):
        """Arrow points the way the panel will move, and the tooltip says so."""
        if getattr(self, '_collapse_arrow', None) is None:
            return
        collapsed = getattr(self, '_panel_collapsed', False)
        self._collapse_arrow.set_from_icon_name(
            'pan-start-symbolic' if collapsed else 'pan-end-symbolic',
            gtk.IconSize.BUTTON)
        self._collapse_btn.set_tooltip_text(
            _('Roll NativeCAM out') if collapsed else _('Roll NativeCAM away'))

    def toggle_panel(self, *arg):
        self.set_panel_collapsed(not getattr(self, '_panel_collapsed', False))

    def set_panel_collapsed(self, collapsed):
        """Hide or restore everything except the rail.

        Width is driven the same way the drag grip drives it - a size request
        plus a resize of the plug's own toplevel, because shrinking does not
        propagate through the size request alone when embedded.
        """
        collapsed = bool(collapsed)
        if collapsed == getattr(self, '_panel_collapsed', False):
            return
        if collapsed:
            w = self.get_allocated_width()
            if w > self.COLLAPSE_RAIL_W:
                self._panel_width = w
        self._panel_collapsed = collapsed

        for w in (getattr(self, 'main_box', None), getattr(self, '_resize_grip', None)):
            if w is not None:
                w.set_visible(not collapsed)

        target = self.COLLAPSE_RAIL_W if collapsed else (self._panel_width or 400)
        self.set_size_request(target, 80)
        top = self.get_toplevel()
        if isinstance(top, gtk.Window) and top is not self:
            try:
                top.resize(target, max(80, top.get_allocated_height()))
            except Exception:
                pass
        self._update_collapse_button()

    def _grip_motion(self, widget, event):
        if self._grip_drag is None:
            return False
        start_x, start_w = self._grip_drag
        # panel sits at the right of the host GUI: dragging left widens it
        new_w = max(200, int(start_w + (start_x - event.x_root)))
        self.set_size_request(new_w, 80)
        # growing propagates through the size request alone, but shrinking
        # does not: the plug must ask its socket for the smaller geometry
        top = self.get_toplevel()
        if isinstance(top, gtk.Window) and top is not self:
            try:
                top.resize(new_w, max(80, top.get_allocated_height()))
            except Exception:
                pass
        return True


    def _close_all_popups(self, *arg):
        """Close all active GTK popup windows when LinuxCNC exits.
        Prevents phantom combo dropdowns and VKB dialogs from remaining on screen.
        """
        self._ncam_shutting_down = True
        self._cancel_autorefresh_timer()
        # Close any open combo popups on all CellRenderers in treeviews
        for tv in [self.treeview]:
            try:
                tv.set_sensitive(False)
            except Exception:
                pass
        # Standalone only: popups are ours; GladeVCP must not gtk.main_quit() or mass-destroy toplevels
        # while the plug/socket is shutting down (GdkWindow destroyed / NULL Gtk warnings).
        if not ncam.NCAM_STANDALONE:
            return
        for w in gtk.Window.list_toplevels():
            try:
                if w is not self.get_toplevel() and w.get_visible():
                    w.hide()
                    w.destroy()
            except Exception:
                pass
        gtk.main_quit()


    def on_destroy(self, *arg):
        self._ncam_shutting_down = True
        self._cancel_autorefresh_timer()

        def _safe_call(fn):
            """Avoid tracebacks during LinuxCNC/gladevcp teardown (SIGINT, X disconnect, half-dead GTK)."""
            try:
                fn()
            except KeyboardInterrupt:
                pass
            except Exception:
                pass

        _safe_call(self._save_autorefresh_preference)
        if self.pref.autosave:
            _safe_call(self.action_saveCurrent)


    def _on_hpane_size_allocate(self, widget, allocation):
        total_w = allocation.width
        if total_w > 100:
            if not self.actionDualView.get_active() or not self.actionSideSide.get_active():
                widget.set_position(total_w)
            else:
                pos = widget.get_position()
                new_pos = pos
                if pos > total_w - 120:
                    new_pos = total_w - 120
                if new_pos < 100:
                    new_pos = 100
                if pos != new_pos:
                    widget.set_position(new_pos)


    def _on_vpane_size_allocate(self, widget, allocation):
        total_h = allocation.height
        if total_h > 100:
            if not self.actionDualView.get_active() or self.actionSideSide.get_active():
                widget.set_position(total_h)
            else:
                pos = widget.get_position()
                new_pos = pos
                if pos > total_h - 100:
                    new_pos = total_h - 100
                if new_pos < 50:
                    new_pos = 50
                if pos != new_pos:
                    widget.set_position(new_pos)


