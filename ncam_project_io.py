import os
import subprocess

from lxml import etree

import lathe_sections

import ncam
from ncam import (
    gtk, gdk, _, tv_select, mess_dlg, get_int, get_float, search_path,
    search_warning, Feature,
    XML_TAG, CFG_DIR, CATALOGS_DIR, PROJECTS_DIR, CURRENT_WORK, DEFAULT_TEMPLATE,
    EXAMPLES_DIR,
)


class NCamProjectIOMixin:
    def treestore_from_xml(self, xml):

        treestore = gtk.TreeStore(object, str, bool, bool)

        def recursive(itr, xmlpath):
            for xml in xmlpath :
                if xml.tag == "feature" :
                    f = Feature(xml = xml)
                    tool_tip = f.get_tooltip()
                    citer = treestore.append(itr, [f, tool_tip, True, False])

                    grp_header = ''

                    for p in f.param :
                        header_name = p.attr["header"].lower() if "header" in p.attr else ''

                        tool_tip = p.get_tooltip() if "tool_tip" in p.attr else None
                        p_type = p.get_type()
                        p_hidden = get_int(p.attr['hidden'] if 'hidden' in p.attr else '0')

                        if self.actionDualView.get_active() :
                            if self.actionSubHdrs.get_active() :
                                m_visible = p_type in ['items', 'header', 'sub-header'] and not p_hidden
                                is_visible = p_type not in ['items', 'header', 'sub-header'] and not p_hidden
                            else :
                                m_visible = p_type in ['items', 'header'] and not p_hidden
                                is_visible = p_type not in ['items', 'header'] and not p_hidden
                        else :
                            m_visible = not p_hidden
                            is_visible = False

                        if p_type == "items" :
                            piter = treestore.append(citer, [p, tool_tip, m_visible, is_visible])
                            xmlpath_ = xml.find(".//param[@type='items']")
                            recursive(piter, xmlpath_)
                        elif p_type in ['header', 'sub-header'] :
                            if (header_name == '') :
                                hiter = treestore.append(citer, [p, tool_tip, m_visible, is_visible])
                            elif grp_header == header_name :
                                hiter = treestore.append(hiter, [p, tool_tip, m_visible, is_visible])
                            else :
                                while True :
                                    f_ = treestore.get_value(hiter, 0)
                                    if f_ == f :
                                        hiter = treestore.append(citer, [p, tool_tip, m_visible, is_visible])
                                        break
                                    if f_.attr['call'][7:] == header_name :
                                        hiter = treestore.append(hiter, [p, tool_tip, m_visible, is_visible])
                                        break
                                    hiter = treestore.iter_parent(hiter)
                            grp_header = p.attr['call'][7:]
                        else :
                            if (header_name == '') or (grp_header == '') :
                                treestore.append(citer, [p, tool_tip, m_visible, is_visible])
                            elif grp_header == header_name :
                                treestore.append(hiter, [p, tool_tip, m_visible, is_visible])
                            else :
                                while True :
                                    f_ = treestore.get_value(hiter, 0)
                                    if f_ == f :
                                        treestore.append(citer, [p, tool_tip, m_visible, is_visible])
                                        grp_header = ''
                                        break
                                    if f_.attr['call'][7:] == header_name :
                                        treestore.append(hiter, [p, tool_tip, m_visible, is_visible])
                                        break
                                    hiter = treestore.iter_parent(hiter)


        if xml is not None :
            recursive(treestore.get_iter_first(), xml)
        self.treestore = treestore
        self.master_filter = self.treestore.filter_new()
        self.master_filter.set_visible_column(2)
        self.treeview.set_model(self.treestore)
        self.treeview.set_model(self.master_filter)
        self.set_expand()


    def resolve_program_units(self) :
        """Set the units the file is about to be written in, from the Workpiece.

        Has to run before the header is built: Preferences.create_defaults()
        runs once at start-up, so without rebuilding it here the G20/G21 line
        and #<_tbl_scale> would still describe the machine rather than this
        project. Every float then converts through Parameter.get_ngc_value(),
        which reads the same flag.

        No Workpiece, or Workpiece set to "From machine", means the machine's
        own units - which is every project that predates this.
        """
        wanted = None
        itr = self.treestore.get_iter_first()
        while itr is not None :
            f = self.treestore.get(itr, 0)[0]
            if f.__class__ is Feature and f.get_attr('type') == 'workpiece' :
                p = f.get_param('param_units')
                if p is not None :
                    wanted = get_int(p.get_ngc_value())
                break
            itr = self.treestore.iter_next(itr)

        machine = getattr(ncam, 'machine_metric', True)
        if wanted == 21 :
            ncam.program_metric = True
        elif wanted == 20 :
            ncam.program_metric = False
        else :
            ncam.program_metric = machine

        # a tool-table reading is in machine units whatever the file declares
        if ncam.program_metric == machine :
            ncam.TBL_SCALE = 1.0
        elif machine :
            ncam.TBL_SCALE = 1.0 / 25.4      # mm table into an inch program
        else :
            ncam.TBL_SCALE = 25.4            # inch table into a metric program

        self.pref.create_defaults()


    def to_gcode(self, *arg) :
        ncam.UNIQUE_ID = 9
        # cleared every build: a face left over from the last generation would
        # silently datum this one against a Workpiece that is no longer there
        lathe_sections.WORKPIECE_FACE_Z = None
        lathe_sections.WORKPIECE_OD = None
        lathe_sections.WORKPIECE_ID = None
        lathe_sections.TOOL_FRONT_ANGLE = 0.0
        lathe_sections.TOOL_NOSE_R = 0.0
        self.resolve_program_units()

        def recursive(itr, ldr, parent_feature = None) :
            gcode_def = ""
            gcode = ""
            sub_ldr = ldr
            f = self.treestore.get(itr, 0)[0]
            if f.__class__ is Feature :
                # Tell the tool table which tool is loaded from here on. The
                # Tool Change [INIT] does this too, but INIT only runs when a
                # feature is built from its cfg or migrates - never on a plain
                # project load - so anything asking at generation time got
                # whatever the last GUI edit happened to leave behind, or 0.
                # Features are processed in order, so by the time a later
                # feature asks, the nearest preceding tool change has spoken.
                # The Workpiece's face, for anything measuring FROM it - the
                # Z-limit datums. Same mechanism and same reason as the tool
                # change below: features are processed in order and the
                # Workpiece is the first of them, so by the time the polyline
                # asks, it has spoken. Set on lathe_sections rather than looked
                # up from there, because that module imports nothing from ncam
                # by design and a Feature has no back-reference to its tree.
                if f.get_attr('type') == 'workpiece' :
                    p_wz = f.get_param('param_z')
                    if p_wz is not None :
                        lathe_sections.WORKPIECE_FACE_Z = \
                            get_float(p_wz.get_ngc_value())
                    # and the stock diameters, for the radial limits' datums -
                    # the same idea as the face, applied to X. An Int. diameter
                    # of 0 is solid bar, which is a real answer and not a
                    # missing one, so it is published as 0 rather than None.
                    p_od = f.get_param('param_od')
                    if p_od is not None :
                        lathe_sections.WORKPIECE_OD = \
                            get_float(p_od.get_ngc_value())
                    p_id = f.get_param('param_id')
                    if p_id is not None :
                        lathe_sections.WORKPIECE_ID = \
                            get_float(p_id.get_ngc_value())
                if f.get_attr('type') == 'tool_change' :
                    p_dnum = f.get_param('param_dnum')
                    if p_dnum is not None :
                        ncam.TOOL_TABLE.save_tool_orient(get_int(p_dnum.get_ngc_value()))
                        # and the front angle, for the leading flank's shadow.
                        # Read here rather than in lathe_sections because that
                        # module imports nothing from ncam; same route as the
                        # workpiece face above.
                        lathe_sections.TOOL_FRONT_ANGLE = \
                            ncam.TOOL_TABLE.get_front_angle()
                        # and the nose radius, for the contact-point diameter
                        # limit. Same route again, and taken from
                        # tip_comp_inputs so it is the SAME number the
                        # compensation and the reachable contour already use -
                        # TBL_SCALE applied, override honoured - rather than a
                        # second read that could disagree with them.
                        lathe_sections.TOOL_NOSE_R = ncam.tip_comp_inputs()[0]
                    # the flank length travels the same way and for the same
                    # reason: it describes the INSERT, so it belongs to the
                    # tool change, and every feature under it - the polyline's
                    # reachable envelope, the preview's silhouette - asks here
                    p_flank = f.get_param('param_flank_len')
                    ncam.TOOL_TABLE.save_flank_len(
                        p_flank.get_ngc_value() if p_flank is not None else 0.0)
                    p_sh = f.get_param('param_shank_h')
                    ncam.TOOL_TABLE.save_shank_h(
                        p_sh.get_ngc_value() if p_sh is not None else 0.0)
                    p_sox = f.get_param('param_shank_ox')
                    p_soz = f.get_param('param_shank_oz')
                    ncam.TOOL_TABLE.save_shank_off(
                        p_sox.get_ngc_value() if p_sox is not None else 0.0,
                        p_soz.get_ngc_value() if p_soz is not None else 0.0)
                    # the holder as GEOMETRY, for the reachable contour: how
                    # far the block sits below the nose, how long it is, and
                    # the insert's own edge length that ends the wedge. Derived
                    # from ncam_preview's own tool_shank so the contour, the
                    # drawing and the collision check cannot describe three
                    # different tools.
                    lathe_sections.TOOL_SHANK_DROP = 0.0
                    lathe_sections.TOOL_SHANK_LEN = 0.0
                    lathe_sections.TOOL_INSERT_EDGE = 0.0
                    try :
                        import ncam_preview
                        _sh = get_float(p_sh.get_ngc_value()) if p_sh is not None else 0.0
                        _dims = ncam_preview.shank_dims(_sh)
                        _nr, _or = ncam.tip_comp_inputs()
                        _blk = ncam_preview.tool_shank(
                            (0.0, 0.0, 0.0), _nr, _or,
                            ncam.TOOL_TABLE.get_front_angle(),
                            ncam.TOOL_TABLE.get_back_angle(),
                            _sh, None, None,
                            ncam.TOOL_TABLE.get_shank_off())
                        if _dims is not None and _blk :
                            lathe_sections.TOOL_SHANK_DROP = abs(_blk[0][1])
                            lathe_sections.TOOL_SHANK_LEN = _dims[0]
                            lathe_sections.TOOL_INSERT_EDGE = _dims[1]
                    except Exception :
                        pass
                    p_bc = f.get_param('param_back_clear')
                    ncam.TOOL_TABLE.save_back_clear(
                        p_bc.get_ngc_value() if p_bc is not None else 0.0)
                    p_rc = f.get_param('param_c_dpt')
                    ncam.TOOL_TABLE.save_rough_cut(
                        p_rc.get_ngc_value() if p_rc is not None else 0.0)
                f.validate()
                # never reuse a cached O-word id: the counter restarts every
                # build, so a stale stored id collides with freshly assigned
                # ones (duplicated features ended up redefining their sub)
                if 'short_id' in f.attr :
                    del f.attr['short_id']
                # reset every build: child_features must reflect only this
                # generation's own children, not whatever a previous build
                # happened to leave here (Feature objects persist across
                # to_gcode() calls, same staleness class as short_id above)
                f.child_features = []
                if parent_feature is not None :
                    parent_feature.child_features.append(f)
                sub_ldr += f.getindent()
                # DEFINITIONS ARE COLLECTED IN A SECOND PASS, below. Taken
                # here they run BEFORE the feature's own children are walked,
                # so a feature does not yet know its own shape: a lathe
                # polyline's resolve_points came back empty and anything built
                # from the profile - the flat roughing sub - could not be
                # emitted at all. See analysis/101.
                # The order they appear in the program is unchanged: they are
                # prepended either way, and the pass below walks the same
                # features in the same order.
                def_order.append(f)
                gcode += f.process(f.attr["before"], ldr)
                gcode += f.process(f.attr["call"], ldr)
            # an "items"-type param row sits between a feature and its item
            # children in the treestore (Feature -> Parameter(items) ->
            # child Feature) - skip over it so children still reach the
            # nearest real Feature ancestor's child_features
            child_parent = f if f.__class__ is Feature else parent_feature
            itr = self.treestore.iter_children(itr)
            while itr :
                g, d = recursive(itr, sub_ldr + '\t', child_parent)
                gcode += g
                gcode_def += d
                itr = self.treestore.iter_next(itr)
            if f.__class__ is Feature :
                gcode += f.process(f.attr["after"], ldr)
            return gcode, gcode_def

        gcode = ""
        gcode_def = ""
        def_order = []
        ncam.DEFINITIONS = []
        ncam.INCLUDE = []
        itr = self.treestore.get_iter_first()
        while itr is not None :
            g, d = recursive(itr, '')
            gcode += g
            gcode_def += d
            itr = self.treestore.iter_next(itr)
        # the second pass - every feature now knows its children, so a
        # definition may be built from the geometry the feature describes
        for f_def in def_order :
            gcode_def += f_def.get_definitions()
        if self.pref.use_pct :
            return self.pref.default + gcode_def + \
            _("(end sub definitions)\n\n") + gcode + self.pref.ngc_post_amble + '\n%\n'
        else :
            return self.pref.default + gcode_def + \
            _("(end sub definitions)\n\n") + gcode + self.pref.ngc_post_amble + '\nM2\n'


    def action_save_ngc(self, *arg) :
        filechooserdialog = gtk.FileChooserDialog(_("Save as ngc..."), None,
            gtk.FileChooserAction.SAVE,
            ('gtk-cancel', gtk.ResponseType.CANCEL, 'gtk-ok', gtk.ResponseType.OK))
        try :
            filt = gtk.FileFilter()
            filt.set_name("NGC")
            filt.add_mime_type("text/ngc")
            filt.add_pattern("*.ngc")
            filechooserdialog.add_filter(filt)
            filechooserdialog.set_current_folder(ncam.NGC_DIR)
            filechooserdialog.set_keep_above(True)
            filechooserdialog.set_transient_for(self.get_toplevel())
            filechooserdialog.set_destroy_with_parent(True)

            if filechooserdialog.run() == gtk.ResponseType.OK:
                filename = filechooserdialog.get_filename()
                if not filename.lower().endswith(".ngc") :
                    filename += ".ngc"
                with open(filename, "w") as f:
                    f.write(self.to_gcode())
                f.close()
        finally :
            filechooserdialog.destroy()


    def import_xml(self, xml_i) :
        if xml_i.tag != XML_TAG:
            xml_i = xml_i.find(".//%s" % XML_TAG)

        if xml_i is not None :
            xml = self.treestore_to_xml()
            if self.iter_selected_type == tv_select.none :
                opt = 0
                next_path = None
            elif self.iter_selected_type == tv_select.items :
                # will append to items
                dest = xml.find(".//*[@path='%s']/param[@type='items']" %
                                self.items_ts_parent_s)
                opt = 2
                i = -1
                next_path = self.items_lpath
            elif self.iter_selected_type != tv_select.none :
                # will append after parent of selected feature
                dest = xml.find(".//*[@path='%s']" % self.selected_feature_ts_path_s)
                parent = dest.getparent()
                i = parent.index(dest)
                opt = 1
                l_path = len(self.selected_feature_path)
                next_path = list(self.selected_feature_path[0:l_path - 1]) + \
                              [self.selected_feature_path[l_path - 1] + 1]

            for x in xml_i :
                if opt == 1 :
                    i += 1
                    if parent is not None:
                        parent.insert(i, x)
                elif opt == 2 :
                    if dest is not None:
                        dest.append(x)
                else :
                    xml.append(x)

                l = x.findall(".//feature")
                if x.tag == "feature" :
                    l = [x] + l
                for xf in l :
                    f = Feature(xml = xf)
                    f.get_id(xml)
                    if 'short_id' in f.attr :
                        del f.attr['short_id']
                    # f.attr is a copy: strip from the element too or duplicated
                    # features keep the same O-word id and redefine their sub
                    if 'short_id' in xf.attrib :
                        del xf.attrib['short_id']
                    xf.set("name", f.attr["name"])
                    xf.set("id", f.attr["id"])

            self.treestore_from_xml(xml)
            self.expand_and_select(next_path)
            self.get_selected_feature(self.treeview)
            self.action(xml)


    def action_save_template(self, *arg):
        xml = self.treestore_to_xml()
        etree.ElementTree(xml).write(os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, \
                    self.catalog_dir, PROJECTS_DIR, DEFAULT_TEMPLATE), pretty_print = True)


    def load_currentWork(self):
        self.treestore.clear()
        self.clear_undo()
        fn = search_path(search_warning.none, CURRENT_WORK, \
                         CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR)
        if fn is not None :
            xml = etree.parse(fn).getroot()
            nxml = self.update_features(xml)
            self.treestore_from_xml(nxml)
            self.expand_and_select((0,))
            ncam.CURRENT_PROJECT = _('Untitle.xml')
            self.display_proj_name()
            self.file_changed = False
            self.action(nxml)
        else :
            print(_('Previous work not saved as current work'))
            self.action_new_project()


    def action_new_project(self, *arg):
        self.treestore.clear()
        self.clear_undo()
        fn = search_path(search_warning.none, DEFAULT_TEMPLATE, \
                         CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR)
        if fn is None :
            print(_('No default template saved'))
        else :
            xml = etree.parse(fn).getroot()
            xml = self.update_features(xml)
            self.treestore_from_xml(xml)
            self.expand_and_select((0,))
        ncam.CURRENT_PROJECT = _('Untitle.xml')
        self.display_proj_name()
        self.file_changed = False
        self.action()


    def treestore_to_xml_recursion(self, itr, xmlpath, allitems = True):
        while itr :
            f = self.treestore.get(itr, 0)[0]
            if f.__class__ is Feature :
                xmlpath.append(f.to_xml())

            # check for the childrens
            citer = self.treestore.iter_children(itr)
            while citer :
                p = self.treestore.get(citer, 0)[0]
                itm = p.get_attr('type')
                if (itm == 'items'):
                    pa = f.get_attr('path')
                    xmlpath_ = xmlpath.find(".//*[@path='%s']/param[@type='items']" % pa)
                    if xmlpath_ is not None:
                        self.treestore_to_xml_recursion(self.treestore.iter_children(citer), xmlpath_)
                citer = self.treestore.iter_next(citer)

            # check for next items
            if allitems :
                itr = self.treestore.iter_next(itr)
            else :
                itr = None


    def treestore_to_xml(self) :
        self.get_expand()
        xml = etree.Element(XML_TAG)
        itr = self.treestore.get_iter_first()
        if itr is not None :
            try :
                self.treestore_to_xml_recursion(itr, xml)
                return xml
            except Exception as detail :
                print(_('Error in treestore_to_xml\n%(err_details)s') % {'err_details':detail})
                mess_dlg(_('Error in treestore_to_xml\n%(err_details)s') % {'err_details':detail})
        else :
            self.iter_selected_type = tv_select.none
            return xml


    def action_importXML(self, *arg) :
        filechooserdialog = gtk.FileChooserDialog(_("Import project"), None, \
                gtk.FileChooserAction.OPEN, ('gtk-cancel', \
                gtk.ResponseType.CANCEL, 'gtk-ok', gtk.ResponseType.OK))
        try:
            filt = gtk.FileFilter()
            filt.set_name(_("NativeCAM projects"))
            filt.add_mime_type("text/xml")
            filt.add_pattern("*.xml")
            filechooserdialog.add_filter(filt)
            filt = gtk.FileFilter()
            filt.set_name(_("All files"))
            filt.add_pattern("*")
            filechooserdialog.add_filter(filt)
            filechooserdialog.set_current_folder(os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR))
            filechooserdialog.set_keep_above(True)
            filechooserdialog.set_transient_for(self.get_toplevel())
            filechooserdialog.set_destroy_with_parent(True)

            if filechooserdialog.run() == gtk.ResponseType.OK:
                fname = filechooserdialog.get_filename()
                try :
                    xml = self.update_features(etree.parse(fname).getroot())
                    self.import_xml(xml)
                    self.file_changed = True
                except etree.ParseError as err :
                    mess_dlg(err, _("Import project"))
        finally:
            filechooserdialog.destroy()

    # will update with new features version and keep the previous values

    def update_features(self, xml_i):
        new_xml = etree.Element(XML_TAG)

        def upd2(parent):
            # A cfg [INIT] block is written against ncam.py's module namespace -
            # that is what Feature.from_src's own exec() gives it (TOOL_TABLE, _,
            # get_float, ...). Since update_features moved out of ncam.py, a bare
            # exec() here would run against THIS module's globals instead and die
            # with "name 'TOOL_TABLE' is not defined" on any tool-aware INIT.
            # Rebuild ncam.py's namespace explicitly; a copy, so the block's own
            # temporaries don't leak back into the real module.
            init_globals = dict(vars(ncam))
            init_globals['parent'] = parent
            exec(parent.attr['init'], init_globals)

        def recursive(xmlpath, dst):
            for xml in xmlpath :
                if xml.tag == "feature" :
                    f_A = Feature(xml = xml)
                    src_f = search_path(search_warning.none, f_A.get_attr('src'), CFG_DIR)
                    if src_f is None :
                        f = f_A
                    else :
                        f_B = Feature(src = src_f)
                        if f_B.get_version() > f_A.get_version() :
                            f_B.attr['src'] = f_A.attr['src']
                            # assign all old values - copy only what the saved
                            # feature actually carries. Nested features (polyline
                            # items and the like) are written without 'expanded'
                            # or the selection flags, so an unguarded copy raises
                            # KeyError and takes down the whole project load the
                            # first time a version bump makes them migrate.
                            for a in ('name', 'expanded', 'old-selected',
                                      'new-selected', 'hidden_count') :
                                if a in f_A.attr :
                                    f_B.attr[a] = f_A.attr[a]
                            if f_A.get_value() != '' :
                                f_B.set_value(f_A.get_value())

                            for p in f_A.param :
                                call = p.attr['call']
                                for q in f_B.param :
                                    if q.attr['call'] == call :
                                        q.attr['path'] = p.attr['path']
                                        if 'value' in p.attr :
                                            q.attr['value'] = p.attr['value']
                                        # Carry a saved bound forward only while the
                                        # cfg still declares one. Every minimum/maximum
                                        # in cfg/ is a static declaration, so a saved
                                        # copy is just a snapshot of what the cfg said
                                        # when the project was saved - and copying it
                                        # back unconditionally meant a cfg could never
                                        # relax a bound: the stale limit kept winning
                                        # on every existing project, so the change
                                        # only ever reached newly added features.
                                        if 'minimum_value' in p.attr and 'minimum_value' in q.attr :
                                            q.attr['minimum_value'] = p.attr['minimum_value']
                                        if 'maximum_value' in p.attr and 'maximum_value' in q.attr :
                                            q.attr['maximum_value'] = p.attr['maximum_value']
                                        if 'hidden' in p.attr :
                                            q.attr['hidden'] = p.attr['hidden']
                                        if 'grayed' in p.attr :
                                            q.attr['grayed'] = p.attr['grayed']
                                        break
                            f = f_B
                            if 'init' in f.attr :
                                upd2(f)
                        else :
                            f = f_A

                    f.get_id(new_xml)
                    if 'short_id' in f.attr :
                        del f.attr['short_id']
                    if "validation" not in f.attr :
                        f.attr["validation"] = ""
                    for p in f_A.param :
                        if 'no_zero' in p.attr :
                            del p.attr['no_zero']
                            p.attr['not_allowed'] = '0'

                    if dst is None :
                        new_xml.append(f.to_xml())
                    else :
                        dest = new_xml.find(".//*[@path='%s']" % dst)
                        dest.append(f.to_xml())

                xmlp = xml.find(".//param[@type='items']")
                if xmlp is not None :
                    recursive(xmlp, xmlp.get("path"))

        recursive(xml_i, None)
        return new_xml



    def action_save_current_project(self, *arg) :
        """Write straight back to the open project file, with no dialog.

        greatEndian, 2026-08-26: a plain Save above Save As, on Ctrl+S, for the
        project already open. Save As keeps the dialog and moves into the menu
        without an accelerator.

        A project that has never been saved has no file to write back to -
        `new_project` sets CURRENT_PROJECT to the bare name 'Untitle.xml', not
        a path - so this hands over to the dialog rather than inventing a
        location. That is also what makes the very first Ctrl+S on a new
        project behave the way Save As always did.
        """
        path = ncam.CURRENT_PROJECT
        if not os.path.isabs(path) or not os.path.isdir(os.path.dirname(path)) :
            return self.action_save_project(*arg)
        try :
            xml = self.treestore_to_xml()
            etree.ElementTree(xml).write(path, pretty_print = True)
            self.file_changed = False
        finally :
            self.display_proj_name()


    def action_save_project(self, *arg) :
        filechooserdialog = gtk.FileChooserDialog(_("Save project as..."), None,
                gtk.FileChooserAction.SAVE, ('gtk-cancel', \
                gtk.ResponseType.CANCEL, 'gtk-ok', gtk.ResponseType.OK))
        try:
            filt = gtk.FileFilter()
            filt.set_name(_("NativeCAM projects"))
            filt.add_mime_type("text/xml")
            filt.add_pattern("*.xml")
            filechooserdialog.add_filter(filt)
            d, fname = os.path.split(ncam.CURRENT_PROJECT)
            filechooserdialog.set_current_folder(os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR))
            filechooserdialog.set_current_name(fname)
            filechooserdialog.set_do_overwrite_confirmation(True)
            filechooserdialog.set_keep_above(True)
            filechooserdialog.set_transient_for(self.get_toplevel())
            filechooserdialog.set_destroy_with_parent(True)

            if filechooserdialog.run() == gtk.ResponseType.OK:
                xml = self.treestore_to_xml()
                ncam.CURRENT_PROJECT = filechooserdialog.get_filename()
                if not ncam.CURRENT_PROJECT.lower().endswith(".xml") :
                    ncam.CURRENT_PROJECT += ".xml"
                etree.ElementTree(xml).write(ncam.CURRENT_PROJECT, pretty_print = True)
                self.file_changed = False
        finally:
            self.display_proj_name()
            filechooserdialog.destroy()


    def display_proj_name(self):
        h, t = os.path.split(ncam.CURRENT_PROJECT)
        t, h = os.path.splitext(t)
        self.mnu_current_project.set_label(_(' "%s"') % t)


    def action_open_project(self, *arg):
        if arg[1][0] == 0 :  # user project
            dlg_title = _("Open project")
            flt_name = _("NativeCAM projects")
            dir_ = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR)
        else :  # example
            dlg_title = _("Open example project")
            flt_name = _("NativeCAM example projects")
            dir_ = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, self.catalog_dir, PROJECTS_DIR, EXAMPLES_DIR)

        filechooserdialog = gtk.FileChooserDialog(dlg_title, None,
                gtk.FileChooserAction.OPEN, ('gtk-cancel', \
                gtk.ResponseType.CANCEL, 'gtk-ok', gtk.ResponseType.OK))
        try:
            filt = gtk.FileFilter()
            filt.set_name(flt_name)
            if arg[1][0] == 0 :
                filt.add_mime_type("text/xml")
                filt.add_pattern("*.xml")
            else :
                filt.add_pattern("*.*")
            filechooserdialog.add_filter(filt)
            filechooserdialog.set_current_folder(dir_)
            filechooserdialog.set_keep_above(True)
            filechooserdialog.set_transient_for(self.get_toplevel())
            filechooserdialog.set_destroy_with_parent(True)

            if filechooserdialog.run() == gtk.ResponseType.OK:
                filename = filechooserdialog.get_filename()
                with open(filename) as f:
                    src_data = f.read()
                if src_data.find(XML_TAG) != 1 :
                    subprocess.call(["xdg-open '%s'" % filename], shell = True)
                else :
                    xml = etree.fromstring(src_data)
                    xml = self.update_features(xml)
                    self.treestore_from_xml(xml)
                    self.expand_and_select(self.path_to_old_selected)
                    self.clear_undo()
                    ncam.CURRENT_PROJECT = filename
                    self.file_changed = False
                    self.action(xml)
        finally:
            self.display_proj_name()
            filechooserdialog.destroy()


