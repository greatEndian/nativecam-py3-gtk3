import ncam
from ncam import (
    gtk, gdk, gobject, _, get_pixbuf, search_path, search_warning, mess_dlg,
    CATALOGS_DIR,
)


class NCamMenuCatalogMixin:
    def _create_menu_item(self, _action, imgfile = None):
        # Modern GAction-bound menu item bypassing _action.create_menu_item() deprecations
        is_toggle = getattr(_action, '_is_toggle', False)
        if is_toggle or isinstance(_action, (gtk.ToggleAction, gtk.RadioAction)):
            mi = gtk.CheckMenuItem.new_with_mnemonic(getattr(_action, '_label', None) or (hasattr(_action, 'get_label') and _action.get_label()) or "")
        else :
            mi = gtk.ImageMenuItem.new_with_mnemonic(getattr(_action, '_label', None) or (hasattr(_action, 'get_label') and _action.get_label()) or "")

        action_name = getattr(_action, '_name', None) or (hasattr(_action, 'get_name') and _action.get_name())
        mi.set_action_name("app." + action_name)

        if action_name in self.accels:
            key, mods = self.accels[action_name]
            mi.add_accelerator("activate", self.accel_group, key, mods, gtk.AccelFlags.VISIBLE)

        if imgfile is None :
            stock_id = getattr(_action, '_stock_id', None) or (hasattr(_action, 'get_stock_id') and _action.get_stock_id())
            if stock_id:
                img = gtk.Image.new_from_icon_name(stock_id, ncam.menu_icon_size)
                if hasattr(mi, 'set_image') :
                    mi.set_image(img)
        else :
            img = gtk.Image()
            img.set_from_pixbuf(get_pixbuf(imgfile, ncam.add_menu_icon_size))
            if hasattr(mi, 'set_image') :
                mi.set_image(img)
        return mi


    def create_popups(self):
        # PopupMenu
        self.pop_up = gtk.Menu()
        mi = self._create_menu_item(self.actionRename)
        self.mi_rename_list.append(mi)
        self.pop_up.append(mi)
        
        digits_menu = gtk.Menu()
        digits_menu.append(self._create_menu_item(self.actionDigit1))
        digits_menu.append(self._create_menu_item(self.actionDigit2))
        digits_menu.append(self._create_menu_item(self.actionDigit3))
        digits_menu.append(self._create_menu_item(self.actionDigit4))
        digits_menu.append(self._create_menu_item(self.actionDigit5))
        digits_menu.append(self._create_menu_item(self.actionDigit6))
        d_menu = self._create_menu_item(self.actionSetDigits)
        d_menu.set_submenu(digits_menu)
        self.mi_setdigits_list.append(d_menu)
        self.pop_up.append(d_menu)
        
        mi = self._create_menu_item(self.actionDataType)
        self.mi_datatype_list.append(mi)
        self.pop_up.append(mi)
        mi = self._create_menu_item(self.actionRevertType)
        self.mi_reverttype_list.append(mi)
        self.pop_up.append(mi)
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionUndo))
        self.pop_up.append(self._create_menu_item(self.actionRedo))
        self.pop_up.append(gtk.SeparatorMenuItem())
        mi = self._create_menu_item(self.actionHideField)
        self.pop_up.append(mi)
        mi = self._create_menu_item(self.actionShowF)
        self.pop_up.append(mi)
        mi = self._create_menu_item(self.actionChngGrp)
        self.mi_chnggrp_list.append(mi)
        self.pop_up.append(mi)
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionAdd))
        self.pop_up.append(self._create_menu_item(self.actionDuplicate))
        self.pop_up.append(self._create_menu_item(self.actionDelete))
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionCut))
        self.pop_up.append(self._create_menu_item(self.actionCopy))
        self.pop_up.append(self._create_menu_item(self.actionPaste))
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionMoveUp))
        self.pop_up.append(self._create_menu_item(self.actionMoveDown))
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionAppendItm))
        self.pop_up.append(self._create_menu_item(self.actionRemoveItm))
        self.pop_up.append(gtk.SeparatorMenuItem())
        self.pop_up.append(self._create_menu_item(self.actionSaveUser))
        self.pop_up.append(self._create_menu_item(self.actionDeleteUser))
        # A Gtk.Menu popped up on its own is NOT in the widget tree - its
        # parent is its own toplevel - so it cannot walk up to the action group
        # inserted on the NCam widget, and every `app.*` item silently does
        # nothing when clicked. The menubar works only because it is packed
        # into main_box. Give the popups the group directly.
        self.pop_up.insert_action_group("app", self.gaction_group)
        self.pop_up.show_all()

        # PopupMenu2
        self.pop_up2 = gtk.Menu()
        digits_menu2 = gtk.Menu()
        digits_menu2.append(self._create_menu_item(self.actionDigit1))
        digits_menu2.append(self._create_menu_item(self.actionDigit2))
        digits_menu2.append(self._create_menu_item(self.actionDigit3))
        digits_menu2.append(self._create_menu_item(self.actionDigit4))
        digits_menu2.append(self._create_menu_item(self.actionDigit5))
        digits_menu2.append(self._create_menu_item(self.actionDigit6))
        d_menu2 = self._create_menu_item(self.actionSetDigits)
        d_menu2.set_submenu(digits_menu2)
        self.mi_setdigits_list.append(d_menu2)
        self.pop_up2.append(d_menu2)

        mi = self._create_menu_item(self.actionDataType)
        self.mi_datatype_list.append(mi)
        self.pop_up2.append(mi)
        mi = self._create_menu_item(self.actionRevertType)
        self.mi_reverttype_list.append(mi)
        self.pop_up2.append(mi)
        self.pop_up2.append(gtk.SeparatorMenuItem())
        self.pop_up2.append(self._create_menu_item(self.actionUndo))
        self.pop_up2.append(self._create_menu_item(self.actionRedo))
        self.pop_up2.append(gtk.SeparatorMenuItem())
        mi = self._create_menu_item(self.actionHideField)
        self.pop_up2.append(mi)
        mi = self._create_menu_item(self.actionShowF)
        self.pop_up2.append(mi)
        mi = self._create_menu_item(self.actionChngGrp)
        self.mi_chnggrp_list.append(mi)
        self.pop_up2.append(mi)
        self.pop_up2.append(gtk.SeparatorMenuItem())
        self.pop_up2.append(self._create_menu_item(self.actionSaveUser))
        self.pop_up2.append(self._create_menu_item(self.actionDeleteUser))
        self.pop_up2.insert_action_group("app", self.gaction_group)
        self.pop_up2.show_all()


    def create_menubar(self):
        if self.menubar is not None :
            self.menubar.destroy()
        self.menubar = gtk.MenuBar()

        # Projects menu
        file_menu = gtk.Menu()
        file_menu.append(self._create_menu_item(self.actionNew))
        file_menu.append(self._create_menu_item(self.actionOpen))
        file_menu.append(self._create_menu_item(self.actionOpenExample))
        file_menu.append(gtk.SeparatorMenuItem())
        file_menu.append(self._create_menu_item(self.actionSave))
        self.mi_current = self._create_menu_item(self.actionCurrent)
        self.mi_current_list.append(self.mi_current)
        file_menu.append(self.mi_current)
        file_menu.append(self._create_menu_item(self.actionSaveTemplate))
        file_menu.append(gtk.SeparatorMenuItem())
        file_menu.append(self._create_menu_item(self.actionSaveNGC))

        f_menu = self._create_menu_item(self.actionProject)
        f_menu.set_submenu(file_menu)
        self.menubar.append(f_menu)

        # Edit menu
        ed_menu = gtk.Menu()
        ed_menu.append(self._create_menu_item(self.actionUndo))
        ed_menu.append(self._create_menu_item(self.actionRedo))
        ed_menu.append(gtk.SeparatorMenuItem())

        ed_menu.append(self._create_menu_item(self.actionCut))
        ed_menu.append(self._create_menu_item(self.actionCopy))
        ed_menu.append(self._create_menu_item(self.actionPaste))
        ed_menu.append(gtk.SeparatorMenuItem())

        ed_menu.append(self._create_menu_item(self.actionAdd))
        ed_menu.append(self._create_menu_item(self.actionDuplicate))
        ed_menu.append(self._create_menu_item(self.actionDelete))
        ed_menu.append(gtk.SeparatorMenuItem())

        ed_menu.append(self._create_menu_item(self.actionMoveUp))
        ed_menu.append(self._create_menu_item(self.actionMoveDown))
        ed_menu.append(gtk.SeparatorMenuItem())

        ed_menu.append(self._create_menu_item(self.actionAppendItm))
        ed_menu.append(self._create_menu_item(self.actionRemoveItm))

        self.sep1 = gtk.SeparatorMenuItem()
        ed_menu.append(self.sep1)
        self.adt_mi = self._create_menu_item(self.actionDataType)
        self.mi_datatype_list.append(self.adt_mi)
        ed_menu.append(self.adt_mi)
        self.art_mi = self._create_menu_item(self.actionRevertType)
        self.mi_reverttype_list.append(self.art_mi)
        ed_menu.append(self.art_mi)

        edit_menu = self._create_menu_item(self.actionEditMenu)
        edit_menu.set_submenu(ed_menu)
        self.menubar.append(edit_menu)

        # View menu
        v_menu = gtk.Menu()
        self.aren_mi = self._create_menu_item(self.actionRename)
        self.mi_rename_list.append(self.aren_mi)
        v_menu.append(self.aren_mi)
        self.agrp_mi = self._create_menu_item(self.actionChngGrp)
        self.mi_chnggrp_list.append(self.agrp_mi)
        v_menu.append(self.agrp_mi)
        self.sep3 = gtk.SeparatorMenuItem()
        v_menu.append(self.sep3)
        v_menu.append(self._create_menu_item(self.actionHideField))
        v_menu.append(self._create_menu_item(self.actionShowF))
        self.sep2 = gtk.SeparatorMenuItem()
        v_menu.append(self.sep2)

        digits_menu = gtk.Menu()
        digits_menu.append(self._create_menu_item(self.actionDigit1))
        digits_menu.append(self._create_menu_item(self.actionDigit2))
        digits_menu.append(self._create_menu_item(self.actionDigit3))
        digits_menu.append(self._create_menu_item(self.actionDigit4))
        digits_menu.append(self._create_menu_item(self.actionDigit5))
        digits_menu.append(self._create_menu_item(self.actionDigit6))
        self.d_menu = self._create_menu_item(self.actionSetDigits)
        self.d_menu.set_submenu(digits_menu)
        self.mi_setdigits_list.append(self.d_menu)
        v_menu.append(self.d_menu)

        v_menu.append(gtk.SeparatorMenuItem())
        v_menu.append(self._create_menu_item(self.actionSingleView))
        v_menu.append(self._create_menu_item(self.actionDualView))
        v_menu.append(gtk.SeparatorMenuItem())
        v_menu.append(self._create_menu_item(self.actionTopBottom))
        v_menu.append(self._create_menu_item(self.actionSideSide))
        v_menu.append(gtk.SeparatorMenuItem())
        v_menu.append(self._create_menu_item(self.actionHideCol))
        v_menu.append(self._create_menu_item(self.actionSubHdrs))
        v_menu.append(gtk.SeparatorMenuItem())
        v_menu.append(gtk.SeparatorMenuItem())
        v_menu.append(self._create_menu_item(self.actionIconColour))
        v_menu.append(self._create_menu_item(self.actionSaveLayout))

        view_menu = self._create_menu_item(self.actionViewMenu)
        view_menu.set_submenu(v_menu)
        self.menubar.append(view_menu)

        # Add menu
        menuAdd = gtk.Menu()
        self.add_catalog_items(menuAdd)
        menuAdd.append(gtk.SeparatorMenuItem())
        menuAdd.append(self._create_menu_item(self.actionLoadCfg))
        menuAdd.append(self._create_menu_item(self.actionImportXML))

        add_menu = self._create_menu_item(self.actionAddMenu)
        add_menu.set_submenu(menuAdd)
        self.menubar.append(add_menu)

        # Utilities menu
        menu_utils = gtk.Menu()

        self.mi_chunits = self._create_menu_item(self.actionChUnits)
        menu_utils.append(self.mi_chunits)
        menu_utils.append(self._create_menu_item(self.actionAutoRefresh))

        # the same Send radio that hangs off the toolbar button, mirrored here
        # so it is discoverable from the menus too. One shared group would tie
        # two menus' lifetimes together, so this builds its own and the two
        # stay in step through _set_send_mode
        menu_utils.append(self._create_menu_item(self.actionWarnUnreach))

        mi_send = gtk.MenuItem.new_with_label(_('Send button'))
        mi_send.set_submenu(self.create_send_mode_menu())
        menu_utils.append(mi_send)

        menu_utils.append(gtk.SeparatorMenuItem())
        menu_utils.append(self._create_menu_item(self.actionLoadTools))
        # restarting the panel alone, so a stuck GUI does not cost the machine
        # controller as well - see action_restart_ncam
        menu_utils.append(self._create_menu_item(self.actionRestart))
        menu_utils.append(gtk.SeparatorMenuItem())
        menu_utils.append(self._create_menu_item(self.actionSaveUser))
        menu_utils.append(self._create_menu_item(self.actionDeleteUser))

        menu_utils.append(gtk.SeparatorMenuItem())

        menu_val = gtk.Menu()
        # Global validation messages toggle
        self.chk_val_all = gtk.CheckMenuItem(label=_('Show All Messages'))
        self.chk_val_all.set_active(not self.pref.val_all_excluded())
        self.chk_val_all.connect('toggled', self.action_toggle_val_all)
        menu_val.append(self.chk_val_all)
        menu_val.append(gtk.SeparatorMenuItem())
        # Per-feature type validation toggle (updated dynamically)
        self.chk_val_feat = gtk.CheckMenuItem(label=_('Show Messages For Current Type'))
        self.chk_val_feat.set_active(True)
        self.chk_val_feat.connect('toggled', self.action_toggle_val_feat)
        menu_val.append(self.chk_val_feat)

        u_menu = self._create_menu_item(self.actionValidationMenu)
        u_menu.set_submenu(menu_val)
        menu_utils.append(u_menu)

        menu_utils.append(gtk.SeparatorMenuItem())
        menu_utils.append(self._create_menu_item(self.actionPreferences))

        u_menu = self._create_menu_item(self.actionUtilMenu)
        u_menu.set_submenu(menu_utils)
        self.menubar.append(u_menu)

        # Help menu
        menu_help = gtk.Menu()
        menu_help.append(self._create_menu_item(self.actionYouTube, "youtube.png"))
#        menu_help.append(self._create_menu_item(self.actionYouTrans, "youtube.png"))
        menu_help.append(gtk.SeparatorMenuItem())
        menu_help.append(self._create_menu_item(self.actionToolOrient, "lathe-tool.png"))
        menu_help.append(self._create_menu_item(self.actionPreviewLines, "offset.png"))
        menu_help.append(gtk.SeparatorMenuItem())
        menu_help.append(self._create_menu_item(self.actionCNCHome, "linuxcncicon.png",))
        menu_help.append(self._create_menu_item(self.actionForum, "linuxcncicon.png",))
        menu_help.append(gtk.SeparatorMenuItem())
        menu_help.append(self._create_menu_item(self.actionAbout))

        h_menu = self._create_menu_item(self.actionHelpMenu)
        h_menu.set_submenu(menu_help)
        self.menubar.append(h_menu)

        self.mnu_current_project = gtk.MenuItem(label = '')
        self.menubar.append(self.mnu_current_project)

        self.main_box.pack_start(self.menubar, False, False, 0)
        self.menubar.show_all()


    def catalog_activate(self, iconview):
        lst = iconview.get_selected_items()
        if lst is not None and (len(lst) > 0) :
            itr = self.icon_store.get_iter(lst[0])
            src = self.icon_store.get(itr, 3)[0]
            tag = self.icon_store.get(itr, 1)[0]
            if tag == "parent" :
                self.update_catalog(xml = "parent")
            elif tag in ["menuitem", "sub"] :
                self.addVBox.hide()
                self.feature_Hpane.show()
                self.menubar.set_sensitive(True)
                self.main_toolbar.set_sensitive(True)
                self.nc_toolbar.set_sensitive(True)
                self.add_feature(None, src)
            elif tag in ["menu", "group"] :
                path = self.icon_store.get(itr, 4)[0]
                self.update_catalog(xml = self.catalog_path[path])


    def update_catalog(self, xml = None) :
        if xml is not None and xml == "parent" :
            self.catalog_path = self.catalog_path.getparent()
        else :
            self.catalog_path = xml

        if self.catalog_path is None :
            self.catalog_path = self.catalog_src

        self.icon_store.clear()

        # add link to upper level
        if (self.catalog_path != self.catalog_src) :
            self.icon_store.append([get_pixbuf("upper-level.png",
                ncam.add_dlg_icon_size), "parent", _('Back...'), "parent", 0, None])

        for path in range(len(self.catalog_path)) :
            p = self.catalog_path[path]
            if p.tag.lower() in ["menuitem", "menu", "group", "sub"] :
                name = p.get('name') if "name" in list(p.keys()) else 'Un-named'
                src = p.get("src") if "src" in list(p.keys()) else None
                tooltip = _(p.get('tool_tip')) if "tool_tip" in \
                        list(p.keys()) else None
                self.icon_store.append([get_pixbuf(p.get("icon"), ncam.add_dlg_icon_size),
                        p.tag.lower(), _(name), src, path, tooltip])


    def build_menu_from_node(self, grp_menu, path) :
        """Fill a Gtk.Menu from a <menu>/<group> node of the catalog XML.

        A method rather than a closure because a toolbar dropdown needs it too -
        that way the dropdown and the menubar are built from the same node by
        the same code, and cannot drift apart.
        """
        for ptr in range(len(path)) :
            try :
                p = path[ptr]
                if p.tag.lower() in ["menu", "menuitem", "group", "sub"] :
                    name = p.get("name") if "name" in p.keys() else ""
                    a_menu_item = gtk.ImageMenuItem(label=_(name))

                    tooltip = _(p.get("tool_tip")) if "tool_tip" in p.keys() else None
                    if (tooltip is not None) and (tooltip != '') :
                        a_menu_item.set_tooltip_markup(_(tooltip))

                    icon = p.get('icon')
                    if icon is not None :
                        img = gtk.Image()
                        img.set_from_pixbuf(get_pixbuf(icon, ncam.add_menu_icon_size))
                        a_menu_item.set_image(img)

                    src = p.get('src')
                    if src is not None :
                        a_menu_item.connect("activate", self.add_feature, src)

                    grp_menu.append(a_menu_item)

                    if p.tag.lower() in ['menu', "group"] :
                        a_menu = gtk.Menu()
                        a_menu_item.set_submenu(a_menu)
                        self.build_menu_from_node(a_menu, p)

                elif p.tag.lower() == "separator":
                    grp_menu.append(gtk.SeparatorMenuItem())
            except Exception:
                pass


    def add_catalog_items(self, menu_add):
        if self.catalog.tag != 'ncam_ui' :
            mess_dlg(_('Menu is old format, no toolbar defined.\nUpdate to new format'))
            self.build_menu_from_node(menu_add, self.catalog)
        else :
            for _ptr in range(len(self.catalog)) :
                _p = self.catalog[_ptr]
                if _p.tag.lower() in ["menu", "group"] :
                    self.build_menu_from_node(menu_add, _p)


    def get_toolbar_actions(self):
        MENU_LISTING = {}
        # <menu>/<group> nodes by action name, so a <toolmenu> in the toolbar
        # can point at one and get a dropdown of everything inside it
        MENU_NODES = {}

        def add_actions(path) :
            for ptr in range(len(path)) :
                try :
                    p = path[ptr]
                    if p.tag.lower() == "menuitem":
                        name = p.get("name")
                        actionname = p.get("action")
                        tooltip = p.get("tool_tip")
                        src = p.get("src")
                        icon = p.get("icon")

                        if (actionname is not None) and (src is not None) :
                            MENU_LISTING[actionname] = [name, tooltip, src, icon]
                    if p.tag.lower() in ["menu", "group"] :
                        if p.get("action") is not None :
                            MENU_NODES[p.get("action")] = p
                        add_actions(p)
                except Exception:
                    return

        def add_toolbar_def(path):
            toolbar_rank = 0
            for ptr in range(len(path)) :
                try :
                    p = path[ptr]
                    if p.tag.lower() == "separator":
                        ncam.TB_CATALOG[toolbar_rank] = "separator"
                    elif p.tag.lower() == 'toolitem':
                        ncam.TB_CATALOG[toolbar_rank] = MENU_LISTING[p.get("action")]
                    elif p.tag.lower() == 'toolmenu':
                        node = MENU_NODES[p.get("action")]
                        ncam.TB_CATALOG[toolbar_rank] = [
                            node.get("name") or p.get("action"),
                            p.get("tool_tip") or node.get("tool_tip"),
                            None,                        # a dropdown adds nothing itself
                            p.get("icon") or node.get("icon"),
                            node]
                except Exception:
                    return
                toolbar_rank += 1

        for _ptr in range(len(self.catalog)) :
            _p = self.catalog[_ptr]
            if _p.tag.lower() == "menu":
                add_actions(_p)
            elif _p.tag.lower() == "toolbar":
                ncam.TB_CATALOG = {}
                add_toolbar_def(_p)


    def create_nc_toolbar(self):
        if self.nc_toolbar is not None :
            self.nc_toolbar.destroy()
        self.nc_toolbar = gtk.Toolbar()
        self.nc_toolbar.set_style(gtk.ToolbarStyle.ICONS)
        self.nc_toolbar.set_can_focus(False)

        count = len(ncam.TB_CATALOG)
        for x in range(count) :
            li = ncam.TB_CATALOG[x]
            if li == 'separator' :
                self.nc_toolbar.insert(gtk.SeparatorToolItem(), -1)
            else :
                icon = None
                if li[3] is not None :
                    icon = gtk.Image()
                    icon.set_from_pixbuf(get_pixbuf(li[3], ncam.quick_access_icon_size))

                if len(li) > 4 and li[4] is not None :
                    # a dropdown: the button itself adds nothing, it just opens
                    # the menu built from the catalog node it names
                    if icon is not None :
                        button = gtk.MenuToolButton(icon_widget = icon, label = _(li[0]))
                    else :
                        button = gtk.MenuToolButton(label = li[0])
                    a_menu = gtk.Menu()
                    self.build_menu_from_node(a_menu, li[4])
                    a_menu.show_all()
                    button.set_menu(a_menu)
                    # clicking the icon should open the menu too, not do nothing
                    button.connect('clicked',
                                   lambda b : b.get_menu().popup_at_pointer(None))
                else :
                    if icon is not None :
                        button = gtk.ToolButton(icon_widget = icon, label = _(li[0]))
                    else :
                        button = gtk.ToolButton(label = li[0])
                    button.connect('clicked', self.add_feature, li[2])

                if li[1] is not None :
                    button.set_tooltip_markup(_(li[1]))
                self.nc_toolbar.insert(button, -1)

        self.main_box.pack_start(self.nc_toolbar, False, False, 0)
        self.nc_toolbar.show_all()


