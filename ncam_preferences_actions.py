import os
import json
import math
import tempfile

import ncam
from ncam import (
    gtk, gdk, GLib, _, mess_dlg, mess_yesno,
    ConfigParser, CATALOGS_DIR, USER_DEFAULT_FILE, CONFIG_FILE,
)


class NCamPreferencesActionsMixin:
    def validation_menu_activate(self, *arg):
        # Update global messages checkmark
        self.chk_val_all.handler_block_by_func(self.action_toggle_val_all)
        self.chk_val_all.set_active(not self.pref.val_all_excluded())
        self.chk_val_all.handler_unblock_by_func(self.action_toggle_val_all)
        # Update per-feature checkmark
        feat_has_data = self.selected_feature is not None
        self.chk_val_feat.set_sensitive(feat_has_data)
        if feat_has_data:
            ftype = self.selected_feature.get_type()
            label = '%s "%s"' % (_('Show Messages For'), self.selected_feature.get_name())
            self.chk_val_feat.set_label(label)
            self.chk_val_feat.handler_block_by_func(self.action_toggle_val_feat)
            self.chk_val_feat.set_active(not self.pref.val_feat_excluded(ftype))
            self.chk_val_feat.handler_unblock_by_func(self.action_toggle_val_feat)
        else:
            self.chk_val_feat.set_label(_('Show Messages For Current Type'))


    def action_ValNoDlg(self, *arg):
        self.pref.val_show_none()


    def action_ValFeatDlg(self, *arg):
        self.pref.val_show_all(self.selected_feature.get_type())


    def action_ValFeatNone(self, *arg):
        self.pref.val_show_none(self.selected_feature.get_type())


    def action_toggle_val_all(self, widget, *arg):
        if widget.get_active():
            self.pref.val_show_all()
        else:
            self.pref.val_show_none()


    def action_toggle_val_feat(self, widget, *arg):
        if self.selected_feature is None:
            return
        ftype = self.selected_feature.get_type()
        if widget.get_active():
            self.pref.val_show_all(ftype)
        else:
            self.pref.val_show_none(ftype)


    def action_saveUser(self, *arg) :
        fname = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, USER_DEFAULT_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(fname)

        section = self.selected_feature.get_type()
        if parser.has_section(section) :
            parser.remove_section(section)
        parser.add_section(section)

        for p in self.selected_feature.param :
            t = p.get_type()
            s = p.attr['call'].lstrip('#')
            parser.set(section, s + '--type', t)
            if 'value' in p.attr :
                parser.set(section, s + '--value', p.attr['value'])
            if p.get_hidden() :
                parser.set(section, s + '--hidden', '2')
            if 'grayed' in p.attr :
                parser.set(section, s + '--grayed', p.attr['grayed'])

        with open(fname, 'w') as configfile:
            parser.write(configfile)

        self.pref.read_user_values()
        self.actionDeleteUser.set_enabled(self.selected_feature.get_type() in ncam.USER_SUBROUTINES)


    def action_deleteUser(self, *arg):
        fname = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir,
                             USER_DEFAULT_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(fname)

        section = self.selected_feature.get_type()
        if parser.has_section(section) :
            parser.remove_section(section)
            with open(fname, 'w') as configfile:
                parser.write(configfile)
            self.pref.read_user_values()
            self.actionDeleteUser.set_enabled(self.selected_feature.get_type() in ncam.USER_SUBROUTINES)


    def action_saveLayout(self, *arg) :
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)

        self._store_layout_choices(parser)
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)


    def _store_layout_choices(self, parser):
        if not parser.has_section('layout') :
            parser.add_section('layout')
        parser.set('layout', 'subheaders_in_master', str(self.actionSubHdrs.get_active()))
        parser.set('layout', 'hide_value_column', str(self.actionHideCol.get_active()))
        parser.set('layout', 'dual_view', str(self.actionDualView.get_active()))
        parser.set('layout', 'side_by_side', str(self.actionSideSide.get_active()))
        parser.set('layout', 'autorefresh', str(self.actionAutoRefresh.get_active()))


    def _session_config(self):
        parser = ConfigParser.ConfigParser(interpolation=None)
        parser.read(self.pref.cfg_file)
        return parser

    def _write_session_config(self, parser):
        # A close or interrupted resize must not leave a truncated preferences file.
        descriptor, temporary = tempfile.mkstemp(prefix='.ncam-session-', dir=os.path.dirname(self.pref.cfg_file))
        try:
            with os.fdopen(descriptor, 'w') as stream:
                parser.write(stream)
            os.replace(temporary, self.pref.cfg_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _init_session_state(self):
        self._session_ready = False
        self._session_save_source = None
        self._session_state = {}
        if self.pref.remember_session:
            try:
                state = json.loads(self._session_config().get('session', 'state', fallback='{}'))
                if isinstance(state, dict):
                    self._session_state = state
            except (ValueError, ConfigParser.Error):
                pass
        if not ncam.NCAM_STANDALONE:
            width = self._session_state.get('panel_width')
            if isinstance(width, int) and 200 <= width <= 4000:
                self.set_size_request(width, 80)
        column_width = self._session_state.get('name_col_width')
        if isinstance(column_width, int) and 20 <= column_width <= 2000:
            self.col_width_adj.set_value(column_width)
        self.connect('size-allocate', self._queue_session_save)
        for pane in (self.feature_Hpane, self.feature_pane, self.preview_paned):
            pane.connect('notify::position', self._queue_session_save)
        self.treeview.get_column(0).connect('notify::width', self._queue_session_save)
        preview = self.preview_pane
        saved = self._session_state.get('preview', {})
        if not isinstance(saved, dict):
            saved = {}
        for key, widget in preview.session_widgets().items():
            value = saved.get(key)
            if isinstance(widget, gtk.CheckMenuItem):
                if isinstance(value, bool):
                    widget.set_active(value)
                signal = 'toggled'
            elif isinstance(widget, gtk.Range):
                if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1:
                    widget.set_value(value)
                signal = 'value-changed'
            elif isinstance(widget, gtk.ComboBox):
                if value in [str(speed) for _label, speed in preview.SPEEDS]:
                    widget.set_active_id(value)
                signal = 'changed'
            else:
                if isinstance(value, str):
                    try:
                        if math.isfinite(float(value)) and float(value) >= 0:
                            widget.set_text(value)
                    except ValueError:
                        pass
                signal = 'changed'
            widget.connect(signal, self._queue_session_save)
        page = saved.get('page')
        if isinstance(page, int) and 0 <= page < preview.widget.get_n_pages():
            preview.widget.set_current_page(page)
        preview.widget.connect('switch-page', self._queue_session_save)

    def _remember_session_toggled(self, action):
        self.pref.remember_session = action.get_active()
        parser = self._session_config()
        if not parser.has_section('layout'):
            parser.add_section('layout')
        parser.set('layout', 'remember_session', str(self.pref.remember_session))
        self._write_session_config(parser)
        self._save_session_state()

    def _queue_session_save(self, *args):
        if (not getattr(self, '_session_ready', False) or not self.pref.remember_session
                or getattr(self, '_ncam_shutting_down', False)):
            return
        if self._session_save_source is not None:
            GLib.source_remove(self._session_save_source)
        self._session_save_source = GLib.timeout_add(350, self._save_session_state)

    def _session_layout_ready(self):
        self._session_ready = True
        if self._session_state.get('collapsed') is True:
            self.set_panel_collapsed(True)
        self._queue_session_save()

    def _session_window_changed(self, window, *args):
        if ncam.NCAM_STANDALONE and not window.is_maximized() and not self._panel_collapsed:
            width, height = window.get_size()
            if width > 200 and height > 200:
                x, y = window.get_position()
                self._session_geometry = dict(width=width, height=height, x=x, y=y)
        self._queue_session_save()
        return False

    def _session_window_closed(self, *args):
        self._save_session_state()
        self._session_ready = False
        return False

    def _connect_session_window(self, window):
        if getattr(self, '_session_window', None) is window:
            return
        self._session_window = window
        window.connect('configure-event', self._session_window_changed)
        window.connect('window-state-event', self._session_window_changed)
        window.connect('delete-event', self._session_window_closed)
        if isinstance(window, gtk.Dialog):
            window.connect('response', self._session_window_closed)

    def restore_session_window(self, window):
        self._connect_session_window(window)
        if not ncam.NCAM_STANDALONE:
            return
        saved = self._session_state.get('window', {})
        if not isinstance(saved, dict):
            saved = {}
        width, height = saved.get('width', 400), saved.get('height', 800)
        if not all(isinstance(v, int) and 200 <= v <= 10000 for v in (width, height)):
            width, height = 400, 800
        x, y = saved.get('x', 0), saved.get('y', 0)
        if not all(isinstance(v, int) and abs(v) < 10000000 for v in (x, y)):
            x, y = 0, 0
        monitor = window.get_display().get_monitor_at_point(x, y)
        if monitor is not None:
            area = monitor.get_workarea()
            width, height = min(width, area.width), min(height, area.height)
            x = max(area.x, min(x, area.x + area.width - width))
            y = max(area.y, min(y, area.y + area.height - height))
        window.set_default_size(width, height)
        window.resize(width, height)
        if saved:
            window.move(x, y)
        self._session_geometry = dict(width=width, height=height, x=x, y=y)
        if saved.get('maximized') is True:
            window.maximize()

    def _save_session_state(self):
        source = getattr(self, '_session_save_source', None)
        self._session_save_source = None
        if source is not None:
            GLib.source_remove(source)
        if not getattr(self, '_session_ready', False) or not self.pref.remember_session:
            return False
        if self.preview_pane.widget.get_n_pages() == 0:
            return False              # GTK teardown has already removed the pages
        state = dict(self._session_state)
        splits = dict(state.get('splits', {})) if isinstance(state.get('splits'), dict) else {}
        panes = [('preview', self.preview_paned, self.preview_paned.get_allocated_height())]
        if self.actionDualView.get_active():
            if self.actionSideSide.get_active():
                panes.append(('horizontal', self.feature_Hpane, self.feature_Hpane.get_allocated_width()))
            else:
                panes.append(('vertical', self.feature_pane, self.feature_pane.get_allocated_height()))
        for key, pane, size in panes:
            if size > 200:
                splits[key] = min(.95, max(.05, pane.get_position() / size))
        state['splits'] = splits
        state['collapsed'] = self._panel_collapsed
        if ncam.NCAM_STANDALONE:
            window = self.get_toplevel()
            if isinstance(window, gtk.Window):
                state['window'] = dict(getattr(self, '_session_geometry', {}), maximized=window.is_maximized())
        else:
            width = self._panel_width if self._panel_collapsed else self.get_allocated_width()
            if isinstance(width, int) and width >= 200:
                state['panel_width'] = width
        width = self.treeview.get_column(0).get_width()
        if width >= 20:
            state['name_col_width'] = width
        preview = {'page': self.preview_pane.widget.get_current_page()}
        for key, widget in self.preview_pane.session_widgets().items():
            if isinstance(widget, gtk.CheckMenuItem):
                preview[key] = widget.get_active()
            elif isinstance(widget, gtk.Range):
                preview[key] = widget.get_value()
            elif isinstance(widget, gtk.ComboBox):
                preview[key] = widget.get_active_id()
            else:
                preview[key] = widget.get_text()
        state['preview'] = preview
        parser = self._session_config()
        self._store_layout_choices(parser)
        if not parser.has_section('session'):
            parser.add_section('session')
        parser.set('session', 'state', json.dumps(state))
        try:
            self._write_session_config(parser)
            self._session_state = state
        except OSError as error:
            print('Could not save NativeCAM session: %s' % error)
        return False


    def _save_autorefresh_preference(self):
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)
        if not parser.has_section('layout'):
            parser.add_section('layout')
        parser.set('layout', 'autorefresh', str(self.actionAutoRefresh.get_active()))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)


