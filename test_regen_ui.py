#!/usr/bin/env python3
"""Real GTK progress lifecycle and collapsed Polyline property groups.

All generation, preferences and interpreter parameters use a scratch config.
"""
import configparser
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from lxml import etree

HERE = Path(__file__).resolve().parent


def check(name, condition):
    assert condition, name
    print('PASS  ' + name, flush=True)


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_regen_ui_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(settings)
    for section in ('layout', 'display'):
        if not parser.has_section(section):
            parser.add_section(section)
    parser.set('layout', 'dual_view', 'True')
    parser.set('layout', 'autorefresh', 'False')
    parser.set('layout', 'subheaders_in_master', 'True')
    parser.set('display', 'tv2_expandable', 'False')
    with settings.open('w') as stream:
        parser.write(stream)
    sys.argv = ['ncam.py', '-i', str(cfg / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    import ncam_preview as P
    from ncam import gtk, gdk, GLib

    def pump():
        while gtk.events_pending():
            gtk.main_iteration_do(False)

    def wait(predicate, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError('GTK did not reach the expected state')

    def find(tv, predicate):
        found = []
        def visit(model, path, itr):
            if predicate(model.get_value(itr, 0)):
                found.append(path.copy())
        tv.get_model().foreach(visit)
        assert found, 'missing row'
        return found[0]

    def group(tv, name):
        param = app.selected_feature.get_param('param_' + name)
        return find(tv, lambda row: row is param)

    def click(tv, path):
        if len(path.get_indices()) > 1:
            tv.expand_to_path(gtk.TreePath(path.get_indices()[:-1]))
        tv.scroll_to_cell(path, None, True, 0.5, 0)
        def positioned():
            rect = tv.get_background_area(path, tv.get_column(0))
            hit = tv.get_path_at_pos(rect.x + 45, int(rect.y + rect.height / 2))
            return hit is not None and hit[0] == path
        try:
            wait(positioned, timeout=3)
        except AssertionError:
            rect = tv.get_background_area(path, tv.get_column(0))
            print('click diagnostic:', path, (rect.x, rect.y, rect.width, rect.height),
                  tv.get_path_at_pos(rect.x + 45, int(rect.y + rect.height / 2)),
                  tv.get_visible_range(), tv.get_cursor(),
                  tv.row_expanded(gtk.TreePath(path.get_indices()[:-1])), flush=True)
            screenshot = gdk.pixbuf_get_from_window(win.get_window(), 0, 0,
                                                   win.get_allocated_width(), win.get_allocated_height())
            screenshot.savev(str(root / 'click-failure.png'), 'png', [], [])
            print('Artifacts:', root, flush=True)
            raise
        rect = tv.get_background_area(path, tv.get_column(0))
        event = gdk.Event.new(gdk.EventType.BUTTON_PRESS)
        event.window = tv.get_bin_window()
        event.button, event.x, event.y = 1, rect.x + 45, rect.y + rect.height / 2
        check('header click reaches the GTK row',
              tv.get_path_at_pos(int(event.x), int(event.y))[0] == path)
        tv.emit('button-press-event', event)
        pump()

    win = gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    win.add(app)
    win.set_default_size(1200, 900)
    win.show_all()
    app.pref.autosave = False
    app.actionDualView.set_active(True)
    pump()
    source = cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml'
    xml = app.update_features(etree.fromstring(source.read_bytes()))
    app.treestore_from_xml(xml)

    def select(feature_type):
        path = find(app.treeview, lambda row: isinstance(row, ncam.Feature)
                    and row.get_attr('type') == feature_type)
        app.treeview.set_cursor(path)
        app.get_selected_feature(app.treeview)
        pump()

    select('polyline')
    app.feature_Hpane.set_position(420)
    tv = app.treeview2
    headings = ('hx', 'hz', 'h_opt', 'h_ret', 'h_fin', 'h_lead')
    check('Polyline shows all six section headings with expand arrows',
          tv.get_show_expanders() and all(group(tv, name) is not None for name in headings))
    check('all Polyline groups initially hide their children',
          all(not tv.row_expanded(group(tv, name)) for name in headings))
    path = group(tv, 'h_opt')
    click(tv, path)
    check('one click opens Roughing', tv.row_expanded(path))
    child = group(tv, 'min_pass')
    check('expanded properties occupy visible rows',
          tv.get_cell_area(child, tv.get_column(0)).height > 0)
    click(tv, path)
    check('clicking the selected heading closes it again', not tv.row_expanded(path))
    click(tv, path)
    select('workpiece')
    select('polyline')
    check('switching features remembers opened groups and keeps other groups closed',
          tv.row_expanded(group(tv, 'h_opt'))
          and all(not tv.row_expanded(group(tv, name)) for name in headings if name != 'h_opt'))
    child = group(tv, 'min_pass')
    param = tv.get_model().get_value(tv.get_model().get_iter(child), 0)
    before_value = param.get_value(editor=True)
    renderer = tv.get_column(1).get_cells()[0]
    renderer.editdata_type = param.get_type()
    app.edited(renderer, child.to_string(), '0.6')
    check('expanded properties still edit through the existing value renderer',
          abs(float(param.get_ngc_value()) - 0.6) < 1e-6)
    app.edited(renderer, child.to_string(), before_value)
    # A refilter is also triggered by the value editor's refresh callback.
    app.get_selected_feature(app.treeview)
    check('refiltering preserves the opened Roughing group',
          tv.row_expanded(group(tv, 'h_opt')))
    click(tv, group(tv, 'h_opt'))

    app.actionSingleView.set_active(True)
    pump()
    select('polyline')
    check('single-view Polyline also starts with closed headings',
          all(not app.treeview.row_expanded(group(app.treeview, name)) for name in headings))
    click(app.treeview, group(app.treeview, 'hx'))
    check('single-view headings open with one click',
          app.treeview.row_expanded(group(app.treeview, 'hx')))
    click(app.treeview, group(app.treeview, 'hx'))
    app.actionDualView.set_active(True)
    pump()
    select('polyline')

    pane = app.preview_pane
    check('idle progress stays hidden even after show_all', not pane.progress.get_visible())
    expected = app.to_gcode()
    phases, painted, heartbeats = [], [], []
    original_step, original_show = pane.generation_step, pane._show_work
    def step(stage):
        original_step(stage)
        if pane._generating:
            painted.append(pane.progress.get_mapped() and pane.progress.get_allocated_height() > 1)
    def show(stage):
        phases.append(stage)
        original_show(stage)
    heartbeat = GLib.timeout_add(30, lambda: heartbeats.append(True) or True)
    with patch.object(pane, 'generation_step', step), patch.object(pane, '_show_work', show), \
            patch.object(ncam.linuxcnc, 'command', side_effect=AssertionError('machine command')):
        button = next(item for item in app.main_toolbar.get_children()
                      if hasattr(item, 'get_action_name') and item.get_action_name() == 'app.Regen')
        button.get_child().clicked()
        check('progress is painted before and during G-code generation', painted and all(painted))
        check('progress stays visible while the interpreter computes the path',
              pane._busy and pane.progress.get_visible())
        pump()
        screenshot = gdk.pixbuf_get_from_window(win.get_window(), 0, 0,
                                               win.get_allocated_width(), win.get_allocated_height())
        screenshot.savev(str(root / 'computing.png'), 'png', [], [])
        wait(lambda: not pane._busy)
    GLib.source_remove(heartbeat)
    generated = Path(ncam.NGC_DIR) / ncam.GENERATED_FILE
    check('Generate preserves the exact NC program', generated.read_text() == expected)
    check('real preview finishes and fills Plot, G-code and Flat',
          pane.toolpath.completed and pane.toolpath.error is None
          and pane.toolpath.feeds and pane.flat_buffer.get_char_count() > 0)
    check('GTK continues servicing timers while path computation runs', len(heartbeats) > 5)
    check('generation, path reading and collision-checking phases are visible',
          any('Generating' in stage for stage in phases)
          and any('Reading' in stage for stage in phases)
          and any('Checking' in stage for stage in phases))
    check('completion removes the progress timer and bar',
          pane._progress_source is None and not pane.progress.get_visible())

    result = pane.toolpath
    stages = []
    def slow_parse(*args):
        time.sleep(0.3)
        return result
    def slow_check(*args, **kwargs):
        time.sleep(0.3)
        return []
    with patch.object(P, 'parse_program', slow_parse), \
            patch.object(P, 'collisions_checked', return_value=True), \
            patch.object(P, 'collisions', slow_check), \
            patch.object(pane, '_show_work', lambda stage: (stages.append(stage), original_show(stage))[-1]):
        pane.refresh(str(generated))
        wait(lambda: 'Checking' in pane.progress.get_text())
        first_text = pane.progress.get_text()
        pane.refresh(str(generated))
        wait(lambda: not pane._busy)
    check('queued regeneration completes and cleans up its indicator',
          sum('Reading' in stage for stage in stages) == 2
          and pane._pending is None and pane._progress_source is None)
    check('elapsed time is shown during computation', 's' in first_text)
    with patch.object(P, 'parse_program', side_effect=RuntimeError('forced parser failure')):
        pane.refresh(str(generated))
        wait(lambda: not pane._busy)
    check('worker failure reports the error and clears busy state',
          'forced parser failure' in pane._last_status and pane._progress_source is None)
    with patch.object(app, 'to_gcode', side_effect=RuntimeError('forced generation failure')):
        try:
            app.write_ngc()
        except RuntimeError:
            pass
        else:
            raise AssertionError('generation failure not raised')
    check('generation failure clears progress and preserves the last program',
          not pane._generating and not pane.progress.get_visible()
          and 'forced generation failure' in pane._last_status
          and generated.read_text() == expected)

    release = threading.Event()
    def delayed_parse(*args):
        assert release.wait(5)
        return result
    with patch.object(P, 'parse_program', delayed_parse):
        pane.refresh(str(generated))
        win.destroy()
        release.set()
        wait(lambda: not pane._busy)
    check('destroying a busy pane removes timers and ignores the late worker result',
          pane._destroyed and pane._progress_source is None)
    print('Artifacts:', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
