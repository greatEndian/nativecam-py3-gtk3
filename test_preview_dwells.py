#!/usr/bin/env python3
"""Dwell metadata and real GTK playback holds without altering geometry."""
import math
from pathlib import Path
import sys
import tempfile

import ncam_preview as P


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-9), (a, b)


def main():
    # Use a short actual G-code program: the parser must preserve positions,
    # zero-distance consecutive waits and waits before the first tracked move.
    root = Path(tempfile.mkdtemp(prefix='ncam_preview_dwells_'))
    path = root / 'dwells.ngc'
    path.write_text('G21 G18 G7 G90 G94\n(begin Test)\n'
                    'G0 X20 Z0\nG4 P0.1\nG1 Z-10 F100\n'
                    '(ncam peck stop)\nG4 P0.4\nG4 P0.2\nG1 Z-20\n'
                    '(ncam peck stop)\nG4 P0\nG4 P0.3\n(end Test)\nM2\n')
    import fcntl
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tp = P.parse_program(str(path), str(Path(__file__).resolve().parent
                                           / 'configs/sim/axis/ncam_demo/lathe-mm.ini'))
    assert tp.completed and not tp.error, tp.error
    assert len(tp.moves) == 2, tp.moves
    assert tp.peck_stops == [(1, tp.moves[0].b, 'Test'), (2, tp.moves[1].b, 'Test')]
    assert P.peck_stop_points(tp) == [m.b for m in tp.moves]
    assert P.peck_stop_points(tp, [tp.moves[1]]) == [tp.moves[1].b]
    assert P.peck_stop_points(tp, []) == []
    # Test pixels, not just the metadata: stop dots must be drawn by default,
    # and must disappear when their path moves are hidden.
    import cairo
    def pixels(moves=None):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 140)
        P.draw_toolpath(cairo.Context(surface), 240, 140, tp, moves=moves)
        surface.flush()
        return bytes(surface.get_data())
    with_dots = pixels()
    hidden = pixels([])
    stops = tp.peck_stops
    tp.peck_stops = []
    without_dots = pixels()
    assert hidden == pixels([]), 'hidden moves must also hide stop markers'
    assert with_dots != without_dots, 'actual stop dots must change rendered pixels'
    tp.peck_stops = stops
    cursor = P.Playback(tp)
    # Record a standalone image for visual review of the default markers.
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 480, 220)
    P.draw_toolpath(cairo.Context(surface), 480, 220, tp)
    surface.write_to_png(str(root / 'peck-dots.png'))
    assert tp.dwells == [(0, 0.1, 'Test'), (1, 0.4, 'Test'), (1, 0.2, 'Test'),
                         (2, 0.3, 'Test')], tp.dwells
    stats = P.statistics(tp)
    close(stats['dwell_time'], 1.0)
    close(stats['time'], stats['cut_time'] + stats['rapid_time'] + 1.0)
    assert stats['moves'] == 2
    close(stats['per_op'][0]['time'], stats['time'])
    cursor = P.Playback(tp)
    close(cursor.advance(0.05), 0)
    close(cursor.remaining, 0.05)
    close(cursor.advance(4.15), 0.5)
    close(cursor.remaining, 0.3)
    close(cursor.advance(0.4), 0.5)
    close(cursor.remaining, 0.1)
    close(cursor.advance(0.9), 0.6)
    close(cursor.advance(100), 1)
    cursor.seek(0.5)
    close(cursor.advance(0.2, speed=2), 0.5)
    close(cursor.advance(0.5, speed=2), 0.6)
    cursor.seek(0.6)
    close(cursor.advance(0.8), 0.7)
    # No dwell controls retain the original 8-second overview.
    plain = P.Toolpath()
    plain.moves = tp.moves
    close(P.Playback(plain).advance(4), 0.5)
    close(P.Playback(plain).advance(0.04), 0.005)
    print('PASS actual dwell positions/counts, time totals, consecutive holds, speed and seeking')

    sys.argv = ['ncam.py', '-c', 'lathe']
    import ncam  # noqa: F401
    from gi.repository import Gtk
    from ncam_preview_ui import PreviewPane
    pane = PreviewPane(ini_path=None)
    win = Gtk.OffscreenWindow()
    win.add(pane.box)
    win.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration()
    pane.toolpath = tp
    pane.speed = 1
    pane.sim_t = 0
    pane._playback = None
    assert pane._sim_tick()
    close(pane.sim_t, 0)
    close(pane._playback.remaining, 0.06)
    assert 'Dwell: 0.06 s remaining' in pane.status.get_text(), pane.status.get_text()
    pane._stop_sim()
    remaining = pane._playback.remaining
    pane._on_play(None)
    close(pane._playback.remaining, remaining)
    pane._stop_sim()
    pane._sim_tick()
    close(pane.sim_t, 0)
    close(pane._playback.remaining, 0.02)
    assert 'Dwell: 0.02 s remaining' in pane.status.get_text(), pane.status.get_text()
    pane.sim_scale.set_value(0.75)
    close(pane.sim_t, 0.75)
    assert pane._sim_tick()
    close(pane.sim_t, 0.755)
    assert 'Dwell:' not in pane.status.get_text(), pane.status.get_text()
    pane._on_stop(None)
    assert pane._playback is None and pane.sim_t == 0
    assert 'Dwell:' not in pane.status.get_text(), pane.status.get_text()
    pane._sim_tick()
    close(pane.sim_t, 0)
    close(pane._playback.remaining, 0.06)
    pane.sim_t = 1
    pane._playback = P.Playback(tp, 1)
    pane._playback.advance(0.1)
    pane._on_play(None)
    close(pane.sim_t, 1)
    close(pane._playback.remaining, 0.2)
    pane._stop_sim()
    win.destroy()
    print('PASS GTK Play pauses, pause/resume retains hold, scrub skips old waits, Stop rewinds')
    print('PASS small stop dots drawn with visible moves and live dwell countdown at fixed slider')
    print('ARTIFACTS', root)


if __name__ == '__main__':
    main()
