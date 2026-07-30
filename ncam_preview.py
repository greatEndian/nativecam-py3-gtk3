#!/usr/bin/env python3
# coding: utf-8
"""NativeCAM's own toolpath preview: run the interpreter, draw the result.

Deliberately imports nothing from ncam - like lathe_sections.py - so it stays
unit-testable with plain python3 and cannot create a circular import.

WHY THE INTERPRETER, AND NOT A TEXT PARSE
-----------------------------------------
ncam.ngc is almost entirely subroutine calls. A representative generated file
has 32 `CALL` lines against 20 literal G moves, in 787 lines: the toolpath does
not exist in the text at all, only in what the calls expand to. Anything that
reads the file and looks for G1/G2/G3 would draw a nearly empty picture and look
like it was working.

So this runs the real LinuxCNC interpreter - but in a SUBPROCESS, via the
`rs274` batch interpreter, not in this process.

That is a deliberate reversal. The first cut of this module used `gcode.parse`
in-process with an `rs274.glcanon.GLCanon` collector, the way AXIS previews, and
it **segfaulted** on the first real generated file. `gcode` is a C extension, and
NativeCAM runs embedded inside AXIS: an in-process crash does not just lose the
preview, it takes the machine-control GUI down with it, potentially mid-job. A
subprocess that dies costs one failed preview and an error message.

The cost of the subprocess route is that rs274's canon dump prints `N.....`
instead of line numbers, so segments cannot be mapped back to source lines. That
is affordable: the running-line highlight comes from `linuxcnc.stat().current_line`,
not from the parsed path.

NEVER POINT THE INTERPRETER AT THE LIVE .var
--------------------------------------------
It is rewritten by the running GUI, a crashed run can corrupt real machine
offsets, and a half-written copy makes the interpreter abort at `T<n> M6` with
no error at all. AXIS copies it to a temp file before previewing and so does
this. The tests assert the live file's checksum is unchanged across a parse.

The canon deliberately does NOT depend on a running LinuxCNC: NativeCAM also
runs standalone, and Regenerate is supposed to work with no machine attached.
Tools therefore report zero length offsets, which previews the PROGRAMMED path
in part coordinates - which is what you want to look at when checking a shape.
"""
import os
import re
import shutil
import subprocess
import tempfile


class Toolpath(object):
    """What came out of one interpreter run."""

    def __init__(self):
        self.feeds = []        # [(lineno, (x,y,z), (x,y,z))]
        self.rapids = []       # same shape
        self.error = None      # human-readable, or None
        self.min = None        # (x,y,z) or None when there is no motion
        self.max = None

    @property
    def empty(self):
        return not self.feeds and not self.rapids

    def extents(self, plane='ZX'):
        """(a_min, a_max, b_min, b_max) in the two plotted axes, or None."""
        if self.min is None:
            return None
        ia, ib = _plane_indices(plane)
        return (self.min[ia], self.max[ia], self.min[ib], self.max[ib])


def _plane_indices(plane):
    # lathe plots Z across and X down, as AXIS draws it; mill plots X and Y
    return (2, 0) if plane == 'ZX' else (0, 1)


def ini_value(ini_path, section, key, default=None):
    """One value out of a LinuxCNC ini, without needing the linuxcnc module."""
    want_sec, cur = section.upper(), None
    try:
        with open(ini_path, errors='replace') as f:
            for line in f:
                s = line.split('#')[0].split(';')[0].strip()
                if s.startswith('[') and s.endswith(']'):
                    cur = s[1:-1].strip().upper()
                elif cur == want_sec and '=' in s:
                    k, v = s.split('=', 1)
                    if k.strip().upper() == key.upper():
                        return v.strip()
    except OSError:
        pass
    return default


def _scratch_parameter_file(ini_path, tmpdir):
    """A COPY of the ini's var file - never the live one. See module docstring."""
    rel = ini_value(ini_path, 'RS274NGC', 'PARAMETER_FILE')
    if not rel:
        return None
    src = rel if os.path.isabs(rel) else os.path.join(os.path.dirname(ini_path), rel)
    dst = os.path.join(tmpdir, os.path.basename(src))
    if os.path.exists(src):
        try:
            shutil.copy(src, dst)
        except OSError:
            return None
    else:
        open(dst, 'w').close()
    return dst


def _canon_dump(path, ini_path, tmpdir):
    """rs274's canon output for `path`, or (None, error).

    Mirrors the invocation the repo's own verification tooling has been using
    all along - see .claude/skills/lathe-gcode-verify/scripts/parse_rs274.py.
    Three details in it are load-bearing:

      -b   block delete ON. The generated file guards itself with a
           `/ o<safety_9999> repeat [1000] / M123 / M0` block; without -b the
           interpreter walks into that M0 and waits on stdin forever.
      -g   batch mode, so it never prompts.
      -v   a COPY of the var file, never the live one.

    cwd must be the ini's directory: SUBROUTINE_PATH and friends are relative
    to it, and this file is almost nothing but subroutine calls.
    """
    out_path = os.path.join(tmpdir, 'canon.out')
    cmd = ['rs274', '-b', '-g']
    if ini_path:
        cmd += ['-i', os.path.abspath(ini_path)]
        var = _scratch_parameter_file(ini_path, tmpdir)
        if var:
            cmd += ['-v', var]
    cmd += [os.path.abspath(path), out_path]
    cwd = os.path.dirname(os.path.abspath(ini_path or path))
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                             timeout=120)
    except FileNotFoundError:
        return None, 'rs274 is not installed'
    except subprocess.TimeoutExpired:
        return None, 'the interpreter did not finish within 120 s'
    if not os.path.exists(out_path):
        return None, (res.stderr or res.stdout or 'rs274 produced no output').strip()
    with open(out_path, errors='replace') as f:
        return f.read(), None


_RE = {
    'feed': re.compile(r'STRAIGHT_FEED\(([^)]*)\)'),
    'rapid': re.compile(r'STRAIGHT_TRAVERSE\(([^)]*)\)'),
    'arc': re.compile(r'ARC_FEED\(([^)]*)\)'),
}


def parse_program(path, ini_path=None):
    """Run the interpreter over `path` and collect the toolpath.

    Returns a Toolpath. Failures land in `.error` rather than raising, and the
    interpreter runs in its own process, so neither a bad file nor a crashing
    interpreter can take the GUI down. Segments carry no line number - rs274's
    dump prints `N.....` - so the lineno slot is always None.
    """
    tp = Toolpath()
    if not path or not os.path.isfile(path):
        tp.error = 'no such file: %s' % path
        return tp

    tmpdir = tempfile.mkdtemp(prefix='ncam_preview_')
    try:
        canon, err = _canon_dump(path, ini_path, tmpdir)
        if canon is None:
            tp.error = err
            return tp

        pos = None
        for line in canon.splitlines():
            m = _RE['feed'].search(line)
            kind = 'feed'
            if not m:
                m = _RE['rapid'].search(line)
                kind = 'rapid'
            if m:
                v = [float(x) for x in m.group(1).split(',')[:3]]
                nxt = (v[0], v[1], v[2])
                if pos is not None:
                    (tp.feeds if kind == 'feed' else tp.rapids).append(
                        (None, pos, nxt))
                pos = nxt
                continue
            m = _RE['arc'].search(line)
            if m:
                v = [float(x) for x in m.group(1).split(',')]
                # G18 lathe canon order:
                #   ARC_FEED(first_end=Z, second_end=X, first_centre=Z,
                #            second_centre=X, rotation, ...)
                # Taking only the endpoint would draw every radius as its
                # chord - on a 15 mm fillet that is millimetres of error in a
                # picture whose whole job is showing the shape - so the arc is
                # walked properly.
                nxt = (v[1], pos[1] if pos else 0.0, v[0])
                if pos is not None:
                    tp.feeds.extend(_walk_arc(pos, nxt, v[2], v[3], v[4]))
                pos = nxt
                continue

        pts = [p for seg in (tp.feeds + tp.rapids) for p in (seg[1], seg[2])]
        if pts:
            tp.min = tuple(min(p[i] for p in pts) for i in range(3))
            tp.max = tuple(max(p[i] for p in pts) for i in range(3))
        if tp.empty:
            tp.error = tp.error or 'the program produced no motion'
        return tp
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


ARC_SAG = 0.02          # mm of chord error allowed when splitting an arc


def _walk_arc(start, end, zc, xc, rot, sag=ARC_SAG):
    """An arc as a list of straight segments, subdivided under a sagitta bound.

    start/end are (x, y, z); the centre and rotation come from the canon call.
    `rot` is positive counter-clockwise, negative clockwise, and its sign is
    what decides which way round the circle the tool actually goes - taking the
    short way regardless would flip any arc over 180 degrees.
    """
    import math
    r = math.hypot(start[0] - xc, start[2] - zc)
    if r < 1e-9:
        return [(None, start, end)]
    a0 = math.atan2(start[0] - xc, start[2] - zc)
    a1 = math.atan2(end[0] - xc, end[2] - zc)
    if rot > 0:
        while a1 <= a0:
            a1 += 2 * math.pi
    else:
        while a1 >= a0:
            a1 -= 2 * math.pi
    sweep = a1 - a0
    step = 2.0 * math.acos(max(1.0 - sag / r, -1.0)) if r > sag else abs(sweep)
    n = max(int(math.ceil(abs(sweep) / max(step, 1e-6))), 1)
    out, prev = [], start
    for i in range(1, n + 1):
        a = a0 + sweep * i / n
        p = (xc + r * math.sin(a), start[1], zc + r * math.cos(a))
        out.append((None, prev, p))
        prev = p
    return out


def decimate(segments, tol=1e-4):
    """Drop segments shorter than tol, and merge runs going the same way.

    A CAM-mode polyline has been measured at 55,460 canon operations. Handing
    that to Cairo on every expose is what turns a preview into a slideshow.
    """
    out = []
    for lineno, a, b in segments:
        if out:
            plineno, pa, pb = out[-1]
            if pb == a and plineno == lineno and _collinear(pa, pb, b, tol):
                out[-1] = (plineno, pa, b)
                continue
        if _dist2(a, b) < tol * tol:
            continue
        out.append((lineno, a, b))
    return out


def _dist2(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3))


def _collinear(a, b, c, tol):
    # cross product of (b-a) and (c-b) small in every component
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - b[i] for i in range(3)]
    cx = (u[1] * v[2] - u[2] * v[1],
          u[2] * v[0] - u[0] * v[2],
          u[0] * v[1] - u[1] * v[0])
    return all(abs(t) <= tol for t in cx)


# ---------------------------------------------------------------------------
# drawing
#
# Cairo only - no GTK - so the renderer can be exercised headlessly onto an
# ImageSurface, which is how it is tested. The widget that owns a DrawingArea
# lives in ncam_preview_ui.py.
# ---------------------------------------------------------------------------
COL = {
    'bg':      (0.12, 0.12, 0.14),
    'stock':   (0.32, 0.30, 0.26),
    'feed':    (0.36, 0.85, 0.40),
    'rapid':   (0.45, 0.45, 0.52),
    'axis':    (0.55, 0.40, 0.40),
    'text':    (0.80, 0.80, 0.84),
}


def _fit(tp, stock, plane, width, height, margin):
    """Scale and offset that fit the path - and the stock - in the widget."""
    ext = tp.extents(plane)
    if ext is None and not stock:
        return None
    a0, a1, b0, b1 = ext if ext else (0.0, 1.0, 0.0, 1.0)
    if stock:
        sa0, sa1, sb0, sb1 = stock
        if ext is None:
            a0, a1, b0, b1 = sa0, sa1, sb0, sb1
        else:
            # Fit the TOOLPATH, and take only the stock's radial extent. Bar
            # stock is routinely far longer than the part - the demo workpiece
            # is 254 mm for a 70 mm part - and fitting their union squeezes the
            # part into a fifth of the pane, which is the one thing the plot
            # exists to show. The bar simply runs off the edge instead, which
            # is what it does in reality.
            b0, b1 = min(b0, sb0), max(b1, sb1)
    da, db = max(a1 - a0, 1e-6), max(b1 - b0, 1e-6)
    s = min((width - 2 * margin) / da, (height - 2 * margin) / db)
    # centre what is left over
    ox = margin + ((width - 2 * margin) - da * s) / 2.0 - a0 * s
    oy = margin + ((height - 2 * margin) - db * s) / 2.0 - b0 * s
    return s, ox, oy


def draw_toolpath(cr, width, height, tp, plane='ZX', stock=None, margin=10,
                  view=None):
    """Render a Toolpath onto a cairo context sized width x height.

    stock is (a_min, a_max, b_min, b_max) in the same two plotted axes, or None.

    On a lathe this plots Z across and X DOWNWARD, which is how AXIS draws it
    and how the tool-orientation figure in this project already draws it. Using
    the mathematical convention instead would mirror the part vertically and
    quietly disagree with every other picture the operator sees.
    """
    cr.set_source_rgb(*COL['bg'])
    cr.paint()

    fit = _fit(tp, stock, plane, width, height, margin)
    if fit is None:
        _centre_text(cr, width, height, tp.error or 'nothing to show')
        return
    s, ox, oy = fit
    if view is not None:
        # zoom about the widget centre and then translate: the pane keeps
        # showing whatever was in the middle as the scale changes, which is
        # what makes scroll-to-zoom feel like it is zooming rather than
        # sliding the drawing off the edge
        cxw, cyw = width / 2.0, height / 2.0
        s2 = s * view.scale
        ox = cxw + (ox - cxw) * view.scale + view.dx
        oy = cyw + (oy - cyw) * view.scale + view.dy
        s = s2
    ia, ib = _plane_indices(plane)

    def pt(p):
        return (p[ia] * s + ox, p[ib] * s + oy)

    if stock:
        sa0, sa1, sb0, sb1 = stock
        cr.set_source_rgba(*(COL['stock'] + (0.55,)))
        cr.rectangle(sa0 * s + ox, sb0 * s + oy,
                     (sa1 - sa0) * s, (sb1 - sb0) * s)
        cr.fill()

    # the spindle centre line, so a lathe plot reads as a lathe plot
    if plane == 'ZX':
        cr.set_source_rgb(*COL['axis'])
        cr.set_line_width(1.0)
        cr.set_dash([6.0, 4.0])
        cr.move_to(0, oy)
        cr.line_to(width, oy)
        cr.stroke()
        cr.set_dash([])

    cr.set_line_width(1.0)
    cr.set_source_rgb(*COL['rapid'])
    cr.set_dash([3.0, 3.0])
    for _n, a, b in tp.rapids:
        cr.move_to(*pt(a))
        cr.line_to(*pt(b))
    cr.stroke()
    cr.set_dash([])

    cr.set_line_width(1.6)
    cr.set_source_rgb(*COL['feed'])
    for _n, a, b in tp.feeds:
        cr.move_to(*pt(a))
        cr.line_to(*pt(b))
    cr.stroke()

    if tp.error:
        _centre_text(cr, width, height * 1.85, tp.error)


def _centre_text(cr, width, height, text):
    cr.set_source_rgb(*COL['text'])
    cr.select_font_face('Sans')
    cr.set_font_size(11)
    ext = cr.text_extents(text)
    cr.move_to(max((width - ext.width) / 2.0, 4), height / 2.0)
    cr.show_text(text)


class View(object):
    """Zoom and pan on top of the fit-to-content transform.

    Kept as a plain object with no GTK in it so the transform can be tested
    without a display. scale 1.0 with no offset is exactly the fitted view,
    which is what "reset" restores and what the pane starts in.
    """

    MIN, MAX = 0.05, 200.0

    def __init__(self):
        self.reset()

    def reset(self):
        self.scale = 1.0
        self.dx = 0.0
        self.dy = 0.0

    @property
    def fitted(self):
        return (abs(self.scale - 1.0) < 1e-9
                and abs(self.dx) < 1e-9 and abs(self.dy) < 1e-9)

    def zoom_at(self, factor, px, py, width, height):
        """Zoom by `factor` keeping the point under (px, py) still.

        Anchoring on the pointer is the whole difference between zooming and
        merely scaling: without it the feature being examined slides away
        exactly when it is being looked at.
        """
        new = max(self.MIN, min(self.MAX, self.scale * factor))
        if new == self.scale:
            return
        f = new / self.scale
        cx, cy = width / 2.0, height / 2.0
        # the pointer, expressed relative to the centre, has to map to itself
        self.dx = px - cx - (px - cx - self.dx) * f
        self.dy = py - cy - (py - cy - self.dy) * f
        self.scale = new

    def pan(self, ddx, ddy):
        self.dx += ddx
        self.dy += ddy
