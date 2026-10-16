#!/usr/bin/env python3
"""Real property editors and Generate stay usable during preview playback."""
import configparser
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from lxml import etree

HERE = Path(__file__).resolve().parent


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_playback_edit_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(settings)
    parser.set('layout', 'autorefresh', 'False')
    parser.set('layout', 'dual_view', 'True')
    with settings.open('w') as stream:
        parser.write(stream)
    sys.argv = ['ncam.py', '-i', str(cfg / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    import ncam_preview as P
    from ncam import gtk, GLib

    events = []
    def check(name, condition, **data):
        events.append(dict(check=name, passed=bool(condition), **data))
        (root / 'results.json').write_text(json.dumps(events, indent=2))
        assert condition, (name, data, 'ARTIFACTS', str(root))
        print('PASS ' + name, data or '', flush=True)

    def wait(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            # A perpetually-ready playback source must not trap the test in
            # a while(events_pending()) loop either. Check deadlines per event.
            if gtk.events_pending():
                gtk.main_iteration_do(False)
            else:
                time.sleep(0.005)
        raise AssertionError('GTK state timed out; artifacts: ' + str(root))

    def settle(seconds=0.15):
        until = time.monotonic() + seconds
        wait(lambda: time.monotonic() >= until, timeout=seconds + 5)

    def find(tv, predicate):
        found = []
        tv.get_model().foreach(lambda model, path, itr: found.append(path.copy())
                               if predicate(model.get_value(itr, 0)) else None)
        assert found
        return found[0]

    win = gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    win.add(app)
    win.set_default_size(1400, 950)
    win.show_all()
    app.pref.autosave = False
    # Apply startup's deferred layout before replacing the project/model.
    # The operator can only edit a mapped view; targeting an unshown details
    # view instead fails get_bin_window before the real editor can run.
    app.actionDualView.set_active(True)
    settle()
    xml = app.update_features(etree.fromstring(
        (cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml').read_bytes()))
    poly = xml.find('.//feature[@type="polyline"]')
    for key, value in [('peck_len', 2), ('peck_ret', 0.1), ('peck_dwell', 0.4)]:
        poly.find('./param[@call="#param_%s"]' % key).set('value', str(value / 25.4))
    app.treestore_from_xml(xml)
    pane = app.preview_pane
    button = next(item for item in app.main_toolbar.get_children()
                  if hasattr(item, 'get_action_name') and item.get_action_name() == 'app.Regen')
    generated = Path(ncam.NGC_DIR) / ncam.GENERATED_FILE
    activations = []
    app.actionRegen.connect('activate', lambda *args: activations.append(True))

    def select_polyline():
        path = find(app.treeview, lambda row: row.get_attr('type') == 'polyline')
        app.treeview.set_cursor(path)
        app.get_selected_feature(app.treeview)

    def row(name):
        tv = app.treeview2 if app.actionDualView.get_active() else app.treeview
        param = app.selected_feature.get_param('param_' + name)
        path = find(tv, lambda item: item is param)
        tv.expand_to_path(path)
        tv.scroll_to_cell(path, None, True, 0.5, 0)
        tv.set_cursor(path)
        wait(lambda: tv.get_mapped() and tv.get_bin_window() is not None)
        return tv, path, param, tv.get_column(1).get_cells()[0]

    def play(dwell=False):
        pane._on_stop(None)
        pane.speed = 0.01
        fraction = 0.4
        if dwell:
            acc, total = P.path_lengths(pane.toolpath)
            after = next(after for after, seconds, op in pane.toolpath.dwells
                         if op == 'Lathe Polyline' and seconds == 0.4)
            fraction = acc[after - 1] / total
        pane.sim_scale.set_value(fraction)
        pane._on_play(None)
        if dwell:
            wait(lambda: pane._playback is not None and pane._playback.remaining > 0)
        check('playback is running before edit', pane.sim_running and pane._sim_source is not None)

    def start(tv, path, renderer):
        rect = tv.get_cell_area(path, tv.get_column(1))
        renderer.do_start_editing(None, tv, path.to_string(), rect, rect,
                                 gtk.CellRendererState.SELECTED)

    def paused(position, cursor, field, remaining):
        check('editor pauses timer without rewinding material or dwell',
              not pane.sim_running and pane._sim_source is None
              and pane.sim_t == position and pane._playback is cursor
              and pane._field is field and cursor.remaining == remaining)

    def numeric(name, value, cancel=False, dwell=False):
        tv, path, param, renderer = row(name)
        play(dwell)
        position, cursor, field = pane.sim_t, pane._playback, pane._field
        remaining = cursor.remaining
        before = param.get_ngc_value()
        opened, committed = [], []
        original = ncam.VKB.run
        original_edited = renderer.edited
        def edited(*args):
            original_edited(*args)
            committed.append(True)
        def run(vkb, not_allowed):
            opened.append(time.monotonic())
            check('numeric editor starts with selected value despite another row repaint',
                  abs(float(vkb.entry.get_text()) - float(before)) < 1e-6,
                  parameter=name)
            def respond():
                vkb.entry.set_markup('<b>%s</b>' % value)
                (vkb.cancel if cancel else vkb.ok)(None)
                return False
            GLib.timeout_add(30, respond)
            return original(vkb, not_allowed)
        requested = time.monotonic()
        with patch.object(ncam.VKB, 'run', run), patch.object(renderer, 'edited', edited):
            start(tv, path, renderer)
            paused(position, cursor, field, remaining)
            other = find(tv, lambda item: item is app.selected_feature.get_param('param_peck_dwell'))
            app.get_col_value(tv.get_column(1), renderer, tv.get_model(), tv.get_model().get_iter(other))
            wait(lambda: opened and (cancel or committed))
            settle()
        expected = float(before) if cancel else value
        check('real numeric popup accepts/cancels and releases its GTK grab',
              abs(float(param.get_ngc_value()) - expected) < 1e-6
              and gtk.grab_get_current() is None,
              parameter=name, cancel=cancel, latency=round(opened[0]-requested, 4))
        check('editing does not restart playback automatically', not pane.sim_running)
        if dwell:
            pane._on_play(None)
            wait(lambda: cursor.remaining < remaining)
            check('Play resumes the remaining dwell at the same point', pane.sim_t == position)
            pane._on_play(None)

    try:
        with open('/tmp/ncam-rs274.lock', 'a') as lock, \
                patch.object(ncam.linuxcnc, 'command', side_effect=AssertionError('controller command')):
            fcntl.flock(lock, fcntl.LOCK_EX)
            button.get_child().clicked()
            wait(lambda: not pane._busy, timeout=60)
            check('actual Generate loads complete peck motion',
                  pane.toolpath.completed and not pane.toolpath.error and pane.toolpath.peck_stops)
            select_polyline()
            idle = []
            def queue_idle():
                GLib.idle_add(lambda: idle.append(time.monotonic()) or False)
                return False
            # Exercise a render workload longer than a playback tick. Complex
            # contours/high-resolution material can take this long naturally.
            # Retain real geometry, and temporarily omit waits so every tick
            # requests another frame rather than resting at a dwell.
            original_profile = pane.profile_cb
            dwells = pane.toolpath.dwells
            def slow_profile():
                time.sleep(0.05)
                return original_profile()
            pane.toolpath.dwells = []
            with patch.object(pane, 'profile_cb', slow_profile):
                play()
                requested = time.monotonic()
                GLib.timeout_add(300, queue_idle)
                settle(1.5)
            check('idle work runs while playback remains active', idle and pane.sim_running,
                  latency=round(idle[0]-requested, 4) if idle else None)
            pane._on_play(None)
            pane.toolpath.dwells = dwells

            numeric('peck_len', 3, dwell=True)
            numeric('peck_ret', 0.2, cancel=True)
            # A different property can be selected immediately afterwards.
            tv, path, param, renderer = row('li_len')
            check('another property can be selected after editing', tv.get_cursor()[0] == path)

            # Use real keyboard input to select from the deferred popup.
            for choice in (1, 0):
                tv, path, param, renderer = row('peck_ret_mode')
                play()
                original_list = renderer.edit_list
                closed = []
                def edit_list(*args):
                    def respond():
                        key = 'End' if choice else 'Home'
                        subprocess.run(['xdotool', 'key', key, 'Return'],
                                       check=True, timeout=2)
                        return False
                    GLib.timeout_add(100, respond)
                    result = original_list(*args)
                    closed.append(True)
                    return result
                with patch.object(renderer, 'edit_list', edit_list):
                    start(tv, path, renderer)
                    wait(lambda: closed and param.get_ngc_value() == str(choice))
                check('repeated combo editors close and keep UI usable',
                      not pane.sim_running and gtk.grab_get_current() is None)

            tv, path, param, renderer = row('pf_on')
            for _ in range(2):
                old = param.get_ngc_value()
                play()
                start(tv, path, renderer)
                other = find(tv, lambda item: item is app.selected_feature.get_param('param_peck_len'))
                app.get_col_value(tv.get_column(1), renderer, tv.get_model(), tv.get_model().get_iter(other))
                wait(lambda: param.get_ngc_value() != old)
                check('boolean edits also pause playback', not pane.sim_running)

            app.actionSingleView.set_active(True)
            wait(lambda: app.treeview2 is None)
            select_polyline()
            numeric('peck_ret', 0.15)
            # Headings and disabled values do not open an editor or pause it.
            for name, disabled in [('h_opt', False), ('peck_ret', True)]:
                tv, path, param, renderer = row(name)
                param.set_grayed(disabled)
                play()
                start(tv, path, renderer)
                check('noneditable rows leave playback running', pane.sim_running)
                pane._on_play(None)
                param.set_grayed(False)

            tv, path, _param, _renderer = row('li_len')
            count = len(activations)
            play()
            button.get_child().clicked()
            check('Generate remains available after edits during playback', len(activations) == count + 1)
            wait(lambda: not pane._busy, timeout=60)
            code = generated.read_text()
            check('Generate uses edited parameters and fills preview',
                  '#<_pl_peck_len> = 3.000000' in code
                  and '#<_pl_peck_ret> = 0.150000' in code
                  and pane.toolpath.completed and not pane.toolpath.error
                  and pane.flat_buffer.get_char_count() > 0)
    finally:
        win.destroy()
    print('ARTIFACTS', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
