import os
import sys
import shutil
import subprocess
import time
import webbrowser

import lathe_comp
import tkinter as Tkinter

import ncam
from ncam import (
    gtk, gdk, Gio, GLib, GdkPixbuf, _, APP_VERSION, APP_AUTHORS, APP_COPYRIGHT,
    mess_dlg, mess_yesno, get_pixbuf, copy_dir_recursive, SYS_DIR,
    tv_select, copymode, linuxcnc, _tk_axis_remote_open,
    CATALOGS_DIR, CFG_DIR, CUSTOM_DIR, DEFAULTS_DIR, EXAMPLES_DIR, GRAPHICS_DIR,
    LIB_DIR, PROJECTS_DIR, VALID_CATALOGS, SUPPORTED_DATA_TYPES,
    APP_COMMENTS, APP_LICENCE, DONATE_URL, FLAT_FILE, GENERATED_FILE, HOME_PAGE,
    ConfigParser, CONFIG_FILE, tip_comp_inputs, tool_wedge,
)


class NCamAppActionsMixin:
    def ask_to_create_standalone(self, fromdirs) :
        for d in fromdirs:
            if os.path.isdir(os.path.join(ncam.NCAM_DIR, d)) :
                return
        msg = _('Create Standalone Directory :\n\n%(dir)s\n\nContinue?') % {'dir':ncam.NCAM_DIR}
        if not mess_yesno(msg, title = _("NativeCAM CREATE")) :
            sys.exit(0)


    def update_user_tree(self, fromdirs, todir):

        if not os.path.isdir(ncam.NCAM_DIR) :
            os.makedirs(ncam.NCAM_DIR, 0o755)

        if not os.path.isdir(ncam.NGC_DIR) :
            os.makedirs(ncam.NGC_DIR, 0o755)

        srcdir = os.path.join(ncam.NCAM_DIR, CUSTOM_DIR)
        if not os.path.exists(srcdir) :
            os.mkdir(srcdir, 0o755)

        srcdir = os.path.join(ncam.NCAM_DIR, LIB_DIR)

        # copy system files to user, make dirs if necessary
        mode = copymode.one_at_a_time
        for d in fromdirs:
            update_ct = 0
            dir_exists = os.path.isdir(os.path.join(ncam.NCAM_DIR, d))
            mode, update_ct = copy_dir_recursive(os.path.join(SYS_DIR, d), os.path.join(todir, d),
                                      update_ct = 0,
                                      mode = mode,
                                      overwrite = False,
                                      verbose = False
                                      )
            if dir_exists:
                fmt2 = _('Updated %(qty)3d files in %(dir)s')
            else :
                fmt2 = _('Created %(qty)3d files in %(dir)s')

            if update_ct > 0 :
                print(fmt2 % {'qty':update_ct, 'dir':ncam.NCAM_DIR.rstrip('/') + '/' + d.lstrip('/')})
        print('')

        for s in VALID_CATALOGS :
            # copy default files if not exist
            srcdir = os.path.join(SYS_DIR, DEFAULTS_DIR, s)
            if os.path.exists(srcdir) :
                for f in os.listdir(srcdir) :
                    dst = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, s, PROJECTS_DIR, f)
                    if not os.path.exists(dst) :
                        try :
                            shutil.copy(os.path.join(srcdir, f), dst)
                        except Exception as error :
                            mess_dlg(_("Error copying file : %(f)s\nCode : %(c)s") \
                                     % {'f':f, 'c':error})

            # create links to examples directories
            srcdir = os.path.join(SYS_DIR, EXAMPLES_DIR, s)
            if os.path.exists(srcdir) :
                dst = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, s, PROJECTS_DIR, EXAMPLES_DIR)
                if os.path.exists(dst) and not os.path.islink(dst) :
                    shutil.rmtree(dst)
                    if os.path.exists(dst) :
                        try :
                            os.remove(dst)
                        except OSError :
                            os.rmdir(dst)
                if not os.path.exists(dst) :
                    try :
                        os.symlink(srcdir, dst)
                    except Exception as err :
                        mess_dlg(_("Error creating link : %(s)s -> %(d)s\nCode : %(c)s") \
                                 % {'s':srcdir, 'd':dst, 'c':err})

        def move_files(dir_processed) :
            mov_src = os.path.join(ncam.NCAM_DIR, dir_processed)
            mov_dst = os.path.join(ncam.NCAM_DIR, CUSTOM_DIR, dir_processed)
            cmp_dir = os.path.join(SYS_DIR, dir_processed)

            if not os.path.isdir(mov_dst) :
                os.makedirs(mov_dst, 0o755)

            for p in os.listdir(mov_src) :
                frompath = os.path.join(mov_src, p)
                if os.path.isdir(frompath) :
                    move_files(os.path.join(dir_processed, p))
                else :
                    cmp_path = os.path.join(cmp_dir, p)
                    if not os.path.exists(cmp_path) :
                        shutil.copy(frompath, os.path.join(mov_dst, p))

        for s in [LIB_DIR, GRAPHICS_DIR, CFG_DIR] :
            srcdir = os.path.join(ncam.NCAM_DIR, s)
            if os.path.isdir(srcdir) :
                # move files that are not in SYS_DIR directories
                if not os.path.islink(srcdir) :
                    move_files(s)
                    shutil.rmtree(srcdir)

            tdir = os.path.join(SYS_DIR, s)
            # Point ncam.NCAM_DIR/<s> at the system tree. Skip unlink if already correct
            # (string compare tdir != srcdir is always true for user vs system paths).
            link_ok = False
            if os.path.lexists(srcdir) and os.path.islink(srcdir):
                try:
                    link_ok = os.path.samefile(srcdir, tdir)
                except OSError:
                    link_ok = False
            if not link_ok and os.path.lexists(srcdir) and os.path.islink(srcdir):
                try:
                    os.unlink(srcdir)
                except FileNotFoundError:
                    pass
            # replace dir with a link
            if not os.path.lexists(srcdir):
                try:
                    os.symlink(tdir, srcdir)
                except Exception as err:
                    mess_dlg(_("Error creating link : %(s)s -> %(d)s\nCode : %(c)s")
                             % {'s': tdir, 'd': srcdir, 'c': err})


    def action_regen(self, *arg) :
        """Regenerate ncam.ngc and nothing else.

        Safe to press while a program is loaded or running: it writes the file
        and refreshes NativeCAM's own preview, and never calls into
        linuxcnc.command(), so the machine's loaded program is untouched.
        """
        fname = self.write_ngc()
        if fname is not None :
            self.refresh_preview(fname)
        self._restore_focus()

    def action_send(self, *arg) :
        """Load ncam.ngc into LinuxCNC.

        Whether this regenerates first is the operator's choice - the radio on
        this button's dropdown. Sending the file on disk is the default because
        it is the honest reading of "send": what LinuxCNC gets is what you
        already looked at. The other mode exists so a single press can do both.
        """
        fname = None
        if getattr(self, 'send_regenerates', False) :
            fname = self.write_ngc()
            if fname is None :
                return
            self.refresh_preview(fname)
        self.send_to_linuxcnc(fname)
        self._restore_focus()

    def action_send_flat(self, *arg) :
        """Load the FLAT program - the interpreter's own output - into LinuxCNC.

        ncam.ngc is O-word calls and expressions; this is what the interpreter
        made of it, with every subroutine, loop and expression already gone.
        Useful when a control cannot handle O-words, and for reading back what
        actually ran.

        Two things are true of it and both are stated in its own header:
        coordinates are in the SAME coordinate system the original used - work
        offsets are not baked in - and cutter compensation is already applied,
        so it must not be run with G41/G42 active as well.

        Taken from the preview's parsed toolpath rather than re-running the
        interpreter here: the pane already has it, and a second rs274 run on
        the GTK thread would freeze the panel for a couple of seconds inside
        AXIS, on a machine that may be cutting.
        """
        pane = getattr(self, 'preview_pane', None)
        flat = getattr(getattr(pane, 'toolpath', None), 'flat', '') if pane else ''
        if not flat.strip() :
            mess_dlg(_('There is no flat program yet.\n\nPress Regenerate '
                       'first - the flat listing is produced by the preview '
                       'when it parses %(filename)s.')
                     % {'filename': GENERATED_FILE})
            return
        fname = os.path.join(ncam.NGC_DIR, FLAT_FILE)
        try :
            with open(fname, 'w') as f :
                f.write(flat)
        except Exception as e :
            mess_dlg(_('Could not write %(filename)s:\n\n%(err)s')
                     % {'filename': FLAT_FILE, 'err': str(e)})
            return
        self.send_to_linuxcnc(fname)
        self._restore_focus()

    def refresh_preview(self, fname = None) :
        """Rebuild NativeCAM's own toolpath preview, when there is one.

        A no-op until the preview pane exists, so the button split can land and
        be used on its own.
        """
        pane = getattr(self, 'preview_pane', None)
        if pane is not None :
            try :
                # the drawn tool comes from the same resolver the generated
                # G-code compensates with, so the picture cannot show a tool
                # the program is not using
                nose_r, orient = tip_comp_inputs()
                cl_deg, included_deg = tool_wedge()
                # the flank length has no tool-table column - it comes off the
                # Tool Change feature, the same route the tool number takes
                tn = getattr(ncam.TOOL_TABLE, 'saved_tool', 0)
                pane.set_tool(nose_r, orient, cl_deg, included_deg,
                              ncam.TOOL_TABLE.get_tool_front_angle(tn),
                              ncam.TOOL_TABLE.get_tool_back_angle(tn),
                              ncam.TOOL_TABLE.get_flank_len(),
                              ncam.TOOL_TABLE.get_shank_h())
                pane.refresh(fname)
            except Exception as e :
                print(_('Preview: could not refresh: %s') % str(e))

    def create_send_mode_menu(self) :
        """The radio group on the Send button's dropdown.

        Two real radio items rather than a checkbox, because the two modes are
        mutually exclusive and the operator should be able to see which one is
        armed without pressing anything.
        """
        menu = gtk.Menu()
        cur = getattr(self, 'send_regenerates', False)
        # this is built once per place it appears - toolbar dropdown and
        # Utilities menu - and every copy is kept, so selecting in one updates
        # the other. Keeping only the last would leave the two disagreeing.
        if not hasattr(self, 'send_mode_groups') :
            self.send_mode_groups = []
        items = {}
        first = None
        for regen, label in ((False, _('Send the file on disk')),
                             (True, _('Regenerate, then send'))) :
            mi = gtk.RadioMenuItem.new_with_label([], label)
            if first is None :
                first = mi
            else :
                mi.join_group(first)
            mi.set_active(regen == cur)
            mi._handler = mi.connect('toggled', self._on_send_mode_toggled, regen)
            menu.append(mi)
            items[regen] = mi
        self.send_mode_groups.append(items)

        # the FLAT program is a separate action, not a third mode: the radios
        # above choose what happens to ncam.ngc, this sends a different file
        menu.append(gtk.SeparatorMenuItem())
        mi = gtk.MenuItem.new_with_label(_('Send flat G-code (%(filename)s)')
                                         % {'filename': FLAT_FILE})
        mi.set_tooltip_text(
            _('Load the interpreter output instead of the O-word program - '
              'every subroutine and expression already expanded. Same '
              'coordinate system as the original; cutter compensation is '
              'already applied, so do not run it with G41/G42 active.'))
        mi.connect('activate', self.action_send_flat)
        menu.append(mi)

        menu.show_all()
        return menu

    def _on_send_mode_toggled(self, item, regenerates) :
        if item.get_active() :
            self._set_send_mode(regenerates)

    def _sync_send_mode_items(self) :
        """Put every radio copy on the current mode without re-entering."""
        cur = getattr(self, 'send_regenerates', False)
        for items in getattr(self, 'send_mode_groups', []) :
            mi = items.get(cur)
            if mi is not None and not mi.get_active() :
                mi.handler_block(mi._handler)
                mi.set_active(True)
                mi.handler_unblock(mi._handler)

    def _warn_unreachable_toggled(self, action) :
        ncam.WARN_UNREACHABLE = bool(action.get_active())
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)
        if not parser.has_section('layout'):
            parser.add_section('layout')
        parser.set('layout', 'warn_unreachable', str(ncam.WARN_UNREACHABLE))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)

    def _save_send_mode(self) :
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)
        if not parser.has_section('layout'):
            parser.add_section('layout')
        parser.set('layout', 'send_regenerates', str(bool(self.send_regenerates)))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)

    def _set_send_mode(self, regenerates) :
        """Radio handler: does Send regenerate first?"""
        if getattr(self, 'send_regenerates', None) == regenerates :
            return
        self.send_regenerates = regenerates
        self._sync_send_mode_items()
        self._save_send_mode()
        act = self._actions.get('Send')
        if act is not None :
            tip = (_('Regenerate %(filename)s, then load it in LinuxCNC')
                   if regenerates else
                   _('Load the current %(filename)s in LinuxCNC without regenerating it'))
            act._tooltip = tip % {'filename': GENERATED_FILE}
            if getattr(self, 'send_tool_button', None) is not None :
                self.send_tool_button.set_tooltip_markup(act._tooltip)


    def restore_bar_order(self):
        """Put the menubar and the two toolbars back at the top of main_box.

        create_menubar and create_nc_toolbar both pack_start, which APPENDS -
        so anything that rebuilds them drops them at the bottom of the window
        and there is no way to drag them back. set_preferences has always done
        this after the preferences dialog rebuilds them; anything else that
        rebuilds has to do it too.
        """
        for pos, w in ((0, getattr(self, 'menubar', None)),
                       (1, getattr(self, 'main_toolbar', None)),
                       (2, getattr(self, 'nc_toolbar', None))):
            if w is not None and w.get_parent() is self.main_box:
                self.main_box.reorder_child(w, pos)

    def _apply_icon_colour(self, rgb):
        """Point the icon loader at a new accent and rebuild everything that
        already has pixbufs baked into it."""
        ncam.set_icon_accent(rgb)
        try:
            self.create_nc_toolbar()
            self.nc_toolbar.show_all()
            self.create_menubar()
            self.menubar.show_all()
            self.update_catalog()
            # both rebuilds re-pack at the end of main_box, which would leave
            # the menubar and toolbar stranded at the bottom of the window
            self.restore_bar_order()
            self.treeview.queue_draw()
            if self.treeview2 is not None:
                self.treeview2.queue_draw()
        except Exception as e:
            print(_('Icon colour: could not refresh the display: %s') % str(e))

    def action_icon_colour(self, *arg):
        """View > Icon Colour: three 0-255 sliders driving the icon accent.

        The icon set is drawn in one accent colour; recolouring moves that hue
        and leaves every other colour alone, so the sliders restyle the whole
        set without touching the artwork. Applied live on release so the
        choice can be judged against the real tree, and reverted on Cancel.
        """
        start = ncam.ICON_ACCENT_RGB or ncam.ICON_BASE_RGB

        dlg = gtk.Dialog(title=_("Icon Colour"), parent=self.get_toplevel(),
                         flags=gtk.DialogFlags.DESTROY_WITH_PARENT)
        dlg.add_button(_("Reset"), 1)
        dlg.add_button(_("Cancel"), gtk.ResponseType.CANCEL)
        dlg.add_button(_("OK"), gtk.ResponseType.OK)
        dlg.set_default_size(360, -1)

        box = dlg.get_content_area()
        box.set_border_width(8)
        grid = gtk.Grid()
        grid.set_row_spacing(4)
        grid.set_column_spacing(8)
        box.pack_start(grid, True, True, 0)

        swatch = gtk.DrawingArea()
        swatch.set_size_request(-1, 34)
        state = {'rgb': list(start)}

        def on_draw(area, cr):
            r, g, b = state['rgb']
            cr.set_source_rgb(r / 255.0, g / 255.0, b / 255.0)
            cr.paint()
            return False
        swatch.connect('draw', on_draw)

        scales = []
        for row, (label, idx) in enumerate((( _("Red"), 0), (_("Green"), 1), (_("Blue"), 2))):
            lbl = gtk.Label(label=label)
            lbl.set_halign(gtk.Align.START)
            sc = gtk.Scale.new_with_range(gtk.Orientation.HORIZONTAL, 0, 255, 1)
            sc.set_value(start[idx])
            sc.set_digits(0)
            sc.set_hexpand(True)
            sc.set_value_pos(gtk.PositionType.RIGHT)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(sc, 1, row, 1, 1)
            scales.append(sc)

            def changed(widget, i=idx):
                state['rgb'][i] = int(widget.get_value())
                swatch.queue_draw()
            sc.connect('value-changed', changed)
            # live apply only once the slider is let go - recolouring every
            # icon on each intermediate value would crawl
            sc.connect('button-release-event',
                       lambda w, e: (self._apply_icon_colour(tuple(state['rgb'])), False)[1])
            sc.connect('key-release-event',
                       lambda w, e: (self._apply_icon_colour(tuple(state['rgb'])), False)[1])

        grid.attach(swatch, 0, 3, 2, 1)
        box.show_all()

        while True:
            resp = dlg.run()
            if resp == 1:
                state['rgb'] = list(ncam.ICON_BASE_RGB)
                for i, sc in enumerate(scales):
                    sc.set_value(ncam.ICON_BASE_RGB[i])
                self._apply_icon_colour(None)
                continue
            break
        dlg.destroy()

        if resp == gtk.ResponseType.OK:
            self._apply_icon_colour(tuple(state['rgb']))
            self._save_icon_colour(tuple(state['rgb']))
        else:
            self._apply_icon_colour(start if tuple(start) != ncam.ICON_BASE_RGB else None)

    def _save_icon_colour(self, rgb):
        cfg_file = os.path.join(ncam.NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(cfg_file)
        if not parser.has_section('display'):
            parser.add_section('display')
        if rgb is None or tuple(rgb) == ncam.ICON_BASE_RGB:
            parser.set('display', 'icon_colour', '')
        else:
            parser.set('display', 'icon_colour', '%d,%d,%d' % tuple(rgb))
        with open(cfg_file, 'w') as configfile:
            parser.write(configfile)


    def action_restart_ncam(self, *_a):
        """Restart the NativeCAM panel without touching LinuxCNC.

        NativeCAM runs inside a GladeVCP panel embedded in AXIS - which is why
        it can be replaced on its own. Killing AXIS to get a fresh panel also
        stops the machine controller, and there is no reason for a stuck GUI to
        cost that.

        THE FIRST VERSION USED os.execv AND NEVER CAME BACK. The reasoning was
        that keeping the pid keeps AXIS's embedding valid, so the panel returns
        in the same place. Both halves of that were wrong, and in opposite
        directions:

        - Keeping the pid was never needed. `gladevcp.xembed.reparent` does a
          FORCED Xlib reparent of a Gtk.Plug into AXIS's Tk frame - not a
          GtkSocket handshake. A Tk frame does not destroy itself when its
          child window goes away, so the parent XID outlives the process and a
          fresh one can reparent into it.
        - Keeping the pid is what BROKE it. gladevcp releases its HAL component
          in a `finally: halcomp.exit()`, and execv replaces the process image
          without unwinding, so that never runs. HAL still sees the component
          owned by a live pid - the SAME pid - and refuses to create it again.
          gladevcp catches that and calls **sys.exit(0)**: silent, status 0, no
          panel. Measured directly: `HAL: ERROR: duplicate component name`.

        So the restart must let this process EXIT CLEANLY, and start the
        replacement only afterwards. A detached child is forked first and
        blocks reading a pipe whose only other end this process holds; when we
        exit, every copy of that write end closes, the read returns EOF and the
        child execs the original command line. No polling, and no pid-reuse
        race - the pipe cannot report EOF early.

        `sys.argv` is re-used verbatim because it still carries gladevcp's
        `-x <XID>`, which is what puts the new panel back in AXIS's frame.

        The project is saved first, and the restart is abandoned if that fails
        - losing a feature tree to a convenience button would be a poor trade.
        """
        # The warning is not caution, it is a measured fact - see analysis/048.
        # AXIS embeds this panel in a Tk frame created with `container=1`, and
        # Tk DESTROYS such a frame when the window embedded in it goes away. So
        # by the time the replacement starts, the XID it was given no longer
        # exists: Gtk.Plug.new() on a dead window raises BadWindow, gladevcp
        # swallows it under Gdk.error_trap_push(), and the panel comes up as its
        # own toplevel. Nothing the replacement can do reaches the tab, and AXIS
        # exposes no way to recreate it - load_gladevcp_panel() runs once at
        # startup with no re-entry point.
        if not mess_yesno(_('Restart NativeCAM?\n\nThe current project is '
                            'saved first. LinuxCNC and the machine are not '
                            'touched.\n\nNOTE: the panel will reopen in its '
                            'OWN WINDOW, not in the AXIS tab, and the tab will '
                            'be left empty. AXIS destroys the tab when the '
                            'panel exits and offers no way to rebuild it, so '
                            'returning it to the tab needs LinuxCNC restarted.')):
            return
        try:
            self.action_saveCurrent()
        except Exception as e:
            mess_dlg(_('Could not save before restarting:\n%s') % e)
            return
        try:
            sys.stderr.write('[ncam] restarting NativeCAM\n')
            sys.stderr.flush()
            sys.stdout.flush()
        except Exception:
            pass
        try:
            self._spawn_relaunch()
        except Exception as e:
            mess_dlg(_('Could not restart NativeCAM:\n%s') % e)
            return
        # Quitting the main loop is what makes this work: it returns through
        # gladevcp's `finally: halcomp.exit()`, which frees the HAL name the
        # replacement needs. Killing the process instead would leave it held.
        gtk.main_quit()

    def _spawn_relaunch(self):
        """Fork a detached child that re-runs our command line once we exit.

        The child holds the read end of a pipe and blocks on it. The write end
        is kept open here and nowhere else - Python 3 makes pipe fds
        non-inheritable, so no subprocess we later spawn can hold it open - so
        it closes exactly when this process dies, however it dies. The child
        then execs and reparents into AXIS's frame.
        """
        if getattr(self, '_relaunch_fd', None) is not None:
            return          # already armed; a second child would be a second panel
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:                                   # the child
            try:
                os.close(w)
                os.setsid()                            # survive our exit
                while os.read(r, 1):                   # EOF when we are gone
                    pass
                os.close(r)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception:
                pass
            os._exit(1)                                # never returns normally
        os.close(r)
        # held open deliberately, for as long as this process lives
        self._relaunch_fd = w

    def action_preferences(self, *arg):
        old_quick_access_icon_size = ncam.quick_access_icon_size
        old_treeview_icon_size = ncam.treeview_icon_size
        old_menu_icon_size = ncam.menu_icon_size
        old_add_menu_icon_size = ncam.add_menu_icon_size
        old_add_dlg_icon_size = ncam.add_dlg_icon_size
        old_view = self.actionDualView.get_active()

        if self.pref.edit(self) :
            if old_quick_access_icon_size != ncam.quick_access_icon_size :
                self.create_nc_toolbar()
                self.nc_toolbar.show_all()
            if old_treeview_icon_size != ncam.treeview_icon_size :
                self.tv1_icon_cell.set_fixed_size(ncam.treeview_icon_size, ncam.treeview_icon_size)
                if self.treeview2 is not None:
                    self.tv2_icon_cell.set_fixed_size(ncam.treeview_icon_size, ncam.treeview_icon_size)
            if (old_menu_icon_size != ncam.menu_icon_size) or (old_add_menu_icon_size != ncam.add_menu_icon_size) :
                self.create_menubar()
                self.menubar.show_all()
            if old_add_dlg_icon_size != ncam.add_dlg_icon_size :
                self.update_catalog()

            self.set_preferences()
            self.autorefresh_call()


    def _prime_accel_for_window(self, w):
        """Attach AccelGroup to GtkWindow (realize first)."""
        if w is None or not isinstance(w, gtk.Window):
            return
        if getattr(self, '_accel_group_on_toplevel', False):
            return
        try:
            if not w.get_realized():
                w.realize()
            w.add_accel_group(self.accel_group)
            self._accel_group_on_toplevel = True
        except Exception:
            pass


    def _setup_toplevel_integration(self):
        """Attach AccelGroup to embedding GtkWindow; hook destroy for cleanup."""
        toplevel = self.get_toplevel()
        if toplevel is None or toplevel == self:
            return
        if not isinstance(toplevel, gtk.Window):
            return
        self._prime_accel_for_window(toplevel)
        if not getattr(self, '_toplevel_destroy_hooked', False):
            toplevel.connect('destroy', self._close_all_popups)
            self._toplevel_destroy_hooked = True
        if not getattr(self, '_toplevel_key_hooked', False):
            toplevel.connect('key-press-event', self._toplevel_key_press)
            self._toplevel_key_hooked = True


    def _on_realize(self, *arg):
        """If hierarchy changes, ensure accel/destroy hooks (idempotent)."""
        self._setup_toplevel_integration()


    def create_add_dialog(self):
        self.icon_store = gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, int, str)
        self.add_iconview.set_model(self.icon_store)
        self.add_iconview.set_pixbuf_column(0)
        self.add_iconview.set_text_column(2)

        if self.catalog.tag == 'xml' :
            self.catalog_src = self.catalog
        else :
            for _ptr in range(len(self.catalog)) :
                _p = self.catalog[_ptr]
                if _p.tag.lower() in ["menu", "group"] :
                    self.catalog_src = _p
                    break
        self.update_catalog()


    def create_actions(self):
        self._actions = {}
        def ca(actionname, stock_id, label, accel, tooltip, callback, *args):
            gact = Gio.SimpleAction.new(actionname, None)
            gact._name = actionname
            gact._label = label
            gact._tooltip = tooltip
            gact._stock_id = stock_id
            gact._is_toggle = False
            
            if callback is not None:
                gact.connect('activate', lambda a, p: callback(gact, args))
            
            if accel:
                key, mods = gtk.accelerator_parse(accel)
                if key != 0:
                    self.accel_group.connect(key, mods, gtk.AccelFlags.VISIBLE, lambda *a: gact.activate(None))
                    self.accels[actionname] = (key, mods)
                
            self.gaction_group.add_action(gact)
            self._actions[actionname] = gact
            
            return gact

        def cta(actionname, label, tooltip, callback):
            gact = Gio.SimpleAction.new_stateful(actionname, None, GLib.Variant.new_boolean(False))
            gact._name = actionname
            gact._label = label
            gact._tooltip = tooltip
            gact._stock_id = None
            gact._is_toggle = True
            
            def get_active():
                return gact.get_state().get_boolean()
            gact.get_active = get_active
            
            def set_active(is_active):
                gact.change_state(GLib.Variant.new_boolean(is_active))
            gact.set_active = set_active
            
            if callback is not None:
                def on_change_state(action, value):
                    action.set_state(value)
                    callback(action)
                gact.connect('change-state', on_change_state)
            
            self.gaction_group.add_action(gact)
            self._actions[actionname] = gact
            return gact

        # actions related to projects_("Create a New Project")("Open A Project")_("Open a Saved Project xml file")_('Save Project')
        # "<control>X"
        self.actionProject = ca('Project', None, _("_Projects"), None, None, None)
        self.actionNew = ca("New", 'gtk-new', _("_New Project"), "<control>N", None, self.action_new_project)
        self.actionOpen = ca("Open", 'gtk-open', _("_Open Project"), "<control>O", None, self.action_open_project, 0)
        self.actionOpenExample = ca("OpenExample", None, _('Open Example'), '', _('Open Example Project'), self.action_open_project, 1)
        self.actionSave = ca("Save", 'gtk-save', _("_Save Project As..."), "<control>S", _("Save project as xml file"), self.action_save_project)
        self.actionSaveTemplate = ca("SaveTemplate", None, _('Save as Default Template'), '', _("Save project as default template"), self.action_save_template)
        self.actionSaveNGC = ca("SaveNGC", None, _('Export gcode as RS274NGC'), '', _('Export gcode as RS274NGC'), self.action_save_ngc)

        # actions related to editing
        self.actionEditMenu = ca("EditMenu", None, _("_Edit"), None, None, self.edit_menu_activate)
        self.actionUndo = ca("Undo", 'gtk-undo', _("_Undo"), "<control>Z", _('Undo last operation'), self.action_undo)
        self.actionRedo = ca("Redo", 'gtk-redo', _("_Redo"), "<control><shift>Z", _('Cancel last Undo'), self.action_redo)
        self.actionCut = ca("Cut", 'gtk-cut', _("Cu_t"), "<control>X", _('Cut selected subroutine to clipboard'), self.action_cut)
        self.actionCopy = ca("Copy", 'gtk-copy', _("_Copy"), "<control>C", _('Copy selected subroutine to clipboard'), self.action_copy)
        self.actionPaste = ca("Paste", 'gtk-paste', _("_Paste"), "<control>V", _('Paste from clipboard'), self.action_paste)
        self.actionAdd = ca("Add", 'gtk-add', _("_Add Subroutine"), "<control>Insert", _('Add a subroutine'), self.action_add)
        self.actionDuplicate = ca("Duplicate", 'gtk-copy', _('Duplicate'), "<control>D", _('Duplicate selected subroutine'), self.action_duplicate)
        self.actionDelete = ca("Delete", 'gtk-remove', _("_Remove Subroutine"), "<control>Delete", _('Remove selected subroutine'), self.action_delete)
        self.actionAppendItm = ca("AppendItm", 'gtk-indent', _("Add to Items"), "<control>Right", _("Add to Items"), self.action_appendItm)
        self.actionRemoveItm = ca("RemoveItm", 'gtk-unindent', _("Remove from Items"), "<control>Left", _('Remove from Items'), self.action_removeItem)
        self.actionMoveUp = ca("MoveUp", 'gtk-go-up', _('Move up'), "<control>Up", _('Move up'), self.move, 1)
        self.actionMoveDown = ca("MoveDown", 'gtk-go-down', _('Move down'), "<control>Down", _('Move down'), self.move, -1)
        self.actionSaveUser = ca("SaveUser", 'gtk-save', _('Save Values as Defaults'), '', _('Save Values of this Subroutine as Defaults'), self.action_saveUser)
        self.actionDeleteUser = ca("DeleteUser", 'gtk-cancel', _("Delete Custom Default Values"), None, _("Delete Custom Default Values"), self.action_deleteUser)
        self.actionSetDigits = ca("SetDigits", None, _('Set Digits'), None, None, None)
        self.actionDigit1 = ca("Digit1", None, '1', None, None, self.action_digits, '1')
        self.actionDigit2 = ca("Digit2", None, '2', None, None, self.action_digits, '2')
        self.actionDigit3 = ca("Digit3", None, '3', None, None, self.action_digits, '3')
        self.actionDigit4 = ca("Digit4", None, '4', None, None, self.action_digits, '4')
        self.actionDigit5 = ca("Digit5", None, "5", None, None, self.action_digits, '5')
        self.actionDigit6 = ca("Digit6", None, '6', None, None, self.action_digits, '6')

        # actions related to adding subroutines
        self.actionAddMenu = ca("AddMenu", None, _("_Add"), None, None, None)
        self.actionLoadCfg = ca("LoadCfg", 'gtk-open', _('Add a Prototype Subroutine'), '', _('Add a Subroutine Definition File'), self.action_loadCfg)
        self.actionImportXML = ca("ImportXML", 'gtk-revert-to-saved', _('Import a Project File'), None, _('Import a Project Into the Current One'), self.action_importXML)

        # actions related to view
        self.actionViewMenu = ca("ViewMenu", None, _("_View"), None, None, self.view_menu_activate)
        self.actionCollapse = ca("Collapse", 'gtk-zoom-out', _("Collapse All Other Nodes"), '<control>K', _("Collapse All Other Nodes"), self.action_collapse)
        self.actionSaveLayout = ca("SaveLayout", 'gtk-save', _('Save As Default Layout'), '', _('Save As Default Layout'), self.action_saveLayout)
        self.actionIconColour = ca("IconColour", 'gtk-select-color', _('Icon Colour...'), None, _('Set the accent colour of the icons'), self.action_icon_colour)

        def on_view_changed(action):
            if not action.get_active():
                action.set_state(GLib.Variant.new_boolean(True))
                return
                
            name = action._name
            if name == "SingleView":
                self.actionDualView.set_state(GLib.Variant.new_boolean(False))
            elif name == "DualView":
                self.actionSingleView.set_state(GLib.Variant.new_boolean(False))
            elif name == "TopBottom":
                self.actionSideSide.set_state(GLib.Variant.new_boolean(False))
            elif name == "SideSide":
                self.actionTopBottom.set_state(GLib.Variant.new_boolean(False))
            self.set_layout()

        self.actionSingleView = cta("SingleView", _('Single View'), None, on_view_changed)
        self.actionDualView = cta("DualView",  _('Dual Views'), None, on_view_changed)
        self.actionTopBottom = cta("TopBottom", _('Top / Bottom Layout'), None, on_view_changed)
        self.actionSideSide = cta("SideSide", _('Side By Side Layout'), None, on_view_changed)

        self.actionHideCol = cta("HideCol", _('Master Value Column Hidden'), _('In master treeview'), self.set_layout)
        self.actionSubHdrs = cta("SubHdrs", _('Sub-Groups In Master Tree'), _('Sub-Groups In Master Tree'), self.set_layout)

        # actions related to utilities
        self.actionUtilMenu = ca("UtilitiesMenu", None, _("_Utilities"), None, None, self.utilMenu_activate)
        self.actionLoadTools = ca("LoadTools", 'gtk-refresh', _("Reload Tool Table"), None, _("Reload Tool Table"), ncam.TOOL_TABLE.load_table)
        self.actionPreferences = ca("Preferences", 'gtk-preferences', _("Edit Preferences"), None, _("Edit Preferences"), self.action_preferences)
        self.actionRestart = ca("RestartNCam", 'gtk-refresh',
                                _("Restart NativeCAM"), None,
                                _("Restart just this panel - LinuxCNC and the "
                                  "machine keep running"),
                                self.action_restart_ncam)

        self.actionAutoRefresh = cta("AutoRefresh", _("Auto-refresh"), _('Auto-refresh LinuxCNC'), self._autorefresh_toggled)
        self.actionAutoRefresh.set_active(False)

        self.actionWarnUnreach = cta("WarnUnreachable",
                                    _("Warn on unreachable contour"),
                                    _('Warn when the tool back angle means part '
                                      'of the drawn profile cannot be reached'),
                                    self._warn_unreachable_toggled)
        self.actionWarnUnreach.set_active(True)

        self.actionChUnits = ca("ChUnits", None, _("Change Units"), None, _(""), self.action_chUnits)

        # actions related to validations
        self.actionValidationMenu = ca("ValidationMenu", 'gtk-info', _("_Validation Messages"), None, None, self.validation_menu_activate)
        self.actionValAllDlg = ca("ValAllDlg", 'gtk-yes', _("Show All"), None, _("Show All Non-validation Messages"), self.action_ValAllDlg)
        self.actionValNoDlg = ca("ValNoDlg", 'gtk-no', _("Show None"), None, _("Do Not Show Any Messages"), self.action_ValNoDlg)
        self.actionValFeatDlg = ca("ValFeatDlg", 'gtk-yes', _("Show All For Current Type"), None, None, self.action_ValFeatDlg)
        self.actionValFeatNone = ca("ValFeatNone", 'gtk-no', _("Show None For Current Type"), None, None, self.action_ValFeatNone)

        # actions related to help
        self.actionHelpMenu = ca("HelpMenu", None, _("_Help"), None, None, None)
        self.actionYouTube = ca("YouTube", None, _('NativeCAM on YouTube'), None, None, self.action_youTube)
        self.actionYouTrans = ca("YouTranslate", None, _('Translating NativeCAM'), None, None, self.action_youTrans)
        self.actionToolOrient = ca("ToolOrient", None, _('Lathe Tool Orientation'), None,
                                   _("LinuxCNC's tool orientation numbers, drawn"),
                                   self.action_toolOrient)
        self.actionPreviewLines = ca("PreviewLines", None, _('Preview Lines'), None,
                                     _("What each line on the preview plot is"),
                                     self.action_previewLines)
        self.actionCNCHome = ca("CNCHome", None, _("LinuxCNC web Site"), None, None, self.action_lcncHome)
        self.actionForum = ca("CNCForum", None, _('LinuxCNC Forum'), None, None, self.action_lcncForum)
        self.actionAbout = ca("About", 'gtk-about', _("_About NativeCAM"), None, None, self.action_about)

        # actions related to toolbars and popup
        self.actionHideField = ca("HideField", None, _("Hide Selected Field"), None, _("Hide Selected Field"), self.action_hideField)
        self.actionShowF = ca("ShowFields", None, _("Show All Fields"), None, _("Show All Fields"), self.action_showFields)
        self.actionCurrent = ca("Current", 'gtk-save', _("Save Project as Current Work"), '', _('Save Project as Current Work'), self.action_saveCurrent)
        # One gear used to generate AND load in a single press, so there was no
        # way to rebuild the G-code without also taking over the machine's
        # loaded program. Two buttons now; Auto-refresh still does both.
        self.actionRegen = ca("Regen", 'gtk-execute', _('Regenerate %(filename)s') % {'filename':GENERATED_FILE}, None,
                     _('Generate %(filename)s. Does not touch LinuxCNC, so it is safe while a program is loaded') % {'filename':GENERATED_FILE}, self.action_regen)
        self.actionSend = ca("Send", 'gtk-jump-to', _('Send %(filename)s to LinuxCNC') % {'filename':GENERATED_FILE}, None,
                     _('Load the current %(filename)s in LinuxCNC without regenerating it') % {'filename':GENERATED_FILE}, self.action_send)
        self.actionRename = ca("Rename", None, _("Rename Subroutine"), None, _('Rename Subroutine'), self.action_renameF)
        self.actionChngGrp = ca("ChngGrp", None, _("Group <-- --> Sub-group"), None, _('Group <-- --> Sub-group'), self.action_chng_group)
        self.actionDataType = ca("DataType", None, _("Change to GCode"), None, _('Change to GCode'), self.action_gcode)
        self.actionRevertType = ca("RevertType", None, _("Revert to original type"), None, _('Revert to original type'), self.action_revert_type)


    def get_actions_reference(self) :
        self.actionSingleView = self._actions.get("SingleView")
        self.actionDualView = self._actions.get("DualView")
        self.actionTopBottom = self._actions.get("TopBottom")
        self.actionSideSide = self._actions.get("SideSide")
        self.actionHideCol = self._actions.get("HideCol")
        self.actionSubHdrs = self._actions.get("SubHdrs")


    def set_preferences(self):
        self.restore_bar_order()

        self.main_toolbar.set_icon_size(ncam.toolbar_icon_size)
        self.add_toolbar.set_icon_size(ncam.toolbar_icon_size)

        self.actionSubHdrs.set_active(self.pref.sub_hdrs_in_tv1)
        self.actionHideCol.set_active(self.pref.hide_value_column)

        # the Send radio, from the saved preference. Assigned before syncing so
        # the sync is a no-op write rather than a change that saves the config
        # back out on every startup
        self.send_regenerates = getattr(self.pref, 'send_regenerates', False)
        self._sync_send_mode_items()

        ncam.WARN_UNREACHABLE = getattr(self.pref, 'warn_unreachable', True)
        self.actionWarnUnreach.set_active(ncam.WARN_UNREACHABLE)
        self.actionTopBottom.set_active(not self.pref.side_by_side)
        self.actionSideSide.set_active(self.pref.side_by_side)
        self.actionSingleView.set_active(not self.pref.use_dual_views)
        self.actionDualView.set_active(self.pref.use_dual_views)
        self.actionAutoRefresh.set_active(self.pref.autorefresh)

        for mi in self.mi_current_list: mi.set_visible(not self.pref.autosave)
        self.name_cell.set_property('ellipsize', self.pref.name_ellipsis)
        self.treeview.set_show_expanders(self.pref.tv_expandable)
        if self.pref.tv_expandable :
            self.treeview.set_level_indentation(-5)
        else :
            self.treeview.set_level_indentation(12)

        if self.treeview2 is not None :
            self.name_cell2.set_property('ellipsize', self.pref.name_ellipsis)
            self.treeview2.set_show_expanders(self.pref.tv2_expandable)
            if self.pref.tv2_expandable :
                self.treeview2.set_level_indentation(-5)
            else :
                self.treeview2.set_level_indentation(12)


    def get_widgets(self):
        self.main_box = self.builder.get_object("MainBox")
        self.col_width_adj = self.builder.get_object("col_width_adj")
        self.col_width_adj.set_value(self.pref.col_width_adj_value)
        self.w_adj = self.builder.get_object("width_adj")
        self.w_adj.set_value(self.pref.w_adj_value)
        self.tv_w_adj = self.builder.get_object("tv_w_adj")
        self.tv_w_adj.set_value(self.pref.tv_w_adj_value)

        self.add_toolbar = self.builder.get_object("add_toolbar")
        self.add_toolbar.set_icon_size(ncam.toolbar_icon_size)

        self.feature_pane = self.builder.get_object("ncam_pane")
        self.feature_pane.connect('size-allocate', self._on_vpane_size_allocate)
        self.feature_Hpane = self.builder.get_object("hpaned1")
        self.feature_Hpane.connect('size-allocate', self._on_hpane_size_allocate)
        self.params_scroll = self.builder.get_object("params_scroll")
        self.frame2 = self.builder.get_object("frame2")
        self.addVBox = self.builder.get_object("frame3")
        self.add_iconview = self.builder.get_object("add_iconview")
        self.hint_label = self.builder.get_object("hint_label")
        # long tooltips must wrap: an unwrapped hint label drives the panel's
        # width request up to the full sentence length in the embedding GUI
        self.hint_label.set_line_wrap(True)
        self.hint_label.set_max_width_chars(40)


    def write_ngc(self) :
        """Generate the G-code and write it to ncam.ngc. Returns the path.

        This half touches no LinuxCNC state at all, which is the point of
        having it separately: it is safe to run while a program is loaded or
        even running. Returns None when the panel is not in a state to
        generate - shutting down, or not yet realized - and callers must treat
        that as "nothing was written" rather than carrying on.
        """
        if getattr(self, '_ncam_shutting_down', False):
            return None
        try:
            if not self.get_realized():
                return None
        except Exception:
            return None
        fname = os.path.join(ncam.NGC_DIR, GENERATED_FILE)
        with open(fname, "w") as f:
            f.write(self.to_gcode())
        return fname

    def send_to_linuxcnc(self, fname = None) :
        """Load an already-written ncam.ngc into LinuxCNC.

        Deliberately does NOT generate - Send and Regenerate are separate
        buttons, and which of them regenerates is the operator's choice. Pass a
        path to load something else; the default is the generated file.
        """
        if fname is None :
            fname = os.path.join(ncam.NGC_DIR, GENERATED_FILE)
        if not os.path.isfile(fname) :
            mess_dlg(_('%(filename)s has not been generated yet.\n\nPress Regenerate first.')
                     % {'filename': GENERATED_FILE})
            return False

        try:
            linuxCNC = linuxcnc.command()
            stat = linuxcnc.stat()
            stat.poll()
            if stat.interp_state == linuxcnc.INTERP_IDLE :
                try :
                    _tk_axis_remote_open(fname)
                except Tkinter.TclError as detail:
                    linuxCNC.reset_interpreter()
                    time.sleep(ncam.gmoccapy_time_out)
                    linuxCNC.mode(linuxcnc.MODE_AUTO)
                    time.sleep(0.3)
                    stat.poll()
                    if stat.task_mode == linuxcnc.MODE_AUTO:
                        linuxCNC.program_open(fname)
                    else:
                        mess_dlg(_('LinuxCNC could not change to AUTO mode. Generated NC file was not loaded.'))
        except Exception as e:
            self.actionAutoRefresh.set_active(False)
            if self.show_not_connected :
                mess_dlg(_('LinuxCNC not running\n\nStart LinuxCNC and\nactivate Auto-refresh menu item'))
            return False
        return True

    def _restore_focus(self) :
        if self.focused_widget is not None :
            try:
                self.focused_widget.grab_focus()
            except Exception:
                pass
        else :
            try:
                self.treeview.grab_focus()
            except Exception:
                pass

    def autorefresh_call(self, *arg) :
        """Generate and load, as one step.

        This is what Auto-refresh and every tree edit call, and its behaviour
        must not change now that the toolbar button has been split in two -
        the two halves below are exactly the two halves this used to inline.
        """
        fname = self.write_ngc()
        if fname is None :
            return False
        self.send_to_linuxcnc(fname)
        self._restore_focus()
        return False


    # Where the tool nose CIRCLE sits relative to the programmed control point,
    # as (X, Z) multiples of the nose radius. Copied from LinuxCNC's own
    # backplot - rs274/glcanon.py, StatCanon.lathe_shapes - rather than from a
    # description of it, so the picture cannot drift from what AXIS draws. The
    # (X, Z) reading is confirmed by the glVertex3f(radius*dx, 0, radius*dy)
    # call that consumes it. Note 1-4 put the centre a diagonal away, R * sqrt2,
    # which is the same offset prove_tip_comp.py works with.
    LATHE_NOSE_OFFSET = lathe_comp.NOSE_OFFSET

    # the centre-line angle LinuxCNC's own figure labels each position with,
    # measured clockwise from a line parallel to Z+
    LATHE_ORIENT_DESC = {
        0: _('not set'),
        1: _('CL 135\u00b0'), 2: _('CL 45\u00b0'), 3: _('CL 315\u00b0'), 4: _('CL 225\u00b0'),
        5: _('CL 180\u00b0'), 6: _('CL 90\u00b0'), 7: _('CL 0\u00b0'), 8: _('CL 270\u00b0'),
        9: _('on the point'),
    }

    def action_previewLines(self, *arg):
        """Say what each line on the preview plot is.

        Nothing did. A grep for the legend's own wording returned exactly one
        file - the swatch that draws it - so an operator who wanted to know
        what the yellow-green line meant had nowhere to look. greatEndian read
        it as a cut standing off the contour, twice, and the second time it
        cost a chain of measurement aimed at a toolpath that was never there.

        Drawn rather than written, and drawn with the REAL colours and dashes
        from ncam_preview, so this cannot drift from the plot it describes.
        Same shape as the tool-orientation help beside it in the menu.
        """
        import ncam_preview as prev

        rows = [
            (prev.COL['prefin_surf'], None, _('pre-finish surface'),
             _('SURFACE'),
             _('Where metal ends after the pre-finish pass - the surface you\n'
               'measure to set the finish compensation. Moves with Offset.')),
            (prev.COL['comp'], [6.0, 3.0], _('comp path'),
             _('TOOL PATH'),
             _('Where the control point actually travels on the finish pass,\n'
               'with compensation applied. The only true path drawn here.')),
            (prev.COL['rgh_entry'], prev.REF_DASH, _('rough entry limit'),
             _('REFERENCE'),
             _('Where a roughing level may BEGIN cutting. The tool never\n'
               'follows it. Sits at Offset + Pre-finish + one depth of cut,\n'
               'so it never meets the offset contour - even at a pre-finish\n'
               'offset of 0, because a depth of cut is not an allowance.')),
            (prev.COL['rgh_stop'], prev.REF_DASH, _('rough stop limit'),
             _('REFERENCE'),
             _('Where a roughing level must STOP. Also never followed, and\n'
               'built WITH the nose, so it is a tool-CENTRE reference:\n'
               'the cut surface lies one nose radius inside it.')),
        ]

        dlg = gtk.Dialog(title=_('Preview lines'),
                         transient_for=self.get_toplevel(), modal=True)
        dlg.set_resizable(False)
        vbox = dlg.get_content_area()
        vbox.set_spacing(6)
        vbox.set_border_width(12)

        lbl = gtk.Label()
        lbl.set_markup('<b>' + _('What each line on the plot is') + '</b>')
        lbl.set_halign(gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)

        intro = gtk.Label(label=_(
            'Three kinds of line, told apart by their dash:\n'
            '   solid       a real surface, where metal ends\n'
            '   dashed      a real tool path, where the tool goes\n'
            '   dash-dot    a construction reference - the tool never goes there'))
        intro.set_halign(gtk.Align.START)
        vbox.pack_start(intro, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        grid = gtk.Grid()
        grid.set_row_spacing(8)
        grid.set_column_spacing(10)
        for r, (colour, dash, name, kind, what) in enumerate(rows):
            sample = gtk.DrawingArea()
            sample.set_size_request(90, 16)

            def _draw(widget, cr, colour=colour, dash=dash):
                w = widget.get_allocated_width()
                h = widget.get_allocated_height()
                cr.set_source_rgb(*colour)
                cr.set_line_width(2.0)
                cr.set_dash(dash or [], 0)
                cr.move_to(2, h / 2.0)
                cr.line_to(w - 2, h / 2.0)
                cr.stroke()
                return False

            sample.connect('draw', _draw)
            grid.attach(sample, 0, r, 1, 1)

            nm = gtk.Label()
            nm.set_markup('<b>%s</b>\n<small>%s</small>' % (name, kind))
            nm.set_halign(gtk.Align.START)
            nm.set_valign(gtk.Align.START)
            grid.attach(nm, 1, r, 1, 1)

            desc = gtk.Label(label=what)
            desc.set_halign(gtk.Align.START)
            desc.set_valign(gtk.Align.START)
            grid.attach(desc, 2, r, 1, 1)
        vbox.pack_start(grid, False, False, 0)

        dlg.add_button(_('Close'), gtk.ResponseType.CLOSE)
        dlg.show_all()
        dlg.run()
        dlg.destroy()
        self._restore_focus()


    def action_toolOrient(self, *arg):
        """Draw LinuxCNC's lathe tool orientation numbers.

        The number goes in the tool table's Q column and decides which way the
        nose radius is offset from the point the program commands, so it is
        what makes tool-nose compensation cut the right side. Nothing in the
        UI said what the numbers meant.
        """
        dlg = gtk.Dialog(title=_('Lathe Tool Orientation'),
                         transient_for=self.get_toplevel(), modal=True)
        dlg.set_resizable(False)
        vbox = dlg.get_content_area()
        vbox.set_spacing(6)
        vbox.set_border_width(12)

        lbl = gtk.Label()
        lbl.set_markup('<b>' + _('Tool table Q column') + '</b>')
        lbl.set_halign(gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)

        intro = gtk.Label(label=_(
            'The cross is the point your program commands. The circle is where the\n'
            'tool nose actually sits, one nose radius away in the direction shown.\n'
            'Lathe view as AXIS draws it: Z to the right, X down.\n'
            'CL is the centre-line angle, clockwise from Z+, as in the LinuxCNC manual.'))
        intro.set_halign(gtk.Align.START)
        vbox.pack_start(intro, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        grid = gtk.Grid()
        grid.set_row_spacing(4)
        grid.set_column_spacing(10)

        for n in range(10) :
            col, row = n % 5, (n // 5) * 3
            area = gtk.DrawingArea()
            area.set_size_request(84, 84)
            area.connect('draw', self.draw_orient_cell, n)
            grid.attach(area, col, row, 1, 1)

            num = gtk.Label()
            num.set_markup('<b>%d</b>' % n)
            grid.attach(num, col, row + 1, 1, 1)

            desc = gtk.Label()
            desc.set_markup('<small>%s</small>' % self.LATHE_ORIENT_DESC[n])
            grid.attach(desc, col, row + 2, 1, 1)

        vbox.pack_start(grid, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        note = gtk.Label(label=_(
            '0 means no orientation is set and compensation has nothing to work from.\n'
            '9 puts the nose on the point itself, for a full-radius or button tool.\n'
            'Set it in the tool table Q column, or as a default in Tool Change.'))
        note.set_halign(gtk.Align.START)
        vbox.pack_start(note, False, False, 0)

        dlg.add_button('gtk-close', gtk.ResponseType.CLOSE)
        dlg.set_destroy_with_parent(True)
        dlg.show_all()
        dlg.run()
        dlg.destroy()


    def draw_orient_cell(self, area, ctx, orient, size = None):
        """One orientation cell: the commanded point and where the nose sits.

        Split out of the dialog so it can be rendered - and checked - without
        putting a modal window on screen. size overrides the widget
        allocation for that case.
        """
        w = h = size if size else 0
        if not size :
            w, h = area.get_allocated_width(), area.get_allocated_height()
        # a diagonal orientation puts the circle sqrt(2)*r away, so the drawing
        # reaches 2.414*r from the centre and anything above size/4.83 gets
        # clipped by the cell edge - which looked like a lopsided nose
        cx, cy, r = w / 2.0, h / 2.0, min(w, h) * 0.19
        ctx.set_line_width(1.0)
        ctx.set_source_rgb(0.55, 0.55, 0.55)          # axes through the point
        ctx.move_to(cx - r * 2.2, cy)
        ctx.line_to(cx + r * 2.2, cy)
        ctx.move_to(cx, cy - r * 2.2)
        ctx.line_to(cx, cy + r * 2.2)
        ctx.stroke()

        off = self.LATHE_NOSE_OFFSET[orient] if orient else None
        if off is None :
            ctx.set_source_rgb(0.6, 0.6, 0.6)
            ctx.arc(cx, cy, r, 0, 2 * 3.14159265)
            ctx.set_dash([3.0, 3.0])
            ctx.stroke()
            ctx.set_dash([])
            return
        # the control point marker goes down FIRST: for 5-8 the nose circle
        # passes exactly through it, and drawing the cross last bit a chunk out
        # of the ring
        ctx.set_line_width(2.0)
        ctx.set_source_rgb(0.85, 0.2, 0.2)
        ctx.move_to(cx - 4, cy)
        ctx.line_to(cx + 4, cy)
        ctx.move_to(cx, cy - 4)
        ctx.line_to(cx, cy + 4)
        ctx.stroke()

        dx, dz = off
        # screen: Z runs right, X runs DOWN - the lathe view AXIS draws, where
        # Position 6 (CL 90, +X) is at the bottom. Screen y already grows
        # downward, so +X needs no inversion
        ncx, ncy = cx + dz * r, cy + dx * r
        ctx.set_line_width(1.0)
        ctx.set_source_rgb(0.15, 0.55, 0.15)
        ctx.arc(ncx, ncy, r, 0, 2 * 3.14159265)
        ctx.stroke()


    def action_about(self, *arg):
        dlg = gtk.Dialog(title=_('About NativeCAM'),
                         transient_for=self.get_toplevel(),
                         modal=True)
        dlg.set_resizable(False)
        vbox = dlg.get_content_area()
        vbox.set_spacing(8)
        vbox.set_border_width(16)

        hbox_top = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=12)
        try :
            logo_path = os.path.join(SYS_DIR, 'graphics', 'linuxcncicon.png')
            pix = GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 64, 64)
            hbox_top.pack_start(gtk.Image.new_from_pixbuf(pix), False, False, 0)
        except Exception :
            pass

        try :
            ver = subprocess.check_output(["dpkg-query", "--show", "--showformat=${Version}", "nativecam"])
            version_str = ver.decode('utf-8').strip()
        except :
            version_str = APP_VERSION

        vbox_title = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=2)
        lbl_title = gtk.Label()
        lbl_title.set_markup('<b><big>NativeCAM for LinuxCNC</big></b>')
        lbl_ver = gtk.Label(label=_('Version: ') + version_str)
        lbl_comment = gtk.Label(label=APP_COMMENTS)
        vbox_title.pack_start(lbl_title, False, False, 0)
        vbox_title.pack_start(lbl_ver, False, False, 0)
        vbox_title.pack_start(lbl_comment, False, False, 0)
        hbox_top.pack_start(vbox_title, True, True, 0)
        vbox.pack_start(hbox_top, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        lbl_a = gtk.Label()
        lbl_a.set_markup('<b>' + _('Authors:') + '</b>')
        lbl_a.set_halign(gtk.Align.START)
        vbox.pack_start(lbl_a, False, False, 0)
        for author in APP_AUTHORS :
            l = gtk.Label(label='  ' + author)
            l.set_halign(gtk.Align.START)
            vbox.pack_start(l, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        lbl_copy = gtk.Label(label=APP_COPYRIGHT)
        lbl_copy.set_halign(gtk.Align.START)
        lbl_copy.set_line_wrap(True)
        vbox.pack_start(lbl_copy, False, False, 0)
        vbox.pack_start(gtk.Separator(), False, False, 4)

        hbox_qr = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=16)
        qr_generated = False
        try :
            import qrcode, tempfile
            qr = qrcode.QRCode(version=2, box_size=4, border=2)
            qr.add_data(HOME_PAGE)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color='black', back_color='white')
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            qr_img.save(tmp.name)
            tmp.close()
            pix_qr = GdkPixbuf.Pixbuf.new_from_file_at_size(tmp.name, 140, 140)
            os.unlink(tmp.name)
            frame_qr = gtk.Frame()
            frame_qr.add(gtk.Image.new_from_pixbuf(pix_qr))
            hbox_qr.pack_start(frame_qr, False, False, 0)
            qr_generated = True
        except Exception :
            pass

        vbox_links = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=8)
        if not qr_generated :
            lbl_hint = gtk.Label(label=_('Install python3-qrcode to show QR code'))
            lbl_hint.set_halign(gtk.Align.START)
            vbox_links.pack_start(lbl_hint, False, False, 0)

        lbl_gh = gtk.Label()
        lbl_gh.set_markup('<b>GitHub:</b>')
        lbl_gh.set_halign(gtk.Align.START)
        vbox_links.pack_start(lbl_gh, False, False, 0)
        btn_github = gtk.LinkButton.new_with_label(HOME_PAGE, 'greatEndian/nativecam-py3-gtk3')
        btn_github.set_halign(gtk.Align.START)
        vbox_links.pack_start(btn_github, False, False, 0)

        lbl_don = gtk.Label()
        lbl_don.set_markup('<b>' + _('Support the project:') + '</b>')
        lbl_don.set_halign(gtk.Align.START)
        vbox_links.pack_start(lbl_don, False, False, 4)
        btn_donate = gtk.Button(label='❤  ' + _('Donate via GitHub Sponsors'))
        btn_donate.connect('clicked', lambda w: webbrowser.open(DONATE_URL))
        vbox_links.pack_start(btn_donate, False, False, 0)
        hbox_qr.pack_start(vbox_links, True, True, 0)
        vbox.pack_start(hbox_qr, False, False, 0)

        dlg.add_button(_('License'), gtk.ResponseType.HELP)
        dlg.add_button(_('Close'), gtk.ResponseType.CLOSE)
        dlg.show_all()
        while True :
            response = dlg.run()
            if response == gtk.ResponseType.HELP :
                try :
                    with open('/usr/share/doc/nativecam/copyright', 'r') as f:
                        data = f.read()
                except Exception:
                    data = APP_LICENCE
                lic = gtk.MessageDialog(transient_for=dlg, modal=True,
                    message_type=gtk.MessageType.INFO,
                    buttons=gtk.ButtonsType.CLOSE, text=data)
                lic.run()
                lic.destroy()
            else :
                break
        dlg.destroy()

    def set_layout(self, *arg):
        def _deferred_layout():
            if self.actionDualView.get_active() :
                if self.treeview2 is None :
                    self.create_second_treeview()
                    self.treeview2.show_all()
                
                target_parent = self.feature_Hpane if self.actionSideSide.get_active() else self.feature_pane
                current_parent = self.frame2.get_parent()
                
                if current_parent != target_parent:
                    if current_parent is not None:
                        current_parent.remove(self.frame2)
                    target_parent.pack2(self.frame2, True, False)
            else :
                if self.treeview2 is not None :
                    self.treeview2.destroy()
                    self.treeview2 = None

            self.treestore_from_xml(self.treestore_to_xml())
            self.expand_and_select(self.path_to_new_selected)

            self.frame2.set_visible(self.actionDualView.get_active())
            self.actionTopBottom.set_enabled(self.actionDualView.get_active())
            self.actionSideSide.set_enabled(self.actionDualView.get_active())
            self.actionSubHdrs.set_enabled(self.actionDualView.get_active())
            self.actionHideCol.set_enabled(self.actionDualView.get_active())
            self.treeview.get_column(1).set_visible(self.actionSingleView.get_active() or \
                                        not self.actionHideCol.get_active())
            
            return False  

        GLib.idle_add(_deferred_layout)


    def set_actions_sensitives(self):
        self.actionCollapse.set_enabled(self.selected_feature is not None)

        self.actionSave.set_enabled(self.selected_feature is not None)
        self.actionSaveTemplate.set_enabled(self.selected_feature is not None)
        self.actionSaveNGC.set_enabled(self.selected_feature is not None)

        self.actionSaveUser.set_enabled(self.selected_feature is not None)
        self.actionDeleteUser.set_enabled((self.selected_feature is not None) and \
                    (self.selected_feature.get_type() in ncam.USER_SUBROUTINES))

        self.actionDelete.set_enabled(self.can_delete_duplicate)
        self.actionDuplicate.set_enabled(self.can_delete_duplicate)
        self.actionMoveUp.set_enabled(self.can_move_up)
        self.actionMoveDown.set_enabled(self.can_move_down)
        self.actionAppendItm.set_enabled(self.can_add_to_group)
        self.actionRemoveItm.set_enabled(self.can_remove_from_group)
        self.actionCut.set_enabled(self.can_delete_duplicate)
        self.actionCopy.set_enabled(self.can_delete_duplicate)

        v = self.selected_type in ["sub-header", "header"] and self.actionDualView.get_active()
        for mi in self.mi_chnggrp_list: mi.set_visible(v)
        
        v = self.selected_type == 'float'
        for mi in self.mi_setdigits_list: mi.set_visible(v)
        
        v = self.selected_type in ['float', 'int']
        for mi in self.mi_datatype_list: mi.set_visible(v)
        
        v = self.selected_type == 'gcode'
        for mi in self.mi_reverttype_list: mi.set_visible(v)
        
        v = self.iter_selected_type == tv_select.feature
        for mi in self.mi_rename_list: mi.set_visible(v)

        self.actionHideField.set_enabled((self.selected_type in SUPPORTED_DATA_TYPES) and \
                                      (self.selected_type != 'items'))
        self.actionShowF.set_enabled(self.selected_feature is not None and \
                                       self.selected_feature.has_hidden_fields())
