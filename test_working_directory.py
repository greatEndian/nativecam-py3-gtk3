#!/usr/bin/env python3
"""Exercise the Projects → Working Directory flow with real GTK dialogs.

Run with xvfb-run -a python3 test_working_directory.py. All settings and
project writes stay in a scratch copy; LinuxCNC is never started.
"""
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from unittest.mock import patch

from lxml import etree

import ncam
import ncam_project_io
from ncam import gtk


HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = []


def check(name, condition):
    assert condition, name
    CHECKS.append(name)
    print('PASS  ' + name, flush=True)


def widgets(widget):
    yield widget
    if isinstance(widget, gtk.Container):
        for child in widget.get_children():
            yield from widgets(child)


def entry_in(dialog):
    return next(w for w in widgets(dialog.get_content_area())
                if isinstance(w, gtk.Entry))


def settle_until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        while gtk.events_pending():
            gtk.main_iteration_do(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('GTK did not reach the expected chooser state')


@contextmanager
def dialogs(*steps):
    """Drive real dialogs without waiting for a human to press their buttons."""
    pending = list(steps)

    def run(dialog):
        assert pending, 'unexpected dialog: ' + str(dialog.get_title())
        title, respond = pending.pop(0)
        assert dialog.get_title() == title, (dialog.get_title(), title)
        dialog.show_all()
        return respond(dialog)

    with patch.object(gtk.Dialog, 'run', run), \
            patch.object(gtk.FileChooserDialog, 'run', run):
        yield
    assert not pending, 'expected dialogs were not opened: ' + str(pending)


def chooser(folder, filename=None, response=gtk.ResponseType.CANCEL):
    def respond(dialog):
        settle_until(lambda: dialog.get_current_folder() == folder)
        check(dialog.get_title() + ' uses the selected folder', True)
        if filename:
            if dialog.get_action() == gtk.FileChooserAction.SAVE:
                dialog.set_current_name(os.path.basename(filename))
            else:
                dialog.set_filename(filename)
            settle_until(lambda: dialog.get_filename() == filename)
        return response
    return respond


def main():
    if not gtk.init_check()[0]:
        raise SystemExit('A display is required; run with xvfb-run -a.')
    with tempfile.TemporaryDirectory(prefix='ncam_working_directory_') as scratch:
        config_dir = os.path.join(scratch, 'config')
        shutil.copytree(os.path.join(HERE, 'configs/sim/axis/ncam_demo'),
                        config_dir, symlinks=True)
        ini = os.path.join(config_dir, 'lathe-mm.ini')
        sys.argv = ['ncam.py', '-i', ini, '-c', 'lathe']
        os.environ['INI_FILE_NAME'] = ini
        os.environ['XDG_CONFIG_HOME'] = os.path.join(scratch, 'xdg')
        window = gtk.Window()
        app = ncam.NCam(accel_toplevel=window)
        window.add(app)
        app.pref.autosave = False
        app.show_all()
        original_dir = os.path.join(ncam.NCAM_DIR, 'catalogs/lathe/projects')
        working = os.path.join(scratch, "work 100% 'quoted'")
        os.mkdir(working)
        original_root = ncam.NCAM_DIR
        original_ngc = ncam.NGC_DIR
        cfg_file = os.path.join(ncam.NCAM_DIR, 'catalogs/ncam.conf')
        cfg_before = open(cfg_file).read()

        check('default folder works without any new preference',
              app.get_project_directory() == original_dir)
        menu = app.menubar.get_children()[0].get_submenu()
        item = next(w for w in menu.get_children()
                    if w.get_action_name() == 'app.WorkingDirectory')
        check('Working Directory is available in Projects', item.get_sensitive())
        before = app.to_gcode()

        def accept_directory(dialog):
            check('dialog initially shows the current project directory',
                  entry_in(dialog).get_text() == original_dir)
            check('dialog belongs to the NativeCAM window',
                  dialog.get_transient_for() == window
                  and dialog.get_destroy_with_parent())
            entry_in(dialog).set_text(working)
            return gtk.ResponseType.OK

        with dialogs(('Working Directory', accept_directory),
                     ('Open project', chooser(working))):
            item.activate()
        check('OK remembers the folder even when file selection is cancelled',
              app.get_project_directory() == working)
        check('choosing a directory does not change generated G-code',
              app.to_gcode() == before)
        check('the configuration and generated-program roots remain correct',
              ncam.NCAM_DIR == original_root and ncam.NGC_DIR == original_ngc)

        child_code = (
            'import sys, ncam; from ncam_project_io import NCamProjectIOMixin; '
            'ncam.NCAM_DIR = sys.argv[1]; a = NCamProjectIOMixin(); '
            'a.catalog_dir = "lathe"; print(a.get_project_directory())')
        fresh = subprocess.run([sys.executable, '-c', child_code, ncam.NCAM_DIR],
                               cwd=HERE, capture_output=True, text=True, timeout=30)
        check('a fresh process restores the selected directory',
              fresh.returncode == 0 and fresh.stdout.strip() == working)
        config = configparser.ConfigParser(interpolation=None)
        config.read(cfg_file)
        old = configparser.ConfigParser()
        old.read_string(cfg_before)
        check('all previous preferences survive saving the folder',
              all(config.get(section, key) == value for section in old.sections()
                  for key, value in old.items(section)))
        mill = ncam_project_io.NCamProjectIOMixin()
        mill.catalog_dir = 'mill'
        check('lathe selection does not change the mill folder',
              mill.get_project_directory()
              == os.path.join(ncam.NCAM_DIR, 'catalogs/mill/projects'))
        mill.set_project_directory(scratch)
        check('another catalog keeps its own choice without changing lathe',
              mill.get_project_directory() == scratch
              and app.get_project_directory() == working)

        with dialogs(('Open project', chooser(working))):
            app.action_open_project(None, (0,))
        with dialogs(('Save project as...', chooser(working))):
            app.action_save_project()
        with dialogs(('Import project', chooser(working))):
            app.action_importXML()
        examples = os.path.join(original_dir, 'examples')
        with dialogs(('Open example project', chooser(examples))):
            app.action_open_project(None, (1,))

        # The same real chooser check must reject the old fixed-folder rule.
        detected = False
        with patch.object(app, 'get_project_directory', return_value=original_dir):
            try:
                with dialogs(('Save project as...', chooser(working))):
                    app.action_save_project()
            except AssertionError:
                detected = True
        check('negative control detects the old fixed-folder behavior', detected)

        source = os.path.join(working, 'a project.xml')
        xml_before = app.treestore_to_xml()
        with open(source, 'wb') as project_file:
            etree.ElementTree(xml_before).write(project_file, pretty_print=True)
        with dialogs(('Open project', chooser(working, source, gtk.ResponseType.OK))):
            app.action_open_project(None, (0,))
        check('a selected project is actually loaded', ncam.CURRENT_PROJECT == source)
        app.action_save_current_project()
        check('plain Save writes back to the opened project',
              etree.parse(source).getroot().tag == ncam.XML_TAG)

        saved = os.path.join(working, 'new project')
        with dialogs(('Save project as...', chooser(working, saved, gtk.ResponseType.OK))):
            app.action_save_project()
        check('Save As writes a new XML project in the working directory',
              os.path.isfile(saved + '.xml') and ncam.CURRENT_PROJECT == saved + '.xml')
        features = len(app.treestore_to_xml().findall('feature'))
        check('the Import fixture contains real features', features > 0)
        with dialogs(('Import project', chooser(working, source, gtk.ResponseType.OK))):
            app.action_importXML()
        check('Import reads the selected project from the working directory',
              len(app.treestore_to_xml().findall('feature')) == 2 * features)

        persisted = open(cfg_file).read()

        def cancel_directory(dialog):
            check('the dialog is prefilled with the remembered directory',
                  entry_in(dialog).get_text() == working)
            entry_in(dialog).set_text(scratch)
            return gtk.ResponseType.CANCEL

        with dialogs(('Working Directory', cancel_directory)):
            app.action_working_directory()
        check('Cancel neither changes settings nor opens a project dialog',
              open(cfg_file).read() == persisted)

        def invalid_directory(dialog):
            entry_in(dialog).set_text(os.path.join(scratch, 'missing'))
            return gtk.ResponseType.OK

        def after_invalid(dialog):
            check('invalid folder leaves an explanation in the dialog',
                  any(isinstance(w, gtk.Label) and 'Folder does not exist' in w.get_text()
                      for w in widgets(dialog.get_content_area())))
            return gtk.ResponseType.CANCEL

        with dialogs(('Working Directory', invalid_directory),
                     ('Working Directory', after_invalid)):
            app.action_working_directory()
        check('invalid folder does not replace the saved working directory',
              open(cfg_file).read() == persisted)

        uri = ncam.Gio.File.new_for_path(working).get_uri()
        check('pasted local file links also resolve correctly',
              app.set_project_directory(uri) == working)
        for bad in ('', source, os.path.join(scratch, 'missing')):
            try:
                app.set_project_directory(bad)
            except ValueError:
                continue
            raise AssertionError('invalid directory was accepted: ' + bad)
        check('blank paths, files and nonexistent folders are refused', True)

        def write_failure(dialog):
            entry_in(dialog).set_text(scratch)
            return gtk.ResponseType.OK

        def after_write_failure(dialog):
            check('a failed preference write is shown in the dialog',
                  any(isinstance(w, gtk.Label) and 'test write failure' in w.get_text()
                      for w in widgets(dialog.get_content_area())))
            return gtk.ResponseType.CANCEL

        with patch.object(ncam_project_io.atomic_write, 'write_atomic',
                          side_effect=OSError('test write failure')):
            with dialogs(('Working Directory', write_failure),
                         ('Working Directory', after_write_failure)):
                app.action_working_directory()
        check('a failed write keeps the previous directory',
              app.get_project_directory() == working)

        def browse_directory(dialog):
            button = next(w for w in widgets(dialog.get_content_area())
                          if isinstance(w, gtk.Button) and w.get_label() == 'Browse…')
            button.clicked()
            check('Browse puts the selected folder into the path field',
                  entry_in(dialog).get_text() == scratch)
            return gtk.ResponseType.OK

        with dialogs(('Working Directory', browse_directory),
                     ('Choose Working Directory',
                      chooser(working, scratch, gtk.ResponseType.OK)),
                     ('Open project', chooser(scratch))):
            app.action_working_directory()
        check('Browse also saves the selection', app.get_project_directory() == scratch)

        missing = os.path.join(scratch, 'removed')
        os.mkdir(missing)
        app.set_project_directory(missing)
        os.rmdir(missing)
        warnings = []
        with patch.object(ncam_project_io, 'mess_dlg', side_effect=warnings.append):
            with dialogs(('Open project', chooser(original_dir))):
                app.action_open_project(None, (0,))
        check('a missing working folder is reported before using the default',
              len(warnings) == 1 and missing in warnings[0])

        window.destroy()
    print('\n%d working-directory checks passed.' % len(CHECKS))


if __name__ == '__main__':
    main()
