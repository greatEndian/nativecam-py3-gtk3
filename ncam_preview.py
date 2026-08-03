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
import collections
import math
import os
import re
import shutil
import subprocess
import tempfile
import lathe_comp


# One move. `op` and `tool` are GROUND TRUTH - NativeCAM writes the
# `(begin <Feature>)` markers itself and the tool comes from the interpreter's
# own tool selection. `cat` is INFERRED, and labelled as such wherever it is
# shown: nothing in the generated code marks a lead, so it is deduced from
# where a feed sits relative to the rapids around it.
#
# `subs` holds the markers nested INSIDE the operation, innermost last. A
# sub-phase of one feature - the pre-finish contour pass inside a polyline - is
# not distinguishable any other way: it shares its feed with the roughing
# levels and its geometry with the finish pass, so neither feed rate nor move
# category separates it. Both were measured and both failed. A marker written
# by the subroutine itself is the only ground truth available.
# `feed`, `fmode` and `rpm` are the interpreter's own state at that move, which
# is what makes a time estimate an estimate rather than a guess: on a lathe the
# feed is usually PER REVOLUTION, so distance alone says nothing about time
# until the spindle speed is known too - and under G96 that speed depends on
# the diameter being cut, so it is resolved per move.
Move = collections.namedtuple('Move', 'kind a b op tool cat subs feed fmode rpm',
                              defaults=((), None, 'min', None))

CUT, LEAD, LINK, CONNECT = 'cut', 'lead', 'link', 'connect'

# The sub-phase markers the preview knows about, by the name the .ngc writes.
# Every lathe op that has a finishing pass brackets it, not just the polyline -
# on facing, turning, boring, the tapers and radius_od the finish IS the only
# phase there is to tell apart from the roughing.
PREFINISH = 'pre-finish'
FINISH = 'finish'
PHASES = (PREFINISH, FINISH)


class Toolpath(object):
    """What came out of one interpreter run."""

    def __init__(self):
        # moves are kept in PROGRAM ORDER as (kind, start, end), kind being
        # 'feed' or 'rapid'. Order is what makes a simulation possible at all -
        # feeds and rapids were originally kept in two separate lists, which
        # draws fine and cannot be walked.
        self.moves = []           # [Move]
        self.flat = ''         # the same program as plain G-code, see flatten_canon
        self.error = None      # human-readable, or None
        self.min = None        # (x,y,z) or None when there is no motion
        self.max = None

    @property
    def feeds(self):
        return [(None, m.a, m.b) for m in self.moves if m.kind == 'feed']

    @property
    def rapids(self):
        return [(None, m.a, m.b) for m in self.moves if m.kind == 'rapid']

    @property
    def operations(self):
        """Operation names in program order, without repeats."""
        out = []
        for m in self.moves:
            if m.op and (not out or out[-1] != m.op):
                out.append(m.op)
        return out

    @property
    def tools(self):
        return sorted({m.tool for m in self.moves if m.tool is not None})

    @property
    def empty(self):
        return not self.moves

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
        # -t is NOT optional. Without it rs274 falls back to whatever tool
        # table it finds rather than the ini's, and every #5410 read in the
        # generated file - the whole of nose compensation - runs on the wrong
        # tool. On this config the fallback was mill.tbl's 1/16 end mill, so
        # the preview compensated for a 0.0625 mm nose where the lathe tool is
        # 0.8 mm. The path drawn was not the path the machine would cut.
        tbl = ini_value(ini_path, 'EMCIO', 'TOOL_TABLE')
        if tbl:
            if not os.path.isabs(tbl):
                tbl = os.path.join(os.path.dirname(os.path.abspath(ini_path)),
                                   tbl)
            if os.path.isfile(tbl):
                cmd += ['-t', tbl]
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
        canon = f.read()
    if res.returncode:
        # An interpreter error truncates the canon file and leaves it looking
        # perfectly well-formed - the toolpath simply stops. Ignoring the exit
        # code showed a partial path with a confident "N cutting moves" under
        # it, which is the worst of both: wrong, and reassuring. The partial
        # canon is still returned, because seeing how far it got is how you
        # find the offending line.
        return canon, _rs274_error(res)
    return canon, None


def _rs274_error(res):
    """The useful part of rs274's complaint, on one line."""
    lines = [ln.strip() for ln in
             ((res.stderr or '') + '\n' + (res.stdout or '')).splitlines()
             if ln.strip() and ln.strip() != 'executing']
    return ' | '.join(lines[-2:]) if lines else 'the interpreter failed'


_RE = {
    'feed': re.compile(r'STRAIGHT_FEED\(([^)]*)\)'),
    'rapid': re.compile(r'STRAIGHT_TRAVERSE\(([^)]*)\)'),
    'arc': re.compile(r'ARC_FEED\(([^)]*)\)'),
    'comment': re.compile(r'COMMENT\("(begin|end) ([^"]*)"\)'),
    'tool': re.compile(r'(?:SELECT_TOOL|CHANGE_TOOL)\(([-0-9.]+)\)'),
    'feed_mode': re.compile(r'SET_FEED_MODE\([^,]*,\s*([-0-9.]+)\)'),
    # note: SET_SPINDLE_MODE's arguments are SPACE separated, not comma
    'spindle_mode': re.compile(r'SET_SPINDLE_MODE\(\S*\s+([-0-9.]+)\)'),
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
        tp.error = err          # a run that failed PART WAY still has a path

        pos = None
        stack = []            # nested (begin X) markers; [0] is the operation
        op = None
        subs = ()             # everything below [0], shared by the moves in it
        tool = None
        feed = None           # as commanded, in the current feed mode
        fmode = 'min'         # 'min' = G94 units/min, 'rev' = G95 units/rev
        css = 0.0             # G96 surface speed; 0 means G97 is in force
        css_cap = 0.0         # the D word on G96 - a ceiling on the rpm
        rpm = None            # G97 rpm, or None until the spindle is commanded

        def rpm_for(x):
            """Effective spindle speed at radius `x`."""
            if css <= 0.0:
                return rpm
            d = abs(x) * 2.0
            if d < 1e-6:
                return css_cap or None       # on centre, CSS runs to its cap
            n = css / (math.pi * d)
            return min(n, css_cap) if css_cap > 0 else n

        for line in canon.splitlines():
            m = _RE['comment'].search(line)
            if m:
                # NativeCAM brackets every feature it writes. That makes
                # operation attribution exact rather than inferred - the one
                # thing a CAM that only reads G-code cannot do.
                word, name = m.group(1), m.group(2).strip()
                if word == 'begin':
                    stack.append(name)
                elif stack:
                    if name in stack:
                        del stack[stack.index(name):]
                    else:
                        stack.pop()
                # rebuilt here rather than per move: one tuple object is then
                # shared by every move of the phase instead of one per move
                op = stack[0] if stack else None
                subs = tuple(stack[1:])
                continue
            m = _RE['tool'].search(line)
            if m:
                tool = int(float(m.group(1)))
                continue
            m = _FLAT_RE['feed'].search(line)
            if m:
                f = float(m.group(1))
                feed = f if f > 0 else None
                continue
            m = _RE['feed_mode'].search(line)
            if m:
                fmode = 'rev' if int(float(m.group(1))) == 1 else 'min'
                continue
            m = _RE['spindle_mode'].search(line)
            if m:
                # SET_SPINDLE_MODE carries the G96 rpm CEILING - the D word -
                # and 0 when G97 constant-rpm is in force
                css_cap = float(m.group(1))
                continue
            m = _FLAT_RE['speed'].search(line)
            if m:
                s = float(m.group(1))
                # under G96 this is the surface speed, under G97 the rpm, and
                # nothing in the call says which. The mode that was set
                # immediately before it does.
                if css_cap > 0:
                    css, rpm = s, None
                else:
                    css, rpm = 0.0, s
                continue
            m = _RE['feed'].search(line)
            kind = 'feed'
            if not m:
                m = _RE['rapid'].search(line)
                kind = 'rapid'
            if m:
                v = [float(x) for x in m.group(1).split(',')[:3]]
                nxt = (v[0], v[1], v[2])
                if pos is not None:
                    # the MEAN radius of the move: under G96 the spindle
                    # changes continuously along a facing cut, and one number
                    # per move has to stand for it. Taking either end instead
                    # would be worst exactly where it matters - a cut to
                    # centre, where the end radius sends rpm to the cap.
                    tp.moves.append(Move(kind, pos, nxt, op, tool, None, subs,
                                         feed, fmode,
                                         rpm_for((pos[0] + nxt[0]) / 2.0)))
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
                    tp.moves.extend(
                        Move('feed', a, b, op, tool, None, subs, feed, fmode,
                             rpm_for((a[0] + b[0]) / 2.0))
                        for _n, a, b in _walk_arc(pos, nxt, v[2], v[3], v[4]))
                pos = nxt
                continue

        tp.flat = flatten_canon(canon)
        tp.moves = categorise(tp.moves)
        pts = [p for m in tp.moves for p in (m.a, m.b)]
        if pts:
            tp.min = tuple(min(p[i] for p in pts) for i in range(3))
            tp.max = tuple(max(p[i] for p in pts) for i in range(3))
        if tp.empty:
            tp.error = tp.error or 'the program produced no motion'
        return tp
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


_FLAT_RE = {
    'units': re.compile(r'USE_LENGTH_UNITS\(CANON_UNITS_(\w+)\)'),
    'plane': re.compile(r'SELECT_PLANE\(CANON_PLANE_(\w+)\)'),
    'feed': re.compile(r'SET_FEED_RATE\(([-0-9.]+)\)'),
    'speed': re.compile(r'SET_SPINDLE_SPEED\([^,]*,\s*([-0-9.]+)\)'),
    'cw': re.compile(r'START_SPINDLE_CLOCKWISE\('),
    'ccw': re.compile(r'START_SPINDLE_COUNTERCLOCKWISE\('),
    'spindle_off': re.compile(r'STOP_SPINDLE_TURNING\('),
    'select': re.compile(r'SELECT_TOOL\(([-0-9.]+)\)'),
    'change': re.compile(r'CHANGE_TOOL\('),
    'flood_on': re.compile(r'FLOOD_ON\('),
    'flood_off': re.compile(r'FLOOD_OFF\('),
    'dwell': re.compile(r'DWELL\(([-0-9.]+)\)'),
    'end': re.compile(r'PROGRAM_END\('),
}

FLAT_HEADER = """(NativeCAM - the generated program as plain G-code)
(Produced by running the real interpreter over ncam.ngc and writing down what)
(it actually did, so every subroutine, loop and expression is already gone and)
(every number here is a number the machine moves to)
(COORDINATES ARE ABSOLUTE - work offsets are already applied, and so is cutter)
(compensation: these are TOOL CONTROL POINTS, not the programmed contour)
(X is a DIAMETER, as everywhere else in NativeCAM; arc I offsets are radius)
(This is a listing to read, not a program to load)
"""


def _num(v):
    """A G-code number: enough digits to be exact, no trailing noise."""
    s = '%.4f' % v
    s = s.rstrip('0').rstrip('.')
    return s if s not in ('', '-0') else '0'


def flatten_canon(canon):
    """The canon dump rewritten as plain, modal G-code.

    The G-code tab used to show ncam.ngc itself, which is O-word calls and
    expressions - true, but it does not tell you where the tool goes. This is
    the other half: what the interpreter made of it.

    Only the begin/end markers survive from the comments. The generated file
    carries some 26,000 comment lines, nearly all of them subroutine headers
    repeated once per call, and keeping them buries the motion they describe.

    Coordinates are canon's own, which are absolute and post-compensation. X is
    doubled back to a diameter because every other number in this program is a
    diameter, and the arc offsets are left in radius because that is what the
    interpreter wants whichever mode it is in.
    """
    out = [FLAT_HEADER.rstrip('\n')]
    pos = None               # (x, y, z) in canon units, X radius
    g_modal = None
    feed = None
    depth = 0

    def xz(x, z):
        words = []
        if pos is None or abs(x - pos[0]) > 5e-5:
            words.append('X' + _num(x * 2.0))       # radius -> diameter
        if pos is None or abs(z - pos[2]) > 5e-5:
            words.append('Z' + _num(z))
        return words

    def once(text):
        if text not in out:
            out.append(text)

    def emit(g, words, indent):
        nonlocal g_modal
        if not words:
            return                              # a move to where we already are
        head = [] if g == g_modal else [g]
        g_modal = g
        out.append('  ' * indent + ' '.join(head + words))

    for line in canon.splitlines():
        m = _RE['comment'].search(line)
        if m:
            word, name = m.group(1), m.group(2).strip()
            if word == 'begin':
                out.append('')
                out.append('  ' * depth + '(begin %s)' % name)
                depth += 1
            elif depth:
                depth -= 1
                out.append('  ' * depth + '(end %s)' % name)
            # ncam.ngc's header carries a couple of (end ...) comments with no
            # begin of their own; printing them would read as a listing bug
            continue

        m = _RE['feed'].search(line) or _RE['rapid'].search(line)
        if m:
            rapid = 'STRAIGHT_TRAVERSE' in line
            v = [float(x) for x in m.group(1).split(',')[:3]]
            emit('G0' if rapid else 'G1', xz(v[0], v[2]), depth)
            pos = (v[0], v[1], v[2])
            continue

        m = _RE['arc'].search(line)
        if m:
            v = [float(x) for x in m.group(1).split(',')]
            ze, xe, zc, xc, rot = v[0], v[1], v[2], v[3], v[4]
            # canon rotation is positive counter-clockwise in the plane's own
            # frame; I and K are from the START point, and stay in radius
            words = xz(xe, ze)
            if pos is not None:
                words += ['I' + _num(xc - pos[0]), 'K' + _num(zc - pos[2])]
            emit('G3' if rot > 0 else 'G2', words, depth)
            pos = (xe, pos[1] if pos else 0.0, ze)
            continue

        m = _FLAT_RE['feed'].search(line)
        if m:
            f = float(m.group(1))
            if f > 0 and (feed is None or abs(f - feed) > 1e-6):
                feed = f
                out.append('  ' * depth + 'F' + _num(f))
            continue

        # the interpreter restates units and plane on every reset; a listing
        # that says G21 four times is just noise
        m = _FLAT_RE['units'].search(line)
        if m:
            once('G21' if m.group(1).startswith('MM') else 'G20')
            once('G7 (diameter mode)')
            continue
        m = _FLAT_RE['plane'].search(line)
        if m:
            once({'XZ': 'G18', 'XY': 'G17'}.get(m.group(1), 'G19'))
            continue
        m = _FLAT_RE['select'].search(line)
        if m:
            out.append('T%d' % int(float(m.group(1))))
            continue
        if _FLAT_RE['change'].search(line):
            out.append('M6')
            continue
        m = _FLAT_RE['speed'].search(line)
        if m:
            out.append('S' + _num(float(m.group(1))))
            continue
        if _FLAT_RE['cw'].search(line):
            out.append('M3')
        elif _FLAT_RE['ccw'].search(line):
            out.append('M4')
        elif _FLAT_RE['spindle_off'].search(line):
            out.append('M5')
        elif _FLAT_RE['flood_on'].search(line):
            out.append('M8')
        elif _FLAT_RE['flood_off'].search(line):
            out.append('M9')
        elif _FLAT_RE['end'].search(line):
            out.append('M2')
        else:
            m = _FLAT_RE['dwell'].search(line)
            if m and float(m.group(1)) > 0:
                out.append('G4 P' + _num(float(m.group(1))))
    return '\n'.join(out) + '\n'


ARC_SAG = 0.02          # mm of chord error allowed when splitting an arc


def _walk_arc(start, end, zc, xc, rot, sag=ARC_SAG):
    """An arc as a list of straight segments, subdivided under a sagitta bound.

    start/end are (x, y, z); the centre and rotation come from the canon call.
    `rot` is positive counter-clockwise, negative clockwise, and its sign is
    what decides which way round the circle the tool actually goes - taking the
    short way regardless would flip any arc over 180 degrees.
    """
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
    'hard':      (0.55, 0.55, 0.62),     # the contour as drawn
    'soft':      (0.95, 0.45, 0.85),     # what the tool can actually reach
    'tool':      (0.95, 0.75, 0.25),
    'tool_body': (0.42, 0.40, 0.46),
    'prefinish': (0.35, 0.60, 1.00),     # the pre-finish contour pass
    'finish':    (1.00, 0.60, 0.15),     # the finishing pass, in any op
    # teal - the COMPENSATED path, where the control point actually travels.
    # Deliberately far from 'finish' orange, 'prefinish' blue and 'soft'
    # magenta: the whole value of this line is being told apart from the
    # profile it is offset from.
    'comp':      (0.30, 0.90, 0.85),
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
                  view=None, tool=None, field=None, classes=None,
                  moves=None, move_colour=None, points=False,
                  hard=None, soft=None, comp=None):
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

    if field is not None:
        # what is LEFT of the material, once the simulation has cut into it
        draw_stock_field(cr, field, plane, s, ox, oy, classes)
    elif stock:
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

    draw = tp.moves if moves is None else moves

    # rapids first and dashed, so a cut is never hidden under a traverse
    cr.set_line_width(1.0)
    cr.set_dash([3.0, 3.0])
    for m in draw:
        if m.kind != 'rapid':
            continue
        cr.set_source_rgb(*(move_colour(m) if move_colour else COL['rapid']))
        cr.move_to(*pt(m.a))
        cr.line_to(*pt(m.b))
        cr.stroke()
    cr.set_dash([])

    cr.set_line_width(1.6)
    for m in draw:
        if m.kind == 'rapid':
            continue
        cr.set_source_rgb(*(move_colour(m) if move_colour else COL['feed']))
        cr.move_to(*pt(m.a))
        cr.line_to(*pt(m.b))
        cr.stroke()

    # The drawn contour and the reachable one, under the toolpath so the path
    # stays readable. Where the tool can reach everything the two coincide and
    # only the soft one shows - which is the honest picture: there is nothing
    # to warn about.
    if hard:
        _draw_profile(cr, hard, pt, COL['hard'], 1.2, [4.0, 3.0])
    if soft:
        _draw_profile(cr, soft, pt, COL['soft'], 2.0, None)
    # The COMPENSATED path last, so it reads on top of the profile it is
    # offset from. This is where the tool CONTROL POINT should travel; the
    # drawn toolpath is where it actually did. The two lying on one another is
    # the check - a visible gap between them is a bug, and that is how both
    # compensation faults found on 2026-08-02/03 first showed.
    if comp:
        _draw_profile(cr, comp, pt, COL['comp'], 1.4, [6.0, 3.0])

    if points:
        cr.set_source_rgb(*COL['text'])
        for m in draw:
            for p in (m.a, m.b):
                x, y = pt(p)
                cr.rectangle(x - 1.0, y - 1.0, 2.0, 2.0)
        cr.fill()

    # the tool last, so it is never hidden under the path it is cutting
    if tool is not None and tool.get('pos') is not None:
        draw_tool(cr, tool['pos'], plane, s, ox, oy,
                  tool.get('nose_r', 0.0), tool.get('orient', 0),
                  tool.get('cl_deg'), tool.get('included_deg'),
                  tool.get('front_deg'), tool.get('back_deg'),
                  tool.get('flank_len', 0.0), tool.get('shank_h', 0.0))

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


# ---------------------------------------------------------------------------
# simulation: where is the tool at a given point along the program
# ---------------------------------------------------------------------------
def path_lengths(tp):
    """Cumulative length along the program, and the total.

    Parameterised by DISTANCE, not time: the canon dump carries no feed rates,
    so a time-accurate simulation would be inventing them. Distance makes the
    scrub bar predictable - halfway along the slider is halfway along the path -
    and it is honest about what it knows. Rapids are included, so the tool is
    seen travelling between cuts rather than teleporting.
    """
    acc, total = [], 0.0
    for m in tp.moves:
        total += math.sqrt(_dist2(m.a, m.b))
        acc.append(total)
    return acc, total


DEFAULT_RAPID = 1200.0          # mm/min, if the ini will not say

# moves outside any feature marker - the header, the retract at the end
NO_OP = 'no operation'


def rapid_rate(ini_path):
    """Rapid traverse in mm/min, from the ini's own limit.

    [TRAJ] MAX_LINEAR_VELOCITY is in units per SECOND, which is the only
    interesting thing about this function: taking it for a per-minute figure
    makes every rapid sixty times too slow and the total time meaningless.
    """
    v = ini_value(ini_path, 'TRAJ', 'MAX_LINEAR_VELOCITY') if ini_path else None
    try:
        return float(v) * 60.0 if v and float(v) > 0 else DEFAULT_RAPID
    except (TypeError, ValueError):
        return DEFAULT_RAPID


def move_rate(m, rapid=DEFAULT_RAPID):
    """How fast this move actually runs, in mm/min, or None if unknowable.

    A lathe programmed in G95 feeds per REVOLUTION, so its feed number is not
    a speed at all until it is multiplied by the spindle. Returning None rather
    than a plausible number is the point: a time built on an invented spindle
    speed looks exactly like a real one.
    """
    if m.kind == 'rapid':
        return rapid
    if not m.feed or m.feed <= 0:
        return None
    if m.fmode != 'rev':
        return m.feed
    if not m.rpm or m.rpm <= 0:
        return None
    return m.feed * m.rpm


def move_seconds(m, rapid=DEFAULT_RAPID):
    """Time for one move in seconds, or None when its rate is unknown."""
    rate = move_rate(m, rapid)
    if not rate:
        return None
    return math.sqrt(_dist2(m.a, m.b)) / rate * 60.0


def statistics(tp, rapid=DEFAULT_RAPID):
    """Distances, times and counts for a whole program.

    `unknown` is reported rather than folded into the total: moves whose rate
    could not be worked out are a hole in the estimate, and a total that
    quietly omits them reads as complete.
    """
    st = {'cut_dist': 0.0, 'rapid_dist': 0.0, 'cut_time': 0.0,
          'rapid_time': 0.0, 'unknown': 0, 'moves': len(tp.moves),
          'ops': [], 'tools': tp.tools, 'per_op': []}
    per_op = collections.OrderedDict()
    for m in tp.moves:
        d = math.sqrt(_dist2(m.a, m.b))
        secs = move_seconds(m, rapid)
        if secs is None:
            st['unknown'] += 1
            secs = 0.0
        if m.kind == 'rapid':
            st['rapid_dist'] += d
            st['rapid_time'] += secs
        else:
            st['cut_dist'] += d
            st['cut_time'] += secs
        key = m.op or NO_OP
        row = per_op.setdefault(key, {'name': key, 'dist': 0.0, 'time': 0.0})
        row['dist'] += d
        row['time'] += secs
    st['dist'] = st['cut_dist'] + st['rapid_dist']
    st['time'] = st['cut_time'] + st['rapid_time']
    st['ops'] = tp.operations
    st['changes'] = len(tp.tools)
    for row in per_op.values():
        row['share'] = (row['time'] / st['time'] * 100.0) if st['time'] else 0.0
        st['per_op'].append(row)
    return st


def fmt_time(secs):
    """Seconds as h:mm:ss / m:ss, or '-' when there is nothing to show."""
    if secs is None:
        return '-'
    secs = int(round(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return '%d:%02d:%02d' % (h, m, s)
    return '%d:%02d' % (m, s)


def info_at(tp, index, point, rapid=DEFAULT_RAPID):
    """Everything the Info panel shows about one point on the path."""
    if not tp.moves or index is None or index < 0 or index >= len(tp.moves):
        return None
    m = tp.moves[index]
    rate = move_rate(m, rapid)
    return {
        'x': (point[0] if point else m.b[0]) * 2.0,      # diameter, as the UI
        'z': point[2] if point else m.b[2],
        'kind': m.kind,
        'cat': m.cat,
        'op': m.op,
        'phase': m.subs[-1] if m.subs else None,
        'tool': m.tool,
        'feed': m.feed,
        'fmode': m.fmode,
        'rpm': m.rpm,
        'rate': rate,
        'index': index,
        'moves': len(tp.moves),
    }


def position_at(tp, t, acc=None, total=None):
    """(point, move index, kind) at fraction t in 0..1 along the program."""
    if not tp.moves:
        return None, -1, None
    if acc is None:
        acc, total = path_lengths(tp)
    if not total:
        m0 = tp.moves[0]
        return m0.a, 0, m0.kind
    want = max(0.0, min(1.0, t)) * total
    lo = 0
    for i, c in enumerate(acc):
        if c >= want:
            lo = i
            break
    else:
        lo = len(tp.moves) - 1
    mv = tp.moves[lo]
    prev = acc[lo - 1] if lo else 0.0
    seg = acc[lo] - prev
    f = 0.0 if seg <= 1e-12 else (want - prev) / seg
    return (tuple(mv.a[j] + (mv.b[j] - mv.a[j]) * f for j in range(3)),
            lo, mv.kind)


def nose_offset(orient):
    """RAW (Z, radius) offset from the control point to the nose centre.

    Multiplied by the nose radius, this is where the circle actually sits. It
    is NOT a unit vector: orientations 1-4 are the diagonal corners and have
    magnitude sqrt(2), because the imaginary sharp tip of a 90 degree corner
    sits sqrt(2)*R from the round nose centre.

    Normalising it and scaling by R - which is what the first version of the
    material removal did - places the nose R short along the diagonal and cuts
    R*(1 - 1/sqrt(2)) too deep: a constant 0.117 mm with a 0.4 mm nose, on
    every surface. CLAUDE.md flags this exact trap, and it still caught this
    code, so the raw table is used directly here and only the DRAWING uses a
    normalised direction.
    """
    if 0 < orient < len(NOSE_DIR):
        return NOSE_DIR[orient]
    return (0.0, 0.0)


def tool_direction(orient, cl_deg=None):
    """Unit (Z, radius) direction from the control point toward the tool body.

    Two sources, and they agree: the centre-line angle from the tool table's
    (I+J)/2, or LinuxCNC's nine-way orientation table. Checked numerically -
    (cos CL, sin CL) reproduces NOSE_DIR for every orientation, which is what
    makes it safe to prefer the tool table and fall back to the number.

    CL is measured CLOCKWISE from Z+ as seen on the plot, and the plot draws
    radius DOWNWARD, so screen-y grows the same way the angle turns. That is
    why this is a plain (cos, sin) with no negation - and getting that wrong is
    what mirrored the tool about the Z axis in the first version.
    """
    if cl_deg is not None:
        a = math.radians(cl_deg)
        return math.cos(a), math.sin(a)
    if 0 < orient < len(NOSE_DIR):
        dz, dx = NOSE_DIR[orient]
        n = math.hypot(dz, dx)
        if n:
            return dz / n, dx / n
    return 0.0, 0.0


# Shank cross-section -> the rest of the holder. From greatEndian's ISO
# reference, 2026-08-02, kept in ref/tool-shank/NOTES.md: external turning
# holders are square (b = h), the overall length l1 follows the shank by the
# ISO length code, and the insert size follows the pocket the shank can carry.
#
# l1 here is the MIDPOINT of the length code's range. The insert edge length is
# the common size for that shank rather than the middle of the stated range - a
# 25 mm holder carries a CNMG 1204 far more often than a 19 mm insert.
#
#   h       l1     insert edge
SHANK_TABLE = (
    (12.0, 110.0, 9.0),
    (16.0, 125.0, 9.0),
    (20.0, 150.0, 12.0),
    (25.0, 160.0, 12.0),
    (32.0, 180.0, 16.0),
)

def shank_dims(shank_h):
    """(overall length l1, insert edge length) for a shank height, or None.

    l1 is INTERPOLATED between the two standard sizes it falls between, and
    extrapolated proportionally outside them: an inch shank is 25.4 mm against
    the 25 mm entry and comes out a little longer rather than snapping to the
    metric number, and a ground-to-fit 22 mm shank lands between the 20 and the
    25. Nearest-match with a scale factor was tried first and is not monotonic
    - it made a 22 mm shank longer than a 25 mm one.

    The insert edge is NOT interpolated. Inserts come in standard sizes and
    12.2 mm is not one of them, so it takes the nearest entry's whole value.
    """
    if not shank_h or shank_h <= 0:
        return None
    lo = hi = None
    for row in SHANK_TABLE:
        if row[0] <= shank_h and (lo is None or row[0] > lo[0]):
            lo = row
        if row[0] >= shank_h and (hi is None or row[0] < hi[0]):
            hi = row
    edge = min(SHANK_TABLE, key=lambda r: abs(r[0] - shank_h))[2]
    if lo is None or hi is None:                # off the end of the table
        row = lo or hi
        return row[1] * shank_h / row[0], edge
    if lo[0] == hi[0]:
        return lo[1], edge
    f = (shank_h - lo[0]) / (hi[0] - lo[0])
    return lo[1] + (hi[1] - lo[1]) * f, edge


def tool_shank(pos, nose_r, orient, front_deg=None, back_deg=None,
               shank_h=0.0, cl_deg=None, length=None):
    """The holder shank behind the insert, as a closed (z, radius) outline.

    A rectangle, shank height radially by overall length in Z, running in the
    direction the body lies. This is what bounds the tool: before it, the
    outline closed by extending both cutting edges to a Z-perpendicular cap
    one flank length back, and the steep front edge needs 3.86 mm of radius per
    mm of Z - so a 6 mm flank drew a 23 mm tool and a 25 mm flank drew a 94 mm
    one. An insert is bounded by its own edge length; the block behind it is
    bounded by the turret, not by anything the flank does.

    ITS CORNER IS ON THE INSERT, NOT ON THE TOOL TIP. The insert stands proud
    of the block it is clamped in - that is the whole point of a pocket - so
    the shank starts where the insert's two far corners are, inset behind it in
    Z and outset from it radially. Anchored on the tip instead, the block's top
    face lies at the cutting radius itself and sweeps the entire part on the
    body's side of the tool: on the demo lathe program that reported 50
    collisions on a program with none, and reported the SAME 50 for a 12 mm
    shank as for a 25 mm one, which is what gave it away.

    Falls back to the tip when the tool table has no angles to build an insert
    from - conservative, and it is the only anchor there is.

    `length` shortens it for drawing; the collision check passes None and gets
    the whole l1. It is never longer than l1 either way.
    """
    dims = shank_dims(shank_h)
    if dims is None or not nose_r or nose_r <= 0:
        return None
    dz, dx = tool_direction(orient, cl_deg)
    zdir = 1.0 if dz > 1e-9 else (-1.0 if dz < -1e-9 else 0.0)
    xdir = 1.0 if dx > 1e-9 else (-1.0 if dx < -1e-9 else 0.0)
    if zdir == 0.0 or xdir == 0.0:
        # a tool pointing straight along Z or straight out has no corner to
        # hang a rectangle on, and guessing one would put steel where there
        # is none
        return None
    z0, x0 = pos[2], pos[0]
    parts = {}
    if tool_silhouette(pos, nose_r, orient, front_deg, back_deg, 0.0,
                       cl_deg, parts, shank_h) and 'e_f' in parts:
        # The INSERT's far corners, taken from parts rather than from the
        # returned outline: that outline now runs on down to the bottom
        # reference line, and measuring its extremes would set the block off
        # from there instead - one shank height too far out, every time.
        corners = (parts['e_f'], parts['e_b'])
        z0 = (max if zdir > 0 else min)(p[0] for p in corners)
        x0 = (max if xdir > 0 else min)(p[1] for p in corners)
    lz = dims[0] if length is None else min(length, dims[0])
    z1, x1 = z0 + zdir * lz, x0 + xdir * shank_h
    return [(z0, x0), (z1, x0), (z1, x1), (z0, x1)]


def tool_silhouette(pos, nose_r, orient, front_deg=None, back_deg=None,
                    flank_len=0.0, cl_deg=None, parts=None, shank_h=0.0):
    """The tool as a closed (z, radius) outline in MODEL units, or None.

    Built the way the insert actually is, from the tool table plus the flank
    length off the Tool Change:

      - the nose circle of radius R, centred where the orientation puts it;
      - the two cutting edges, tangent to that circle, running at the FRONT
        and BACK angles the tool table gives (both measured from Z+);
      - a back, closing the two of them.

    How that back is drawn depends on whether a SHANK HEIGHT is known:

      - with one, each edge runs its own INSERT EDGE LENGTH - derived from the
        shank by shank_dims - and the two ends are joined. That is the insert:
        a nose corner between two edges of a known length, which is what an
        ISO designation actually specifies. What lies behind it is the shank,
        returned separately by tool_shank.
      - without one, the older construction: two lines perpendicular to Z, one
        tangent to the nose circle on its leading side and the other one flank
        length behind it, with both edges extended to reach the second. Kept
        so a project that has never been given a shank draws what it drew
        before, but it is not a bound - the steep front edge grows 3.86 mm of
        radius per mm of Z, which is why a 6 mm flank drew a 48 mm tool.

    Returns None rather than a guess when the tool table carries no angles, or
    neither a shank height nor a flank length is set: a silhouette drawn at
    invented dimensions is a claim about the tool that nothing supports, and
    this one is used to judge clearance.
    """
    if not nose_r or nose_r <= 0:
        return None
    if front_deg is None or back_deg is None or front_deg == back_deg:
        return None
    dims = shank_dims(shank_h)
    if dims is None and (not flank_len or flank_len <= 0):
        return None
    dz, dx = tool_direction(orient, cl_deg)
    if not (dz or dx):
        return None
    rz, rx = nose_offset(orient)
    cz, cx = pos[2] + rz * nose_r, pos[0] + rx * nose_r

    def edge(deg):
        """(tangent point, unit direction into the body) for one cutting edge.

        The table's angle is measured off the PERPENDICULAR, so the edge sits
        at 90 - it from Z. That is the same reading flank_slope has always
        used for the back angle - a J75 insert ramps at 15 degrees - and
        photo/toolFlank_1.png labels both the same way: the angle called
        "back angle" is between the Z axis and the shallow edge, and the one
        called "front angle" is between the RADIAL direction and the steep
        one. Taking them as directions from Z instead swapped the two edges.
        """
        a = math.radians(90.0 - deg)
        ez, ex = math.cos(a), math.sin(a)
        # the outward normal is the one pointing AWAY from the body, so the
        # edge lies on the cutting side of the circle rather than through it
        nz, nx = -ex, ez
        if nz * dz + nx * dx > 0:
            nz, nx = -nz, -nx
        # and the edge runs from its tangent point INTO the body, not out of it
        if ez * dz + ex * dx < 0:
            ez, ex = -ez, -ex
        return (cz + nz * nose_r, cx + nx * nose_r), (ez, ex)

    # the cap lines: perpendicular to Z, so both are a constant Z. The first is
    # tangent to the nose circle on the side the body is NOT, the second one
    # flank length further into the body.
    zdir = 1.0 if dz > 1e-9 else (-1.0 if dz < -1e-9 else 0.0)
    xdir = 1.0 if dx > 1e-9 else (-1.0 if dx < -1e-9 else 0.0)
    if zdir == 0.0:
        return None                 # straight facing or boring: no Z extent
    z_lead = cz - zdir * nose_r
    z_back = z_lead + zdir * flank_len

    def to_cap(t0, d):
        """Where an edge crosses the back cap, or None if it never does."""
        if abs(d[0]) < 1e-9:
            return None
        k = (z_back - t0[0]) / d[0]
        if k < 0:
            return None
        return (t0[0] + d[0] * k, t0[1] + d[1] * k)

    (t_f, d_f), (t_b, d_b) = edge(front_deg), edge(back_deg)
    if dims is not None:
        # the insert: each edge runs its own length from where it leaves the
        # nose circle, and the two far corners are joined. No extension, so
        # nothing here depends on how steeply an edge climbs.
        el = dims[1]
        e_f = (t_f[0] + d_f[0] * el, t_f[1] + d_f[1] * el)
        e_b = (t_b[0] + d_b[0] * el, t_b[1] + d_b[1] * el)
    else:
        e_f, e_b = to_cap(t_f, d_f), to_cap(t_b, d_b)
        if e_f is None or e_b is None:
            return None
    if parts is not None:
        parts.update(centre=(cz, cx), t_f=t_f, t_b=t_b, e_f=e_f, e_b=e_b,
                     d_f=d_f, d_b=d_b, z_lead=z_lead, z_back=z_back,
                     zdir=zdir, r=nose_r)

    # the nose arc, from one tangent point round the exposed side to the other
    a_f = math.atan2(t_f[1] - cx, t_f[0] - cz)
    a_b = math.atan2(t_b[1] - cx, t_b[0] - cz)
    span = (a_b - a_f) % (2 * math.pi)
    if span > math.pi:              # take the short way, over the cutting side
        span -= 2 * math.pi
    steps = max(6, int(abs(span) / 0.15) + 1)
    ts = [i / float(steps) for i in range(steps + 1)]
    # The leading tangent point has to be a VERTEX, not something the sampling
    # passes near: it is where the first cap line touches, so the drawn tool
    # would otherwise be a fraction short of its own flank length - 0.6 um at
    # this step size, which is invisible and still wrong.
    a_ext = math.pi if zdir > 0 else 0.0
    t_ext = (((a_ext - a_f) % (2 * math.pi))
             - (2 * math.pi if span < 0 else 0.0)) / span
    if 1e-9 < t_ext < 1.0 - 1e-9:
        ts.append(t_ext)
        ts.sort()
    arc = [(cz + math.cos(a_f + span * t) * nose_r,
            cx + math.sin(a_f + span * t) * nose_r) for t in ts]
    ins = arc + [e_b, e_f]
    if parts is not None:
        parts['tail'] = 3
    if dims is None or not xdir:
        return ins

    # THE SHANK IS NOT DRAWN AS A BLOCK OF ITS OWN. Its two near reference
    # lines close the tool instead: the side facing the cut becomes the tool's
    # right-hand reference, and the far side becomes the tool's bottom.
    # greatEndian, photo/toolFlank_3.png - drawn as a separate square it read
    # as a second object floating clear of the tool it belongs to, which is
    # exactly what it looked like in AXIS.
    #
    # BOTH SIDES ARE CONSTANT-Z LINES, and they are parallel. The far one is
    # the shank's near face. The NEAR one is `z_face`, the vertical tangent to
    # the nose circle on the side OPPOSITE the cut - the tool tip mirrored
    # through the nose centre, the line tool_holder has always used as the
    # front face of the holder.
    #
    # That line is what makes the front cutting edge SHORT: the edge leaves the
    # nose at the front angle and runs only as far as the face, six-odd
    # millimetres on a 0.8 mm nose at 15 degrees, and the holder takes over
    # from there. Running the front edge all the way down to the bottom instead
    # put the near side on a slant of the front angle - 9.8 mm of Z over 37.6 mm
    # of radius, photo/toolFlank_3_0.png - and dropping it altogether lost the
    # short edge with it.
    cand = list(arc) + [e_f, e_b]
    z_ref = (max if zdir > 0 else min)(p[0] for p in cand)
    x_far = (max if xdir > 0 else min)(p[1] for p in cand)
    x_bot = x_far + xdir * shank_h
    z_face = cz + zdir * nose_r
    if abs(d_f[0]) < 1e-9 or (z_face - z_ref) * zdir >= 0:
        return ins                  # no face to cut the front edge short on
    k = (z_face - t_f[0]) / d_f[0]
    if k <= 0:
        return ins
    cross = (z_face, t_f[1] + d_f[1] * k)
    if (cross[1] - x_bot) * xdir >= 0:
        # a shallow front edge reaches the bottom before it ever reaches the
        # face: there is no near vertical then, only the edge
        return ins
    if parts is not None:
        # five closing points for the collision body: back tangent, back edge
        # end, the two bottom corners, and the foot of the short front edge.
        # That covers the back edge, the shank reference, the bottom and the
        # holder face - every surface that is not an edge. The short front edge
        # itself is left out, as the front edge always was: it cuts, and
        # testing it reports every pass as a crash.
        parts.update(z_ref=z_ref, z_face=z_face, x_bot=x_bot, cross=cross,
                     tail=5)
    return arc + [e_b, (z_ref, x_bot), (z_face, x_bot), cross]


def tool_holder(pos, nose_r, orient, front_deg=None, back_deg=None,
                flank_len=0.0, cl_deg=None, shank_h=0.0):
    """The holder in front of the insert, as a closed (z, radius) outline.

    A third line perpendicular to Z, tangent to the nose circle on its BACK
    side - the tool tip mirrored through the nose centre. That line is the
    front face of the holder, and the sliver between it and the insert's back
    edge is body: metal that is not an edge and must not touch anything.

    Without it the tool stops at its own cutting edge, which is only the front
    corner of a real tool. The insert is a few millimetres; what actually
    fouls a shoulder is the block behind it.

    Returned separately from tool_silhouette rather than merged into it, and
    drawn in the same grey: they are one tool to look at, but the collision
    check has to tell them apart, because the insert's front edge is allowed
    to be in metal and none of the holder is.
    """
    parts = {}
    if tool_silhouette(pos, nose_r, orient, front_deg, back_deg, flank_len,
                       cl_deg, parts, shank_h) is None:
        return None
    cz, cx = parts['centre']
    t_f, e_f, zdir = parts['t_f'], parts['e_f'], parts['zdir']
    # The face is the perpendicular-to-Z tangent on the BACK of the nose
    # circle - the tool tip mirrored through the nose centre, which is the
    # red line in photo/toolFlank_1.png. It is one nose DIAMETER behind the
    # leading tangent the insert already caps with, not the same line.
    z_face = cz + zdir * nose_r
    # the holder runs from that face back to wherever the insert's back edge
    # reaches the cap, and down to the same radius
    # The face and the front edge CROSS: near the nose the steep edge is in
    # front of the face, and below the crossing the face is in front of the
    # edge. The holder is the part on the second side - the block standing
    # proud of the insert - so it is the triangle from that crossing down.
    # Taking the whole strip instead gives a self-intersecting outline, which
    # cairo happily fills into a bow tie.
    d_f = parts['d_f']
    if abs(d_f[0]) < 1e-9:
        return None
    k = (z_face - t_f[0]) / d_f[0]
    if k < 0:
        return None
    x_cross = (z_face, t_f[1] + d_f[1] * k)
    if e_f[1] - x_cross[1] < 1e-9:
        return None
    del cx
    return [x_cross, (z_face, e_f[1]), (e_f[0], e_f[1])]


def draw_tool(cr, pos, plane, s, ox, oy, nose_r=0.0, orient=0,
              cl_deg=None, included_deg=None, front_deg=None, back_deg=None,
              flank_len=0.0, shank_h=0.0):
    """The tool at `pos`: its nose circle, and the insert behind it.

    The BODY LIES IN THE SAME DIRECTION AS THE NOSE OFFSET, not opposite it.
    LinuxCNC's lathe_shapes gives the vector from the commanded control point -
    the imaginary sharp tip - to the centre of the nose circle, and that centre
    is inside the tool. The first version drew the holder the other way, which
    put the tool on the far side of its own tip and read as a mirror image.

    Given the tool table's angles AND a flank length from the Tool Change, the
    body is the real silhouette from tool_silhouette() - dimensioned in mm, so
    it scales with the plot instead of being a fixed number of pixels, and the
    flank length is something the operator can see rather than only type.

    With I and J but no flank length it falls back to the old wedge, tangent to
    the nose circle on both faces but of arbitrary length; with neither, to a
    plain schematic. A wedge drawn at a guessed angle would be a claim about
    the tool that nothing supports.
    """
    ia, ib = _plane_indices(plane)
    px, py = pos[ia] * s + ox, pos[ib] * s + oy
    r = max(nose_r * s, 2.0)
    dz, dx = tool_direction(orient, cl_deg)
    # the CENTRE uses the raw offset - sqrt(2) on a corner orientation - while
    # the wedge below is aimed with the unit direction
    rz, rx = nose_offset(orient)

    if dz or dx:
        cx, cy = px + rz * nose_r * s, py + rx * nose_r * s
        half = None
        if included_deg is not None and 1.0 < included_deg < 179.0:
            half = math.radians(included_deg / 2.0)
        # a lathe silhouette in the ZX plane only - it is built from a nose
        # orientation and a flank, neither of which means anything on a mill
        outline = (tool_silhouette(pos, nose_r, orient, front_deg, back_deg,
                                   flank_len, cl_deg, None, shank_h)
                   if plane == 'ZX' else None)
        # The holder face is only drawn on the FLANK-LENGTH outline. Once a
        # shank closes the tool on its two vertical references that sliver is
        # wholly inside the body, and drawing it again only put a visible
        # seam across it.
        holder = (tool_holder(pos, nose_r, orient, front_deg, back_deg,
                              flank_len, cl_deg)
                  if plane == 'ZX' and not shank_dims(shank_h) else None)
        # the shank is NOT drawn as a block of its own - the silhouette above
        # already closes on its two reference lines. See tool_silhouette.
        if holder:
            # the SAME grey as the insert: the two are one tool, and the
            # split was only ever a way of showing which part is which
            cr.set_source_rgba(*(COL['tool_body'] + (0.9,)))
            first = True
            for pz, prx in holder:
                (cr.move_to if first else cr.line_to)(pz * s + ox, prx * s + oy)
                first = False
            cr.close_path()
            cr.fill()
        cr.set_source_rgba(*(COL['tool_body'] + (0.9,)))
        if outline:
            # model units, so it is drawn through the same transform the
            # toolpath is - a silhouette that did not scale with the zoom
            # would be a picture of nothing in particular
            first = True
            for pz, prx in outline:
                sx, sy = pz * s + ox, prx * s + oy
                (cr.move_to if first else cr.line_to)(sx, sy)
                first = False
            cr.close_path()
            cr.fill_preserve()
            cr.set_source_rgb(*COL['tool_body'])
            cr.set_line_width(1.0)
            cr.stroke()
        elif half is not None:
            # a real wedge, tangent to the nose circle on both faces
            apex = r / math.sin(half)
            ax, ay = cx - dz * apex, cy - dx * apex
            base = math.atan2(dx, dz)
            L = max(r * 10.0, 34.0)
            cr.move_to(ax, ay)
            for sgn in (-1.0, 1.0):
                a = base + sgn * half
                cr.line_to(ax + math.cos(a) * L, ay + math.sin(a) * L)
            cr.close_path()
            cr.fill()
        else:
            L, w = max(r * 6.0, 26.0), max(r * 1.6, 5.0)
            cr.move_to(px - dx * w, py + dz * w)
            cr.line_to(px + dx * w, py - dz * w)
            cr.line_to(cx + dz * L + dx * w * 1.6, cy + dx * L - dz * w * 1.6)
            cr.line_to(cx + dz * L - dx * w * 1.6, cy + dx * L + dz * w * 1.6)
            cr.close_path()
            cr.fill()

        cr.set_source_rgb(*COL['tool'])
        cr.set_line_width(1.4)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()

    # the commanded point itself, always drawn: it is what the G-code says
    cr.set_source_rgb(*COL['tool'])
    cr.set_line_width(1.6)
    cr.move_to(px - 4, py)
    cr.line_to(px + 4, py)
    cr.move_to(px, py - 4)
    cr.line_to(px, py + 4)
    cr.stroke()


# which way the nose sits from the control point, as (Z, radius) signs -
# lathe_comp's one table, transposed there into the order this module plots in.
NOSE_DIR = lathe_comp.NOSE_DIR


# ---------------------------------------------------------------------------
# material removal
# ---------------------------------------------------------------------------
class StockField(object):
    """The remaining material, as a radial profile sampled along Z.

    A lathe part is a solid of revolution, so at any Z the material is the ring
    between an inner and an outer radius. That makes removal a 1-D problem
    rather than a 2-D boolean: columns along Z, each holding [inner, outer],
    and a cut simply pushes one of those two bounds. This is how lathe
    simulators do it, and it is fast enough to run per frame.

    The nose is swept as a CIRCLE, not a point: at each Z the disc reaches from
    cx - sqrt(R^2 - dz^2) to cx + that, which is what puts a real fillet in an
    inside corner instead of a sharp one.

    KNOWN LIMIT: a cut that lands wholly INSIDE the ring - a plunge into the
    middle of a wall, touching neither bound - would split the material in two,
    which one inner/outer pair cannot represent. Such a cut is charged to the
    outer bound. That is wrong for a deep grooving plunge and right for
    everything the lathe ops currently generate.
    """

    @staticmethod
    def columns_for(z0, z1, nose_r, cap=4000):
        """Enough columns that the nose circle is not visibly quantised.

        Sampling a disc at column centres biases the result DEEPER by
        R - sqrt(R^2 - (dz/2)^2). With 0.42 mm columns and a 0.4 mm nose that
        is 0.06 mm, and the simulated part came out 0.07-0.12 mm under its
        profile - small, but exactly the sort of error someone would try to
        explain as a compensation fault. A sixth of the nose radius puts it
        under a micron.
        """
        span = abs(z1 - z0)
        if span <= 0 or nose_r <= 0:
            return 600
        return int(max(200, min(cap, span / (nose_r / 6.0))))

    def __init__(self, z0, z1, inner, outer, columns=600):
        self.z0, self.z1 = min(z0, z1), max(z0, z1)
        self.n = max(int(columns), 8)
        span = self.z1 - self.z0
        self.dz = span / float(self.n) if span > 0 else 1.0
        self.inner = [float(inner)] * self.n
        self.outer = [float(outer)] * self.n
        self.r_in0, self.r_out0 = float(inner), float(outer)

    def _col(self, z):
        return int((z - self.z0) / self.dz) if self.dz else 0

    def cut_disc(self, cz, cx, r):
        """Remove the disc of radius r centred at (cz, cx)."""
        if r <= 0:
            return
        lo, hi = self._col(cz - r), self._col(cz + r)
        for i in range(max(lo, 0), min(hi + 1, self.n)):
            zc = self.z0 + (i + 0.5) * self.dz
            d = r * r - (zc - cz) ** 2
            if d <= 0:
                continue
            h = math.sqrt(d)
            lo_r, hi_r = cx - h, cx + h
            if hi_r >= self.outer[i] and lo_r < self.outer[i]:
                self.outer[i] = max(lo_r, self.inner[i])
            elif lo_r <= self.inner[i] and hi_r > self.inner[i]:
                self.inner[i] = min(hi_r, self.outer[i])
            elif lo_r > self.inner[i] and hi_r < self.outer[i]:
                # wholly inside the ring - see the note above
                self.outer[i] = max(lo_r, self.inner[i])

    def cut_move(self, a, b, r, direction=(0.0, 0.0)):
        """Sweep the nose along a segment, stepping under one column width.

        `direction` is the unit (Z, radius) vector from the commanded control
        point to the NOSE CENTRE - lathe_shapes' offset. The swept disc has to
        be centred there, not on the control point: the control point is an
        imaginary sharp tip that removes no metal. Sweeping at the control
        point instead cut the demo part to r19.60 where the profile is r20.00,
        out by exactly the nose radius.
        """
        dz = b[2] - a[2]
        dx = b[0] - a[0]
        oz, ox = direction[0] * r, direction[1] * r
        # Stepping is driven by the move's Z EXTENT, not its length. For each
        # column the deepest reach of the sweep is either at an endpoint or
        # where the path passes closest in Z, so Z resolution is what has to be
        # covered. A radial plunge or retract - most of the length in a typical
        # program - then costs two samples instead of thousands.
        steps = max(int(abs(dz) / max(self.dz, 1e-9)) + 1, 2)
        for k in range(steps + 1):
            f = k / float(steps)
            self.cut_disc(a[2] + dz * f + oz, a[0] + dx * f + ox, r)

    def polygon(self):
        """The remaining silhouette as (z, radius) points, outer then inner."""
        pts = [(self.z0 + (i + 0.5) * self.dz, self.outer[i])
               for i in range(self.n)]
        pts += [(self.z0 + (i + 0.5) * self.dz, self.inner[i])
                for i in range(self.n - 1, -1, -1)]
        return pts


# ---------------------------------------------------------------------------
# collisions
# ---------------------------------------------------------------------------
# One reported hit. `at` is the fraction along the whole program, so the
# timeline can mark it where the operator will look for it.
Collision = collections.namedtuple('Collision', 'index kind pos depth at')

RAPID_HIT, BODY_HIT = 'rapid into material', 'tool body into material'

# how finely the tool is stepped along a move while looking for a hit. Half a
# millimetre: a collision that only exists for less than that is a graze the
# operator cannot act on, and the cost is linear in every move in the program.
STEP_MM = 0.5


def _inside(field, z, r, tol=1e-4):
    """How deep (z, radius) sits inside the remaining material, or None.

    Depth is measured to the NEAREST surface, so a tool a hair under the skin
    reports a hair rather than the full wall thickness.
    """
    if field is None or field.n <= 0:
        return None
    i = field._col(z)
    if i < 0 or i >= field.n:
        return None
    lo, hi = field.inner[i], field.outer[i]
    if not (lo + tol < r < hi - tol):
        return None
    return min(r - lo, hi - r)


def _outline_samples(poly, step=0.5, closed=True):
    """A path, densified so an edge cannot slip through between its ends.

    Testing the vertices alone misses the obvious case: a long straight flank
    with both ends in clear air and its middle buried in the boss.
    """
    out = []
    pairs = zip(poly, list(poly[1:]) + ([poly[0]] if closed else []))
    for a, b in pairs:
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d / step))
        for k in range(n):
            f = k / float(n)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def collisions(tp, stock, nose_r=0.0, orient=0, front_deg=None, back_deg=None,
               flank_len=0.0, cl_deg=None, columns=None, limit=50,
               min_depth=None, shank_h=0.0):
    """Where the tool runs into material it is not cutting.

    Two things are reported, and they are not the same fault:

      - a RAPID whose tool - nose included - is inside material. On a real
        machine that is a crash.
      - the tool BODY inside material during a feed. The nose is meant to be
        in the metal; the flank behind it is not. This is the failure the
        whole back-angle shadow exists to prevent, and until now nothing
        checked whether the shadow actually worked.

    Needs the silhouette, so it needs the tool table's angles and a flank
    length. Without them there is no body to test and this returns [] rather
    than guessing at one - see tool_silhouette.

    The material is simulated as it goes, so a pass is judged against what the
    passes before it left, not against the bar.
    """
    if not tp.moves or not stock or nose_r <= 0:
        return []
    parts0 = {}
    poly0 = tool_silhouette((0.0, 0.0, 0.0), nose_r, orient, front_deg,
                            back_deg, flank_len, cl_deg, parts0, shank_h)
    if not poly0:
        return []
    # The shank at its FULL length, which the picture no longer shows at all:
    # what fouls a shoulder is the block running back to the turret, and a
    # check that stopped where the drawing stops would be a drawing rather
    # than a check.
    shank0 = tool_shank((0.0, 0.0, 0.0), nose_r, orient, front_deg,
                        back_deg, shank_h, cl_deg)
    # the outline in TOOL coordinates, once - it does not change shape as the
    # tool moves, so it is built here and translated per sample
    whole = _outline_samples(poly0)
    # The BACK flank and everything closing behind it - and nothing else.
    # tool_silhouette returns the nose arc first and then the closing points,
    # and says in `tail` how many of them there are: three for the flank-length
    # cap (back tangent, back edge end, front edge end), four once the shank's
    # reference lines close it (back tangent, back edge end, the corner, the
    # front edge down at the bottom line). Hard-coding three dropped the
    # bottom line, which is most of the tool.
    #
    # The nose and the FRONT edge are left out on purpose. Both are cutting
    # surfaces - the nose is the cut and the front edge is where the chip
    # comes off - so testing them reports every roughing pass as a collision,
    # which is what the first run of this did: 21 hits on a clean program, all
    # of them the front edge doing its job.
    body = _outline_samples(list(poly0[-parts0.get('tail', 3):]), closed=False)
    if shank0:
        # all of it, both for a rapid and for a feed - no part of the holder is
        # ever entitled to be in metal
        shank_pts = _outline_samples(shank0)
        whole = whole + shank_pts
        body = body + shank_pts

    a0, a1, b0, b1 = stock
    # Deliberately coarser than the removal field the picture is drawn from.
    # A collision is millimetres of tool in metal, not microns, and this walks
    # the whole silhouette at every step of every move - at removal resolution
    # that is tens of millions of lookups and twenty seconds.
    cols = columns or max(200, min(1200, int(abs(a1 - a0) / 0.25)))
    field = StockField(a0, a1, b0, b1, cols)
    d = nose_offset(orient)
    acc, total = path_lengths(tp)

    # Below this the report is quantisation, not a collision. Sampling the
    # swept nose at column centres under-cuts by R - sqrt(R^2 - (dz/2)^2), and
    # the tool then reads as that far into its own groove: 0.02 mm on this
    # field, which is exactly the depth the first clean run reported. Five
    # times it, because at three a plain retract out through its own cut still
    # measured 0.063 against a 0.060 floor. A tool 0.1 mm into metal is not
    # something an operator can act on anyway.
    quant = nose_r - math.sqrt(max(nose_r ** 2 - (field.dz / 2.0) ** 2, 0.0))
    floor = min_depth if min_depth is not None else max(5.0 * quant, 0.05)

    out = []
    for i, m in enumerate(tp.moves):
        # A FEED is tested against the material as this move LEAVES it: the
        # metal the nose takes off on the way through is not a collision, and
        # the body follows the nose through the same groove. Testing first
        # reported the body brushing the skin the nose was removing at that
        # instant - 0.2 to 0.4 mm, on every roughing pass, all of it noise.
        # A RAPID is tested BEFORE anything is cut, because a rapid is not
        # entitled to remove metal at all.
        if m.kind != 'rapid':
            field.cut_move(m.a, m.b, nose_r, d)
        pts = whole if m.kind == 'rapid' else body
        dz, dx = m.b[2] - m.a[2], m.b[0] - m.a[0]
        steps = max(2, int(max(abs(dz), abs(dx)) / STEP_MM) + 1)
        worst, where = None, None
        for k in range(steps + 1):
            f = k / float(steps)
            pz, px = m.a[2] + dz * f, m.a[0] + dx * f
            for tz, tx in pts:
                depth = _inside(field, pz + tz, px + tx, floor)
                if depth is not None and (worst is None or depth > worst):
                    worst, where = depth, (pz + tz, px + tx)
        if worst is not None:
            prev = acc[i - 1] if i else 0.0
            out.append(Collision(i, RAPID_HIT if m.kind == 'rapid'
                                 else BODY_HIT, where, worst,
                                 (prev / total) if total else 0.0))
            if len(out) >= limit:
                break
        if m.kind == 'rapid':
            # a rapid that ploughs through metal has still moved it, and
            # leaving it in place would report every later move as a collision
            field.cut_move(m.a, m.b, nose_r, d)
    return out


def _nose_c(nose_r, orient):
    """Nose centre offset from the control point, in tool coordinates."""
    rz, rx = nose_offset(orient)
    return (rz * nose_r, rx * nose_r)


def draw_stock_field(cr, field, plane, s, ox, oy, classes=None):
    """Fill what is left of the material.

    With `classes` from compare_field the fill is banded by classification;
    without it the whole silhouette is one colour. Consecutive columns of the
    same class are merged into runs before filling - a field is several
    thousand columns wide, and one Cairo path per column would make every
    redraw a slideshow.
    """
    if field.n <= 0:
        return
    ia, ib = _plane_indices(plane)

    def scr(z, r):
        v = [0.0, 0.0, 0.0]
        v[2], v[0] = z, r
        return v[ia] * s + ox, v[ib] * s + oy

    def fill_run(i0, i1, colour):
        # +1 column of overlap so neighbouring runs meet with no seam
        hi = min(i1 + 1, field.n - 1)
        cr.set_source_rgba(*(colour + (0.9,)))
        cr.move_to(*scr(field.z0 + (i0 + 0.5) * field.dz, field.outer[i0]))
        for i in range(i0, hi + 1):
            cr.line_to(*scr(field.z0 + (i + 0.5) * field.dz, field.outer[i]))
        for i in range(hi, i0 - 1, -1):
            cr.line_to(*scr(field.z0 + (i + 0.5) * field.dz, field.inner[i]))
        cr.close_path()
        cr.fill()

    if classes is None:
        fill_run(0, field.n - 1, COL['stock'])
        return

    run_start, run_cls = 0, classes[0]
    for i in range(1, field.n):
        if classes[i] != run_cls:
            fill_run(run_start, i - 1, CMP_COL.get(run_cls, COL['stock']))
            run_start, run_cls = i, classes[i]
    fill_run(run_start, field.n - 1, CMP_COL.get(run_cls, COL['stock']))


# ---------------------------------------------------------------------------
# comparison: how the remaining material differs from the part
# ---------------------------------------------------------------------------
UNCUT, EXCESS, IN_TOL, GOUGE = 0, 1, 2, 3

CMP_COL = {
    EXCESS:  (0.25, 0.45, 0.85),     # material still standing proud
    IN_TOL:  (0.30, 0.72, 0.35),     # on size
    GOUGE:   (0.85, 0.22, 0.22),     # cut past the part - red, as errors are
    UNCUT:   (0.32, 0.30, 0.26),     # outside the profile: nothing to compare
}


def profile_radius_at(z, points):
    """Target RADIUS of the finished part at this Z, or None off its ends.

    `points` are (z, diameter) as lathe_sections.resolve_points returns them -
    the same list the G-code is generated from, so the thing being compared
    against is the part itself and not a second description of it.

    A vertical wall makes the profile multi-valued at its own Z; the outermost
    value bounds the material, so that is the one taken.
    """
    best = None
    for (z0, d0), (z1, d1) in zip(points, points[1:]):
        lo, hi = min(z0, z1), max(z0, z1)
        if not (lo - 1e-9 <= z <= hi + 1e-9):
            continue
        if abs(z1 - z0) < 1e-12:
            r = max(d0, d1) / 2.0
        else:
            t = (z - z0) / (z1 - z0)
            r = (d0 + (d1 - d0) * t) / 2.0
        best = r if best is None else max(best, r)
    return best


def compare_field(field, points, leftover=0.0, tol=0.01):
    """Classify every column of the field against the target profile.

    Mirrors the reference CAM's Comparison colorization:
      - `leftover` is the stock deliberately left ON the part, so deviations are
        measured from that surface rather than from the model. 0 compares
        against the model itself.
      - `tol` is the band either side of it; outside that the material counts as
        excess or gouged.

    Returns a list of UNCUT/EXCESS/IN_TOL/GOUGE, one per column. Columns whose Z
    lies off the ends of the profile are UNCUT rather than being compared
    against nothing - a bar is usually far longer than the part, and calling all
    of that "excess" would drown the part in blue.
    """
    out = []
    if not points or len(points) < 2:
        return [UNCUT] * field.n
    for i in range(field.n):
        z = field.z0 + (i + 0.5) * field.dz
        target = profile_radius_at(z, points)
        if target is None:
            out.append(UNCUT)
            continue
        dev = field.outer[i] - (target + leftover)
        if dev > tol:
            out.append(EXCESS)
        elif dev < -tol:
            out.append(GOUGE)
        else:
            out.append(IN_TOL)
    return out


def compare_summary(classes):
    """{class: column count} - what the Info tab reports."""
    return {c: classes.count(c) for c in (UNCUT, EXCESS, IN_TOL, GOUGE)}


def removed_volume(field):
    """(removed, start) volume in mm^3, by Pappus on each column's ring.

    Each column is an annulus of thickness dz, so its volume is
    pi*(outer^2 - inner^2)*dz. Summing gives what is left; the difference from
    the starting cylinder is what the tool took off.
    """
    start = removed = 0.0
    for i in range(field.n):
        s = math.pi * (field.r_out0 ** 2 - field.r_in0 ** 2) * field.dz
        now = math.pi * (field.outer[i] ** 2 - field.inner[i] ** 2) * field.dz
        start += s
        removed += s - now
    return removed, start


def categorise(moves):
    """Label each move cut / lead / link / connect.

    Unlike the operation and tool tags, this is INFERRED. Nothing in the
    generated code marks a lead, so the rule is positional: a feed that starts
    a run of cutting, or ends one, next to a rapid is the lead in or out; the
    feeds between are the cut. A rapid is a link inside one operation and a
    connection when it crosses between two.

    Said plainly because the distinction matters when reading the display: the
    operation colours are what NativeCAM knows, these are what it reckons.
    """
    out = []
    n = len(moves)
    for i, m in enumerate(moves):
        if m.kind == 'rapid':
            prev_op = moves[i - 1].op if i else None
            nxt_op = moves[i + 1].op if i + 1 < n else None
            cat = CONNECT if (prev_op != m.op or nxt_op != m.op) else LINK
        else:
            before = moves[i - 1].kind if i else 'rapid'
            after = moves[i + 1].kind if i + 1 < n else 'rapid'
            cat = LEAD if (before == 'rapid' or after == 'rapid') else CUT
        out.append(m._replace(cat=cat))
    return out


# Toolpath Mode, as the reference panel names them
MODE_ALL, MODE_BEHIND, MODE_AHEAD, MODE_OPERATION, MODE_TAIL = (
    'all', 'behind', 'ahead', 'operation', 'tail')
TAIL_LEN = 40           # moves shown behind the tool in Tail mode


def visible_moves(tp, mode=MODE_ALL, index=None, show=None, tail=TAIL_LEN):
    """The moves to draw, for a Toolpath Mode and a set of categories.

    `index` is where the tool currently is; without it the mode collapses to
    All, which is what an un-played preview should show.
    """
    moves = tp.moves
    if show is not None:
        moves = [(i, m) for i, m in enumerate(moves) if m.cat in show]
    else:
        moves = list(enumerate(moves))
    if index is None or mode == MODE_ALL:
        return [m for _i, m in moves]
    if mode == MODE_BEHIND:
        return [m for i, m in moves if i <= index]
    if mode == MODE_AHEAD:
        return [m for i, m in moves if i >= index]
    if mode == MODE_TAIL:
        return [m for i, m in moves if index - tail <= i <= index]
    if mode == MODE_OPERATION:
        op = tp.moves[index].op if 0 <= index < len(tp.moves) else None
        return [m for _i, m in moves if m.op == op]
    return [m for _i, m in moves]


# A stable palette for per-operation / per-tool colouring. Stable matters: the
# same operation must keep its colour between redraws and between regenerates,
# or the display becomes a kaleidoscope every time anything is edited.
PALETTE = [(0.36, 0.85, 0.40), (0.35, 0.60, 0.95), (0.95, 0.70, 0.25),
           (0.85, 0.40, 0.80), (0.40, 0.85, 0.85), (0.90, 0.45, 0.35),
           (0.70, 0.80, 0.35), (0.60, 0.55, 0.95)]


def palette_colour(key, order):
    """Colour for `key`, by its position in `order`. Unknown keys go grey."""
    try:
        return PALETTE[order.index(key) % len(PALETTE)]
    except (ValueError, AttributeError):
        return COL['rapid']


def phase_colour(m):
    """Plain-mode colour for one move, by which pass of the op it belongs to.

    Roughing keeps the plain feed colour, so what changes colour is what is
    actually cutting the finished surface.

    Rapids stay rapid-coloured whatever phase they are in - they are already
    dashed and grey everywhere else, and recolouring them would say the machine
    is cutting where it is not.
    """
    if m.kind == 'rapid':
        return COL['rapid']
    # pre-finish first: on the polyline the finish loop and the pre-finish pass
    # are separate brackets, but a nested one must not be masked by an outer
    if PREFINISH in m.subs:
        return COL['prefinish']
    if FINISH in m.subs:
        return COL['finish']
    return COL['feed']


def phases_in(moves):
    """Which sub-phases this toolpath actually contains, in PHASES order."""
    seen = {s for m in moves for s in m.subs}
    return tuple(p for p in PHASES if p in seen)


def has_phase(moves, name=None):
    """True when any move carries `name`, or any known phase when name is None."""
    if name is None:
        return bool(phases_in(moves))
    return any(name in m.subs for m in moves)


# resolve_points works in DIAMETERS; the plot works in radius, as canon does
PROFILE_DIA = 2.0


def _draw_profile(cr, pts, pt, colour, width, dash):
    """One contour, in (z, diameter) as resolve_points returns it."""
    if len(pts) < 2:
        return
    cr.set_source_rgb(*colour)
    cr.set_line_width(width)
    cr.set_dash(dash or [])
    first = True
    for z, x in pts:
        px, py = pt((x / PROFILE_DIA, 0.0, z))
        if first:
            cr.move_to(px, py)
            first = False
        else:
            cr.line_to(px, py)
    cr.stroke()
    cr.set_dash([])
