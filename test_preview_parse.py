#!/usr/bin/env python3
# coding: utf-8
"""Checks the toolpath parser behind NativeCAM's preview.

Standalone, like the other test_*.py here - run it directly, no pytest.

The thing that makes this parser worth having, and the thing most likely to
silently rot, are the same: ncam.ngc has almost no literal motion in it. The
toolpath lives inside o<...> subroutine calls. So the tests below are built
around proving the INTERPRETER is doing the work:

  - a file whose only motion is inside a subroutine call, with not one literal
    G1 in it, must still produce a toolpath. A text scanner scores zero here.
  - a file whose G-code sits inside a subroutine that is never called must
    produce NOTHING. A text scanner scores highly here, and would be wrong.

Together those two pin the parser between the two failure modes. Either one
alone can be passed by a broken implementation.

Also checked: the live .var is never touched - the interpreter rewrites its
parameter file, and pointing it at the real one can corrupt machine offsets.
"""
import hashlib
import math
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ncam_preview as P  # noqa: E402

INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


HEADER = """G21
G18 G7 G90 G94 G54
#<_diameter_mode> = 2
"""


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, 'w') as f:
        f.write(text)
    return p


def main():
    if not os.path.isfile(INI):
        print('SKIP  demo config not present at %s' % INI)
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    d = tempfile.mkdtemp(prefix='preview_test_')

    # --- 1. motion that exists ONLY inside a subroutine ---------------------
    # not a single literal G1 in the calling file; a text parser sees nothing
    # The subroutine is defined in the same file because SUBROUTINE_PATH points
    # at the config's own lib dirs, not at a temp directory. That costs nothing
    # here: the pair that matters is this file against the identical file with
    # the CALL removed, below. The only difference between them is the call, so
    # the only thing that can explain a toolpath appearing is expansion.
    body = """o<movesub> sub
	G1 X20 Z-10 F100
	G1 X30 Z-20
o<movesub> endsub
"""
    caller = write(d, 'caller.ngc', HEADER + 'G0 X40 Z2\n' + body
                   + 'o<movesub> CALL\nM2\n')
    cut = re.compile(r'^\s*G0?[123](\.\d)?\b')
    with open(caller) as f:
        outside = [ln for ln in f
                   if cut.match(ln) and not ln.startswith('\t')]
    check('every cutting move in the caller is inside the subroutine',
          not outside,
          'these are at top level: %s' % [ln.strip() for ln in outside])

    tp = P.parse_program(caller, INI)
    check('a call-only program still yields a toolpath',
          tp.error is None and len(tp.feeds) >= 2,
          'error=%s feeds=%d - the interpreter is not being run'
          % (tp.error, len(tp.feeds)))

    # and the geometry is the subroutine's, not something invented.
    # NOTE the header is G7 - DIAMETER mode - and canon always reports RADIUS.
    # So the sub's X20/X30 and the approach's X40 are diameters, and the X
    # extents are their halves: 10 to 20. Expecting 30 here is the same
    # diameter-vs-radius slip that this project keeps having to relearn.
    if tp.feeds:
        ext = tp.extents('ZX')
        check('its extents match the subroutine geometry, in radius',
              ext is not None and abs(ext[0] - (-20.0)) < 1e-6
              and abs(ext[2] - 10.0) < 1e-6 and abs(ext[3] - 20.0) < 1e-6,
              'got %s, expected z_min -20 and x 10..20' % (ext,))

    # --- 2. G-code that is never called must NOT appear --------------------
    # byte-for-byte the caller above, minus the one CALL line
    dead = write(d, 'dead.ngc', HEADER + 'G0 X40 Z2\n' + body + 'M2\n')
    tp2 = P.parse_program(dead, INI)
    check('G-code inside an uncalled subroutine produces no motion',
          not tp2.feeds,
          '%d feed(s) - the parser is matching text, not interpreting'
          % len(tp2.feeds))

    # --- 3. a broken file reports, and does not raise ----------------------
    bad = write(d, 'bad.ngc', HEADER + 'G1 X[ Z-1\nM2\n')
    tp3 = P.parse_program(bad, INI)
    check('a malformed program returns an error instead of raising',
          tp3.error is not None, 'error was None')
    check('and returns no toolpath with it', tp3.empty)

    # a missing file is a report, not a traceback
    tp4 = P.parse_program(os.path.join(d, 'nope.ngc'), INI)
    check('a missing file is reported too', tp4.error is not None)

    # --- 4. the live .var must be untouched --------------------------------
    var_rel = P.ini_value(INI, 'RS274NGC', 'PARAMETER_FILE')
    var = os.path.join(os.path.dirname(INI), var_rel) if var_rel else None
    if var and os.path.isfile(var):
        def digest():
            with open(var, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        before = digest()
        P.parse_program(caller, INI)
        check('the live .var is byte-identical after a parse', digest() == before,
              'the interpreter wrote to the real parameter file')
    else:
        print('SKIP  no PARAMETER_FILE to checksum')

    # --- 5. arcs are subdivided, not drawn as their chord ------------------
    arc = write(d, 'arc.ngc', HEADER + """G0 X40 Z2
G1 X40 Z0 F100
G3 X20 Z-10 I0 K-10
M2
""")
    tp5 = P.parse_program(arc, INI)
    check('an arc becomes many segments, not one chord',
          len(tp5.feeds) > 5,
          '%d segment(s) - a quarter arc drawn as a chord' % len(tp5.feeds))
    if len(tp5.feeds) > 2:
        # the decisive property, and one that needs no assumption about
        # diameter mode or where I/K put the centre: an arc BULGES away from
        # the straight line between its ends. A chord does not.
        arc_segs = tp5.feeds[1:]
        a, b = arc_segs[0][1], arc_segs[-1][2]
        chord = math.hypot(b[0] - a[0], b[2] - a[2])
        worst = 0.0
        for _n, _s, p in arc_segs:
            if chord > 1e-9:
                dev = abs((p[0] - a[0]) * (b[2] - a[2])
                          - (p[2] - a[2]) * (b[0] - a[0])) / chord
                worst = max(worst, dev)
        check('and the sampled arc bulges off its chord', worst > 0.5,
              'max deviation %.4f mm - it is being drawn as a straight chord'
              % worst)

    # --- 6. decimate must not move anything --------------------------------
    dec = P.decimate(tp.feeds)
    check('decimation keeps the path endpoints',
          dec and dec[0][1] == tp.feeds[0][1] and dec[-1][2] == tp.feeds[-1][2])

    shutil.rmtree(d, ignore_errors=True)

    test_view()
    test_walk()

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Preview parser behaves.')

def test_walk():
    """Walking the toolpath, which the simulation is built on.

    The parser originally kept feeds and rapids in two separate lists. That
    draws perfectly well and cannot be walked at all, because program order is
    gone - so the first check here is that order survives.
    """
    tp = P.Toolpath()
    tp.moves = [('rapid', (0.0, 0.0, 0.0), (0.0, 0.0, -10.0)),
                ('feed',  (0.0, 0.0, -10.0), (10.0, 0.0, -10.0)),
                ('rapid', (10.0, 0.0, -10.0), (10.0, 0.0, 0.0))]
    check('program order is preserved through the move list',
          [k for k, _a, _b in tp.moves] == ['rapid', 'feed', 'rapid'])
    check('feeds/rapids still read back correctly',
          len(tp.feeds) == 1 and len(tp.rapids) == 2)

    acc, total = P.path_lengths(tp)
    check('total length is the sum of the segments', abs(total - 30.0) < 1e-9,
          'got %.6f' % total)

    # the ends, and a point whose answer can be worked out by hand
    p0, i0, k0 = P.position_at(tp, 0.0, acc, total)
    p1, i1, k1 = P.position_at(tp, 1.0, acc, total)
    check('t=0 is the start of the first move', p0 == (0.0, 0.0, 0.0))
    check('t=1 is the end of the last move', p1 == (10.0, 0.0, 0.0), str(p1))
    pm, im, km = P.position_at(tp, 0.5, acc, total)
    check('t=0.5 is halfway along by DISTANCE, in the middle move',
          km == 'feed' and abs(pm[0] - 5.0) < 1e-9 and abs(pm[2] + 10.0) < 1e-9,
          'got %s in a %s move' % (pm, km))

    # rapids are included in the walk, or the tool teleports between cuts
    check('rapids are part of the walk', k0 == 'rapid')

    # an empty path must not raise
    empty = P.Toolpath()
    pe, ie, ke = P.position_at(empty, 0.5)
    check('an empty toolpath yields no position, and does not raise', pe is None)


def test_view():
    """The zoom/pan transform, headlessly.

    Pointer-anchored zoom is the difference between zooming and merely scaling:
    without the anchor the feature under the cursor slides away exactly when it
    is being looked at. That is checked here by mapping a point through the
    same expression draw_toolpath uses and requiring it to stay put.
    """
    W, H = 400.0, 300.0

    def screen(v, ox, oy, s, wx, wy):
        """Where world (wx, wy) lands, mirroring draw_toolpath's transform."""
        cx, cy = W / 2.0, H / 2.0
        s2 = s * v.scale
        ox2 = cx + (ox - cx) * v.scale + v.dx
        oy2 = cy + (oy - cy) * v.scale + v.dy
        return wx * s2 + ox2, wy * s2 + oy2

    v = P.View()
    check('a fresh view is the fitted view', v.fitted)

    # a world point that currently sits under the pointer must stay there
    ox, oy, s = 40.0, 25.0, 3.0
    px, py = 275.0, 190.0
    wx, wy = (px - ox) / s, (py - oy) / s          # world point under (px,py)
    v.zoom_at(1.15 ** 4, px, py, W, H)
    sx, sy = screen(v, ox, oy, s, wx, wy)
    check('zoom keeps the point under the pointer still',
          abs(sx - px) < 1e-6 and abs(sy - py) < 1e-6,
          'moved to (%.4f, %.4f) from (%.1f, %.1f)' % (sx, sy, px, py))
    check('and the scale actually changed', v.scale > 1.0, 'scale %.4f' % v.scale)
    check('a zoomed view no longer reports as fitted', not v.fitted)

    # zooming out by the same amount returns to the fitted view
    v2 = P.View()
    v2.zoom_at(2.0, 111.0, 77.0, W, H)
    v2.zoom_at(0.5, 111.0, 77.0, W, H)
    check('zoom in then out about the same point returns to fit',
          v2.fitted, 'scale %.6f dx %.6f dy %.6f' % (v2.scale, v2.dx, v2.dy))

    # limits, so a stray touchpad gesture cannot lose the drawing entirely
    v3 = P.View()
    for _ in range(400):
        v3.zoom_at(2.0, 200.0, 150.0, W, H)
    check('zoom is clamped at the top', v3.scale <= P.View.MAX + 1e-9,
          'scale %.4f' % v3.scale)
    for _ in range(800):
        v3.zoom_at(0.5, 200.0, 150.0, W, H)
    check('zoom is clamped at the bottom', v3.scale >= P.View.MIN - 1e-9,
          'scale %.6f' % v3.scale)

    # pan then reset
    v4 = P.View()
    v4.pan(30.0, -12.0)
    check('pan moves the view', not v4.fitted)
    v4.reset()
    check('reset restores the fitted view', v4.fitted)

if __name__ == '__main__':
    main()
