import os

from lxml import etree

import ncam
from ncam import (
    gtk, gdk, GLib, _, tv_select, mess_dlg, search_path, search_warning, Feature,
    XML_TAG, CFG_DIR, CATALOGS_DIR, PROJECTS_DIR, CURRENT_WORK, CUSTOM_DIR,
    SUPPORTED_DATA_TYPES, UNDO_MAX_LEN,
)


class NCamFeatureTreeMixin:
    def action_cut(self, *arg):
        self.action_copy()
        self.action_delete()


    def action_copy(self, *arg):
        self.get_expand()
        xml = etree.Element(XML_TAG)
        self.treestore_to_xml_recursion(self.selected_feature_ts_itr, xml, False)
        self.clipboard.set_text(etree.tostring(xml).decode('utf-8'), len = -1)
        self.actionPaste.set_enabled(True)


    def action_paste(self, *arg):
        txt = self.clipboard.wait_for_text()
        if txt and (XML_TAG in txt) :
            self.import_xml(etree.fromstring(txt))


    def action_ValAllDlg(self, *arg):
        self.pref.val_show_all()
        self.to_gcode()


    def btn_cancel_add(self, *arg):
        self.addVBox.hide()
        self.feature_Hpane.show()
        self.menubar.set_sensitive(True)
        self.main_toolbar.set_sensitive(True)
        self.nc_toolbar.set_sensitive(True)


    def action_add(self, *arg) :
        self.feature_Hpane.hide()
        self.addVBox.show()
        self.menubar.set_sensitive(False)
        self.main_toolbar.set_sensitive(False)
        self.nc_toolbar.set_sensitive(False)
        self.add_iconview.grab_focus()


    def action_saveCurrent(self, *arg):
        fname = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR, CURRENT_WORK)
        try:
            if self.treestore.get_iter_first() is not None :
                xml = self.treestore_to_xml()
                etree.ElementTree(xml).write(fname, pretty_print = True)
            else :
                if os.path.isfile(fname) :
                    os.remove(fname)
        except KeyboardInterrupt:
            pass


    def pop_menu(self, tv, event):
        if event.button == 3:
            self.click_x = int(event.x)
            self.click_y = int(event.y)
            path = tv.get_path_at_pos(self.click_x, self.click_y - 1)
            if path is not None:
                path = path[0]
                tv.set_cursor(path)
            else :
                selection = tv.get_selection()
                if selection is not None :
                    model, itr = selection.get_selected()
                    itr = model.get_iter_first()
                    if itr is not None :
                        tv.set_cursor(model.get_path(itr))

            self.edit_menu_activate()

            if tv == self.treeview :
                self.pop_up.popup(None, None, None, None, event.button, event.time)
            else :
                self.pop_up2.popup(None, None, None, None, event.button, event.time) 
            return True


    def move(self, *arg) :
        itr = self.master_filter.convert_iter_to_child_iter(self.selected_feature_itr)
        if (arg[1][0] < 0) :
            itr_swap = self.master_filter.convert_iter_to_child_iter(self.iter_next)
        elif (arg[1][0] > 0) :
            itr_swap = self.master_filter.convert_iter_to_child_iter(self.iter_previous)
        self.treestore.swap(itr, itr_swap)
        self.get_selected_feature(self.treeview)
        self.action()


    def get_selected_feature(self, widget) :
        old_selected_feature = self.selected_feature
        (model, itr) = self.treeview.get_selection().get_selected()

        if itr is not None :

            self.selected_type = model.get_value(itr, 0).attr.get("type")
            self.hint_label.set_markup(model.get_value(itr, 0).get_tooltip())

            ts_itr = model.convert_iter_to_child_iter(itr)
            self.selected_param = None

            if self.selected_type == "items" :
                self.iter_selected_type = tv_select.items
                self.items_ts_parent_s = self.treestore.get_string_from_iter(ts_itr)

                self.items_path = model.get_path(itr)
                n_children = model.iter_n_children(itr)
                self.items_lpath = tuple(self.items_path.get_indices()) + (n_children,)

            elif self.selected_type in ["header", 'sub-header'] :
                self.iter_selected_type = tv_select.header
                self.selected_param = ts_itr

            elif self.selected_type in SUPPORTED_DATA_TYPES :
                self.iter_selected_type = tv_select.param
                self.selected_param = ts_itr

            else :
                self.iter_selected_type = tv_select.feature

            tree_path = model.get_path(itr)
            depth = len(tree_path)
            index_s = tree_path[depth - 1]

            if self.iter_selected_type in [tv_select.items, tv_select.header] :
                items_ts_path = self.treestore.get_path(ts_itr)
                ts_itr = self.treestore.iter_parent(ts_itr)
                self.items_ts_parent_s = self.treestore.get_string_from_iter(ts_itr)

            itr_p = itr
            while model.get_value(itr_p, 0).attr.get("type") in SUPPORTED_DATA_TYPES :
                itr_p = model.iter_parent(itr_p)

            self.selected_feature_itr = itr_p
            self.selected_feature = model.get(itr_p, 0)[0]
            ts_itr = model.convert_iter_to_child_iter(itr_p)
            self.selected_feature_ts_itr = ts_itr
            self.feature_ts_path = self.treestore.get_path(ts_itr)
            self.selected_feature_ts_path_s = self.treestore.get_string_from_iter(ts_itr)

            self.iter_next = model.iter_next(itr_p)
            if self.iter_next :
                self.can_move_down = (self.iter_selected_type == tv_select.feature)
                s = str(model.get(self.iter_next, 0)[0])
                self.can_add_to_group = ('type="items"' in s) and \
                        (self.iter_selected_type == tv_select.feature)
            else :
                self.can_add_to_group = False
                self.can_move_down = False

            self.selected_feature_parent_itr = model.iter_parent(itr_p)
            if self.selected_feature_parent_itr :
                path_parent = model.get_path(self.selected_feature_parent_itr)
                self.can_remove_from_group = (self.iter_selected_type == tv_select.feature) and \
                    model.get_value(self.selected_feature_parent_itr, 0).attr.get("type") == "items"
            else :
                path_parent = None
                self.can_remove_from_group = False

            self.selected_feature_path = model.get_path(itr_p)
            indices = self.selected_feature_path.get_indices()
            depth = len(indices)
            index_s = indices[depth - 1]
            self.can_move_up = (index_s > 0) and \
                (self.iter_selected_type == tv_select.feature)

            if index_s :
                if path_parent is None :
                    path_previous = (index_s - 1,)
                else :
                    parent_indices = path_parent.get_indices()
                    path_previous = tuple(parent_indices[0: depth - 1]) + (index_s - 1,)
                self.iter_previous = model.get_iter(path_previous)
            else :
                self.iter_previous = None

        else:
            self.iter_selected_type = tv_select.none
            self.selected_feature = None
            self.selected_type = 'xxx'
            self.can_move_up = False
            self.can_move_down = False
            self.can_add_to_group = False
            self.can_remove_from_group = False
            n_children = model.iter_n_children(None)
            self.items_lpath = (n_children,)
            tree_path = None
            self.hint_label.set_text('')

        if self.actionDualView.get_active() :
            if self.iter_selected_type == tv_select.none :
                if self.treeview2 is None:
                    self.create_second_treeview()
                else :
                    self.treeview2.set_model(None)

            if ((old_selected_feature == self.selected_feature) and \
                (self.iter_selected_type in [tv_select.items, tv_select.feature, tv_select.header])) \
                    or (old_selected_feature != self.selected_feature) :

                if self.iter_selected_type in [tv_select.items, tv_select.header] :
                    a_filter = self.treestore.filter_new(items_ts_path)
                else :
                    a_filter = self.treestore.filter_new(self.feature_ts_path)
                a_filter.set_visible_column(3)
                self.details_filter = a_filter

                if self.treeview2 is not None:
                    self.treeview2.set_model(self.treestore)
                    self.treeview2.set_model(self.details_filter)
                    self.treeview2.expand_all()

        if tree_path is not None :
            self.treeview.expand_to_path(gtk.TreePath(list(tree_path) + [0, 0]))
        self.can_delete_duplicate = (self.iter_selected_type == tv_select.feature)
        self.set_actions_sensitives()



    def action_appendItm(self, *arg) :
        ts_itr = self.master_filter.convert_iter_to_child_iter(self.iter_next)
        pnext = self.treestore.get_string_from_iter(ts_itr)
        xml = self.treestore_to_xml()
        src = xml.find(".//*[@path='%s']" % self.selected_feature_ts_path_s)
        dst = xml.find(".//*[@path='%s']/param[@type='items']" % pnext)
        if (dst is not None) and (src is not None) :
            src.set("new-selected", "True")
            dst.insert(0, src)
            dst.set("expanded", "True")
            dst = xml.find(".//*[@path='%s']" % pnext)
            dst.set("expanded", "True")
            self.treestore_from_xml(xml)
            self.expand_and_select(self.path_to_new_selected)
            self.action(xml)


    def action_removeItem(self, *arg) :
        xml = self.treestore_to_xml()
        src = xml.find(".//*[@path='%s']" % self.selected_feature_ts_path_s)
        src.set("new-selected", "True")
        parent = src.getparent().getparent()
        n = None
        while parent != xml and \
                    not (parent.tag == "param" and parent.get("type") == "items") and \
                    parent is not None :
            p = parent
            parent = parent.getparent()
            n = parent.index(p)
        if parent is not None and n is not None:
            parent.insert(n, src)
            self.treestore_from_xml(xml)
            self.expand_and_select(self.path_to_new_selected)
            self.action(xml)


    def expand_and_select(self, path):
        if path is not None :
            self.treeview.expand_to_path(gtk.TreePath(path))
            self.treeview.set_cursor(path)
        else :
            self.treeview.expand_to_path(gtk.TreePath((0,)))
            self.treeview.set_cursor(gtk.TreePath((0,)))


    def action_duplicate(self, *arg) :
        xml = etree.Element(XML_TAG)
        self.treestore_to_xml_recursion(self.selected_feature_ts_itr, xml, False)
        self.import_xml(xml)


    def tv_row_activated(self, tv, path, col) :
        if tv.row_expanded(path) :
            tv.collapse_row(path)
        else:
            tv.expand_row(path, True)


    def action_delete(self, *arg) :
        if self.iter_next is not None :
            next_path = self.master_filter.get_path(self.selected_feature_itr)
        elif self.iter_previous is not None :
            next_path = self.master_filter.get_path(self.iter_previous)
        elif self.selected_feature_parent_itr is not None :
            next_path = self.master_filter.get_path(self.selected_feature_parent_itr)
        else :
            next_path = None

        if self.selected_feature_ts_itr is not None :
            self.treestore.remove(self.selected_feature_ts_itr)

        if next_path is not None :
            self.treeview.set_cursor(next_path)

        self.action()
        self.get_selected_feature(self.treeview)


    def action_collapse(self, *arg) :
        (model, itr) = self.treeview.get_selection().get_selected()
        path = model.get_path(itr)
        if self.treeview2 is not None :
            (model, itr) = self.treeview2.get_selection().get_selected()
        self.treeview.collapse_all()
        self.treeview.expand_to_path(path)
        self.treeview.set_cursor(path)

        if (self.treeview2 is not None) :
            self.treeview2.collapse_all()
            if  (itr is not None) :
                path = model.get_path(itr)
                self.treeview2.expand_to_path(path)
                self.treeview2.set_cursor(path)

        if self.focused_widget is not None :
            self.focused_widget.grab_focus()


    def action_renameF(self, *arg):
        self.newnamedlg = gtk.MessageDialog(transient_for = self.get_toplevel(),
            flags = gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            type = gtk.MessageType.QUESTION,
            buttons = gtk.ButtonsType.OK_CANCEL
        )
        old_name = self.selected_feature.get_attr('name')
        self.newnamedlg.set_markup(_('Enter new name for'))
        self.newnamedlg.format_secondary_markup(old_name)
        self.newnamedlg.set_title('NativeCAM')
        edit_entry = gtk.Entry()
        edit_entry.set_editable(True)
        edit_entry.set_text(old_name)
        edit_entry.connect('key-press-event', self.action_rename_keyhandler)
        self.newnamedlg.get_content_area().add(edit_entry)
        self.newnamedlg.set_keep_above(True)

        (status, tree_x, tree_y) = self.treeview.get_bin_window().get_origin()
        self.newnamedlg.move(tree_x, tree_y + self.click_y)

        self.newnamedlg.show_all()
        response = self.newnamedlg.run()
        if (response == gtk.ResponseType.OK) :
            newname = edit_entry.get_text().lstrip(' ')
            if newname :
                self.selected_feature.attr['name'] = newname
                self.refresh_views()
        self.newnamedlg.destroy()


    def action_rename_keyhandler(self, widget, event):
        keyname = gdk.keyval_name(event.keyval)
        if keyname in ['Return', 'KP_Enter']:
            self.newnamedlg.response(gtk.ResponseType.OK)


    def add_feature(self, widget, src) :
        src_file = search_path(search_warning.dialog, src, CFG_DIR)
        if src_file is None:
            return

        with open(src_file) as a :
            src_data = a.read()
        if (".//%s" % XML_TAG) in src_data :
            xml = etree.parse(src_file).getroot()
        elif ('[SUBROUTINE]' in src_data)  :
            f = Feature(src = src_file)
            f.attr['src'] = src
            xml = etree.Element(XML_TAG)
            xml.append(f.to_xml())
        else :
            mess_dlg(_("'%(source_file)s' is not a valid cfg or xml file") % {'source_file':src_file})
            return
        self.import_xml(xml)


    def action_hideField(self, *arg):
        path = self.master_filter.get_path(self.selected_feature_itr)
        self.treestore.get(self.selected_param, 0)[0].set_hidden(True)
        self.selected_feature.hide_field()
        xml_ = self.treestore_to_xml()
        self.treestore_from_xml(xml_)
        self.expand_and_select(path)
        self.action(xml = xml_, refresh = False)


    def action_showFields(self, *args):
        path = self.master_filter.get_path(self.selected_feature_itr)
        if self.selected_feature.show_all_fields() :
            xml_ = self.treestore_to_xml()
            self.treestore_from_xml(xml_)
            self.expand_and_select(path)
            self.action(xml = xml_, refresh = False)


    def action_chng_group(self, *arg):
        if self.treestore.get(self.selected_param, 0)[0].change_group() :
            path = self.master_filter.get_path(self.selected_feature_itr)
            xml_ = self.treestore_to_xml()
            self.treestore_from_xml(xml_)
            self.expand_and_select(path)
            self.action(xml = xml_, refresh = False)


    def action(self, xml = None, refresh = True) :
        if xml is None :
            xml = self.treestore_to_xml()

        self.undo_list = self.undo_list[:self.undo_pointer + 1]
        self.undo_list = self.undo_list[max(0, len(self.undo_list) - UNDO_MAX_LEN):]
        self.undo_list.append(etree.tostring(xml))
        self.undo_pointer = len(self.undo_list) - 1

        self.update_do_btns(refresh)


    def update_do_btns(self, refresh):
        self.set_do_buttons_state()
        self._cancel_autorefresh_timer()
        if self.actionAutoRefresh.get_active() and refresh:
            self.timeout = GLib.timeout_add(self.pref.timeout_value,
                    self.autorefresh_call)


    def action_undo(self, *arg) :
        save_restore = self.pref.restore_expand_state
        self.pref.restore_expand_state = True
        self.undo_pointer -= 1
        self.treestore_from_xml(etree.fromstring(self.undo_list[self.undo_pointer]))
        self.expand_and_select(self.path_to_old_selected)
        self.pref.restore_expand_state = save_restore
        self.update_do_btns(True)


    def action_redo(self, *arg) :
        save_restore = self.pref.restore_expand_state
        self.pref.restore_expand_state = True
        self.undo_pointer += 1
        self.treestore_from_xml(etree.fromstring(self.undo_list[self.undo_pointer]))
        self.expand_and_select(self.path_to_old_selected)
        self.pref.restore_expand_state = save_restore
        self.update_do_btns(True)


    def set_do_buttons_state(self):
        self.actionUndo.set_enabled(self.undo_pointer > 0)
        self.actionRedo.set_enabled(self.undo_pointer < (len(self.undo_list) - 1))


    def clear_undo(self, *arg) :
        self.undo_list = []
        self.undo_pointer = -1
        self.set_do_buttons_state()


    def set_expand(self) :
        def treestore_set_expand(model, path, itr) :
            try :
                mf_itr = self.master_filter.convert_child_iter_to_iter(itr)
                mf_pa = self.master_filter.get_path(mf_itr)
                p = model.get(itr, 0)[0].attr
                if ("expanded" in p and p["expanded"] == "True") \
                        and self.pref.restore_expand_state :
                    self.treeview.expand_row(mf_pa, False)
                if "old-selected" in p and p["old-selected"] == "True":
                    self.treeview.set_cursor(mf_pa)
                    self.path_to_old_selected = mf_pa
                if "new-selected" in p and p["new-selected"] == "True":
                    self.treeview.set_cursor(mf_pa)
                    self.path_to_new_selected = mf_pa
            except Exception:
                # not in treeview (do not use bare except: must not swallow KeyboardInterrupt)
                pass

        self.path_to_new_selected = None
        self.path_to_old_selected = None
        self.selection = self.treeview.get_selection()
        self.selection.unselect_all()
        self.treestore.foreach(treestore_set_expand)


    def get_expand(self) :
        self.selection = self.treeview.get_selection()
        model, pathlist = self.selection.get_selected_rows()

        def treestore_get_expand(model, path, itr) :
            try:
                p = model.get(itr, 0)[0]
                p.attr["path"] = model.get_string_from_iter(itr)
                mf_itr = self.master_filter.convert_child_iter_to_iter(itr)
                mf_pa = self.master_filter.get_path(mf_itr)
                p.attr["old-selected"] = mf_pa in pathlist
                p.attr["new-selected"] = False
                p.attr["expanded"] = self.treeview.row_expanded(mf_pa)
            except Exception:
                # not in filter/treeview (do not use bare except: must not swallow KeyboardInterrupt)
                pass

        self.treestore.foreach(treestore_get_expand)


    def action_loadCfg(self, *arg) :
        filechooserdialog = gtk.FileChooserDialog(_("Open a cfg file"), None, \
                    gtk.FileChooserAction.OPEN, \
                    ('gtk-cancel', gtk.ResponseType.CANCEL,
                     'gtk-ok', gtk.ResponseType.OK))
        try:
            filt = gtk.FileFilter()
            filt.set_name(_("Config files"))
            filt.add_mime_type("text/xml")
            filt.add_pattern("*.cfg")
            filechooserdialog.add_filter(filt)
            filechooserdialog.set_current_folder(os.path.join(ncam.NCAM_DIR, CUSTOM_DIR))
            filechooserdialog.set_keep_above(True)
            filechooserdialog.set_transient_for(self.get_toplevel())
            filechooserdialog.set_destroy_with_parent(True)

            if filechooserdialog.run() == gtk.ResponseType.OK:
                self.add_feature(None, filechooserdialog.get_filename())
        finally :
            filechooserdialog.destroy()


