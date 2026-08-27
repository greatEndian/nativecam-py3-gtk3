import os

import ncam
from ncam import (
    gtk, gdk, gobject, pango, _, tv_select, CellRendererMx, Feature, get_float,
    NO_ICON_TYPES, GROUP_HEADER_TYPES, NUMBER_TYPES, SUPPORTED_DATA_TYPES,
    decimal_point, items_fmt_str, gray_header_fmt_str, gray_sub_header_fmt_str2,
    gray_sub_header_fmt_str, gray_items_fmt_str, gray_val, gray_feature_fmt_str,
    header_fmt_str, sub_header_fmt_str2, sub_header_fmt_str, feature_fmt_str,
)


# THE MASK HAS TO REACH THE GdkWindow, NOT JUST THE WIDGET.
# gtk_widget_add_events sets the WIDGET mask, and GTK copies that onto the
# GdkWindow when the window is created - and only then. A widget already
# realized when the mask is added keeps its old window mask, and the wheel
# then does nothing over it.
#
# Both treeviews here are exposed to that. create_treeview adds itself to the
# builder's "feat_scrolledwindow" BEFORE calling add_events, so if that
# container is already realized the mask lands too late; and the parameters
# view is repacked into feature_Hpane by set_layout's deferred pass, which is
# a reparent.
#
# greatEndian, 2026-08-25 and 2026-08-26: scroll-to-zoom needed the wheel held
# DOWN - the signature of a missing SCROLL_MASK, since a button press takes an
# implicit pointer grab and a grab routes scroll to the grab window whatever
# its mask says - and then scrolling failed in the preview AND the properties.
# `8a0bf34 fix(ui): mouse wheel scrolling` had already had to chase this once.
#
# So the mask is re-applied at realize, where it is actually read. Idempotent:
# an OR onto a window that already carries these bits changes nothing.
TV_EVENT_MASK = (gdk.EventMask.BUTTON_PRESS_MASK
                 | gdk.EventMask.SCROLL_MASK
                 | gdk.EventMask.SMOOTH_SCROLL_MASK)


def arm_scroll_events(widget):
    """Put TV_EVENT_MASK on the widget's own GdkWindow. Safe before realize.

    Set NCAM_SCROLL_DEBUG=1 to have the real masks printed as each widget is
    realized. The repair below is proven - stripping the bits off a live
    window and firing realize puts them back - but the FAULT has never been
    reproduced outside the running panel, so if the wheel is still dead this
    says whether the bits are actually missing or whether something above the
    widget is eating the event.
    """
    win = widget.get_window()
    if win is None:
        return
    before = int(win.get_events())
    win.set_events(win.get_events() | TV_EVENT_MASK)
    if os.environ.get('NCAM_SCROLL_DEBUG'):
        print('NCam scroll mask: %-14s before %d after %d'
              % (type(widget).__name__, before, int(win.get_events())))


class NCamTreeviewMixin:
    def create_treeview(self):
        self.treeview = gtk.TreeView(model=self.treestore)
        self.treeview.set_grid_lines(gtk.TreeViewGridLines.VERTICAL)
        self.builder.get_object("feat_scrolledwindow").add(self.treeview)

        self.treeview.add_events(TV_EVENT_MASK)
        self.treeview.connect('realize', arm_scroll_events)
        self.treeview.connect('button-press-event', self.pop_menu)
        self.treeview.connect('row_activated', self.tv_row_activated)
        self.treeview.connect('key_press_event', self.tv_key_pressed_event)

        # icon and name
        col = gtk.TreeViewColumn(_("Name"))
        cell = gtk.CellRendererPixbuf()
        cell.set_fixed_size(ncam.treeview_icon_size, ncam.treeview_icon_size)
        self.tv1_icon_cell = cell
        col.pack_start(cell, expand = False)
        col.set_cell_data_func(cell, self.get_col_icon)
        col.set_min_width(int(self.col_width_adj.get_value()))

        self.name_cell = gtk.CellRendererText()
        col.pack_start(self.name_cell, expand = True)
        col.set_cell_data_func(self.name_cell, self.get_col_name)
        col.set_resizable(True)
        self.name_cell.set_property('ellipsize', self.pref.name_ellipsis)
        self.name_cell.set_property('xpad', 2)

        self.treeview.append_column(col)

        # value
        col = gtk.TreeViewColumn(_("Value"))

        cell = CellRendererMx(self.treeview)
        cell.edited = self.edited
        cell.set_preediting(self.get_editinfo)
        cell.set_refresh_fn(self.get_selected_feature)
        col.pack_start(cell, expand = True)
        col.set_cell_data_func(cell, self.get_col_value)
        col.set_min_width(200)
        col.set_resizable(True)
        self.treeview.append_column(col)

        self.treeview.set_tooltip_column(1)
        #self.treeview.connect("cursor-changed", self.get_selected_feature)

        self.treeview.set_model(self.master_filter)
        self.treeview.show_all()


    def action_digits(self, *arg) :
        self.treestore.get(self.selected_param, 0)[0].set_digits(arg[1][0])
        self.refresh_views()


    def create_second_treeview(self):
        self.treeview2 = gtk.TreeView()
        self.treeview2.add_events(TV_EVENT_MASK)
        self.treeview2.connect('realize', arm_scroll_events)
        self.treeview2.connect('button-press-event', self.pop_menu)
        self.treeview2.connect('cursor-changed', self.tv2_selected)
        self.treeview2.connect('row_activated', self.tv_row_activated)
        self.treeview2.set_grid_lines(gtk.TreeViewGridLines.VERTICAL)
        self.treeview2.set_show_expanders(self.pref.tv2_expandable)
        if self.pref.tv2_expandable :
            self.treeview2.set_level_indentation(-5)
        else :
            self.treeview2.set_level_indentation(12)

        # icon and name
        col = gtk.TreeViewColumn(_("Name"))
        cell = gtk.CellRendererPixbuf()
        cell.set_fixed_size(ncam.treeview_icon_size, ncam.treeview_icon_size)
        self.tv2_icon_cell = cell

        col.pack_start(cell, expand = False)
        col.set_cell_data_func(cell, self.get_col_icon)

        self.name_cell2 = gtk.CellRendererText()
        self.name_cell2.set_property('xpad', 2)
        self.name_cell2.set_property('ellipsize', self.pref.name_ellipsis)
        col.pack_start(self.name_cell2, expand = True)
        col.set_cell_data_func(self.name_cell2, self.get_col_name)
        col.set_resizable(True)
        col.set_min_width(int(self.col_width_adj.get_value()))
        self.treeview2.append_column(col)

        # value
        col = gtk.TreeViewColumn(_("Value"))
        cell = CellRendererMx(self.treeview2)
        cell.set_property("editable", True)
        cell.edited = self.edited
        cell.set_preediting(self.get_editinfo)
        cell.set_refresh_fn(self.get_selected_feature)

        col.pack_start(cell, expand = False)
        col.set_cell_data_func(cell, self.get_col_value)
        col.set_resizable(True)
        col.set_min_width(200)
        self.treeview2.append_column(col)

        self.treeview2.set_tooltip_column(1)
        if self.treeview2 is not None:
            self.treeview2.set_model(self.treestore)
        self.treeview2.set_model(self.details_filter)
        self.params_scroll.add(self.treeview2)
        self.treeview2.connect('key-press-event', self.tv_key_pressed_event)


    def tv2_selected(self, tv, *arg):
        (model, itr) = tv.get_selection().get_selected()
        if itr is None :
            self.selected_type = 'xxx'
            self.selected_param = None
            self.hint_label.set_text("")
        else :
            itr_m = self.details_filter.convert_iter_to_child_iter(itr)
            self.selected_type = self.treestore.get_value(itr_m, 0).get_type()
            self.selected_param = itr_m
            self.hint_label.set_markup(self.treestore.get_value(itr_m, 0).get_tooltip())
            if self.selected_type in GROUP_HEADER_TYPES :
                tree_path = model.get_path(itr)
                if not tv.row_expanded(tree_path) :
                    tv.expand_row(tree_path, True)

        self.set_actions_sensitives()


    def tv_w_adj_value_changed(self, *arg):
        pos = int(self.tv_w_adj.get_value())
        total_w = self.feature_Hpane.get_allocated_width()
        if total_w > 100:
            if pos > total_w - 120:
                pos = total_w - 120
            if pos < 100:
                pos = 100
        self.feature_Hpane.set_position(pos)


    def col_width_adj_value_changed(self, *arg):
        self.treeview.get_column(0).set_min_width(int(self.col_width_adj.get_value()))
        if self.treeview2 is not None :
            self.treeview2.get_column(0).set_min_width(int(self.col_width_adj.get_value()))


    def tv_key_pressed_event(self, widget, event) :
        keyname = gdk.keyval_name(event.keyval)
        model, itr = widget.get_selection().get_selected()

        self.focused_widget = widget

        if itr is not None :
            path = model.get_path(itr)
        else :
            path = None

        if event.state & gdk.ModifierType.SHIFT_MASK :
            if event.state & gdk.ModifierType.CONTROL_MASK :
                if keyname in ['z', 'Z'] :
                    self.actionRedo.activate()

        elif event.state & gdk.ModifierType.CONTROL_MASK :
            if keyname in ['z', 'Z'] :
                self.actionUndo.activate()

            elif keyname == "Up" :
                self.actionMoveUp.activate()

            elif keyname == "Down" :
                self.actionMoveDown.activate()

            elif keyname == "Left" :
                self.actionRemoveItm.activate()

            elif keyname == "Right" :
                self.actionAppendItm.activate()

            elif keyname == "Insert" :
                self.actionAdd.activate()

            elif keyname == "Delete" :
                self.actionDelete.activate()

            elif (keyname in ["d", "D"]) :
                self.actionDuplicate.activate()

            elif (keyname in ["x", "X"]) :
                self.actionCut.activate()

            elif (keyname in ["c", "C"]) :
                self.actionCopy.activate()

            elif (keyname in ["v", "V"]) :
                self.actionPaste.activate()

            elif (keyname in ["n", "N"]) :
                self.actionNew.activate()

            elif (keyname in ["o", "O"]) :
                self.actionOpen.activate()

            elif (keyname in ["s", "S"]) :
                self.actionSave.activate()

            elif (keyname in ["k", "K"]) :
                self.actionCollapse.activate()

        else :

            if keyname == "Tab" and self.treeview2 is not None:
                if widget == self.treeview :
                    self.hint_label.set_markup(items_fmt_str % _("Secondary treeview focused"))
                    self.treeview2.grab_focus()
                    model, itr = self.treeview2.get_selection().get_selected()
                    if itr is None :
                        self.treeview2.set_cursor((0,))
                    else :
                        p = model.get_path(itr)
                        self.treeview2.set_cursor(p)
                else :
                    self.hint_label.set_markup(items_fmt_str % _("Primary treeview focused"))
                    self.treeview.grab_focus()
                    model, itr = self.treeview.get_selection().get_selected()
                    p = model.get_path(itr)
                    self.treeview.set_cursor(p)

            elif path is None :
                return False

            elif keyname == "Up" :
                if path != (0,) :
                    depth = len(path)
                    index_s = path[depth - 1]
                    if index_s > 0 :
                        p = path[0: depth - 1] + (index_s - 1,)
                        iter_p = model.get_iter(p)
                        while iter_p is not None :
                            count = model.iter_n_children(iter_p)
                            if (count == 0) or not widget.row_expanded(model.get_path(iter_p)) :
                                p = model.get_path(iter_p)
                                break
                            else :
                                iter_p = model.iter_nth_child(iter_p, count - 1)
                    else :
                        p = path[0: depth - 1]

                    widget.expand_to_path(p)
                    widget.set_cursor(p)

            elif keyname == "Down" :
                p = None
                if widget.row_expanded(path) :
                    p = model.get_path(model.iter_children(itr))
                else :
                    itn = model.iter_next(itr)
                    if itn is not None :
                        p = model.get_path(itn)
                    else :
                        itn = model.iter_parent(itr)
                        while itn is not None :
                            ito = model.iter_next(itn)
                            if ito is not None :
                                p = model.get_path(ito)
                                break
                            else :
                                itn = model.iter_parent(itn)

                if p is not None :
                    widget.set_cursor(p)

            elif keyname == "Left" :
                if widget.row_expanded(path) :
                    widget.collapse_row(path)
                else :
                    depth = len(path)
                    d_len = 1
                    if depth > d_len :
                        apath = path[0:depth - d_len]
                        widget.set_cursor_on_cell(apath, None, None, False)
                        widget.collapse_row(apath)

            elif keyname == "Right" :
                widget.expand_to_path(path + (0, 0))

            elif keyname == "Home" :
                widget.set_cursor((0,))

            elif keyname == "Page_Up" :
                if path != (0,) :
                    depth = len(path)
                    index_s = path[depth - 1]
                    if index_s > 0 and widget.row_expanded(path) :
                        widget.set_cursor(path[0: depth - 1] + (index_s - 1,))
                    else :
                        if depth > 1 :
                            widget.set_cursor(path[0: depth - 1],)
                        else :
                            widget.set_cursor((path[0] - 1,))

            elif keyname == "End" :
                p = (path[0],)
                iter_p = model.get_iter(p)
                ito = iter_p
                while iter_p is not None :
                    p = model.get_path(iter_p)
                    ito = iter_p
                    iter_p = model.iter_next(iter_p)

                while widget.row_expanded(p) :
                    p = model.get_path(model.iter_children(ito))
                    iter_p = model.get_iter(p)
                    ito = iter_p
                    while iter_p is not None :
                        p = model.get_path(iter_p)
                        ito = iter_p
                        iter_p = model.iter_next(iter_p)

                widget.set_cursor(p)

            elif keyname == "Page_Down" :
                itr_n = model.iter_next(itr)
                if itr_n is not None :
                    widget.set_cursor(model.get_path(itr_n))
                else :
                    itr_n = model.iter_children(itr)
                    if itr_n is not None :
                        widget.set_cursor(model.get_path(itr_n))

            elif keyname in ["Return", "KP_Enter", "space", "F2"] :
                widget.set_cursor_on_cell(path, widget.get_column(1), None, True)

            elif keyname == "BackSpace" :
                widget.get_column(1).get_cells()[0].set_Input('BS')
                widget.set_cursor_on_cell(path, widget.get_column(1), None, True)

            elif (keyname[-1] >= "0" and keyname[-1] <= "9") :
                widget.get_column(1).get_cells()[0].set_Input(keyname[-1])
                widget.set_cursor_on_cell(path, widget.get_column(1), None, True)

            elif keyname in ['KP_Decimal', 'period', 'comma', 'KP_Separator'] :
                widget.get_column(1).get_cells()[0].set_Input('0' + decimal_point)
                widget.set_cursor_on_cell(path, widget.get_column(1), None, True)

            elif keyname in ['KP_Subtract', 'KP_Add', 'plus', 'minus'] :
                widget.get_column(1).get_cells()[0].set_Input('-')
                widget.set_cursor_on_cell(path, widget.get_column(1), None, True)

            else :
                return False

        return True


    def edited(self, renderer, path, new_value) :
        self.focused_widget = renderer.get_treeview()
        model = self.focused_widget.get_model()
        
        if model is None:
            return 
            
        itr = model.get_iter(path)
        itr = model.convert_iter_to_child_iter(itr)
        param = self.treestore.get_value(itr, 0)

        # find parent to pass as arg to param.set_value
        parent_itr = self.treestore.iter_parent(itr)
        while self.treestore.get(parent_itr, 0)[0].__class__ is not Feature :
            parent_itr = self.treestore.iter_parent(parent_itr)
        parent = self.treestore.get_value(parent_itr, 0)

        value_changed = False

        if renderer.editdata_type == 'combo-user' :
            p_name = None
            df = param.get_attr('links')
            if (df is not None) :
                for dg in df.split(":") :
                    opt = dg.split('=')
                    if (opt[1] == new_value) :
                        p_name = '#param_' + opt[0]
                        break

            if p_name is not None :
                itr_n = self.treestore.iter_parent(itr)
                itr_n = self.treestore.iter_children(itr_n)

                # finding the linked param
                param_e = None
                while (itr_n is not None) :
                    param_u = self.treestore.get_value(itr_n, 0)
                    if param_u.get_attr('call') == p_name :
                        param_e = param_u
                        break
                    itr_n = self.treestore.iter_next(itr_n)

                if param_e is not None :
                    r = gtk.ResponseType.NONE
                    renderer.set_tooltip(param_e.get_tooltip())
                    dt = param_e.get_type()
                    renderer.set_edit_datatype(dt)
                    renderer.set_param_value(param_e.get_value(True))
                    if dt in NUMBER_TYPES :
                        renderer.set_max_value(get_float(param_e.get_max_value()))
                        renderer.set_min_value(get_float(param_e.get_min_value()))
                        renderer.set_not_allowed(param_e.get_attr('not_allowed'))
                        r, v = renderer.edit_number(ncam.gmoccapy_time_out)

                    elif dt in ['string', 'gcode'] :
                        r, v = renderer.edit_string(ncam.gmoccapy_time_out)

                    elif dt == 'list' :
                        renderer.set_options(param_e.get_options())
                        r, v = renderer.edit_list(ncam.gmoccapy_time_out)

                    if r == gtk.ResponseType.OK :
                        value_changed = param_e.set_value(v, parent)
                    else :
                        return

        if param.set_value(new_value, parent) or value_changed:
            self.refresh_views()
            self.action()
        self.focused_widget.grab_focus()


    def action_gcode(self, *arg) :
        self.treestore.get(self.selected_param, 0)[0].set_type('gcode')
        self.selected_type = 'gcode'
        self.refresh_views()
        self.action()


    def action_revert_type(self, *arg) :
        self.treestore.get(self.selected_param, 0)[0].revert_type()
        self.selected_type = self.treestore.get(self.selected_param, 0)[0].get_type()
        self.refresh_views()
        self.action()


    def action_chUnits(self, *args):
        ncam.default_metric = not ncam.default_metric
        self.pref.read(None, False)
        self.refresh_views()


    def refresh_views(self):
        self.treeview.queue_draw()
        if self.treeview2 is not None :
            self.treeview2.queue_draw()


    def on_scale_change_value(self, widget):
        self.main_box.set_size_request(int(self.w_adj.get_value()), 100)


    def get_col_name(self, column, cell, model, itr, *arg) :
        data_type = model.get_value(itr, 0).get_type()
        val = model.get_value(itr, 0).get_name()
        if model.get_value(itr, 0).get_grayed() :
            if data_type == 'header' :
                cell.set_property('markup', gray_header_fmt_str % val)
            elif data_type == 'sub-header' :
                if  self.actionDualView.get_active() and not self.actionSubHdrs.get_active() :
                    cell.set_property('markup', gray_sub_header_fmt_str2 % val)
                else :
                    cell.set_property('markup', gray_sub_header_fmt_str % val)
            elif data_type == 'items' :
                cell.set_property('markup', gray_items_fmt_str % val)
            elif data_type in SUPPORTED_DATA_TYPES :
                cell.set_property('markup', gray_val % val)
            else :
                cell.set_property('markup', gray_feature_fmt_str % val)

        else :
            if data_type == 'header' :
                cell.set_property('markup', header_fmt_str % val)
            elif data_type == 'sub-header' :
                if  self.actionDualView.get_active() and not self.actionSubHdrs.get_active() :
                    cell.set_property('markup', sub_header_fmt_str2 % val)
                else :
                    cell.set_property('markup', sub_header_fmt_str % val)
            elif data_type == 'items' :
                cell.set_property('markup', items_fmt_str % val)
            elif data_type in SUPPORTED_DATA_TYPES :
                cell.set_property('markup', val)
            else :
                cell.set_property('markup', feature_fmt_str % val)


    def get_editinfo(self, cell, treeview, path):
        model = treeview.get_model()
        itr = model.get_iter(path)
        param = model.get_value(itr, 0)

        if param.get_grayed() :
            data_type = 'grayed'
        else :
            data_type = param.get_type()
            cell.set_param_value(param.get_value(True))
            cell.set_tooltip(_(param.get_tooltip()))

        cell.set_edit_datatype(data_type)

        if data_type in ['combo', 'combo-user', 'list']:
            cell.set_options(_(param.get_options()))

        elif data_type in NUMBER_TYPES:
            cell.set_max_value(get_float(param.get_max_value()))
            cell.set_min_value(get_float(param.get_min_value()))
            cell.set_not_allowed(param.get_attr('not_allowed'))
            cell.set_convertible_units('metric_value' in param.attr)

        elif data_type == 'tool' :
            cell.set_options(ncam.TOOL_TABLE.list)

        elif data_type == 'filename' :
            cell.set_fileinfo(param.attr['patterns'], \
                            param.attr['mime_types'], \
                            param.attr['filter_name'])



    def get_col_value(self, column, cell, model, itr, *arg) :

        param = model.get_value(itr, 0)
        val = param.get_value()
        dval = param.get_display_string()

        cell.set_param_value(val)

        data_type = param.get_type()
        cell.set_data_type(data_type)

        if data_type == 'filename':
            h, dval = os.path.split(val)

        elif data_type == 'prjname':
            h, dval = os.path.split(ncam.CURRENT_PROJECT)
            dval, h = os.path.splitext(dval)

        elif data_type == 'tool' :
            dval = ncam.TOOL_TABLE.get_text(val)

        if data_type == 'combo':
            options = _(param.get_attr('options'))
            for option in options.split(":") :
                opt = option.split('=')
                if opt[1] == val :
                    dval = opt[0]
                    break

        elif data_type == 'combo-user':
            p_name = None
            df = param.get_attr('links')
            if df is not None :
                for dg in df.split(":") :
                    opt = dg.split('=')
                    if (opt[1] == val) :
                        p_name = '#param_' + opt[0]
                        break

            # not a user defined value but one proposed
            if p_name is None :
                options = _(param.attr['options'])
                for option in options.split(":") :
                    opt = option.split('=')
                    if opt[1] == val :
                        dval = opt[0]
                        break
            else :
                itr_n = model.convert_iter_to_child_iter(itr)
                itr_n = self.treestore.iter_parent(itr_n)
                itr_n = self.treestore.iter_children(itr_n)

                # finding the linked param
                while (itr_n is not None) :
                    param = self.treestore.get_value(itr_n, 0)
                    if param.get_attr('call') == p_name :
                        break
                    itr_n = self.treestore.iter_next(itr_n)

                if param is not None :
                    data_type = param.get_type()
                    link_val = param.get_value()
                    if data_type == 'list':
                        options = _(param.get_attr('options'))
                        for option in options.split(":") :
                            opt = option.split('=')
                            if opt[1] == link_val :
                                dval = opt[0]
                                break
                    else :
                        dval = param.get_display_string()

        ps = param.get_attr('prefix')
        if ps is not None :
            dval = ps + ' ' + dval
        ps = param.get_attr('suffix')
        if ps is not None :
            dval += ' ' + ps

        if data_type == 'text' :
            cell.set_property("wrap-width", 180)
        else :
            cell.set_property("wrap-width", -1)
        if param.get_grayed() :
            cell.set_property('markup', gray_val % dval.replace('&#176;', '°'))
        else :
            cell.set_property('text', dval.replace('&#176;', '°'))



    def get_col_icon(self, column, cell, model, itr, user_data=None) :
        if model.get_value(itr, 0).get_type() in NO_ICON_TYPES :
            cell.set_property('pixbuf', None)
        else :
            cell.set_property('pixbuf', model.get_value(itr, 0).get_icon(ncam.treeview_icon_size))


