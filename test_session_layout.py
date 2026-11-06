#!/usr/bin/env python3
"""Window geometry, dividers and display choices survive a fresh process."""
import configparser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def stage(root, name):
    sys.argv = ['ncam.py', '-i', str(root / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    from gi.repository import Gtk, GLib, Gdk
    ncam.NCAM_STANDALONE = name not in ('embedded', 'embedded_restore')
    win = Gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    app.pref.autosave = False
    assert hasattr(app, 'actionRememberSession'), 'missing Remember Window and Layout menu checkbox'
    win.add(app)
    app.restore_session_window(win)
    win.show_all()

    def pump(ms=750):
        loop = GLib.MainLoop()
        GLib.timeout_add(ms, lambda: (loop.quit(), False)[1])
        loop.run()

    pump()
    settings = root / 'ncam/catalogs/ncam.conf'
    def saved():
        parser = configparser.ConfigParser()
        parser.read(settings)
        return parser, json.loads(parser.get('session', 'state', fallback='{}'))

    if name == 'save':
        assert app.actionRememberSession.get_active(), 'remember should default on'
        win.resize(940, 820)
        win.move(70, 55)
        pump(250)
        app.feature_Hpane.set_position(int(app.feature_Hpane.get_allocated_width() * .34))
        app.preview_paned.set_position(int(app.preview_paned.get_allocated_height() * .61))
        app.preview_pane.points_btn.set_active(True)
        app.preview_pane.speed_combo.set_active_id('2.0')
        app.preview_pane.widget.set_current_page(3)
        app.actionHideCol.set_active(True)
        pump()
        parser, state = saved()
        assert state['window']['width'] == win.get_size().width
        assert abs(state['splits']['horizontal'] - .34) < .02
        assert abs(state['splits']['preview'] - .61) < .02
        assert parser.getboolean('layout', 'hide_value_column')
        print('PASS automatic save of window, dividers and display options')
    elif name == 'restore':
        _, state = saved()
        assert tuple(win.get_size()) == (state['window']['width'], state['window']['height'])
        assert tuple(win.get_position()) == (state['window']['x'], state['window']['y'])
        assert abs(app.feature_Hpane.get_position() / app.feature_Hpane.get_allocated_width() - .34) < .02
        assert abs(app.preview_paned.get_position() / app.preview_paned.get_allocated_height() - .61) < .02
        assert app.preview_pane.points_btn.get_active()
        assert app.preview_pane.speed_combo.get_active_id() == '2.0'
        assert app.preview_pane.widget.get_current_page() == 3
        assert app.actionHideCol.get_active()
        app.actionTopBottom.set_active(True)
        pump(200)
        app.feature_pane.set_position(int(app.feature_pane.get_allocated_height() * .43))
        pump()
        print('PASS fresh process restores geometry, splits, layout and preview settings')
    elif name == 'disable':
        assert app.actionTopBottom.get_active()
        assert not app.actionSideSide.get_active(), 'saved top/bottom layout reverted to side-by-side'
        assert abs(app.feature_pane.get_position() / app.feature_pane.get_allocated_height() - .43) < .03
        app.actionRememberSession.set_active(False)
        parser, before = saved()
        assert not parser.getboolean('layout', 'remember_session')
        win.resize(1050, 900)
        app.preview_paned.set_position(200)
        pump()
        assert saved()[1] == before, 'disabled memory changed the saved session'
        print('PASS top/bottom split restores and checkbox disables saving')
    elif name == 'disabled_start':
        assert not app.actionRememberSession.get_active()
        assert abs(app.preview_paned.get_position() / app.preview_paned.get_allocated_height() - .5) < .02
        print('PASS disabled startup uses default dividers')
    elif name == 'embedded':
        assert not ncam.NCAM_STANDALONE
        win.resize(1100, 850)
        pump(250)
        size = tuple(win.get_size())
        app.restore_session_window(win)
        pump(250)
        assert tuple(win.get_size()) == size, 'panel changed the host window geometry'
        print('PASS embedding leaves host window geometry under host control')
    elif name == 'embedded_restore':
        assert app.get_size_request().width == saved()[1]['panel_width'] >= 200
        print('PASS embedded panel width survives closing and restarting')
    elif name == 'close':
        app.preview_pane.points_btn.set_active(False)
        win.emit('delete-event', Gdk.Event.new(Gdk.EventType.DELETE))
        assert saved()[1]['preview']['points'] is False, 'close lost a change pending in the save timer'
        print('PASS close flushes pending session changes immediately')
    elif name == 'invalid':
        assert app.actionRememberSession.get_active()
        assert abs(app.preview_paned.get_position() / app.preview_paned.get_allocated_height() - .5) < .02
        app._session_state['window'] = dict(width=10**9, height=-1, x=10**50, y=None)
        app.restore_session_window(win)
        pump(200)
        monitor = win.get_display().get_monitor_at_window(win.get_window()).get_workarea()
        assert win.get_size().width <= monitor.width and win.get_size().height <= monitor.height
        app._session_state['window']['maximized'] = True
        with patch.object(win, 'maximize') as maximize:
            app.restore_session_window(win)
            maximize.assert_called_once_with()
        print('PASS malformed state, invalid geometry and maximized restore')
    ncam.NCAM_STANDALONE = False
    win.destroy()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--stage':
        stage(Path(sys.argv[2]), sys.argv[3])
        return
    root = Path(tempfile.mkdtemp(prefix='ncam_session_test_')) / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', root, symlinks=True)
    settings = root / 'ncam/catalogs/ncam.conf'
    parser = configparser.ConfigParser()
    parser.read(settings)
    for section in ('session',):
        parser.remove_section(section)
    parser.set('layout', 'autorefresh', 'False')
    parser.set('layout', 'dual_view', 'True')
    parser.set('layout', 'side_by_side', 'True')
    parser.set('layout', 'hide_value_column', 'False')
    parser.remove_option('layout', 'remember_session')
    with settings.open('w') as stream:
        parser.write(stream)
    for name in ('save', 'restore', 'disable', 'disabled_start', 'embedded', 'embedded_restore', 'close', 'invalid'):
        if name in ('embedded', 'close', 'invalid'):
            parser.read(settings)
            parser.set('layout', 'remember_session', 'True')
            if name == 'invalid':
                parser.set('session', 'state', '{invalid json')
            with settings.open('w') as stream:
                parser.write(stream)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--stage', str(root), name],
                                capture_output=True, text=True, timeout=45)
        print(result.stdout, end='', flush=True)
        assert result.returncode == 0, result.stderr
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
