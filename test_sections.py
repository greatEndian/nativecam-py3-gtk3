#!/usr/bin/env python3
# coding: utf-8
"""Checks lathe_sections against the record array the machine really builds.

Standalone, like the other test_*.py here - run it directly, no pytest.

Sectioning decides where roughing windows fall, so a profile it resolves
differently from the one the machine cuts produces windows for a shape that
does not exist. Nothing here reads the cfg text and calls that a test. It
builds the same poly_add_item calls the cfgs emit, runs them through rs274,
dumps the resulting record array field by field, and requires
resolve_segments() to agree with it - endpoint, direction and arc centre - for
every item type the lathe polyline offers. The arc subdivision is then checked
the same way, against poly_mesh_lathe.ngc's own output.

Needs rs274 and the ncam_demo sim config; skips with a clear message without.
"""
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '.claude', 'skills', 'lathe-gcode-verify', 'scripts'))

import lathe_sections as ls  # noqa: E402

INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
DM = 2.0
TOL = 1e-3
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


# --- stand-ins for Feature/Parameter, just enough for resolve_segments ------
class P(object):
    def __init__(self, v):
        self.v = v

    def get_ngc_value(self):
        return self.v


class Child(object):
    def __init__(self, kind, **params):
        self.kind = kind
        self.params = params

    def get_attr(self, a):
        return self.kind if a == 'type' else None

    def get_param(self, n):
        return P(self.params[n]) if n in self.params else None


class Poly(Child):
    def __init__(self, b_z, b_x, kids):
        Child.__init__(self, 'polyline', param_b_z=str(b_z), param_b_x=str(b_x))
        self.child_features = kids


def line_to(x, z, item_type=1, m_r=0.0):
    return Child('poly-line-to', param_act='1', param_type=str(item_type),
                 param_x=str(x), param_z=str(z),
                 param_m_style='1' if m_r else '0', param_m_r=str(m_r))


def polar(length, angle, pos_ref=2, ang_ref=0):
    return Child('poly-line-polar', param_act='1', param_l=str(length),
                 param_a=str(angle), param_type=str(pos_ref),
                 param_a_ref=str(ang_ref))


def arc_to(x, z, size, item_type=5, atype=0, direction=2, rev=0):
    return Child('poly_arc_to_coords', param_act='1', param_type=str(item_type),
                 param_x=str(x), param_z=str(z), param_atype=str(atype),
                 param_height=str(size), param_dir=str(direction), param_rev=str(rev))


def arc_ij(i, k, angle, item_type=6, etype=0, direction=3):
    return Child('poly_arc_IJ', param_act='1', param_type=str(item_type),
                 param_i=str(i), param_k=str(k), param_a=str(angle),
                 param_etype=str(etype), param_dir=str(direction))


# --- the same poly_add_item calls cfg/lathe/polyline-*.cfg emit -------------
def item_call(k):
    p = k.params
    if k.kind == 'poly-line-to':
        return ("o<poly_add_item> CALL [%s] [%s] [%s / #<_diameter_mode>] "
                "[1] [%s] [%s] [0] [1] [0] [0] [0]"
                % (p['param_type'], p['param_z'], p['param_x'],
                   p['param_m_style'], p['param_m_r']))

    if k.kind == 'poly-line-polar':
        pos = int(float(p['param_type']))
        aref = int(float(p['param_a_ref']))
        length, angle = p['param_l'], p['param_a']
        if pos == 1:
            return ("o<poly_add_item> CALL [12] [%s] [%s] [1] [0] [0] [0] [1] [0] [0] [0]"
                    % (length, angle))
        t = 3 if aref == 1 else (30 if aref == 2 else 2)
        return ("o<poly_add_item> CALL [%d] [%s * COS[%s]] [%s * SIN[%s]] "
                "[1] [0] [0] [0] [1] [0] [0] [0]"
                % (t, length, angle, length, angle))

    if k.kind == 'poly_arc_to_coords':
        return ("o<poly_add_item> CALL [%s] [%s] [%s / #<_diameter_mode>] [%s] "
                "[0] [0] [0] [1] [%s] [%s] [%s]"
                % (p['param_type'], p['param_z'], p['param_x'], p['param_dir'],
                   p['param_height'], p['param_atype'], p['param_rev']))

    # Arc I,K - the cfg divides I by the diameter mode only when it is an
    # absolute centre, not when it is an offset
    t = int(float(p['param_type']))
    x_val = p['param_i'] + (' / #<_diameter_mode>' if t in (7, 61) else '')
    return ("o<poly_add_item> CALL [%s] [%s] [%s] [%s] [0] [0] [0] [1] [%s] [%s] [0]"
            % (p['param_type'], p['param_k'], x_val, p['param_dir'],
               p['param_a'], p['param_etype']))


def gcode_for(poly, mesh=False):
    out = ["G21", "G18 G40 G49 G90 G92.1 G94 G54 G64 p0.001",
           "#<_diameter_mode> = %.1f" % DM, "#<in_polyline> = 0",
           "o<poly_add_item> CALL [-1] [%s] [%s / #<_diameter_mode>] "
           "[0] [0] [0] [0] [0] [0] [0] [0]"
           % (poly.params['param_b_z'], poly.params['param_b_x'])]
    out += [item_call(k) for k in poly.child_features]
    out += ["o<poly_create> CALL", "o<poly_copy_lathe> CALL [70]"]

    if mesh:
        # the mesh array is laid out past the forward one, exactly as
        # poly_lathe_mill.ngc lays it out
        out += ["#<md> = [70 + #[70] * 8 + 1]",
                "o<poly_mesh_lathe> CALL [70] [#<md>] [0.005]",
                "#<n> = #[#<md>]", "#<p> = [#<md> + 1]", "#<i> = 0",
                "o<dump> while [#<i> LT #<n>]",
                "\tG0 X#[#<p>] Z#[#<p> + 1]",
                "\t#<p> = [#<p> + 8]", "\t#<i> = [#<i> + 1]",
                "o<dump> endwhile"]
    else:
        # three rapids per record: endpoint, direction, arc centre. Duplicate
        # rapids are emitted by the interpreter, so the triples never desync.
        out += ["#<n> = #[70]", "#<p> = 71", "#<i> = 0",
                "o<dump> while [#<i> LT #<n>]",
                "\tG0 X#[#<p>] Z#[#<p> + 1]",
                "\tG0 X#[#<p> + 2] Z0",
                "\tG0 X#[#<p> + 3] Z#[#<p> + 4]",
                "\t#<p> = [#<p> + 8]", "\t#<i> = [#<i> + 1]",
                "o<dump> endwhile"]
    out += ["M2", ""]
    return "\n".join(out)


def trace(poly, mesh=False):
    """Rapids the dump loop emits, as (first_word, second_word) pairs."""
    from parse_rs274 import run_rs274, parse_canon
    d = tempfile.mkdtemp(prefix='test_sections_')
    try:
        path = os.path.join(d, 'p.ngc')
        with open(path, 'w') as f:
            f.write(gcode_for(poly, mesh))
        canon, _raw = run_rs274(INI, path)
        bad = [ln for ln in canon.splitlines()
               if 'error' in ln.lower() and 'COMMENT(' not in ln
               and 'error_code' not in ln.lower()]
        if bad:
            raise AssertionError('interpreter error: %s' % bad[0].strip()[:130])
        # the dump writes each record field as the X word and the next as Z
        return [(m['x'], m['z']) for m in parse_canon(canon) if m['kind'] == 'rapid']
    finally:
        shutil.rmtree(d, ignore_errors=True)


def machine_records(poly):
    """The record array as a list of dicts, straight off the interpreter."""
    raw = trace(poly)
    out = []
    for i in range(0, len(raw) - 2, 3):
        out.append({'z': raw[i][0], 'r': raw[i][1], 'dir': int(round(raw[i + 1][0])),
                    'cz': raw[i + 2][0], 'cr': raw[i + 2][1]})
    return out


def fmt(recs):
    return ['(%.3f, %.3f) dir%d c(%.3f, %.3f)'
            % (r['z'], r['r'], r['dir'], r['cz'], r['cr']) for r in recs]


def same_record(a, b):
    if a['dir'] != b['dir']:
        return False
    if abs(a['z'] - b['z']) > TOL or abs(a['r'] - b['r']) > TOL:
        return False
    if a['dir'] not in (2, 3):
        return True          # centre fields are unused on a straight record
    return abs(a['cz'] - b['cz']) <= TOL and abs(a['cr'] - b['cr']) <= TOL


def compare(name, poly):
    """resolve_segments must reproduce the record array exactly."""
    want = machine_records(poly)
    resolved = ls.resolve_segments(poly)
    if resolved is None:
        check(name, False, 'resolve_segments returned None - sectioning would be off')
        return
    got = resolved[1]
    ok = len(got) == len(want) and all(same_record(a, b) for a, b in zip(got, want))
    check(name, ok, '' if ok else '\n      resolved=%s\n      machine =%s'
          % (fmt(got), fmt(want)))


def compare_mesh(name, poly):
    """The Python subdivision must reproduce poly_mesh_lathe.ngc's own."""
    want = trace(poly, mesh=True)
    resolved = ls.resolve_segments(poly)
    if resolved is None:
        check(name, False, 'resolve_segments returned None')
        return
    origin, segs = resolved
    got = []
    pz, pr = origin
    for index, seg in enumerate(segs):
        if index > 0 and seg['dir'] in (2, 3):
            got.extend(ls._densify_arc(pz, pr, seg))
        else:
            got.append((seg['z'], seg['r']))
        pz, pr = seg['z'], seg['r']

    ok = (len(got) == len(want) and
          all(abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL
              for a, b in zip(got, want)))
    check(name, ok, '%d python points vs %d mesh records%s'
          % (len(got), len(want),
             '' if ok else '\n      first mismatch: %s'
             % next(('py %s / mesh %s' % (a, b) for a, b in zip(got, want)
                     if abs(a[0] - b[0]) > TOL or abs(a[1] - b[1]) > TOL), 'length only')))


def main():
    if shutil.which('rs274') is None:
        print('SKIP - rs274 not on PATH; this test needs the LinuxCNC interpreter')
        return
    if not os.path.exists(INI):
        print('SKIP - demo ini not found at %s' % INI)
        return

    # ---- Line To, every position mode -------------------------------------
    compare('line-to, absolute',
            Poly(0, 60, [line_to(40, 0), line_to(40, -15), line_to(60, -15)]))
    compare('line-to, relative and both mixed modes',
            Poly(0, 60, [line_to(40, 0), line_to(0, -10, item_type=0),
                         line_to(60, 0, item_type=10), line_to(-30, 0, item_type=11)]))
    compare('a line-to that lands where the profile already is is not recorded',
            Poly(0, 60, [line_to(40, 0), line_to(40, 0), line_to(40, -15)]))

    # ---- Line Polar, every reference combination ---------------------------
    compare('polar step, angle from Z+',
            Poly(0, 60, [line_to(40, 0), polar(25, 45)]))
    compare('polar step, negative length',
            Poly(0, 60, [line_to(40, 0), polar(-25, 45)]))
    compare('polar step, angle from the previous line',
            Poly(0, 60, [line_to(40, 0), line_to(50, -20), polar(20, 30, ang_ref=1)]))
    compare('polar step, angle from the previous line, second case',
            Poly(0, 60, [line_to(40, 0), line_to(20, -12), polar(15, -60, ang_ref=1)]))
    compare('polar step, angle from the previous arc centre',
            Poly(0, 60, [line_to(40, 0), arc_ij(-6, 0, 90), polar(20, 30, ang_ref=2)]))
    compare('polar step, arc-centre reference falls back to the chord after a line',
            Poly(0, 60, [line_to(40, 0), line_to(50, -20), polar(20, 30, ang_ref=2)]))
    compare('polar from origin',
            Poly(0, 60, [line_to(40, 0), line_to(40, -10), polar(-40, -45, pos_ref=1)]))
    compare('polar from origin at 0 deg is parallel to Z',
            Poly(0, 60, [line_to(40, 0), line_to(40, -10), polar(-40, 0, pos_ref=1)]))

    # ---- Arc To Coords -----------------------------------------------------
    compare('arc to coords, absolute, radius, CW',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10)]))
    compare('arc to coords, absolute, radius, CCW',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10, direction=3)]))
    compare('arc to coords, flipped centre puts the arc on the other side',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10, rev=1)]))
    compare('arc to coords, relative',
            Poly(0, 60, [line_to(40, 0), arc_to(20, -10, 10, item_type=4)]))
    compare('arc to coords, Z relative and X absolute',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10, item_type=41)]))
    compare('arc to coords, Z absolute and X relative',
            Poly(0, 60, [line_to(40, 0), arc_to(20, -10, 10, item_type=42)]))
    compare('arc to coords, defined by arc height',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 3, atype=1)]))
    compare('arc to coords, arc height flipped',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 3, atype=1, rev=1)]))
    # a radius smaller than half the chord cannot span it - the interpreter
    # gives up and cuts a straight line, and the analysis has to agree
    compare('a radius too small for its chord degenerates to a line',
            Poly(0, 60, [line_to(40, 0), arc_to(60, -30, 2)]))

    # ---- Arc I,K -----------------------------------------------------------
    compare('arc I,K, offsets, CCW',
            Poly(0, 60, [line_to(40, 0), arc_ij(0, -8, 90)]))
    compare('arc I,K, offsets, CW sweeps the other way',
            Poly(0, 60, [line_to(40, 0), arc_ij(0, -8, 90, direction=2)]))
    compare('arc I,K, absolute centre',
            Poly(0, 60, [line_to(40, 0), arc_ij(20, -8, 60, item_type=7)]))
    compare('arc I,K, K offset with X absolute',
            Poly(0, 60, [line_to(40, 0), arc_ij(20, -8, 60, item_type=61)]))
    compare('arc I,K, K absolute with X offset',
            Poly(0, 60, [line_to(40, 0), arc_ij(6, -8, 60, item_type=62)]))
    compare('arc I,K, angle absolute about the centre',
            Poly(0, 60, [line_to(40, 0), arc_ij(0, -8, 200, etype=1)]))

    # ---- mixed profiles, the shapes that actually get drawn ----------------
    mixed = Poly(0, 60, [line_to(40, 0.5), line_to(40, -8), arc_to(50, -13, 5),
                         line_to(50, -25), arc_ij(0, -5, 90), line_to(60, -32)])
    compare('a mixed line/arc/arc-ij profile', mixed)

    reported = Poly(0, 60, [line_to(40, 0.5), line_to(40, -8), polar(-10, 45),
                            line_to(0, -25, item_type=0), line_to(60, 0, item_type=10)])
    compare('the testing_12_3 shape', reported)

    # ---- subdivision must match the runtime mesh, not just look plausible --
    compare_mesh('arc subdivision matches poly_mesh_lathe',
                 Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10), line_to(60, -20)]))
    compare_mesh('a large radius subdivides the same way',
                 Poly(0, 60, [line_to(40, 0), arc_to(80, -40, 40), line_to(80, -50)]))
    compare_mesh('a CW arc subdivides the same way',
                 Poly(0, 60, [line_to(40, 0), arc_to(60, -10, 10, direction=3),
                              line_to(60, -20)]))
    compare_mesh('an arc-I,K subdivides the same way',
                 Poly(0, 60, [line_to(40, 0), arc_ij(0, -8, 90), line_to(60, -20)]))
    compare_mesh('a mixed profile subdivides the same way', mixed)

    # ---- what the sectioning layer then does with all this ------------------
    for name, poly in (('a polar profile', reported), ('an arc profile', mixed)):
        pts = ls.resolve_points(poly)
        check('%s no longer disables sectioning' % name, pts is not None)
        if not pts:
            continue
        secs = ls.detect_sections(pts)
        check('%s yields at least one section' % name, len(secs) >= 1,
              'sections=%d from %d points' % (len(secs), len(pts)))
        wins = ls.band_windows(secs, ls.rank_weakest_first(secs), pts)
        check('%s yields banded windows to drive roughing' % name, len(wins) >= 1,
              'windows=%d' % len(wins))

    # an arc must be analysed as the curve it is, not as its chord: the mid
    # point of a convex arc stands proud of the chord by the sagitta, and it
    # is that material a roughing level has to stop against
    bulge = Poly(0, 60, [line_to(40, 0), line_to(40, -5),
                         arc_to(40, -25, 12, direction=3, rev=1), line_to(60, -30)])
    pts = ls.resolve_points(bulge)
    check('an arc is resolved as a curve, not as its chord',
          pts is not None and len(pts) > 4, 'points=%s' % (len(pts) if pts else None))
    if pts:
        arc_pts = [p for p in pts if -25 < p[0] < -5]
        peak = max(p[1] for p in arc_pts) if arc_pts else 0.0
        # R12 across a 20 mm chord: sagitta = 12 - sqrt(144 - 100) = 5.367 mm
        # of radius, so the profile reaches 40 + 2 * 5.367 in diameter
        check('the arc bulge reaches its true crest, not the chord',
              abs(peak - (40.0 + 2 * (12.0 - math.sqrt(144.0 - 100.0)))) < 0.05,
              'crest D%.3f' % peak)

    # ---- the safety valve still works --------------------------------------
    check('an item type this module does not model still returns None',
          ls.resolve_points(Poly(0, 60, [line_to(40, 0), Child('poly-line-mirror')])) is None)
    check('a Line To missing a parameter returns None',
          ls.resolve_points(Poly(0, 60, [Child('poly-line-to', param_act='1')])) is None)
    check('an Arc To Coords missing its size returns None',
          ls.resolve_points(Poly(0, 60, [
              Child('poly_arc_to_coords', param_act='1', param_type='5',
                    param_x='60', param_z='-10')])) is None)

    test_entry_contour()
    test_table_layout()

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All section resolution tests passed.')



def test_entry_contour():
    """Where a roughing level may BEGIN cutting.

    The level stops on the floor allowance - by then it is already down on the
    floor - but against the shallow ramp a peak leaves behind, that allowance
    costs its own length over the sine of the ramp angle before the cut even
    starts: 4.51 mm per level and 36.1 mm of metal on testing_15_2.

    The offset rule has to be IDENTICAL to lathe_level_pass's own, because the
    entry and the stop are compared against each other. So it is checked as a
    perpendicular distance from each segment, which is what that subroutine
    computes with its own normals.
    """
    import lathe_sections as L
    prof = [(0.0, 40.0), (-10.0, 40.0), (-10.0, 22.0), (-90.0, 22.0)]

    env = L.entry_contour(prof, 1.0, 0)
    check('every segment contributes both its offset ends',
          len(env) == 2 * (len(prof) - 1), '%d points' % len(env))

    worst = 0.0
    for i, (a, b) in enumerate(zip(prof, prof[1:])):
        dz, dx = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dz, dx)
        for p in (env[2 * i], env[2 * i + 1]):
            d = abs((p[0] - a[0]) * dx - (p[1] - a[1]) * dz) / n
            worst = max(worst, abs(d - 1.0))
    check('every offset point is exactly the offset from its own segment',
          worst < 1e-9, 'worst error %.3e' % worst)

    # the side matters: outward means away from the material, and it flips
    # with the roughing direction exactly as flank_sides does
    fwd = L.entry_contour(prof, 1.0, 0)
    rev = L.entry_contour(prof, 1.0, 1)
    check('the offset side follows the roughing direction',
          fwd != rev, 'front-to-back and back-to-front came out identical')
    check('front to back offsets AWAY from the axis',
          fwd[0][1] > prof[0][1], 'r%.3f against r%.3f' % (fwd[0][1], prof[0][1]))
    check('back to front offsets the other way',
          rev[0][1] < prof[0][1], 'r%.3f against r%.3f' % (rev[0][1], prof[0][1]))

    # it scales, rather than being right at one value by luck
    for d in (0.25, 0.508, 2.0):
        e = L.entry_contour(prof, d, 0)
        got = e[0][1] - prof[0][1]
        check('an offset of %g moves the contour %g' % (d, d),
              abs(got - d) < 1e-9, 'moved %.6f' % got)

    # THE trap, and it was live: the profile arrives in DIAMETERS and the
    # offset is a RADIUS. A perpendicular offset is not the same construction
    # in the two spaces - a ramp that measures 13 degrees in radius measures
    # 24.78 in diameter - so offsetting there and halving afterwards gives
    # 1.129 mm of Z where 2.258 is wanted. Silent, and exactly half.
    ramp = [(0.0, 20.0), (-40.0, 20.0 - 40.0 * math.tan(math.radians(13.0)))]
    off = L.entry_contour(ramp, 0.508, 0)
    # where the offset ramp reaches the radius the bare one has at Z-20
    r_at = ramp[0][1] - 20.0 * math.tan(math.radians(13.0))
    (z0, r0), (z1, r1) = off[0], off[1]
    z_off = z0 + (z1 - z0) * (r_at - r0) / (r1 - r0)
    shift = abs(z_off - (-20.0))
    want = 0.508 / math.sin(math.radians(13.0))
    check('a 0.508 offset shifts a 13 deg ramp by 2.258 mm of Z',
          abs(shift - want) < 1e-6,
          'shifted %.4f, wanted %.4f - the diameter/radius factor is back'
          % (shift, want))

    check('no offset, no contour change', L.entry_contour(prof, 0.0, 0) == prof)
    check('a degenerate profile comes back untouched',
          L.entry_contour([(0.0, 1.0)], 1.0, 0) == [(0.0, 1.0)])
    check('and zero-length segments are dropped, not divided by',
          len(L.entry_contour([(0.0, 10.0), (0.0, 10.0), (-5.0, 10.0)],
                              1.0, 0)) == 2)


def test_table_layout():
    """The fixed parameter-table regions must not overlap.

    Each table is written in emission order, so a later one silently overwrites
    an earlier one and the damage shows up only as motion that makes no sense.
    The finish-contour table was first placed at 3500 with room for 130 slots
    and ran straight through the flank envelope at 3600: roughing then stopped
    4 mm above its floor and drove through the boss it was supposed to split
    around, with no error anywhere.
    """
    import lathe_sections as L
    regions = [('sections', L.SECT_BASE, L.FLANK_BASE),
               ('flank envelope', L.FLANK_BASE, L.FLANK_TOP),
               ('finish contour', L.FC_BASE, L.FC_TOP),
               ('entry contour', L.ENTRY_BASE, L.ENTRY_TOP),
               ('In-CAM offsets', L.CAM_BASE, L.CAM_TOP)]
    for i in range(len(regions) - 1):
        n0, _b0, t0 = regions[i]
        n1, b1, _t1 = regions[i + 1]
        check('%s ends before %s begins' % (n0, n1), t0 <= b1,
              '%s top %d overlaps %s base %d' % (n0, t0, n1, b1))
    check('every region is non-empty', all(t > b for _n, b, t in regions))
    check('nothing runs into LinuxCNC own parameters at 5060',
          max(t for _n, _b, t in regions) <= 5060,
          'top is %d' % max(t for _n, _b, t in regions))


if __name__ == '__main__':
    main()
