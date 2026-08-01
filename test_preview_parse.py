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

    # A file that fails PART WAY is the dangerous one. rs274 exits non-zero,
    # but it has already written a canon file, and that file is well-formed -
    # the toolpath simply stops. The exit code used to be ignored, so the pane
    # drew the truncated path and reported "N cutting moves" underneath it:
    # wrong, and reassuring. This arc's start and end radii do not agree.
    part = write(d, 'part.ngc', HEADER + """G0 X50 Z2
G1 X40 Z-2 F120
G3 X30 Z-10 I0 K-4
G1 Z-40
M2
""")
    tp4b = P.parse_program(part, INI)
    check('a run that fails part way is reported, not silently truncated',
          tp4b.error is not None, 'the partial canon was taken as success')
    check('and says what the interpreter actually complained about',
          tp4b.error and 'adius' in tp4b.error, str(tp4b.error))
    check('while still returning what it got as far as',
          bool(tp4b.moves), 'the partial path is how you find the bad line')

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

    # --- 7. nested markers name a phase INSIDE an operation ----------------
    # The pre-finish contour pass sits inside the polyline feature and shares
    # its feed rate with the roughing levels and its geometry with the finish
    # pass. Both of those were measured as discriminators and both failed, so
    # the marker the subroutine writes is the only thing that separates it.
    marked = write(d, 'marked.ngc', HEADER + """G0 X40 Z2
(begin Lathe Polyline)
G1 X40 Z-1 F100
(begin pre-finish)
G1 X30 Z-5
G3 X20 Z-10 I0 K-5
(end pre-finish)
G1 X20 Z-15
(end Lathe Polyline)
G1 X40 Z-16
M2
""")
    tp6 = P.parse_program(marked, INI)
    feeds6 = [m for m in tp6.moves if m.kind == 'feed']
    pf = [m for m in feeds6 if P.PREFINISH in m.subs]
    check('the nested marker tags the moves inside it',
          len(pf) > 2, '%d tagged of %d feeds' % (len(pf), len(feeds6)))
    check('and the arc inside it is tagged too, segment by segment',
          len([m for m in pf if m.a[2] < -5.0]) > 2,
          'the arc walk drops the phase')
    check('the operation is still the OUTER marker, not the phase',
          all(m.op == 'Lathe Polyline' for m in pf),
          str({m.op for m in pf}))
    check('moves before and after the phase are untagged',
          not P.PREFINISH in feeds6[0].subs
          and not P.PREFINISH in feeds6[-1].subs)
    check('a move outside every marker has no operation and no phase',
          feeds6[-1].op is None and feeds6[-1].subs == ())
    check('has_phase sees it', P.has_phase(tp6.moves))

    # colours: blue only for the phase's CUTS, everything else as before
    check('the phase colour is not the plain feed colour',
          P.phase_colour(pf[0]) == P.COL['prefinish']
          and P.COL['prefinish'] != P.COL['feed'])
    check('moves outside the phase keep the plain feed colour',
          P.phase_colour(feeds6[-1]) == P.COL['feed'])
    rapids6 = [m for m in tp6.moves if m.kind == 'rapid']
    check('rapids are never recoloured by a phase',
          all(P.phase_colour(m) == P.COL['rapid'] for m in rapids6),
          '%d rapid(s)' % len(rapids6))

    # the negative control: the same program without the phase markers must
    # tag nothing and draw exactly as it did before this existed
    plain = write(d, 'plain.ngc', HEADER + """G0 X40 Z2
(begin Lathe Polyline)
G1 X40 Z-1 F100
G1 X30 Z-5
G3 X20 Z-10 I0 K-5
G1 X20 Z-15
(end Lathe Polyline)
M2
""")
    tp7 = P.parse_program(plain, INI)
    check('a program with no phase marker tags nothing',
          not P.has_phase(tp7.moves)
          and all(m.subs == () for m in tp7.moves))
    check('and every one of its feeds keeps the plain colour',
          all(P.phase_colour(m) == P.COL['feed']
              for m in tp7.moves if m.kind == 'feed'))

    # --- 8. the flattened listing ------------------------------------------
    test_flatten(d)

    shutil.rmtree(d, ignore_errors=True)

    test_view()
    test_walk()
    test_tool_and_removal()
    test_comparison()
    test_tagging()

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Preview parser behaves.')

def test_tool_and_removal():
    """The drawn tool's direction, and the material it removes.

    Both had a bug that a picture hides. The tool body was drawn OPPOSITE the
    nose offset, which reads as a mirror image. And the swept disc was placed
    using a NORMALISED orientation vector, where lathe_shapes entries 1-4 are
    raw and sqrt(2) long - so every surface came out R*(1 - 1/sqrt(2)) too
    deep, a constant 0.117 mm that looks like a compensation fault.
    """
    import cairo

    # --- the raw offset, which is the one that matters for geometry --------
    for n in (1, 2, 3, 4):
        check('orientation %d offset is raw sqrt(2), not normalised' % n,
              abs(math.hypot(*P.nose_offset(n)) - math.sqrt(2)) < 1e-12,
              '|%s| = %.6f' % (P.nose_offset(n),
                               math.hypot(*P.nose_offset(n))))
    for n in (5, 6, 7, 8):
        check('orientation %d offset is unit' % n,
              abs(math.hypot(*P.nose_offset(n)) - 1.0) < 1e-12)

    # --- the tool body must lie WITH the nose offset, not opposite it ------
    W = H = 160
    CL = {1: 135, 2: 45, 3: 315, 4: 225, 5: 180, 6: 90, 7: 0, 8: 270}
    for n, cl in CL.items():
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr = cairo.Context(surf)
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        P.draw_tool(cr, (0.0, 0.0, 0.0), 'ZX', 1.0, W / 2.0, H / 2.0,
                    5.0, n, cl, 60.0)
        surf.flush()
        buf, stride = surf.get_data(), surf.get_stride()
        sx = sy = cnt = 0
        for y in range(H):
            for x in range(W):
                o = y * stride + x * 4
                if (abs(buf[o + 2] - 107) < 26 and abs(buf[o + 1] - 102) < 26
                        and abs(buf[o] - 117) < 26):
                    sx += x
                    sy += y
                    cnt += 1
        if not cnt:
            check('orientation %d draws a tool body' % n, False)
            continue
        vz, vx = sx / cnt - W / 2.0, sy / cnt - H / 2.0
        ez, ex = P.tool_direction(n)
        dot = (vz * ez + vx * ex) / max(math.hypot(vz, vx), 1e-9)
        check('orientation %d draws the body toward the nose, not mirrored' % n,
              dot > 0.9, 'body centroid (%+.1f,%+.1f) vs offset (%+.2f,%+.2f)'
              % (vz, vx, ez, ex))

    # --- removal lands on the programmed surface --------------------------
    # a straight cut along Z at radius 20, tool nose 0.4 on a corner
    # orientation. The material left behind must be r20, not r20 - 0.117.
    R, orient = 0.4, 2
    fld = P.StockField(-50.0, 0.0, 0.0, 30.0,
                       P.StockField.columns_for(-50.0, 0.0, R))
    fld.cut_move((20.0, 0.0, -5.0), (20.0, 0.0, -45.0), R, P.nose_offset(orient))
    for z in (-10.0, -25.0, -40.0):
        r = fld.outer[fld._col(z)]
        check('material at Z%.0f is left at the programmed radius' % z,
              abs(r - 20.0) < 0.01, 'r %.4f, out by %+.4f' % (r, r - 20.0))
    check('material beyond the cut is untouched',
          abs(fld.outer[fld._col(-2.0)] - 30.0) < 1e-9)

    # and the normalised vector - the bug - must be measurably different, or
    # the check above would pass either way
    bad = P.StockField(-50.0, 0.0, 0.0, 30.0,
                       P.StockField.columns_for(-50.0, 0.0, R))
    u = P.tool_direction(orient)
    bad.cut_move((20.0, 0.0, -5.0), (20.0, 0.0, -45.0), R, u)
    err = abs(bad.outer[bad._col(-25.0)] - 20.0)
    check('the normalised offset really does cut too deep',
          err > 0.1, 'only %.4f off - the two would be indistinguishable' % err)

    # --- material comes off progressively, not a whole move at a time -----
    # Cutting a move whole the instant the tool reached it made an entire pass
    # of material vanish at once, so the tool appeared to follow a cut somebody
    # else had already made. What is removed must track where the tool IS.
    part = P.StockField(-50.0, 0.0, 0.0, 30.0,
                        P.StockField.columns_for(-50.0, 0.0, R))
    a, b = (20.0, 0.0, -5.0), (20.0, 0.0, -45.0)
    half = (20.0, 0.0, -25.0)             # halfway along the move
    part.cut_move(a, half, R, P.nose_offset(orient))
    cut_r = part.outer[part._col(-15.0)]
    uncut_r = part.outer[part._col(-35.0)]
    check('material behind the tool is removed',
          abs(cut_r - 20.0) < 0.01, 'r %.4f' % cut_r)
    check('material ahead of the tool is still there',
          abs(uncut_r - 30.0) < 1e-9,
          'r %.4f - the whole move was cut at once' % uncut_r)
    # and finishing the move removes the rest
    part.cut_move(a, b, R, P.nose_offset(orient))
    check('completing the move removes the rest',
          abs(part.outer[part._col(-35.0)] - 20.0) < 0.01)
    # re-cutting is idempotent, which is what makes re-applying the growing
    # partial every frame safe
    before = list(part.outer)
    part.cut_move(a, b, R, P.nose_offset(orient))
    check('re-cutting the same metal changes nothing', part.outer == before)

    # finer nose -> finer columns, or the circle is quantised into the surface
    check('column count scales with the nose radius',
          P.StockField.columns_for(-100.0, 0.0, 0.1)
          > P.StockField.columns_for(-100.0, 0.0, 0.8))


def test_walk():
    """Walking the toolpath, which the simulation is built on.

    The parser originally kept feeds and rapids in two separate lists. That
    draws perfectly well and cannot be walked at all, because program order is
    gone - so the first check here is that order survives.
    """
    tp = P.Toolpath()
    tp.moves = [P.Move('rapid', (0.0, 0.0, 0.0), (0.0, 0.0, -10.0),
                       'Op', 1, None),
                P.Move('feed', (0.0, 0.0, -10.0), (10.0, 0.0, -10.0),
                       'Op', 1, None),
                P.Move('rapid', (10.0, 0.0, -10.0), (10.0, 0.0, 0.0),
                       'Op', 1, None)]
    check('program order is preserved through the move list',
          [m.kind for m in tp.moves] == ['rapid', 'feed', 'rapid'])
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


def test_comparison():
    """Comparison colouring: excess, in tolerance and gouge.

    The classification is a subtraction, so what needs pinning is the DATUM.
    `leftover` is stock deliberately left on the part, and deviations are
    measured from that surface rather than from the model - so a part sitting
    0.5 mm proud is a gouge when nothing was to be left, and exactly on size
    when 0.5 was.
    """
    # r20 flanks with an r25 boss between Z-20 and Z-50, as (z, DIAMETER)
    pts = [(0.0, 40.0), (-20.0, 40.0), (-20.0, 50.0), (-50.0, 50.0),
           (-50.0, 40.0), (-80.0, 40.0)]

    check('target radius on a flank', P.profile_radius_at(-10.0, pts) == 20.0)
    check('target radius on the boss', P.profile_radius_at(-35.0, pts) == 25.0)
    check('a vertical wall takes its OUTER radius',
          P.profile_radius_at(-20.0, pts) == 25.0,
          'got %s - the inner value would under-report a gouge'
          % P.profile_radius_at(-20.0, pts))
    check('off the ends of the profile there is nothing to compare',
          P.profile_radius_at(-90.0, pts) is None)

    # a field deliberately built 0.5 proud, 0.5 deep, and on size
    f = P.StockField(-80.0, 0.0, 0.0, 30.0, columns=400)
    for i in range(f.n):
        z = f.z0 + (i + 0.5) * f.dz
        t = P.profile_radius_at(z, pts)
        if t is None:
            continue
        f.outer[i] = t + (0.5 if z > -30 else (-0.5 if z > -60 else 0.0))

    cls = P.compare_field(f, pts, leftover=0.0, tol=0.01)
    names = {P.UNCUT: 'UNCUT', P.EXCESS: 'EXCESS',
             P.IN_TOL: 'IN_TOL', P.GOUGE: 'GOUGE'}
    for z, want in ((-10.0, P.EXCESS), (-45.0, P.GOUGE), (-70.0, P.IN_TOL)):
        got = cls[f._col(z)]
        check('Z%.0f classifies as %s' % (z, names[want]), got == want,
              'got %s' % names.get(got))

    # the datum moves with leftover: 0.5 proud IS on size when 0.5 was to be left
    cls2 = P.compare_field(f, pts, leftover=0.5, tol=0.01)
    check('leftover shifts the datum, so proud material reads on-size',
          cls2[f._col(-10.0)] == P.IN_TOL,
          'got %s' % names.get(cls2[f._col(-10.0)]))
    check('and a gouge is still a gouge against the shifted datum',
          cls2[f._col(-45.0)] == P.GOUGE)

    # tolerance widens the acceptable band
    f2 = P.StockField(-80.0, 0.0, 0.0, 30.0, columns=400)
    for i in range(f2.n):
        z = f2.z0 + (i + 0.5) * f2.dz
        t = P.profile_radius_at(z, pts)
        if t is not None:
            f2.outer[i] = t + 0.03
    tight = P.compare_field(f2, pts, 0.0, 0.01)
    loose = P.compare_field(f2, pts, 0.0, 0.05)
    check('0.03 proud is excess at 0.01 tolerance',
          tight[f2._col(-10.0)] == P.EXCESS)
    check('and in tolerance at 0.05',
          loose[f2._col(-10.0)] == P.IN_TOL)

    # Bar beyond the part must not be reported as excess, or the untouched
    # length of a long bar drowns the part in colour. The field above spans
    # exactly the profile, so this needs one that runs past it - which is the
    # normal case: the demo workpiece is 254 mm for an 80 mm part.
    long_f = P.StockField(-120.0, 0.0, 0.0, 30.0, columns=600)
    long_cls = P.compare_field(long_f, pts, 0.0, 0.01)
    summary = P.compare_summary(long_cls)
    check('stock off the ends of the profile is UNCUT, not EXCESS',
          summary[P.UNCUT] > 0 and long_cls[long_f._col(-100.0)] == P.UNCUT,
          'summary %s' % {names[k]: v for k, v in summary.items()})
    check('and stock within the profile still compares',
          long_cls[long_f._col(-10.0)] == P.EXCESS,
          'got %s' % names.get(long_cls[long_f._col(-10.0)]))

    # volume: an uncut field has removed nothing
    f3 = P.StockField(-10.0, 0.0, 0.0, 10.0, columns=100)
    rem, start = P.removed_volume(f3)
    check('an uncut field has removed no volume', abs(rem) < 1e-9)
    check('and reports the starting volume', abs(start - math.pi * 100 * 10) < 1.0,
          'got %.1f, expected %.1f' % (start, math.pi * 100 * 10))
    for i in range(f3.n):
        f3.outer[i] = 5.0
    rem2, _s = P.removed_volume(f3)
    check('turning it down to half radius removes three quarters',
          abs(rem2 / start - 0.75) < 1e-6, 'removed %.4f' % (rem2 / start))


def test_flatten(d):
    """The O-code program rewritten as plain G-code, proved by re-running it.

    Reading the output and agreeing with it proves nothing: a flattener can
    look perfectly reasonable and still put an arc round the wrong way, or take
    canon's radius X for a diameter, and the listing would read fine either
    way. So the flattened text goes back through the interpreter and the two
    toolpaths are compared move for move - and because arcs are walked into
    segments before the comparison, a G2 written where a G3 belongs fails on
    the intermediate points even though its endpoints match.
    """
    src = write(d, 'flat_src.ngc', HEADER + """o<shape> sub
	G1 X40 Z-2 F120
	G3 X30 Z-7 I-5 K0
	G1 Z-20
	#<i> = 0
	o<lp> while [#<i> LT 3]
		G1 X[30 + #<i>] Z[-20 - #<i>]
		#<i> = [#<i> + 1]
	o<lp> endwhile
o<shape> endsub
T2 M6
S500 M3
G0 X50 Z2
(begin Turning)
o<shape> CALL
(end Turning)
G0 X60
M5
M2
""")
    tp = P.parse_program(src, INI)
    check('the source program parses at all', tp.error is None and tp.moves,
          str(tp.error))
    flat = tp.flat
    check('a flattened listing comes back with the toolpath', bool(flat))

    # it must be FLAT: no calls, no loops, no expressions, no parameters
    body = [ln for ln in flat.splitlines()
            if ln.strip() and not ln.strip().startswith('(')]
    leftovers = [ln for ln in body
                 if 'o<' in ln or '#' in ln or '[' in ln]
    check('no subroutine, loop or expression survives the flattening',
          not leftovers, str(leftovers[:3]))
    check('the loop is unrolled into its actual moves',
          len([ln for ln in body if 'Z-2' in ln or 'Z-21' in ln]) >= 1,
          'the while body never appears')
    check('the markers survive, so the listing keeps its structure',
          '(begin Turning)' in flat and '(end Turning)' in flat)
    check('the tool change and spindle carry over',
          'T2' in body and 'M6' in body and 'M3' in body and 'S500' in body,
          str(body[:8]))

    # --- the round trip ----------------------------------------------------
    # canon coordinates are ABSOLUTE, so the frame has to be identity for the
    # re-run to reproduce them. That preamble is deliberately not part of the
    # listing itself: it would rewrite the operator's G54 if anyone loaded it.
    run = write(d, 'flat_run.ngc',
                'G10 L2 P1 X0 Y0 Z0\nG92.1\nG54\n' + flat)
    tp2 = P.parse_program(run, INI)
    check('the flattened listing is itself valid G-code',
          tp2.error is None, str(tp2.error))

    # A move to where the tool already is is dropped from the listing - the
    # source program has one, where the loop's first iteration re-commands the
    # position the line before it reached. It is bookkeeping, not motion, so
    # both sides are compared on motion only.
    def real(moves):
        return [m for m in moves
                if max(abs(p - q) for p, q in zip(m.a, m.b)) > 1e-9]
    real1, real2 = real(tp.moves), real(tp2.moves)
    check('the source program does contain a zero-length move',
          len(tp.moves) > len(real1),
          'nothing here exercises the null-move case any more')
    check('and it is not written into the listing',
          len(tp2.moves) == len(real2),
          '%d of %d moves are null' % (len(tp2.moves) - len(real2),
                                       len(tp2.moves)))
    check('the round trip yields the same number of real moves',
          len(real2) == len(real1), '%d vs %d' % (len(real2), len(real1)))
    if len(real2) == len(real1):
        worst, kinds = 0.0, 0
        for m1, m2 in zip(real1, real2):
            if m1.kind != m2.kind:
                kinds += 1
            worst = max(worst, max(abs(p - q) for p, q in
                                   zip(m1.a + m1.b, m2.a + m2.b)))
        check('every move is the same KIND after the round trip', not kinds,
              '%d differ' % kinds)
        check('and lands on the same coordinates', worst < 1e-3,
              'worst difference %.6f mm' % worst)
        # a control on the control: the comparison must be able to see a
        # difference at all, or "worst 0.0" means nothing
        moved = [m._replace(a=(m.a[0] + 1.0, m.a[1], m.a[2]))
                 for m in real2]
        seen = max(abs(p - q) for m1, m2 in zip(real1, moved)
                   for p, q in zip(m1.a + m1.b, m2.a + m2.b))
        check('the comparison notices a 1 mm shift when there is one',
              seen > 0.9, '%.6f' % seen)

    check('X is written as a diameter, not canon\'s radius',
          any('X40' in ln for ln in body),
          'the X40 of the source is not in the listing: %s' % body[:12])


def test_tagging():
    """Operation/tool tags, move categories, and Toolpath Mode."""
    def mv(kind, z0, z1, op, tool):
        return P.Move(kind, (20.0, 0.0, z0), (20.0, 0.0, z1), op, tool, None)

    raw = [mv('rapid', 0, -1, 'A', 1),     # into A
           mv('feed', -1, -2, 'A', 1),     # lead in
           mv('feed', -2, -3, 'A', 1),     # cut
           mv('feed', -3, -4, 'A', 1),     # cut
           mv('feed', -4, -5, 'A', 1),     # lead out
           mv('rapid', -5, -6, 'A', 1),    # link inside A
           mv('feed', -6, -7, 'A', 1),
           mv('rapid', -7, -8, 'B', 2)]    # crosses into B
    tagged = P.categorise(raw)
    cats = [m.cat for m in tagged]
    check('a feed next to a rapid is a lead',
          cats[1] == P.LEAD and cats[4] == P.LEAD, str(cats))
    check('feeds between feeds are cutting moves',
          cats[2] == P.CUT and cats[3] == P.CUT, str(cats))
    check('a rapid inside one operation is a link', cats[5] == P.LINK,
          str(cats))
    check('a rapid crossing operations is a connection', cats[7] == P.CONNECT,
          str(cats))

    tp = P.Toolpath()
    tp.moves = tagged
    check('operations come out in program order', tp.operations == ['A', 'B'],
          str(tp.operations))
    check('tools are collected', tp.tools == [1, 2], str(tp.tools))

    # --- Toolpath Mode -----------------------------------------------------
    n = len(tp.moves)
    idx = 4
    beh = P.visible_moves(tp, P.MODE_BEHIND, idx)
    ahd = P.visible_moves(tp, P.MODE_AHEAD, idx)
    check('Behind and Ahead together cover the path, overlapping at the tool',
          len(beh) + len(ahd) == n + 1, '%d + %d vs %d' % (len(beh), len(ahd), n))
    check('Behind stops at the tool', len(beh) == idx + 1)
    check('Ahead starts at the tool', len(ahd) == n - idx)
    check('All shows everything', len(P.visible_moves(tp, P.MODE_ALL, idx)) == n)
    check('Tail is bounded',
          len(P.visible_moves(tp, P.MODE_TAIL, idx, tail=2)) == 3)
    op_only = P.visible_moves(tp, P.MODE_OPERATION, idx)
    check('Operation shows only the current one',
          all(m.op == 'A' for m in op_only) and len(op_only) == 7,
          '%d moves, ops %s' % (len(op_only), {m.op for m in op_only}))

    # without a tool position every mode collapses to All, which is what an
    # un-played preview should show rather than an empty pane
    check('no tool position means All',
          len(P.visible_moves(tp, P.MODE_BEHIND, None)) == n)

    # category filter
    cuts = P.visible_moves(tp, P.MODE_ALL, idx, show={P.CUT})
    check('the category filter selects only what is asked for',
          all(m.cat == P.CUT for m in cuts) and len(cuts) == 2,
          '%d moves' % len(cuts))

    # palette stability - the same key must keep its colour
    order = ['A', 'B']
    check('palette colours are stable for a key',
          P.palette_colour('A', order) == P.palette_colour('A', order))
    check('and differ between keys',
          P.palette_colour('A', order) != P.palette_colour('B', order))


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
