import os

import ncam
from ncam import (
    gtk, gdk, _, mess_dlg, mess_yesno,
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

        if not parser.has_section('layout') :
            parser.add_section('layout')
        parser.set('layout', 'subheaders_in_master', str(self.actionSubHdrs.get_active()))
        parser.set('layout', 'hide_value_column', str(self.actionHideCol.get_active()))
        parser.set('layout', 'dual_view', str(self.actionDualView.get_active()))
        parser.set('layout', 'side_by_side', str(self.actionSideSide.get_active()))
        parser.set('layout', 'autorefresh', str(self.actionAutoRefresh.get_active()))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)


    def _save_autorefresh_preference(self):
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)
        if not parser.has_section('layout'):
            parser.add_section('layout')
        parser.set('layout', 'autorefresh', str(self.actionAutoRefresh.get_active()))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)


