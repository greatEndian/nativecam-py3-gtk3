#!/usr/bin/env python3
"""Real Generate -> interpreter -> plot/G-code/Flat, without running LinuxCNC.

Run with xvfb-run -a python3 -u test_generate_preview.py. Each launch mode
gets a fresh Python process and all generated/configuration files are scratch.
"""
import argparse
import configparser
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import ncam_preview


HERE = Path(__file__).resolve().parent


def check(name, condition):
    assert condition, name
    print('PASS  ' + name, flush=True)


def wait_for(gtk, predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        while gtk.events_pending():
            gtk.main_iteration_do(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('GTK/preview did not finish in 45 seconds')


def child(case, root):
    ini = root / 'config/lathe-mm.ini'
    project = root / 'config/ncam/catalogs/lathe/projects/testing_15_9.xml'
    standalone = root / ('standalone-' + case)
    shutil.copytree(root / 'config/ncam', standalone, symlinks=True)
    # Restore a blank start, then load the test project through the real Open action.
    current = standalone / 'catalogs/lathe/projects/current_work.xml'
    if current.exists():
        current.unlink()
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(standalone / 'catalogs/ncam.conf')
    if not parser.has_section('project_directories'):
        parser.add_section('project_directories')
    parser.set('project_directories', 'lathe', str(project.parent))
    with (standalone / 'catalogs/ncam.conf').open('w') as output:
        parser.write(output)

    os.environ.pop('INI_FILE_NAME', None)
    if case == 'environment':
        os.environ['INI_FILE_NAME'] = str(ini)
    sys.argv = ['ncam.py', '-c', 'lathe']
    if case == 'command-line':
        sys.argv += ['-i', str(ini)]
    import ncam
    from ncam import gtk

    original_expand = os.path.expanduser

    def expand(path):
        return str(standalone) if path == '~/nativecam' else original_expand(path)

    commands = []

    def machine_command(*args):
        commands.append(args)
        raise AssertionError('Generate must not issue LinuxCNC commands')

    with patch.object(os.path, 'expanduser', expand), \
            patch.object(ncam.linuxcnc, 'command', machine_command):
        window = gtk.Window()
        app = ncam.NCam(accel_toplevel=window)
        window.add(app)
        window.set_default_size(1000, 850)
        app.pref.autosave = False
        window.show_all()
        pane = app.preview_pane
        # Earlier launches can remember Raw/Flat; map Plot before waiting for it.
        pane.widget.set_current_page(0)
        wait_for(gtk, lambda: pane.area.get_window() is not None)
        check(case + ': preview receives the correct machine INI',
              pane.ini_path == str(ini))
        check(case + ': generation uses that machine tool table',
              ncam.TOOL_TABLE.table_fname == str(root / 'config/lathe_mm.tbl'))
        if case == 'standalone':
            check('standalone context does not redirect its output into the machine config',
                  ncam.NCAM_DIR == str(standalone)
                  and ncam.NGC_DIR == str(standalone / 'scripts'))
        else:
            check(case + ': explicit configuration takes precedence',
                  app.ini_file == str(ini)
                  and ncam.NCAM_DIR == str(root / 'config/ncam'))

        def choose_project(dialog):
            dialog.show_all()
            dialog.set_filename(str(project))
            wait_for(gtk, lambda: dialog.get_filename() == str(project))
            return gtk.ResponseType.OK

        with patch.object(gtk.FileChooserDialog, 'run', choose_project):
            app.action_open_project(None, (0,))
        check(case + ': actual Open loads the requested project',
              ncam.CURRENT_PROJECT == str(project))
        button = next(item for item in app.main_toolbar.get_children()
                      if hasattr(item, 'get_action_name')
                      and item.get_action_name() == 'app.Regen')
        activations = []
        app.actionRegen.connect('activate', lambda *args: activations.append(True))
        def click_generate():
            count = len(activations)
            # The inner GtkButton runs the ToolButton's action helper before
            # emitting its public clicked signal, just like a physical click.
            button.get_child().clicked()
            check(case + ': clicking the toolbar activates Generate exactly once',
                  len(activations) == count + 1)
        generated = Path(ncam.NGC_DIR) / ncam.GENERATED_FILE
        parameter_file = root / 'config/lathe.var'
        var_before = hashlib.sha256(parameter_file.read_bytes()).digest()

        if case == 'standalone':
            # Isolate the old missing-INI fault while keeping the tool table
            # correct: the same generated program must fail to produce motion.
            with patch.object(app, 'configure_preview_context', return_value=None):
                pane.ini_path = None
                click_generate()
                wait_for(gtk, lambda: not pane._busy)
            check('negative control: missing machine context produces no toolpath',
                  not pane.toolpath.moves and bool(pane.toolpath.error))
            control_program = generated.read_bytes()

        # Generate while the raw listing is selected; all three views must fill.
        pane.widget.set_current_page(1)
        click_generate()
        wait_for(gtk, lambda: not pane._busy)
        check(case + ': the toolbar button activates Generate', bool(activations))
        check(case + ': Generate writes a complete NC program',
              generated.is_file() and generated.read_text().rstrip().endswith('M2'))
        check(case + ': interpreter completes without an error',
              pane.toolpath.error is None and pane.toolpath.completed)
        check(case + ': plot contains cutting moves and measurable extents',
              bool(pane.toolpath.feeds) and pane.toolpath.extents() is not None)
        check(case + ': G-code tab contains the generated program',
              pane.buffer.get_text(*pane.buffer.get_bounds(), True)
              == generated.read_text())
        check(case + ': Flat tab contains interpreted G-code',
              bool(pane.toolpath.flat.strip())
              and pane.flat_buffer.get_text(*pane.flat_buffer.get_bounds(), True)
              == pane.toolpath.flat)
        check(case + ': source parameter file is byte-identical after preview',
              hashlib.sha256(parameter_file.read_bytes()).digest() == var_before)
        check(case + ': Generate never calls LinuxCNC commands', not commands)
        if case == 'standalone':
            check('restoring interpreter context does not change the generated program',
                  generated.read_bytes() == control_program)
        (root / ('program-' + case + '.ngc')).write_bytes(generated.read_bytes())
        print('RESULT %s: %d moves; %d raw characters; %d flat characters'
              % (case, len(pane.toolpath.moves), pane.buffer.get_char_count(),
                 pane.flat_buffer.get_char_count()), flush=True)
        window.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if args.case:
        child(args.case, args.root)
        return
    with tempfile.TemporaryDirectory(prefix='ncam_generate_preview_') as temp:
        root = Path(temp)
        shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', root / 'config',
                        symlinks=True)
        projects = root / 'config/ncam/catalogs/lathe/projects'
        metric = str(root / 'config/lathe-mm.ini')
        check('discovery selects metric lathe context for the selected working folder',
              ncam_preview.project_ini_candidates(str(projects), 'lathe', True) == [metric])
        check('imperial lathe discovery selects the imperial configuration',
              ncam_preview.project_ini_candidates(str(projects), 'lathe', False)
              == [str(root / 'config/lathe.ini')])
        check('discovery does not select a nearby unrelated machine configuration',
              not ncam_preview.project_ini_candidates(str(root), 'lathe', True))
        check('discovery also supports a project filename',
              ncam_preview.project_ini_candidates(str(projects / 'testing_15_9.xml'),
                                                  'lathe', True) == [metric])
        duplicate = root / 'config/duplicate.ini'
        shutil.copyfile(metric, duplicate)
        check('ambiguous contexts are returned together instead of guessing',
              len(ncam_preview.project_ini_candidates(str(projects), 'lathe', True)) == 2)
        duplicate.unlink()

        for case in ('standalone', 'command-line', 'environment'):
            result = subprocess.run(
                [sys.executable, '-u', __file__, '--case', case, '--root', str(root)],
                capture_output=True, text=True, timeout=120)
            print(result.stdout, end='', flush=True)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end='', flush=True)
            check(case + ': complete GUI/interpreter regression exits successfully',
                  result.returncode == 0)
        check('standalone emits exactly the same program as a configured launch',
              (root / 'program-standalone.ngc').read_bytes()
              == (root / 'program-command-line.ngc').read_bytes()
              == (root / 'program-environment.ngc').read_bytes())
    print('\nGenerate, plot, raw G-code and Flat checks passed in all launch modes.')


if __name__ == '__main__':
    main()
