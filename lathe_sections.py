"""Lathe polyline Sectioning: profile-wall detection and rigidity ranking,
computed in Python at G-code generation time instead of at G-code runtime.

Two on-modes share this module: "Natural" (profile-wall sections only)
and "Artificial" (those same natural sections further sliced into
param_sec_len-long pieces) - see build_sections_gcode()'s own docstring
for how the mode is selected and why subdividing rather than replacing
natural boundaries is the whole point of "Artificial" existing at all.

Standalone on purpose - no import of ncam/Feature - so it stays independently
unit-testable with plain python3 and has no circular-import risk with ncam.py
(which imports this module and calls build_sections_gcode from a <exec> tag
in cfg/lathe/polyline.cfg's [AFTER] content).

Resolves every item type the lathe polyline offers: Line To, Line Polar,
Arc To Coords and Arc I,K. Arcs are subdivided into sub-chords on the true
radius, by the same rule poly_mesh_lathe.ngc uses at runtime, so a radius is
analysed as the curve it is and not as the chord across it. Anything else -
an item type added later, or a missing parameter - still makes
resolve_points() return None, so build_sections_gcode() emits nothing and
poly_lathe_mill.ngc's own _pl_sect_count > 0 gate falls back to plain
(Sectioning-off) windowing. A wrong-but-plausible section list is more
dangerous than no section list at all, since an unmodelled item could reach
a radius the analysis never saw - which is why the resolution here is checked
against the record array the machine actually builds, in test_sections.py,
not against the cfg text.
"""

import math

EPS = 0.0001


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _fmt(val):
    # These become the #3401+ window bounds, which decide where a roughing
    # level stops. Six decimals is 0.001 mm in a metric program but 0.025 mm in
    # an inch one, and that quantisation showed up directly as ~0.025 mm of
    # drift in the level stops when the same part was generated both ways.
    # Eight costs nothing in metric and removes it.
    return '%0.8f' % val


def resolve_points(polyline_feature):
    """Ordered list of (z, x) absolute points for each active polyline
    child, in the same units the child's own param_x/param_z are entered
    in (diameter units as typed - see module docstring in the plan:
    diameter-vs-radius is a uniform scale that doesn't affect wall
    detection or ranking, only the final ceiling value, which
    poly_lathe_mill.ngc itself divides by #<_diameter_mode> on the way in).

    The polyline's own Start Z/Start Diameter (the "origin") is used only
    to resolve the first child's relative coordinates - it is NOT included
    in the returned list, matching the real G-code record array built by
    poly_add_item/poly_create, which likewise never stores the origin as
    a record (a poly_add_item CALL [-1] ... init call, not a real point).
    Folding the origin in as a real point is actively wrong, not just
    redundant: if the origin's own diameter happens to be on the opposite
    side of the first child's diameter from where the child's *own* next
    neighbor sits (a common case - the origin is stock diameter, and the
    profile immediately drops to something smaller and then features a
    peak), the origin's transition into record 1 registers as its own
    direction reversal, and record 1's true value gets discarded by the
    zero-length guard before it can seed a section's minimum. Whether the
    origin sits above or below the whole recorded profile is exactly what
    the ceiling's clamp against start_radius in poly_lathe_mill.ngc is
    already for - this function has no need to duplicate that.

    Returns None if any child item is of a kind this module cannot resolve,
    or if a param is missing - callers must treat None as "can't safely
    analyze this profile", not as an empty result.
    """
    resolved = resolve_segments(polyline_feature)
    if resolved is None:
        return None
    origin, segments = resolved

    points = []
    merges = []
    prev_z, prev_r = origin

    for index, seg in enumerate(segments):
        # An arc reaches the analysis as the straight chord between its two
        # endpoints unless it is broken up here, and the chord runs through
        # material the arc itself leaves standing. That is the same error
        # poly_mesh_lathe.ngc exists to remove at runtime, so this uses its
        # subdivision rule verbatim - see _densify_arc.
        #
        # The first record is the exception, and deliberately so: it is the
        # profile's start point, no recorded segment leads into it, and
        # poly_mesh_lathe copies it through without subdividing. The level
        # scans are blind to the run from the origin into it for the same
        # reason. Densifying it here would give the analysis points the scans
        # can never stop against, which is exactly the mismatch this module
        # exists to avoid.
        if index > 0 and seg['dir'] in (ARC_CW, ARC_CCW):
            span = _densify_arc(prev_z, prev_r, seg)
        else:
            span = [(seg['z'], seg['r'])]

        for i, (z, r) in enumerate(span):
            points.append((z, r * DIAMETER_MODE))
            # the merge radius rounds the vertex where this item BEGINS, so
            # it belongs to the first sub-point only; apply_merge_radii reads
            # merges[j + 1] as the radius rounding points[j]
            merges.append(seg['merge'] if i == 0 else 0.0)

        prev_z, prev_r = seg['z'], seg['r']

    return apply_merge_radii(points, merges)


# X is entered and carried here as a diameter, while a polar length, an arc
# radius and the fillet maths are lengths in the Z/radius plane.
# #<_diameter_mode> is a fixed 2.0 everywhere in this project - it is set once
# in Preferences.create_defaults and never reassigned in cfg/ or lib/ - so the
# conversion is a constant. resolve_segments works entirely in radius units,
# the units the record array itself holds; only resolve_points converts back.
DIAMETER_MODE = 2.0

# a record's dir field carries the G-code word itself for arcs
ARC_CW = 2
ARC_CCW = 3

# item kinds this module can resolve, and the cfg they come from
LINE_TO = 'poly-line-to'
LINE_POLAR = 'poly-line-polar'
ARC_TO_COORDS = 'poly_arc_to_coords'
ARC_IJ = 'poly_arc_IJ'

# param_type on a Line Polar: where the LENGTH is measured from.
POLAR_FROM_ORIGIN = 1
# param_a_ref: what the ANGLE is measured from.
POLAR_ANGLE_PREV_LINE = 1
POLAR_ANGLE_PREV_ARC = 2

# the sagitta poly_lathe_mill.ngc asks poly_mesh_lathe for
MESH_MAX_SAG = 0.005


def _phi(z1, r1, z2, r2):
    """Direction from point 1 to point 2, degrees 0-360.

    lib/utilities/line.ngc, which every angle in poly_add_item comes from,
    including its snap to a vertical when the Z travel is negligible.
    """
    dz, dr = z2 - z1, r2 - r1
    if abs(dz) >= 0.000001:
        return math.degrees(math.atan2(dr, dz)) % 360.0
    return 90.0 if dr >= 0 else 270.0


def resolve_segments(polyline_feature):
    """(origin, segments) mirroring the record array poly_add_item builds,
    or None if any item cannot be resolved.

    Each segment is a dict with the same fields a record carries - z, r, dir,
    cz, cr - in radius units, plus the merge radius the item asks for. This is
    deliberately a record-for-record mirror rather than a convenient shape of
    its own: it is what lets test_sections.py diff it against the array the
    interpreter actually builds, which is the only way to know the analysis
    and the machine are looking at the same profile.

    The origin is returned separately because poly_add_item's [-1] init call
    is not a record - see resolve_points on why folding it in is wrong.
    """
    b_z_param = polyline_feature.get_param('param_b_z')
    b_x_param = polyline_feature.get_param('param_b_x')
    if b_z_param is None or b_x_param is None:
        return None

    origin = (_to_float(b_z_param.get_ngc_value()),
              _to_float(b_x_param.get_ngc_value()) / DIAMETER_MODE)
    prev_z, prev_r = origin

    # the record fields poly_add_item reads back off the PREVIOUS record when
    # it resolves a relative item. prev_ph is field +5 and prev_rh field +6;
    # both are zero before the first record exists, from the init call.
    prev_ph = 0.0
    prev_rh = 0.0
    prev_d = 0

    segments = []

    for child in getattr(polyline_feature, 'child_features', []):
        kind = child.get_attr('type')
        if kind not in (LINE_TO, LINE_POLAR, ARC_TO_COORDS, ARC_IJ):
            return None

        act_param = child.get_param('param_act')
        if act_param is not None and _to_float(act_param.get_ngc_value()) <= 0:
            continue

        if kind == LINE_TO:
            resolved = _resolve_line_to(child, prev_z, prev_r)
        elif kind == LINE_POLAR:
            resolved = _resolve_polar(child, prev_z, prev_r, prev_ph, prev_rh, prev_d)
        elif kind == ARC_TO_COORDS:
            resolved = _resolve_arc_to_coords(child, prev_z, prev_r)
        else:
            resolved = _resolve_arc_ij(child, prev_z, prev_r)

        if resolved is None:
            return None
        new_z, new_r, direction, cz, cr = resolved

        # poly_add_item's own validity_1 guard: an item that lands exactly
        # where the profile already is never becomes a record at all, and the
        # next relative item resolves from the point before it. Emitting it
        # here would put a zero-length segment in front of every analysis
        # walking this list.
        if abs(new_z - prev_z) <= EPS and abs(new_r - prev_r) <= EPS:
            continue

        style_param = child.get_param('param_m_style')
        r_param = child.get_param('param_m_r')
        style = int(_to_float(style_param.get_ngc_value())) if style_param is not None else 0
        radius = _to_float(r_param.get_ngc_value()) if r_param is not None else 0.0

        segments.append({'z': new_z, 'r': new_r, 'dir': direction,
                         'cz': cz, 'cr': cr,
                         'merge': radius if style == MERGE_STYLE_RADIUS and radius > 0 else 0.0})

        # field +5 is the angle from the record BACK to the point before it -
        # the reverse of travel - and field +6 the angle from the record to
        # its own arc centre. Relative polar items are measured from those,
        # so getting the direction of +5 backwards puts every "relative to
        # previous line" item 180 degrees out; caught exactly that way by
        # test_sections.py against the real array.
        prev_ph = _phi(new_z, new_r, prev_z, prev_r)
        prev_rh = _phi(new_z, new_r, cz, cr) if direction in (ARC_CW, ARC_CCW) else prev_ph
        prev_d = direction
        prev_z, prev_r = new_z, new_r

    return origin, segments


def _resolve_line_to(child, prev_z, prev_r):
    """A Line To child, as poly_add_item item types 0, 1, 10 and 11."""
    type_param = child.get_param('param_type')
    z_param = child.get_param('param_z')
    x_param = child.get_param('param_x')
    if type_param is None or z_param is None or x_param is None:
        return None

    item_type = int(_to_float(type_param.get_ngc_value()))
    z = _to_float(z_param.get_ngc_value())
    r = _to_float(x_param.get_ngc_value()) / DIAMETER_MODE

    if item_type == 0:
        new_z, new_r = prev_z + z, prev_r + r
    elif item_type == 10:
        new_z, new_r = prev_z + z, r
    elif item_type == 11:
        new_z, new_r = z, prev_r + r
    else:
        new_z, new_r = z, r
    return new_z, new_r, 1, 0.0, 0.0


def _resolve_polar(child, prev_z, prev_r, prev_ph, prev_rh, prev_d):
    """A Line Polar child, as poly_add_item item types 12, 2, 3 and 30.

    Mirrors cfg/lathe/polyline-polar.cfg's [CALL] exactly - the same four
    combinations of position reference and angle reference. Getting this wrong
    would hand detect_sections a profile the machine never cuts, so it is
    checked against the real record array in test_sections.py rather than by
    reading the cfg.
    """
    l_param = child.get_param('param_l')
    a_param = child.get_param('param_a')
    if l_param is None or a_param is None:
        return None
    length = _to_float(l_param.get_ngc_value())
    angle = _to_float(a_param.get_ngc_value())

    t_param = child.get_param('param_type')
    pos_ref = int(_to_float(t_param.get_ngc_value())) if t_param is not None else 2
    r_param = child.get_param('param_a_ref')
    ang_ref = int(_to_float(r_param.get_ngc_value())) if r_param is not None else 0

    if pos_ref == POLAR_FROM_ORIGIN:
        # length is the Z coordinate itself, measured parallel to Z; the angle
        # is the slope the line runs at, so the radius follows from the travel
        if abs(math.cos(math.radians(angle))) < EPS:
            return length, prev_r, 1, 0.0, 0.0
        d_radius = (length - prev_z) * math.tan(math.radians(angle))
        return length, prev_r + d_radius, 1, 0.0, 0.0

    # a step from the previous point, at an angle that may be measured from
    # whichever direction the record array says the profile came in on
    if ang_ref == POLAR_ANGLE_PREV_ARC:
        angle += prev_rh if prev_d in (ARC_CW, ARC_CCW) else prev_ph
    elif ang_ref == POLAR_ANGLE_PREV_LINE:
        angle += prev_ph
    rad = math.radians(angle)
    return (prev_z + length * math.cos(rad),
            prev_r + length * math.sin(rad), 1, 0.0, 0.0)


def _resolve_arc_to_coords(child, prev_z, prev_r):
    """An Arc To Coords child, as poly_add_item item types 4, 5, 41 and 42.

    The end point comes straight from the coordinates; the centre is what
    takes work. poly_add_item builds it off the chord: for a stated radius by
    stepping the chord's half-height off the chord midpoint, and for a stated
    arc height by intersecting the two perpendicular bisectors through the
    apex. Both are reproduced here rather than replaced with a tidier
    circumcentre, because "Flip center" and the too-short-chord fallback are
    decisions the interpreter makes and the analysis has to make identically.
    """
    type_param = child.get_param('param_type')
    z_param = child.get_param('param_z')
    x_param = child.get_param('param_x')
    h_param = child.get_param('param_height')
    if None in (type_param, z_param, x_param, h_param):
        return None

    item_type = int(_to_float(type_param.get_ngc_value()))
    z = _to_float(z_param.get_ngc_value())
    r = _to_float(x_param.get_ngc_value()) / DIAMETER_MODE
    size = _to_float(h_param.get_ngc_value())

    a_param = child.get_param('param_atype')
    atype = int(_to_float(a_param.get_ngc_value())) if a_param is not None else 0
    d_param = child.get_param('param_dir')
    direction = int(_to_float(d_param.get_ngc_value())) if d_param is not None else ARC_CW
    v_param = child.get_param('param_rev')
    flipped = int(_to_float(v_param.get_ngc_value())) if v_param is not None else 0

    if item_type == 4:
        new_z, new_r = prev_z + z, prev_r + r
    elif item_type == 41:
        new_z, new_r = prev_z + z, r
    elif item_type == 42:
        new_z, new_r = z, prev_r + r
    else:
        new_z, new_r = z, r

    # phi runs from the END back to the start, matching the o<line> call
    # poly_add_item makes here; the centre side is picked off that
    phi = _phi(new_z, new_r, prev_z, prev_r)
    chord = math.hypot(new_z - prev_z, new_r - prev_r)
    mid_z, mid_r = (prev_z + new_z) / 2.0, (prev_r + new_r) / 2.0
    side = phi + (270.0 if flipped else 90.0)

    if atype == 0:
        if chord >= size * 2.0:
            # the interpreter prints "changed arc to line" and records a
            # straight move; an analysis that kept treating it as an arc
            # would be reasoning about a curve the machine never cuts
            return new_z, new_r, 1, 0.0, 0.0
        half = math.sqrt(max(size * size - (chord / 2.0) ** 2, 0.0))
        cz = mid_z + half * math.cos(math.radians(side))
        cr = mid_r + half * math.sin(math.radians(side))
    else:
        apex_z = mid_z + size * math.cos(math.radians(side))
        apex_r = mid_r + size * math.sin(math.radians(side))
        centre = _isect(((prev_z + apex_z) / 2.0, (prev_r + apex_r) / 2.0),
                        _rot90(apex_z - (prev_z + apex_z) / 2.0,
                               apex_r - (prev_r + apex_r) / 2.0),
                        (mid_z, mid_r), (apex_z - mid_z, apex_r - mid_r))
        if centre is None:
            # parallel bisectors mean there is no circle through the three
            # points. poly_add_item leaves the centre at 0,0 and still records
            # an arc, which is a curve nobody can analyse - refuse instead.
            return None
        cz, cr = centre

    return new_z, new_r, direction, cz, cr


def _resolve_arc_ij(child, prev_z, prev_r):
    """An Arc I,K child, as poly_add_item item types 6, 7, 61 and 62.

    Here the centre is given and the end point is swept to. Note the I value
    is a radius when it is an offset but a diameter when it is absolute -
    polyline-arc-ij.cfg divides only in the absolute cases, and so does this.
    """
    type_param = child.get_param('param_type')
    i_param = child.get_param('param_i')
    k_param = child.get_param('param_k')
    a_param = child.get_param('param_a')
    if None in (type_param, i_param, k_param, a_param):
        return None

    item_type = int(_to_float(type_param.get_ngc_value()))
    i_val = _to_float(i_param.get_ngc_value())
    k_val = _to_float(k_param.get_ngc_value())
    angle = _to_float(a_param.get_ngc_value())

    e_param = child.get_param('param_etype')
    etype = int(_to_float(e_param.get_ngc_value())) if e_param is not None else 0
    d_param = child.get_param('param_dir')
    direction = int(_to_float(d_param.get_ngc_value())) if d_param is not None else ARC_CCW

    if item_type in (7, 61):
        i_val /= DIAMETER_MODE

    if item_type == 6:
        cz, cr = prev_z + k_val, prev_r + i_val
    elif item_type == 7:
        cz, cr = k_val, i_val
    elif item_type == 61:
        cz, cr = prev_z + k_val, i_val
    else:
        cz, cr = k_val, prev_r + i_val

    radius = math.hypot(prev_z - cz, prev_r - cr)
    if etype == 1:
        # the angle is absolute about the centre, so the end point is simply
        # that bearing at the radius the start point already sets
        new_z = cz + radius * math.cos(math.radians(angle))
        new_r = cr + radius * math.sin(math.radians(angle))
    else:
        sweep = -angle if direction == ARC_CW else angle
        new_z, new_r = _rotate(prev_z, prev_r, cz, cr, sweep)

    return new_z, new_r, direction, cz, cr


def _rotate(z, r, cz, cr, degrees):
    """lib/utilities/rotate_xy.ngc."""
    cos_a, sin_a = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return ((z - cz) * cos_a - (r - cr) * sin_a + cz,
            (z - cz) * sin_a + (r - cr) * cos_a + cr)


def _rot90(vz, vr):
    return -vr, vz


def _isect(p0, s1, p2, s2):
    """Where two lines given as point + direction cross, or None if parallel.

    lib/utilities/isect_lines.ngc with its "extend the lines" branch, which is
    the branch poly_add_item uses.
    """
    test = s1[0] * s2[1] - s2[0] * s1[1]
    if abs(test) < 1e-12:
        return None
    t = (s2[0] * (p0[1] - p2[1]) - s2[1] * (p0[0] - p2[0])) / test
    return p0[0] + t * s1[0], p0[1] + t * s1[1]


def _densify_arc(prev_z, prev_r, seg):
    """The arc's own points, subdivided the way poly_mesh_lathe.ngc does.

    Deliberately the same rule and the same constants as the runtime mesh -
    the step that holds each sub-chord's sagitta under MESH_MAX_SAG, the same
    0.05 degree floor and the same 64 sub-record cap - so the profile this
    module reasons about and the profile the level scans stop against are the
    same curve. Returns the intermediate points followed by the arc's own end
    point exactly, so the chain cannot drift off the profile.
    """
    cz, cr = seg['cz'], seg['cr']
    radius = math.hypot(prev_z - cz, prev_r - cr)
    if radius <= MESH_MAX_SAG or radius <= 0.0001:
        return [(seg['z'], seg['r'])]

    a1 = math.degrees(math.atan2(prev_r - cr, prev_z - cz))
    a2 = math.degrees(math.atan2(seg['r'] - cr, seg['z'] - cz))
    if seg['dir'] == ARC_CCW:
        while a2 <= a1:
            a2 += 360.0
    else:
        while a2 >= a1:
            a2 -= 360.0
    sweep = a2 - a1

    step = max(2.0 * math.degrees(math.acos(1.0 - MESH_MAX_SAG / radius)), 0.05)
    steps = min(max(int(math.ceil(abs(sweep) / step)), 1), 64)

    out = []
    for k in range(1, steps):
        ang = math.radians(a1 + sweep * k / steps)
        out.append((cz + radius * math.cos(ang), cr + radius * math.sin(ang)))
    out.append((seg['z'], seg['r']))
    return out


# A Line-To child's "Merge with previous" = Radius. The radius rounds the
# vertex at the PREVIOUS item, blending that item's incoming segment into
# this one - see cfg/lathe/polyline-to.cfg's own tooltip.
MERGE_STYLE_RADIUS = 1


def apply_merge_radii(points, merges):
    """Replace every filleted vertex with the geometry the profile actually
    has: the two tangent points, plus the arc's own extreme X when the arc
    sweeps past it.

    Without this the analysis sees the sharp corner the user typed rather
    than the rounded one that gets cut, and both things this module produces
    come out wrong wherever a radius is used. The ceiling (see ceiling())
    reads the corner's full height, so the unsectioned full-length phase
    stops higher than it needs to; and detect_sections() sees a wall running
    all the way to that corner, so it puts a section boundary across levels
    the real profile never obstructs. The visible result is one roughing
    level cut as two passes with two retracts, split at a wall that - once
    rounded - only reaches a fraction of that height.

    points/merges are parallel, in the diameter units resolve_points works
    in; merges[i] is the radius rounding the vertex at points[i - 1], in
    radius units, 0 for none. The fillet itself is computed in true
    (Z, radius) space - a fillet is not scale-invariant, so doing it on
    diameters would be wrong by exactly the factor of two.

    A vertex is left sharp when the fillet cannot be built: no preceding
    point (the origin is deliberately not in points - see resolve_points),
    degenerate or straight corner, or tangent points that would run past
    either neighbour. Leaving it sharp is the conservative direction - it
    can only over-estimate the corner, never invent material.
    """
    if not points:
        return points
    out = []
    n = len(points)
    for j in range(n):
        # vertex j is rounded by the radius carried on item j + 1, and needs
        # a neighbour on both sides to have a corner at all
        radius = merges[j + 1] if j + 1 < len(merges) else 0.0
        filleted = None
        if radius > 0 and 1 <= j <= n - 2:
            filleted = _fillet_vertex(points[j - 1], points[j], points[j + 1], radius)
        if filleted is None:
            out.append(points[j])
        else:
            out.extend(filleted)
    return _dedupe(out)


def _fillet_vertex(a, v, c, radius):
    """The two tangent points that replace vertex v, or None when no fillet
    can be built there.

    Deliberately only the tangent points - not the arc's own extreme-X
    point. Adding that apex makes detect_sections see a direction reversal
    at the top of a smooth arc and open a section boundary there, which
    puts back the very split this is meant to remove. The apex is at most
    radius*(1 - cos(sweep/2)) above the higher tangent point, so leaving it
    out only understates the ceiling by a fraction of one roughing step."""
    az, ax = a[0], a[1] / 2.0
    vz, vx = v[0], v[1] / 2.0
    cz, cx = c[0], c[1] / 2.0

    d1z, d1x = az - vz, ax - vx
    d2z, d2x = cz - vz, cx - vx
    l1 = math.hypot(d1z, d1x)
    l2 = math.hypot(d2z, d2x)
    if l1 < EPS or l2 < EPS:
        return None
    u1z, u1x = d1z / l1, d1x / l1
    u2z, u2x = d2z / l2, d2x / l2

    cos_t = max(-1.0, min(1.0, u1z * u2z + u1x * u2x))
    theta = math.acos(cos_t)
    if theta < EPS or abs(theta - math.pi) < EPS:
        return None
    half = theta / 2.0
    tan_half = math.tan(half)
    sin_half = math.sin(half)
    if abs(tan_half) < EPS or abs(sin_half) < EPS:
        return None
    tangent = radius / tan_half
    if tangent > l1 - EPS or tangent > l2 - EPS:
        return None

    t1 = (vz + tangent * u1z, vx + tangent * u1x)
    t2 = (vz + tangent * u2z, vx + tangent * u2x)

    return [(t1[0], t1[1] * 2.0), (t2[0], t2[1] * 2.0)]


def _dedupe(points):
    out = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > EPS or abs(p[1] - out[-1][1]) > EPS:
            out.append(p)
    return out


def detect_sections(points):
    """Raw (z_from, z_to, min_x) sections, splitting at every edge where
    the profile's own trend changes - rising, flat, or falling, tracked
    per segment (three states, not just a rising/falling sign flip). A
    vertical wall is just the fast/instant rising-or-falling case of this;
    a peak or valley formed by two sloped (tapered) segments meeting is
    exactly the same kind of boundary, just slower - and a flat run (a
    straight OD, e.g. the top of a real boss) has to be its own state too,
    not silently absorbed into whatever direction was active before it -
    otherwise a genuine flat-topped, both-walls-bounded boss gets merged
    into its neighbor instead of splitting on both its own edges. Any
    transition between states is a boundary, including flat<->rising and
    flat<->falling, not only rising<->falling.

    Splitting at every such edge guarantees every resulting section is
    internally monotonic (never both rising and falling), which is what
    makes redoing every level across a section's full span - the
    execution poly_lathe_mill.ngc already does - trace a single
    shrinking/growing diagonal instead of wastefully attempting-then-
    retreating around a hidden interior peak or plateau.

    Zero-length guard on every stored section, and "reset to a large
    sentinel, not the edge vertex's own X" rule for a new section's
    running minimum, both carried over unchanged from the original
    wall-only version - consecutive edges landing at the identical Z (a
    rise immediately followed by a flat's own end, both at the same wall)
    collapse to one real boundary instead of a spurious zero-length one.
    """
    if len(points) < 2:
        return []

    e_z, e_x = points[0]
    l_z, l_x = points[-1]

    sections = []
    sec_z_from = e_z
    sec_min_x = e_x
    prev_category = None
    pz, px = e_z, e_x

    for cz, cx in points[1:]:
        dx = cx - px
        category = 1 if dx > EPS else (-1 if dx < -EPS else 0)

        if prev_category is not None and category != prev_category:
            if abs(pz - sec_z_from) > EPS:
                sections.append((sec_z_from, pz, sec_min_x))
            sec_z_from = pz
            sec_min_x = float('inf')

        prev_category = category
        if cx < sec_min_x:
            sec_min_x = cx
        pz, px = cz, cx

    if abs(l_z - sec_z_from) > EPS:
        sections.append((sec_z_from, l_z, sec_min_x))

    return sections


def _interpolate_x(points, z):
    """X at a given Z, linearly interpolated along the resolved polyline.

    Only ever called with a z that lies strictly inside one natural
    section's own span (a subdivision cut point), never past either end
    of the whole profile - callers guarantee that, so the "outside every
    segment" clamp below is just a defensive fallback, not a real path.
    """
    for (z1, x1), (z2, x2) in zip(points, points[1:]):
        lo, hi = (z1, z2) if z1 <= z2 else (z2, z1)
        if lo - EPS <= z <= hi + EPS:
            if abs(z2 - z1) <= EPS:
                return x1
            t = (z - z1) / (z2 - z1)
            return x1 + t * (x2 - x1)
    return points[0][1] if abs(z - points[0][0]) < abs(z - points[-1][0]) else points[-1][1]


def split_by_length(sections, points, sec_len):
    """Further subdivide each natural section into pieces no longer than
    sec_len, along Z - "Artificial" sectioning layered on top of "Natural"
    boundaries, never across them: a natural section only ever gets cut
    into more, shorter pieces here, and a natural boundary always stays a
    boundary in the result too (this function never merges sections, only
    splits them further). Pieces are made equal-length within a section
    (ceil(length/sec_len) even pieces) rather than sec_len-sized-with-a-
    short-remainder, so the last piece of a section is never a sliver.

    Every section here is monotonic by construction (detect_sections'
    guarantee), so a piece's own min_x is just the smaller of its two
    endpoint X values - interpolated along the real polyline geometry via
    _interpolate_x, not linearly guessed between the section's own
    endpoints (a section can itself be more than one original line
    segment, e.g. two different taper angles both still rising).

    sec_len <= 0 is the "Natural" case - returns sections unchanged.
    """
    if sec_len <= 0:
        return sections

    pieces = []
    for z_from, z_to, min_x in sections:
        length = abs(z_to - z_from)
        if length <= sec_len + EPS:
            pieces.append((z_from, z_to, min_x))
            continue

        n = math.ceil(length / sec_len)
        step = (z_to - z_from) / n
        prev_z = z_from
        prev_x = _interpolate_x(points, prev_z)
        for i in range(1, n + 1):
            cur_z = z_to if i == n else z_from + step * i
            cur_x = _interpolate_x(points, cur_z)
            pieces.append((prev_z, cur_z, min(prev_x, cur_x)))
            prev_z, prev_x = cur_z, cur_x

    return pieces


def rank_weakest_first(sections):
    """(z_from, z_to) pairs ordered weakest/smallest-diameter section
    first. sorted() is stable, so tied sections keep discovery order -
    matching the first-found-wins-ties behavior of the original selection
    sort.
    """
    return [(z_from, z_to) for z_from, z_to, _min_x
            in sorted(sections, key=lambda s: s[2])]


def ceiling(points, stock_x=None):
    """The largest X reached anywhere in the whole *machined* profile -
    "the highest edge": above this radius nothing along the whole Z length
    has reached target size yet, so one continuous full-length pass is
    always safe. At or below it, at least one point is already at-or-past
    target.

    Points at (or above) stock_x are excluded from this, when given. A
    point sitting at full stock diameter isn't a feature that needs
    protecting - it represents raw, uncut material (nearly every real
    profile has at least one such point, typically a closing wall back to
    stock at the far end) - so it can't be the thing that determines how
    deep a full-length pass is safe to go. Counting it anyway makes the
    ceiling collapse to stock itself for almost any real profile, since
    stock is by definition the largest diameter anywhere - silently
    erasing the "one full-length pass first" phase entirely rather than
    letting the profile's own highest real feature (e.g. a boss) set it.
    Falls back to every point if the profile is nothing but stock-diameter
    points (nothing would be excluded from an already-empty set).
    """
    candidates = [x for _z, x in points]
    if stock_x is not None:
        machined = [x for x in candidates if x < stock_x - EPS]
        if machined:
            candidates = machined
    return max(candidates)


def profile_problem(polyline_feature):
    """One plain-language reason this profile cannot be roughed, or None.

    The failure this exists for is silent: a profile whose items all sit at
    one Z, or that resolves to a single point, generates a valid G-code file
    containing no useful motion at all. Regenerate appears to succeed and the
    backplot is empty, with nothing said anywhere.

    Every item type the polyline offers is checked, since resolve_points now
    resolves all of them; a profile it cannot resolve still returns None and
    stays quiet, because a wrong warning is worse than none.

    Keep every message free of parentheses: callers put it in a G-code
    comment, and LinuxCNC treats a nested one as an unclosed comment.
    """
    points = resolve_points(polyline_feature)
    if points is None:
        return None
    if len(points) < 2:
        return ('the profile has %d point, and needs at least two items - '
                'the Start Z and Start Diameter are what the first item is '
                'measured from, not a point on the profile itself'
                % len(points))
    zs = [z for z, _x in points]
    if max(zs) - min(zs) < EPS:
        return ('every item sits at Z %s, so the profile has no length along '
                'Z and there is nothing to rough - give the items different '
                'Z positions' % _fmt(zs[0]))
    xs = [x for _z, x in points]
    if min(xs) < EPS:
        return ('the profile reaches diameter %s, at or through the spindle '
                'axis - check the item that goes there' % _fmt(min(xs)))
    return None


def build_sections_gcode(polyline_feature):
    """Returns literal G-code text assigning _pl_sect_count, _pl_sect_mode,
    the raw (unconverted) ceiling, and the #3400+ window block - or '' if
    Sectioning is off, or the profile couldn't be safely analyzed.

    Sectioning has two on-modes, selected purely by param_sec_len, exactly
    like the "Sectioning" checkbox's own tool_tip in polyline.cfg says -
    but they are NOT just two different ways of building the same window
    list, they use two different EXECUTION strategies in
    poly_lathe_mill.ngc, told apart by _pl_sect_mode:

    - 0, "Natural" (param_sec_len = 0): sections are the profile's own
      wall boundaries, one piece each, ranked weakest (smallest-diameter,
      most chatter-prone) section first - the rest of the stock stays
      near full diameter while that section is roughed. Above the
      weakest section's own ceiling, a single unsectioned full-length
      pass is safe and used (poly_lathe_mill.ngc's "violet" phase),
      since nothing there has reached target size yet anywhere.

    - 1, "Artificial" (param_sec_len > 0): each natural section longer
      than param_sec_len is further sliced into that many equal-length
      pieces via split_by_length() - natural boundaries are never
      crossed by this, only subdivided further. Unlike Natural, pieces
      are kept in plain sequential (front-to-back, or back-to-front if
      param_dir already reversed `points` above) order - NOT ranked by
      diameter - and every window gets the FULL roughing depth
      (start_radius to step_target) with no unsectioned violet phase at
      all. This is deliberate: Artificial's whole purpose is bounding
      how long a single continuous cut can ever be, for chatter/rigidity
      control on thin or slender stock - a full-length pass at any
      level, even a shallow one above every natural feature, would
      already defeat that purpose. Natural's weakest-first strategy
      makes no sense here either: length-based pieces of a monotonic
      taper would get processed back-to-front (deepest/thinnest first),
      which is not the sequential "sausage slicing" behavior Artificial
      is for - so pieces stay in discovery order, one full-depth pass
      through the whole part in the configured direction.
    """
    sectioning_param = polyline_feature.get_param('param_sectioning')
    if sectioning_param is None or _to_float(sectioning_param.get_ngc_value()) <= 0:
        return ''

    points = resolve_points(polyline_feature)
    if not points or len(points) < 2:
        return ''

    dir_param = polyline_feature.get_param('param_dir')
    rough_dir = int(_to_float(dir_param.get_ngc_value())) if dir_param is not None else 0
    if rough_dir == 1:
        points = list(reversed(points))

    sections = detect_sections(points)
    if not sections:
        return ''

    sec_len_param = polyline_feature.get_param('param_sec_len')
    sec_len = _to_float(sec_len_param.get_ngc_value()) if sec_len_param is not None else 0.0

    if sec_len > 0:
        pieces = split_by_length(sections, points, sec_len)
        ordered = [(z_from, z_to) for z_from, z_to, _min_x in pieces]
        sect_mode = 1
    else:
        ordered = rank_weakest_first(sections)
        sect_mode = 0

    b_x_param = polyline_feature.get_param('param_b_x')
    stock_x = _to_float(b_x_param.get_ngc_value()) if b_x_param is not None else None
    top_x = ceiling(points, stock_x)

    if sect_mode == 0:
        windows = band_windows(sections, ordered, points)
    else:
        # Artificial bounds how long any single cut may be, at every depth,
        # so its pieces deliberately apply over the whole radius range - see
        # this function's own docstring for why it must not be merged.
        windows = [(z_from, z_to, 0.0, BAND_ALL) for z_from, z_to in ordered]

    lines = [
        '#<_pl_sect_count> = %d' % len(windows),
        '#<_pl_sect_mode> = %d' % sect_mode,
        '#<_pl_sect_top_dia> = %s' % _fmt(top_x),
    ]
    for i, (z_from, z_to, r_lo, r_hi) in enumerate(windows):
        slot = 3400 + i * 4
        lines.append('#%d = %s' % (slot + 1, _fmt(z_from)))
        lines.append('#%d = %s' % (slot + 2, _fmt(z_to)))
        lines.append('#%d = %s' % (slot + 3, _fmt(r_lo)))
        lines.append('#%d = %s' % (slot + 4, _fmt(r_hi)))

    return '\n'.join(lines) + '\n'


# Stand-in for "no upper limit" on a window's radius band, in the diameter
# units the whole module works in. Larger than any real workpiece.
BAND_ALL = 1.0e6


def boundary_height(points, z_b):
    """How far up the profile actually reaches at boundary z_b - the height
    of whatever separates the two sections meeting there.

    For a step it is the top of that wall; for a peak between two sections
    it is the peak itself. Either way, a roughing level ABOVE this sees
    continuous material across the boundary and must not be stopped by it.
    """
    hits = []
    for (z1, x1), (z2, x2) in zip(points, points[1:]):
        lo, hi = min(z1, z2), max(z1, z2)
        if lo - EPS <= z_b <= hi + EPS:
            if abs(z2 - z1) < EPS:
                hits.extend((x1, x2))
            else:
                hits.append(x1 + (x2 - x1) * (z_b - z1) / (z2 - z1))
    return max(hits) if hits else 0.0


def band_windows(sections, ordered, points):
    """Turn the ranked section list into windows carrying the radius band
    each one applies over: (z_from, z_to, r_lo, r_hi).

    A section boundary only obstructs levels at or below the height of the
    thing that forms it. Above that the material runs straight through, so
    the sections either side are one window and splitting them there just
    cuts the same level twice - a full pass stopping dead on the boundary,
    then a stub pass with its own lead-in, lead-out and retract clearing
    what was left, which is what showed up as a doubled lead-out inside a
    merge radius.

    Rather than teach the runtime to merge, the merged windows are computed
    here and emitted alongside the plain ones, each gated to the band of
    radii where it applies. poly_lathe_mill.ngc then needs only to skip a
    level outside a window's band - no merging logic at runtime at all.

    Ordering is preserved from `ordered` (weakest-first) within each band,
    and bands are emitted highest-first so roughing still works downward.
    """
    z_ordered = sorted(sections, key=lambda s: -s[0]) if sections[0][0] > sections[-1][0] \
        else sorted(sections, key=lambda s: s[0])
    spans = [(z_from, z_to) for z_from, z_to, _m in z_ordered]
    if len(spans) < 2:
        return [(z_from, z_to, 0.0, BAND_ALL) for z_from, z_to in spans]

    # height of each internal boundary, in profile order
    heights = [boundary_height(points, spans[i][1]) for i in range(len(spans) - 1)]

    # band edges: every distinct boundary height, lowest first
    edges = sorted(set(round(h, 6) for h in heights))
    windows = []
    seen = set()
    # highest band first: above every boundary the whole profile is one window
    bands = [(edges[-1], BAND_ALL)] + \
            [(edges[i - 1], edges[i]) for i in range(len(edges) - 1, 0, -1)] + \
            [(0.0, edges[0])]
    for r_lo, r_hi in bands:
        if r_hi - r_lo < EPS:
            continue
        # merge runs of sections whose separating boundary is below this band
        merged = []
        cur = spans[0]
        for i in range(1, len(spans)):
            if heights[i - 1] <= r_lo + EPS:
                cur = (cur[0], spans[i][1])
            else:
                merged.append(cur)
                cur = spans[i]
        merged.append(cur)
        # keep the caller's weakest-first order for pieces that survive whole
        rank = {(z_from, z_to): n for n, (z_from, z_to) in enumerate(ordered)}
        merged.sort(key=lambda s: rank.get(s, -1))
        for s in merged:
            key = (round(s[0], 6), round(s[1], 6), round(r_lo, 6), round(r_hi, 6))
            if key in seen:
                continue
            seen.add(key)
            windows.append((s[0], s[1], r_lo, r_hi))
    return windows


# --- tool flank shadow -------------------------------------------------------
#
# A roughing level cannot drop straight down behind a raised feature: the insert
# is a wedge, not a point, and the material behind a taller feature is only
# reachable along a line leaving that feature's corner at the flank angle.
# Cutting past it drives the tool body into the boss - see
# photo/spaceBehindIssue_0.png.
#
# The two flank directions come from the tool table's I (front angle) and J
# (back angle), both measured clockwise from a line parallel to Z+, the same
# convention the orientation figure uses for CL. Their bisector IS the CL angle,
# which is a useful check on a table: T2 I15 J75 bisects to 45, and tool 2 is
# orientation 2, CL 45.
#
# Travel direction deliberately does not enter into this. The tool body occupies
# the wedge between BOTH flanks whichever way it drives, so both constrain at
# once; direction only decides which end of a given level ends up limited, and
# that falls out. Constraining just the trailing flank would be wrong the moment
# roughing runs in Both directions.


def _outer_x(points, z):
    """The OUTERMOST material diameter at a Z.

    A vertical wall gives one Z two diameters, and _interpolate_x answers with
    only one of them - the foot. Seeding the envelope from that puts it BELOW
    the profile across the whole wall, which is not a missed optimisation but a
    gouge: roughing would cut into the boss it is supposed to be avoiding.
    """
    best = None
    for (z0, x0), (z1, x1) in zip(points, points[1:]):
        lo, hi = min(z0, z1), max(z0, z1)
        if lo - EPS <= z <= hi + EPS:
            if abs(z1 - z0) < EPS:
                cand = max(x0, x1)
            else:
                cand = x0 + (x1 - x0) * (z - z0) / (z1 - z0)
            best = cand if best is None else max(best, cand)
    return best


def flank_slope(back_deg):
    """Rise in radius per unit of Z along the trailing flank, or None.

    The tool table's BACK angle is measured off the perpendicular, so the ramp
    the flank actually leaves behind a wall sits at 90 - BACK from the Z axis:
    a J75 insert ramps at 15 degrees and needs a long projection in Z to clear
    a wall, not a short one. Using BACK directly gives the complement and a
    shadow far too short.
    """
    eff = 90.0 - back_deg
    if eff <= EPS or eff >= 90.0 - EPS:
        return None
    return math.tan(math.radians(eff))


def flank_sides(rough_dir):
    """Which side of a peak casts a shadow, from the roughing direction.

    Cutting front to back the tool drives past a boss and the sections BEHIND
    it are the ones it can no longer reach, so only peaks on the +Z side
    constrain. Back to front mirrors that. Both directions has to take both,
    since each pass meets a different face of the same boss.
    """
    if rough_dir == 1:
        return (-1,)
    if rough_dir == 2:
        return (1, -1)
    return (1,)


def flank_envelope(points, back_deg, rough_dir=0, flank_len=0.0):
    """The profile widened into the shape the tool can actually reach.

    A wedge dilation by the trailing flank: a point (zp, rp) on the shadowed
    side bounds the nose radius below by

        rp - |zp - z0| * slope

    and the envelope is the largest such bound over every point, never below
    the profile. Reaching the true profile is the finishing passes' job; this
    shape is only for the roughing scans - the same thing the mesh copy
    poly_mesh_lathe builds is for, and the only thing that reads it.

    Returns BREAKPOINTS, not a sampled curve: the envelope is piecewise linear,
    every corner sits where one point's ray meets another point's radius, and
    the result has to travel into G-code as a record array.

    flank_len is how far the flank actually extends along itself before the
    tool steps back - the insert is not an infinite wedge. Past that, the body
    has ended and the obstruction no longer touches it, so only obstructions
    within it constrain. An obstruction at a Z distance d lies L = d / cos(ramp)
    along the flank, so the reach in Z is flank_len * cos(ramp). 0 means treat
    the flank as unbounded, which is what this did before the parameter existed
    and is the conservative answer.

    points are (z, x) in the diameter units resolve_points works in, so the
    slope - a rise in RADIUS - is scaled to match, or the ramp comes out at
    half the angle.
    """
    if not points or len(points) < 2:
        return list(points)

    k = flank_slope(back_deg)
    if k is None:
        return list(points)
    k *= DIAMETER_MODE
    slopes = [(side, k) for side in flank_sides(rough_dir)]

    # how far along Z the flank still exists
    reach = None
    if flank_len and flank_len > EPS:
        reach = flank_len * math.cos(math.radians(90.0 - back_deg))
        if reach <= EPS:
            return list(points)

    zs = [p[0] for p in points]
    lo, hi = min(zs), max(zs)

    cand = set(zs)
    # A vertical wall puts two diameters at one Z. The candidate set holds that
    # Z once and _outer_x answers with the top, so the foot is lost and the
    # output interpolates straight across the wall - which reads as a phantom
    # ramp on the side that should have been left alone. Put a candidate just
    # clear of each wall so the foot survives as its own breakpoint.
    walls = set()
    for (z0, x0), (z1, x1) in zip(points, points[1:]):
        if abs(z1 - z0) < EPS and abs(x1 - x0) > EPS:
            walls.add(z0)
    step = EPS * 2          # must clear _outer_x own EPS or the wall swallows it
    for zw in walls:
        for zc in (zw - step, zw + step):
            if lo <= zc <= hi:
                cand.add(zc)

    for zp, rp in points:
        for side, kk in slopes:
            for _z2, r2 in points:
                if r2 < rp - EPS:
                    zc = zp - side * (rp - r2) / kk
                    if lo <= zc <= hi:
                        cand.add(zc)
            # where the flank ends, so the shadow can release there. BOTH sides
            # of the limit are needed: the point exactly at it still lies on the
            # full ramp line and gets dropped as collinear, so without the one
            # just past it the release is never expressed and a finite flank
            # looks identical to an infinite one.
            if reach is not None:
                for zc in (zp - side * reach, zp - side * (reach + EPS * 4)):
                    if lo <= zc <= hi:
                        cand.add(zc)

    out = []
    for z0 in sorted(cand):
        best = _outer_x(points, z0)
        if best is None:
            best = points[0][1]
        for zp, rp in points:
            for side, kk in slopes:
                d = (zp - z0) * side
                if d > EPS and (reach is None or d <= reach + EPS):
                    bound = rp - d * kk
                    if bound > best:
                        best = bound
        out.append((z0, best))

    if len(out) < 3:
        return out
    keep = [out[0]]
    for i2 in range(1, len(out) - 1):
        z0, r0 = keep[-1]
        z1, r1 = out[i2]
        z2, r2 = out[i2 + 1]
        if abs(z2 - z0) < EPS:
            keep.append(out[i2])
            continue
        on_line = r0 + (r2 - r0) * (z1 - z0) / (z2 - z0)
        if abs(on_line - r1) > EPS:
            keep.append(out[i2])
    keep.append(out[-1])
    return keep


def build_flank_gcode(polyline_feature, back_deg):
    """Literal G-code building the reachable envelope as a record array, or ''.

    Emitted as records so poly_lathe_mill can hand it straight to the level
    scans in place of the mesh poly_mesh_lathe would build. The scans are the
    only thing that reads that array - the contour passes keep tracing the true
    profile - so this changes what roughing stops against and nothing else.

    Returns '' when there is nothing to do: no back angle, a flank that
    constrains nothing, or an envelope identical to the profile. The runtime
    gate is _pl_env_count > 0, so '' leaves roughing exactly as it was.
    """
    if back_deg is None or back_deg <= 0:
        return ''
    points = resolve_points(polyline_feature)
    if not points or len(points) < 2:
        return ''

    d_param = polyline_feature.get_param('param_dir')
    rough_dir = int(_to_float(d_param.get_ngc_value())) if d_param is not None else 0
    l_param = polyline_feature.get_param('param_flank_len')
    flank_len = _to_float(l_param.get_ngc_value()) if l_param is not None else 0.0
    env = flank_envelope(points, back_deg, rough_dir, flank_len)
    # the scans walk records in profile order, so hand the envelope back the
    # same way round the profile was drawn rather than sorted ascending
    if points[0][0] > points[-1][0]:
        env = list(reversed(env))
    if len(env) == len(points) and all(
            abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) < EPS
            for a, b in zip(sorted(env), sorted(points))):
        return ''

    base = FLANK_BASE
    if base + 2 * len(env) > FLANK_TOP:
        return ('(WARNING - the reachable envelope needs %d parameter slots '
                'and only %d are free, so roughing will use the plain mesh.)'
                % (2 * len(env), FLANK_TOP - FLANK_BASE))
    lines = ['(reachable envelope: the profile widened by the tool back angle)',
             '(so roughing cannot try to cut where the flank would foul a wall)',
             '#<_pl_env_base>  = %d' % base,
             '#<_pl_env_count> = %d' % len(env)]
    for i, (z, x) in enumerate(env):
        slot = base + i * 2
        lines.append('#%d = %s' % (slot, _fmt(z)))
        lines.append('#%d = %s' % (slot + 1, _fmt(x / DIAMETER_MODE)))
    return '\n'.join(lines)


# --- compensation done in CAM ------------------------------------------------
#
# Native LinuxCNC compensation carries real restrictions: a comp entry must be a
# straight feed of at least the nose radius in free air, an arc cannot establish
# it, and the interpreter refuses a concave corner smaller than the nose. When
# the path is offset here instead, none of those apply and the backplot shows
# what the tool actually does - at the cost of owning the geometry, which is why
# this is a third option and never a replacement for native.
#
# Where the nose sits relative to the programmed control point, as (X, Z)
# multiples of the nose radius. LinuxCNC's own table, from rs274/glcanon.py
# StatCanon.lathe_shapes - kept here as well so this module needs no import.
# 1-4 are the diagonal corners at R*sqrt(2), and that is a RAW vector:
# normalising it to R mis-places the tool, which CLAUDE.md already flags.
NOSE_OFFSET = [None, (1, -1), (1, 1), (-1, 1), (-1, -1),
               (0, -1), (1, 0), (0, 1), (-1, 0), (0, 0)]


def _unit(dz, dx):
    n = math.hypot(dz, dx)
    return (dz / n, dx / n) if n > EPS else (0.0, 0.0)


def offset_contour(points, nose_r, orient, side=1):
    """The control-point path that puts the nose circle tangent to the profile.

    With compensation off the machine positions the tool's CONTROL point, and
    the nose sits one radius away from it in the direction the orientation
    names. So for the nose circle to ride the profile:

        control = profile + nose_r * normal - nose_r * (dz, dx)_orient

    side is which way the normal points: +1 outward in radius, for outside work,
    -1 for a bore.

    Corners are joined by their sign, which is what makes the result a toolpath
    rather than a list of disconnected offsets:

    - An INTERNAL corner - the offsets converge - is trimmed to where the two
      offset lines cross. The nose then stops short of the vertex and leaves a
      fillet of its own radius, which is physically unavoidable and is exactly
      what a real nose does in a 90 degree inside corner.
    - An EXTERNAL corner - the offsets diverge - is rounded. Both offset ends
      already sit exactly nose_r from the vertex, so the join is an arc of that
      radius about it, and the nose rolls around the corner. Emitted as chords
      under a sagitta bound rather than a true arc, the same way
      poly_mesh_lathe bounds its own subdivision, so the error is knowable and
      arc emission is not written twice. A miter join here would hold the nose
      nose_r*(sqrt(2)-1) too far out at a 90 degree corner and leave material.

    points are (z, x) in the diameter units resolve_points works in; nose_r is a
    radius. Returns the same (z, diameter) form.
    """
    if not points or len(points) < 2 or nose_r <= EPS:
        return list(points)

    off = NOSE_OFFSET[orient] if 0 < orient < len(NOSE_OFFSET) else None
    # the table is (X, Z); this module works in (z, radius)
    ozd, oxd = (off[1], off[0]) if off else (0.0, 0.0)

    # work in true radius: a normal is not scale invariant, so doing this on
    # diameters would be wrong by exactly a factor of two
    pts = [(z, x / DIAMETER_MODE) for z, x in points]

    segs = []
    for i in range(len(pts) - 1):
        (z0, r0), (z1, r1) = pts[i], pts[i + 1]
        dz, dr = z1 - z0, r1 - r0
        if abs(dz) < EPS and abs(dr) < EPS:
            continue
        uz, ur = _unit(dz, dr)
        # The outward normal, rotated -90 from the travel direction. That is
        # the rotation that points away from the material for a profile drawn
        # front to back with material below it, which is how the polyline draws
        # one: an axial run offsets to +radius, and the two faces of a boss
        # offset to +Z and -Z respectively, each away from its own material.
        # The other rotation gets the cylinder right and both walls backwards.
        nz, nr = ur * side, -uz * side
        segs.append({'v0': (z0, r0), 'v1': (z1, r1), 'u': (uz, ur),
                     'a': (z0 + nose_r * nz, r0 + nose_r * nr),
                     'b': (z1 + nose_r * nz, r1 + nose_r * nr)})
    if not segs:
        return list(points)

    out = [segs[0]['a']]
    for i in range(len(segs)):
        cur = segs[i]
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        if nxt is None:
            out.append(cur['b'])
            break
        (uz0, ur0), (uz1, ur1) = cur['u'], nxt['u']
        cross = (uz0 * ur1 - ur0 * uz1) * side
        if cross > EPS:
            # external: roll the nose around the shared vertex
            out.append(cur['b'])
            out.extend(_corner_arc(cur['v1'], cur['b'], nxt['a'], nose_r))
        elif cross < -EPS:
            # internal: both offsets are trimmed back to where they cross
            hit = _isect(cur['a'], cur['u'], nxt['a'], nxt['u'])
            out.append(hit if hit is not None else cur['b'])
        else:
            out.append(cur['b'])          # collinear, nothing to join

    # everything above is the NOSE CENTRE path - which is where the corner
    # geometry belongs, since it is the nose centre that rolls around a vertex
    # at exactly nose_r. The control point is that path shifted by the constant
    # orientation vector, applied once here.
    res = [(z - nose_r * ozd, (r - nose_r * oxd) * DIAMETER_MODE) for z, r in out]
    # drop repeats the joins can leave behind
    dedup = [res[0]]
    for p in res[1:]:
        if abs(p[0] - dedup[-1][0]) > EPS or abs(p[1] - dedup[-1][1]) > EPS:
            dedup.append(p)
    return dedup


def _corner_arc(vertex, start, end, radius):
    """Chords around an external corner, from start to end about vertex.

    Both ends already lie radius from the vertex; this fills the sweep between
    them, taking the short way round, subdivided so each chord's sagitta stays
    under MESH_MAX_SAG.
    """
    vz, vr = vertex
    a0 = math.atan2(start[1] - vr, start[0] - vz)
    a1 = math.atan2(end[1] - vr, end[0] - vz)
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= 2 * math.pi
    while sweep < -math.pi:
        sweep += 2 * math.pi
    if abs(sweep) < 1e-9 or radius <= MESH_MAX_SAG:
        return [end]
    step = 2.0 * math.acos(max(1.0 - MESH_MAX_SAG / radius, -1.0))
    n = max(int(math.ceil(abs(sweep) / max(step, 1e-6))), 1)
    return [(vz + radius * math.cos(a0 + sweep * k / n),
             vr + radius * math.sin(a0 + sweep * k / n))
            for k in range(1, n + 1)]


# One offset path per contour pass, because each pass carries a different
# allowance. Native mode gets that allowance from cutter comp's D word, so every
# pass can trace one shared record array; in CAM mode the allowance is part of
# the geometry, so each pass needs its own already-offset path.
#
# Laid out as a DIRECTORY rather than at fixed bases per pass: an arc-heavy
# profile densifies into far more points than any fixed window would hold, and
# overrunning into the next table is silent - the pass would trace a path made
# half of one offset and half of another. So the base of each table is computed
# here, where the point counts are actually known, and published in the
# directory for the runtime to read.
#
#   #[dir + 2k]     pointer to pass k's first point
#   #[dir + 2k + 1] pass k's point count
#   #[ptr + 2i]     point i, Z          #[ptr + 2i + 1]  point i, radius
#
# Pass 0 is the pre-finish pass; 1..n are the finish passes in order.
CAM_BASE = 4400
# Numbered parameters above roughly #5060 are LinuxCNC's own - #5061+ are probe
# results, #5161+ home positions, #5221+ the coordinate-system offsets, #5401+
# the tool table. Writing a table through them would corrupt live machine state,
# so a profile that does not fit under this refuses instead.
CAM_TOP = 5000


def cam_pass_offsets(fin_off, pf_off, fin_passes):
    """The allowance each contour pass runs at, pass 0 being the pre-finish.

    These must match what poly_lathe_mill.ngc hands native compensation as its
    D word, or CAM mode cuts a different part from native mode at the same
    settings:

    - pre-finish: rough_target - final_radius, and rough_target is
      final_radius + dirsign*fin_off, so the allowance is fin_off. NOT
      fin_off + pf_off - pf_off is what the roughing LEVELS stop short by
      (step_target), which the pre-finish pass then cuts away.
    - finish pass i of n: fin_off * (n - i) / n, stepping down to exactly 0 on
      the last pass, which is what puts it on the finished profile.

    Signs are not carried here - offset_contour takes the direction as `side`
    and the allowance as a magnitude.
    """
    n = max(int(fin_passes), 0)
    return [fin_off] + [fin_off * (n - i) / float(n) for i in range(1, n + 1)]


def build_cam_comp_gcode(polyline_feature, nose_r, orient, back_deg=None):
    """Literal G-code with the CAM-offset contours, or a warning comment.

    Emitted as point tables the same way build_flank_gcode emits the flank
    envelope, one per contour pass - see the layout note above.

    Never returns a silent '': in CAM mode the machine compensates nothing, so
    an empty table means the pass would trace the UNCOMPENSATED profile and cut
    the part undersize by the nose radius, with a backplot that looks right.
    Every early return therefore emits a warning comment and leaves
    _pl_cam_n at 0, which poly_lathe_mill turns into an (ABORT,).
    """
    def _refuse(why):
        return ('(WARNING - In CAM nose compensation: %s. The pass cannot run '
                'uncompensated, so the program will abort.)' % why)

    if nose_r is None or nose_r <= EPS:
        return _refuse('no tool nose radius is known - set D in the tool table '
                       'or the nose diameter override in the Tool Change')
    if not 0 < int(orient) < len(NOSE_OFFSET):
        return _refuse('tool orientation %s is not one of 1-9' % orient)
    # the SOFT contour, for the same reason the native passes now follow it:
    # offsetting an unreachable profile just produces an unreachable path
    points, _soft = finish_profile(polyline_feature, back_deg)
    if not points or len(points) < 2:
        return _refuse('the profile does not resolve to at least two points')

    s_param = polyline_feature.get_param('param_side')
    side = -1 if (s_param is not None
                  and int(_to_float(s_param.get_ngc_value())) == 1) else 1

    def _off(pname):
        p = polyline_feature.get_param(pname)
        return _to_float(p.get_ngc_value()) if p is not None else 0.0

    fin_off = _off('param_f_off')
    pf_off = _off('param_pf_off') * (1 if _off('param_pf_on') else 0)
    offsets = cam_pass_offsets(fin_off, pf_off, _off('param_f_pass'))

    paths = [offset_contour(points, nose_r + extra, int(orient), side)
             for extra in offsets]
    if any(len(p) < 2 for p in paths):
        return _refuse('the offset path collapsed - the nose radius is too '
                       'large for this profile')

    # directory first, then the points; the base of each table depends on how
    # long every table before it turned out to be
    ptr = CAM_BASE + 2 * len(paths)
    ptrs = []
    for p in paths:
        ptrs.append(ptr)
        ptr += 2 * len(p)
    if ptr > CAM_TOP:
        return _refuse('the offset path needs %d parameter slots and only %d '
                       'are safe to use - reduce the number of finish passes, '
                       'or use Native LinuxCNC' % (ptr - CAM_BASE,
                                                   CAM_TOP - CAM_BASE))

    lines = ['(nose compensation done in CAM: these are already-offset control)',
             '(point paths, so the machine runs uncompensated - see _tip_cam)',
             '#<_pl_cam_dir> = %d' % CAM_BASE,
             '#<_pl_cam_n>   = %d' % len(paths),
             '#<_pl_cam_max> = %d' % max(len(p) for p in paths)]
    for k, (p, base) in enumerate(zip(paths, ptrs)):
        lines.append('#%d = %d' % (CAM_BASE + 2 * k, base))
        lines.append('#%d = %d' % (CAM_BASE + 2 * k + 1, len(p)))
    for k, (p, base) in enumerate(zip(paths, ptrs)):
        lines.append('(%s, allowance %s + nose %s, %d points)'
                     % ('pre-finish pass' if k == 0 else 'finish pass %d' % k,
                        _fmt(offsets[k]), _fmt(nose_r), len(p)))
        for i, (z, x) in enumerate(p):
            lines.append('#%d = %s' % (base + 2 * i, _fmt(z)))
            lines.append('#%d = %s' % (base + 2 * i + 1, _fmt(x / DIAMETER_MODE)))
    return '\n'.join(lines)


# --- the manufacturable contour ---------------------------------------------
#
# The profile the operator draws is the HARD contour: what the part should be.
# It is not always reachable. A tool with a back angle cannot drop straight down
# behind a raised feature - its heel fouls the wall it has just driven past - so
# the surface it can actually leave is the hard contour widened by that shadow.
# That is the SOFT contour.
#
# Roughing has respected this since the flank work: poly_lathe_mill loads the
# envelope into the mesh the level scans read. The CONTOUR passes did not - they
# traced the hard contour - so on a part with a shadowed region the finish pass
# commanded the tool into metal it cannot enter, which is the very gouge the
# shadow exists to prevent, reintroduced on the last pass. Measured on
# testing_15_2: the two disagreed by up to 9.75 mm of radius.
#
# The finishing passes use the FINISHING direction, not the roughing one. It is
# the finish pass that leaves the surface, so what IT can reach is what the part
# ends up as; if the two directions differ the two soft contours legitimately
# differ too.
# Fixed parameter-space layout. These MUST NOT overlap: the tables are written
# in emission order, so a later one silently overwrites an earlier one and the
# damage shows up as motion that makes no sense. The finish-contour table was
# first placed at 3500 with room for 130 slots, which ran straight through the
# flank envelope at 3600 - roughing then stopped 4 mm short of the floor and
# drove through the boss it was supposed to split around.
#
#   3400  sections window table   i*4
#   3600  flank envelope          i*2, capped below
#   4000  finish soft contour     i*2, capped below
#   4400  In-CAM offsets          directory + points, capped at CAM_TOP
#
# test_table_layout in test_sections.py asserts they stay disjoint.
SECT_BASE = 3400
FLANK_BASE = 3600
FLANK_TOP = 4000
FC_BASE = 4000
FC_TOP = 4400


def finish_profile(polyline_feature, back_deg, nose_r=0.0):
    """(points, soft) - the contour the finishing passes should follow.

    Returns the hard contour and soft=False when nothing constrains it: no back
    angle, the flank switch off, or an envelope that comes out identical.
    """
    points = resolve_points(polyline_feature)
    if not points or len(points) < 2:
        return points, False
    if back_deg is None or back_deg <= 0:
        return points, False

    p = polyline_feature.get_param('param_flank')
    if p is not None and _to_float(p.get_ngc_value()) < 1:
        return points, False

    d = polyline_feature.get_param('param_f_dir')
    fin_dir = int(_to_float(d.get_ngc_value())) if d is not None else 0
    lp = polyline_feature.get_param('param_flank_len')
    flank_len = _to_float(lp.get_ngc_value()) if lp is not None else 0.0

    env = flank_envelope(points, back_deg, fin_dir, flank_len)
    if not env or len(env) < 2:
        return points, False
    if points[0][0] > points[-1][0]:
        env = list(reversed(env))
    same = (len(env) == len(points)
            and all(abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) < EPS
                    for a, b in zip(env, points)))
    if same:
        return points, False
    # 1.2 x the nose DIAMETER. Measured on testing_15_2: this limit departs
    # from the true envelope by 0.105 mm, where 2 x diameter costs 0.729 mm -
    # accuracy falls away quickly above it, and the surface being approximated
    # is an artefact of the tool that is not to size anyway.
    # Applied to the WHOLE contour, not just the ramp stretches. The segment
    # that aborted the pass sat at the junction where the ramp meets the drawn
    # profile, so filtering the ramp alone left it in place and the interpreter
    # still refused. This only ever runs on a profile that HAS an unreachable
    # region - a fully reachable one is returned untouched above - so the blast
    # radius is exactly the parts that would otherwise abort.
    return _min_segment(_clean_ramp(env, points), 2.4 * nose_r), True


def _upper_hull(pts):
    """Upper hull of a Z-ordered run, in (z, x). A straight ramp reduces to its
    two endpoints; a sawtooth riding on that ramp reduces to the ramp."""
    if len(pts) < 3:
        return list(pts)
    fwd = pts[0][0] <= pts[-1][0]
    seq = pts if fwd else list(reversed(pts))
    out = []
    for p in seq:
        while len(out) >= 2:
            (z0, x0), (z1, x1) = out[-2], out[-1]
            cross = (z1 - z0) * (p[1] - x0) - (x1 - x0) * (p[0] - z0)
            if cross >= -1e-12:
                out.pop()
            else:
                break
        out.append(p)
    return out if fwd else list(reversed(out))


def _clean_ramp(env, hard, tol=1e-4):
    """Replace each artificial ramp in `env` with its upper hull.

    flank_envelope takes the pointwise maximum of the profile and the back-angle
    ramp. Where the profile is a densified arc the two interleave, and the
    result is a SAWTOOTH of tiny alternating steps rather than a ramp - about
    thirty of them on testing_15_2, each a 105 degree concave corner. Roughing
    never noticed, because its scans only look for crossings. Traced as a
    contour it is unusable: cutter compensation refuses a concave corner tighter
    than the nose and aborts the program mid-pass, which is exactly what it did.

    Only the stretches that actually differ from the drawn profile are touched,
    so real geometry - walls, arcs, corners the operator drew - passes through
    untouched.
    """
    # compared BY Z, not index by index: the envelope carries extra points
    # where a ramp starts and ends, so the two lists are different lengths and
    # a positional comparison silently matches nothing
    out, run = [], []
    for e in env:
        h = _profile_x_at(e[0], hard)
        if h is not None and abs(e[1] - h) > tol:
            run.append(e)
            continue
        if run:
            out.extend(_close_run(run, e))
            run = []
        out.append(e)
    if run:
        out.extend(_upper_hull(run))
    return out


def _min_segment(pts, limit):
    """Drop points that would leave a segment shorter than `limit`.

    Cutter compensation shrinks each segment by R*tan(deficit/2) at a concave
    corner - two-sided, so a segment shorter than that reverses and the
    interpreter refuses the whole pass with "concave corner cannot be reached
    without gouging". The back-angle ramp on testing_15_2 contained a 0.252 mm
    segment against 0.238 mm of shrink, which is what aborted the pre-finish
    pass halfway.

    Note this is NOT about sharp corners: the worst corner on that part is
    146.8 degrees and most are 176.8, so filleting them would have fixed
    nothing. Length is what matters.

    The endpoints are always kept, so the ramp still starts and ends where it
    meets the drawn profile.
    """
    if limit <= 0 or len(pts) < 3:
        return list(pts)
    keep = [pts[0]]
    for q in pts[1:-1]:
        if math.hypot(q[0] - keep[-1][0],
                      (q[1] - keep[-1][1]) / DIAMETER_MODE) >= limit:
            keep.append(q)
    keep.append(pts[-1])
    return keep


def _close_run(run, nxt):
    """Finish a ramp so it MEETS the profile instead of stopping above it.

    The last ramp point often sits at the same Z as the profile point that
    follows, leaving a short vertical drop between them - and the corner between
    the ramp and that drop is far tighter than the nose, so compensation refuses
    the whole pass. Dropping the point lets the ramp run into the profile at one
    open corner instead.
    """
    hull = _upper_hull(run)
    while len(hull) > 1 and abs(hull[-1][0] - nxt[0]) < 1e-6:
        hull = hull[:-1]
    return hull


def unreachable_spans(polyline_feature, back_deg, tol=0.01):
    """[(z_from, z_to, worst_radius_gap)] where the part cannot be made.

    What the validation message reports, and what the preview colours.
    """
    hard = resolve_points(polyline_feature)
    soft, is_soft = finish_profile(polyline_feature, back_deg)
    if not is_soft:
        return []
    zs = sorted({z for z, _x in hard} | {z for z, _x in soft})
    if len(zs) < 2:
        return []
    spans, cur = [], None
    step = max((zs[-1] - zs[0]) / 400.0, 1e-6)
    z = zs[0]
    while z <= zs[-1] + 1e-9:
        h, s = _profile_x_at(z, hard), _profile_x_at(z, soft)
        gap = 0.0 if (h is None or s is None) else (s - h) / DIAMETER_MODE
        if gap > tol:
            if cur is None:
                cur = [z, z, gap]
            else:
                cur[1], cur[2] = z, max(cur[2], gap)
        elif cur is not None:
            spans.append(tuple(cur))
            cur = None
        z += step
    if cur is not None:
        spans.append(tuple(cur))
    return spans


def _profile_x_at(z, points):
    """Outermost profile X - diameter units - at this Z, or None off the ends."""
    best = None
    for (z0, x0), (z1, x1) in zip(points, points[1:]):
        lo, hi = min(z0, z1), max(z0, z1)
        if not (lo - 1e-9 <= z <= hi + 1e-9):
            continue
        if abs(z1 - z0) < 1e-12:
            x = max(x0, x1)
        else:
            x = x0 + (x1 - x0) * ((z - z0) / (z1 - z0))
        best = x if best is None else max(best, x)
    return best


def build_finish_contour_gcode(polyline_feature, back_deg, nose_r=0.0):
    """The soft contour as a point table, or '' when the hard one will do.

    Runtime gate is _pl_fc_n > 0, so '' leaves the contour passes exactly as
    they were.
    """
    pts, is_soft = finish_profile(polyline_feature, back_deg, nose_r)
    if not is_soft:
        return ''

    # Kept for the record: tracing this contour under native compensation used
    # to abort the program - "Straight feed in concave corner cannot be reached
    # by the tool without gouging" - and the cause was segment LENGTH, not
    # corner angle. _min_segment above fixes it. Two other routes exist if this
    # ever hits a dead end: trace the soft stretch with compensation off, which
    # needs the pass split so real surfaces keep their comp; or trace it In-CAM,
    # where offset_contour trims internal corners itself and the interpreter is
    # never asked - though on this part that offset came out non-monotone in Z,
    # so it needs its self-intersections resolved first.
    top = FC_BASE + 2 * len(pts)
    if top > FC_TOP:
        return ('(WARNING - the reachable finishing contour needs %d parameter '
                'slots and only %d are free, so the finishing passes will '
                'follow the drawn contour instead.)'
                % (top - FC_BASE, FC_TOP - FC_BASE))
    lines = ['(the contour the tool can actually reach: the drawn profile)',
             '(widened where the tool back angle shadows it. The finishing)',
             '(passes follow this, as roughing already does)',
             '#<_pl_fc_base> = %d' % FC_BASE,
             '#<_pl_fc_n>    = %d' % len(pts)]
    for i, (z, x) in enumerate(pts):
        lines.append('#%d = %s' % (FC_BASE + 2 * i, _fmt(z)))
        lines.append('#%d = %s' % (FC_BASE + 2 * i + 1, _fmt(x / DIAMETER_MODE)))
    return '\n'.join(lines)
