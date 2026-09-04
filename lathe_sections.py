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
import os
import lathe_comp

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


def resolve_points_untrimmed(polyline_feature):
    """The profile as drawn, before any Z limit is applied.

    The validation needs it to say whether a limit actually falls inside the
    profile: asked of the TRIMMED points, a limit is always at the edge and
    every limit would look inert.
    """
    return resolve_points(polyline_feature, trim=False)


def extend_tangent(points, front=0.0, back=0.0):
    """Run the profile on past its own ends, along its own direction.

    Gap 9. The reference package: *"Creates a tangential extension of the
    geometry from the Front limit"* - the end segment continued along its own
    tangent, front and back each with their own length.

    ALONG THE TANGENT, not along Z, which is what the reference does and the
    only reading that means anything on a taper: extending a 30 degree lead-in
    "by 2 mm" in Z would move the radius 1.15 mm as well and change the shape.
    Along its own direction the segment simply gets longer.

    Applied AFTER the Z limits, so the extension grows from the trimmed end -
    "from the Front limit", in the reference's words - rather than from a
    drawn end the limit has already cut off.

    A profile of fewer than two points, or a zero-length end segment, has no
    tangent to extend along and is returned untouched.
    """
    if not points or len(points) < 2:
        return points

    # A LENGTH IS A LENGTH IN THE Z/RADIUS PLANE. These points carry X as a
    # DIAMETER - this module says so at the top - so taking the tangent in
    # (z, x) as given makes the radial half of it twice its true size: the
    # direction comes out wrong on every taper, and a 3.0 extension of a
    # vertical wall moved the surface 1.5. Measured on testing_15_5 before
    # this: the floor contour's last point went 35.1657 -> 36.6657 in radius
    # for an extension of 3.0. Convert in, extend, convert back.
    def _run_on(p_from, p_to, dist):
        uz, ur = _unit(p_to[0] - p_from[0],
                       (p_to[1] - p_from[1]) / DIAMETER_MODE)
        if abs(uz) <= EPS and abs(ur) <= EPS:
            return p_to
        return (p_to[0] + uz * dist,
                p_to[1] + ur * dist * DIAMETER_MODE)

    pts = list(points)
    if front > EPS:
        pts[0] = _run_on(pts[1], pts[0], front)
    if back > EPS:
        pts[-1] = _run_on(pts[-2], pts[-1], back)
    return pts


# The Workpiece's face Z, published here by `to_gcode` as it walks the tree -
# see z_limit_abs. None when no Workpiece has been seen this build.
#
# Set from OUTSIDE rather than looked up: this module imports nothing from ncam
# on purpose, so that it stays GTK-free and unit-testable, and a Feature has no
# back-reference to the tree it sits in - it holds only its own attributes and
# parameters. The one-way dependency ncam -> lathe_sections already exists
# (ncam.py imports this module), so ncam sets the attribute and this module
# never has to know ncam is there.
WORKPIECE_FACE_Z = None

# The Workpiece's stock diameters, published the same way and for the same
# reason as WORKPIECE_FACE_Z. None means no Workpiece has spoken, and every
# datum that needs one then falls back to the value as written - which is what
# every project did before the datums existed.
WORKPIECE_OD = None
WORKPIECE_ID = None

# The front angle of the tool in force, published by to_gcode's walk the same
# way WORKPIECE_FACE_Z is and for the same reason: this module imports nothing
# from ncam, and a Feature has no back-reference to its tree. 0 means no tool
# has spoken yet, which is indistinguishable from a table with no I column -
# and both must mean "do not constrain", never "0 degrees".
TOOL_FRONT_ANGLE = 0.0

# The loaded tool's nose radius, for the contact-point diameter limit. Same
# route and same reason as the front angle. 0 means no tool has spoken, which
# must mean "do not shift a limit", never "a zero-radius nose".
TOOL_NOSE_R = 0.0


def z_limit_abs(polyline_feature, which):
    """The absolute Z a Z limit sits at, or None when its switch is off.

    Gap 8/14's useful half. A limit used to be an absolute Z and nothing else.
    The reference package gives each one a datum, but its datums - Model front,
    Chuck front, Selection - point at solid geometry we do not have. Ours is a
    real object with a real face, so that is the datum that survives the
    translation: `POLYLINE-GAPS.md` says as much.

    `which` is 'front' or 'end'. Datum 0 is Absolute Z, exactly what the value
    has always meant. Datum 1 measures FROM THE WORKPIECE FACE, into the stock:
    the face is the origin and the value is how far past it the limit sits, so
    the absolute Z is `face - value`. That sign is what makes the number read
    the way a machinist says it - "40 from the face" - rather than as a
    coordinate that happens to be negative.

    WITH NO WORKPIECE IN THE TREE the datum cannot be resolved and the value is
    taken as absolute, which is the behaviour every existing project already
    has. Falling back rather than refusing is deliberate but not silent: it is
    the caller's job to say so, and `build_z_limit_note` emits a comment into
    the program when it happens.
    """
    sw = polyline_feature.get_param(
        'param_fr_z_on' if which == 'front' else 'param_e_z_on')
    val = polyline_feature.get_param(
        'param_fr_z' if which == 'front' else 'param_e_z')
    if sw is None or val is None or _to_float(sw.get_ngc_value()) <= 0:
        return None
    v = _to_float(val.get_ngc_value())
    dat = polyline_feature.get_param(
        'param_fr_z_dat' if which == 'front' else 'param_e_z_dat')
    if dat is None or int(_to_float(dat.get_ngc_value())) != 1:
        return v
    if WORKPIECE_FACE_Z is None:
        return v                       # no Workpiece - see the docstring
    return WORKPIECE_FACE_Z - v


def x_stock_ref(polyline_feature, which):
    """The datum-resolved diameter, with NO tool shift - where the stock is.

    greatEndian, 2026-09-02: *"origin should stay put, only the ladder bound
    moves"*. `param_b_x` does double duty - it is the operation's Begin limit
    AND where the profile starts, and the reference package has no equivalent,
    so it could not settle which of the two the tool reference point applies
    to. The answer is the limit only.

    So the DATUM applies to both - "start at the stock OD" has to move the
    origin with it or the profile begins where the limit no longer is - and
    CONTACT POINT applies to neither the origin, the sectioning stock envelope,
    nor the X-wall stand-off. Those three are asking where the material is, not
    where the cut must stop.
    """
    return x_limit_abs(polyline_feature, which, contact=False)


def x_limit_abs(polyline_feature, which, nose_r=None, contact=True):
    """The diameter a radial limit sits at, in the units param_b_x carries.

    Gap 14's diameter half and gap 10, resolved in one place because they are
    two adjustments to the same number and applying them in different places
    would let them disagree.

    `which` is 'begin' or 'end'.

    GAP 14 - THE DATUM. Value 0 is the diameter itself, exactly what it has
    always meant. Stock OD (1) and Stock ID (2) make the number an OFFSET from
    the Workpiece's own diameter, so the operation follows the stock when the
    stock changes: 0 from the OD is the bar, and a negative offset comes in
    from it. This is the vocabulary `cfg/lathe/facing.cfg` already uses for its
    Begin/End diameters, borrowed rather than reinvented so the two operations
    read the same. `POLYLINE-GAPS.md` records why the reference's own datums -
    Model OD/ID, picked faces - do not survive the translation: they point at
    solid geometry we do not have, and OUR real object is the Workpiece.

    GAP 10 - CUTTING EDGE vs CONTACT POINT. Every limit we have is on the
    CONTROL POINT, so a diameter limit could not say whether it meant where the
    edge stops or where the nose touches; the two differ by the nose radius,
    which is the quantity the whole compensation effort has been about.
    Cutting edge (0) is the control point and is what the value has always
    meant. Contact point (1) shifts the limit by one nose radius so the stated
    diameter is where the nose actually TOUCHES - outward on OD work, inward on
    a bore, because the material is on the other side there.

    WITH NO WORKPIECE the datum cannot resolve and the value is taken as
    written, which is every existing project's behaviour. Falling back rather
    than refusing is deliberate; `build_x_limit_note` says so in the program.
    """
    # None means "the tool that is loaded", which is what every internal caller
    # wants and none of them can look up: they hold a Feature, and a Feature
    # has no back-reference to the tree. Passing 0 explicitly still means "no
    # shift". Getting this wrong is what made the contact-point half cosmetic
    # on its first run - the limit moved 70.0 -> 70.8 in the emitted global and
    # the toolpath did not move at all, because every consumer took the 0.
    if nose_r is None:
        nose_r = TOOL_NOSE_R
    key = 'param_b_x' if which == 'begin' else 'param_e_x'
    prm = polyline_feature.get_param(key)
    if prm is None:
        return None
    v = _to_float(prm.get_ngc_value())

    dat = polyline_feature.get_param(
        'param_b_x_dat' if which == 'begin' else 'param_e_x_dat')
    mode = int(_to_float(dat.get_ngc_value())) if dat is not None else 0
    if mode == 1 and WORKPIECE_OD is not None:
        v = WORKPIECE_OD + v
    elif mode == 2 and WORKPIECE_ID is not None:
        v = WORKPIECE_ID + v

    if not contact:
        return v

    lim = polyline_feature.get_param('param_x_limit')
    if (lim is not None and int(_to_float(lim.get_ngc_value())) == 1
            and nose_r > EPS):
        side = polyline_feature.get_param('param_side')
        inside = side is not None and int(_to_float(side.get_ngc_value())) == 1
        # a diameter moves by TWICE the radius, and DIAMETER_MODE is 2 exactly
        # when these parameters are diameters - so the shift is written in the
        # same units the value arrived in rather than converted twice
        d = nose_r * DIAMETER_MODE
        v = v - d if inside else v + d
    return v


def z_limit_band(polyline_feature):
    """(lo, hi) - the Z band roughing may work in, or None when neither limit
    is set.

    Split out of build_z_limit_bounds_gcode so the roughing window can be
    clamped at generation time from the same band the runtime is handed.
    999999 stands for unbounded on that side, so one limit can be set without
    the other and the single limit still bites.
    """
    fz = z_limit_abs(polyline_feature, 'front')
    ez = z_limit_abs(polyline_feature, 'end')
    if fz is None and ez is None:
        return None
    lo, hi = -999999.0, 999999.0
    for v in (fz, ez):
        if v is None:
            continue
        if fz is not None and ez is not None:
            lo, hi = min(fz, ez), max(fz, ez)
        elif v == fz:
            hi = v
        else:
            lo = v
    return lo, hi


def build_z_limit_bounds_gcode(polyline_feature):
    """The Z band the operation may machine in, for the ROUGHING window.

    The Z limits trim the PROFILE, and every table built from it - the finish,
    pre-finish, entry and stop contours - inherits the trim. The roughing
    window does not: poly_lathe_mill takes its extents from the RECORD ARRAY,
    which is built from the raw polyline items and never sees the trim. Its own
    comment says as much about the back extension, and it carries a
    displacement for that; this is the same correction for the same reason.

    What that cost, measured on testing_15_5 with End Z -40: six roughing FEED
    moves ran the full bar - one of them Z-0.4000 to Z-70.8000 at a constant
    X34.4371 - cutting 30 mm of stock the limit was set to protect. The finish
    passes stopped correctly, so the program looked half right. testing_15_2
    obeys the same limit, because there every level crosses the profile before
    reaching it and the window end never bites; that is why this survived.

    A BAND RATHER THAN TWO CLAMPS, worked out here rather than in the O-code,
    because which limit is the near one depends on the direction the profile
    was drawn in and on which switches are on. Python knows all of that; the
    subroutine should only have to keep two numbers in range.

    999999 stands for "unbounded on that side" so one limit can be set without
    the other. `_pl_lim_on` is 0 when neither is, and the clamp is then skipped
    entirely - which is every project that sets no limit.
    """
    got = z_limit_band(polyline_feature)
    if got is None:
        return '#<_pl_lim_on> = 0'
    lo, hi = got
    return '\n'.join([
        '(the Z band roughing may work in. The contours are trimmed by the)',
        '(limits already; the roughing window comes from the RAW record array)',
        '(and has to be clamped into the same band or a level that never)',
        '(crosses the trimmed profile runs the whole bar. See)',
        '(build_z_limit_bounds_gcode.)',
        '#<_pl_lim_on> = 1',
        '#<_pl_lim_lo> = %s' % _fmt(lo),
        '#<_pl_lim_hi> = %s' % _fmt(hi)])


def build_x_limit_gcode(polyline_feature, nose_r=None):
    """The two resolved radial limits as globals, plus the fallback warning.

    Returned from Python rather than formatted in the cfg because a literal
    `#<name>` inside an inline <exec> is not decoded - the cfg is INI-style,
    not XML, so the escapes stay as written and the interpreter is handed
    `#&lt;_pl_b_x&gt;`. Every other emitter here returns its own lines for the
    same reason; this one is no different.
    """
    # DATUM ONLY. These two feed poly_add_item's origin and the canned-cycle
    # framing rapid - both are "where the stock is", not "where the cut stops",
    # so the contact-point shift must not reach them. The ladder bound takes
    # the full resolution in rough_radius_bounds instead.
    b = x_stock_ref(polyline_feature, 'begin')
    e = x_stock_ref(polyline_feature, 'end')
    if b is None or e is None:
        return ''
    out = ['(the radial limits, resolved: the datum against the Workpiece own)',
           '(stock diameters and the cutting-edge / contact-point choice, both)',
           '(worked out here so the O-code and every table agree on one number)',
           '#<_pl_b_x> = %s' % _fmt(b),
           '#<_pl_e_x> = %s' % _fmt(e)]
    note = build_x_limit_note(polyline_feature)
    if note:
        out.append(note)
    return '\n'.join(out)


def build_x_limit_note(polyline_feature):
    """A comment when a diameter datum has no Workpiece to measure from."""
    for which in ('begin', 'end'):
        dat = polyline_feature.get_param(
            'param_b_x_dat' if which == 'begin' else 'param_e_x_dat')
        if dat is None:
            continue
        mode = int(_to_float(dat.get_ngc_value()))
        if ((mode == 1 and WORKPIECE_OD is None)
                or (mode == 2 and WORKPIECE_ID is None)):
            return ('(WARNING - a diameter limit is set to measure from the '
                    'stock and there is no Workpiece in the tree, so it has '
                    'been taken as a diameter instead.)')
    return ''


def build_z_limit_note(polyline_feature):
    """A comment when a limit asks for a datum there is no Workpiece for."""
    if WORKPIECE_FACE_Z is not None:
        return ''
    for which in ('front', 'end'):
        dat = polyline_feature.get_param(
            'param_fr_z_dat' if which == 'front' else 'param_e_z_dat')
        sw = polyline_feature.get_param(
            'param_fr_z_on' if which == 'front' else 'param_e_z_on')
        if (dat is not None and sw is not None
                and _to_float(sw.get_ngc_value()) > 0
                and int(_to_float(dat.get_ngc_value())) == 1):
            return ('(WARNING - a Z limit is set to measure from the workpiece '
                    'face and there is no Workpiece in the tree, so it has '
                    'been taken as an absolute Z instead.)')
    return ''


def trim_to_front_z(points, f_z):
    """The profile clipped at a FRONT limit, keeping the part behind it.

    The mirror of trim_to_end_z: that one keeps what is in front of the limit,
    this one keeps what is behind it, so the two together cut a span out of the
    profile. Same rules - active only when the limit falls inside the profile,
    and the clipped segment interpolated so the profile begins exactly on it.

    NOT param_b_z. Start Z is a DATUM: it resolves the first item's relative
    coordinates and it is the reference roughing starts from, and it never
    removes profile. Measured on testing_15_2, moving Start Z to -1 and -5 left
    the contour table unchanged at (1.0, 20.0) both times and only moved the
    roughing start. Overloading it would change where relative items land as a
    side effect of asking for a limit.
    """
    if not points or len(points) < 2 or f_z is None:
        return points
    zs = [z for z, _x in points]
    if not (min(zs) < f_z < max(zs)):
        return points

    # the far end tells us which way "behind" is, without assuming a direction
    behind_is_less = points[-1][0] < points[0][0]
    out = []
    for i, (z, x) in enumerate(points):
        keep = z < f_z if behind_is_less else z > f_z
        if keep:
            if not out and i:
                pz, px = points[i - 1]
                if abs(z - pz) > EPS:
                    t = (f_z - pz) / (z - pz)
                    out.append((f_z, px + (x - px) * t))
            out.append((z, x))
    return out if len(out) >= 2 else points


def trim_to_end_z(points, e_z):
    """The profile clipped at an End Z, keeping the part in front of it.

    A back limit stops the operation short of where the polyline itself ends -
    machine this much of the part and leave the rest for another setup, or for
    a tool that can reach past a chuck.

    It is applied HERE, to the profile every builder reads, rather than to each
    of them: the contours, the section windows, the floor ladder and the entry
    and stop tables are all derived from these points, so trimming once is what
    keeps them agreeing with each other. That is the same reason the reference
    package puts its Front and Back limits on the geometry rather than on the
    passes.

    ACTIVE ONLY WHEN THE LIMIT FALLS INSIDE THE PROFILE. At or beyond either
    end it does nothing.

    THE CALLER GATES IT ON ITS OWN SWITCH, and that is not belt-and-braces.
    Using 0.0 as "no limit" was tried and is wrong: testing_15_2's profile
    starts at **Z+1.0**, so 0.0 falls inside it and trimmed the part down to
    its first millimetre - 29 roughing levels became 2. A profile may begin at
    a positive Z, so no Z value is safe as a sentinel.

    The clipped segment is interpolated, so the profile ends exactly on the
    limit rather than at the last vertex before it.
    """
    if not points or len(points) < 2 or e_z is None:
        return points
    zs = [z for z, _x in points]
    if not (min(zs) < e_z < max(zs)):
        return points

    # which side is "in front" is the side the profile starts on
    forward = points[0][0] > e_z
    out = []
    for i, (z, x) in enumerate(points):
        keep = z > e_z if forward else z < e_z
        if keep:
            out.append((z, x))
            continue
        if out:
            pz, px = points[i - 1]
            if abs(z - pz) > EPS:
                t = (e_z - pz) / (z - pz)
                out.append((e_z, px + (x - px) * t))
            break
    return out if len(out) >= 2 else points


def resolve_points(polyline_feature, vertices=None, trim=True, extend=True):
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

    `vertices`, when a list is passed, is filled with the points that are an
    ITEM'S OWN ENDPOINT rather than a sub-point of a densified arc. Those are
    the profile's real corners, and _min_segment must never drop one: dropping
    a chord out of the middle of an arc costs that chord's sagitta, while
    dropping the point where the arc MEETS the next item shortcuts the whole
    corner. On testing_13_arcs that cost 0.94 mm of radius - see the note on
    _min_segment. Collected before apply_merge_radii, so a vertex that a merge
    radius rounds away simply never matches, which is harmless.

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
            if vertices is not None and i == len(span) - 1:
                vertices.append(points[-1])
            # the merge radius rounds the vertex where this item BEGINS, so
            # it belongs to the first sub-point only; apply_merge_radii reads
            # merges[j + 1] as the radius rounding points[j]
            merges.append(seg['merge'] if i == 0 else 0.0)

        prev_z, prev_r = seg['z'], seg['r']

    pts = apply_merge_radii(points, merges)
    # and the back limit, if one falls inside the profile - see trim_to_end_z
    # the front limit first, then the back one - each gated on its own switch,
    # because no Z value is safe as a sentinel when a profile may begin at a
    # positive Z. See trim_to_end_z.
    if not trim:
        return pts

    # each limit resolved through its own datum first - see z_limit_abs. The
    # trims themselves are unchanged and still take an absolute Z, so every
    # contour, window, ladder and table inherits the datum without knowing it
    # exists.
    fz = z_limit_abs(polyline_feature, 'front')
    if fz is not None:
        pts = trim_to_front_z(pts, fz)
    ez = z_limit_abs(polyline_feature, 'end')
    if ez is not None:
        pts = trim_to_end_z(pts, ez)

    # and then run on past the ends, along the profile's own direction - see
    # extend_tangent. AFTER the trims, so the extension grows from the limit
    # rather than from a drawn end the limit has already removed. Here rather
    # than in any one builder, for the same reason the trims are here: the
    # contours, the section windows, the floor ladder and the entry and stop
    # tables are all derived from these points, so they can only agree with
    # each other if the profile they read has already been extended.
    def _ext(name):
        p = polyline_feature.get_param(name)
        return _to_float(p.get_ngc_value()) if p is not None else 0.0

    fr, bk = _ext('param_ext_fr'), _ext('param_ext_bk')
    if extend and (fr > EPS or bk > EPS):
        pts = extend_tangent(pts, fr, bk)
    return pts


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

    # THE ORIGIN TAKES THE RESOLVED DIAMETER TOO. param_b_x is the profile's
    # start point as well as the operation's Begin limit, so a datum that says
    # "start at the stock OD" has to move the origin with it or the profile
    # would begin somewhere the limit no longer is.
    origin = (_to_float(b_z_param.get_ngc_value()),
              x_stock_ref(polyline_feature, 'begin') / DIAMETER_MODE)
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

    THE ROUGHING ALLOWANCE IS NOT ADDED HERE - the caller adds it. This is the
    contour's own peak and nothing else, which is what makes it testable
    against the drawn profile; build_sections_gcode adds level_allowance() to
    turn it into the radius at which a roughing LEVEL first touches something.
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


def section_windows(polyline_feature):
    """The sectioning windows, mode and ceiling as DATA - (windows, sect_mode,
    top_x) or None when Sectioning is off or the profile cannot be analysed.

    Split out of build_sections_gcode so the roughing ladder can be worked
    out at generation time from the same windows the runtime is handed,
    rather than from a re-parse of the G-code this emits. The emitter below
    is now only the emitter; every decision stayed here.

    Originally: returns literal G-code text assigning _pl_sect_count,
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
        return None

    points = resolve_points(polyline_feature)
    if not points or len(points) < 2:
        return None

    dir_param = polyline_feature.get_param('param_dir')
    rough_dir = int(_to_float(dir_param.get_ngc_value())) if dir_param is not None else 0
    # ONE FRAME. `points` used to be reversed here for direction 1, which made
    # the sections, their ranking and their radius bands a different
    # decomposition rather than the same one taken the other way round - see
    # rough_frame_dir. Back to front now re-orders the finished window list
    # below and changes nothing about what the windows ARE.
    frame_dir = rough_frame_dir(rough_dir)

    sections = detect_sections(points)
    if not sections:
        return None

    sec_len_param = polyline_feature.get_param('param_sec_len')
    sec_len = _to_float(sec_len_param.get_ngc_value()) if sec_len_param is not None else 0.0

    if sec_len > 0:
        pieces = split_by_length(sections, points, sec_len)
        ordered = [(z_from, z_to) for z_from, z_to, _min_x in pieces]
        sect_mode = 1
    else:
        ordered = rank_weakest_first(sections)
        sect_mode = 0

    stock_x = x_stock_ref(polyline_feature, 'begin')
    # PLUS THE ALLOWANCE. The ceiling is a question about the ROUGHING FLOOR,
    # not about the finished part: a roughing level stops at the profile
    # offset by fin_off + prefin_off, so nothing anywhere has reached that
    # floor until the level drops below the profile's highest point PLUS that
    # offset. Read off the raw contour it stopped 1.508 mm (in radius) too
    # high on testing_15_6 - 65.3182 instead of 68.3342 in diameter - and
    # every one of those levels was sectioned when a full-length pass was
    # still safe. greatEndian, 2026-08-18: *"we are going full long length
    # passes deeper, till level of the highest spot of part contour and just
    # then we splitting it to sections"*. build_level_split_gcode already
    # asks the same geometric question the same way, peak + level_allowance -
    # see _boundary_list - so the two agree by construction now instead of by
    # coincidence. poly_lathe_mill.ngc clamps the result against start_radius,
    # so a ceiling the allowance lifts above the stock costs no passes.
    top_x = ceiling(points, stock_x) + level_allowance(polyline_feature)

    if sect_mode == 0:
        windows = band_windows(sections, ordered, points)
    else:
        # Artificial bounds how long any single cut may be, at every depth,
        # so its pieces deliberately apply over the whole radius range - see
        # this function's own docstring for why it must not be merged.
        windows = [(z_from, z_to, 0.0, BAND_ALL) for z_from, z_to in ordered]

    # BACK TO FRONT ONLY - not "any direction whose frame differs". Direction 2
    # also decomposes in frame 0 now (see rough_frame_dir), but it is not a
    # re-ordering of the windows: it visits them in direction 0's own order and
    # alternates the EMISSION of each pass. Testing `frame_dir != rough_dir`
    # here would have handed it direction 1's window order as well, which is a
    # different traversal from the one greatEndian asked for and would have
    # moved the split levels on top of it.
    if rough_dir == 1:
        windows = _sections_back_to_front(windows, points)
        windows = _split_level_intervals(windows, points, sections,
                                         level_allowance(polyline_feature))

    return windows, sect_mode, top_x


def build_sections_gcode(polyline_feature):
    """The #3400 window block, _pl_sect_count, _pl_sect_mode and the
    raw ceiling - or '' when section_windows has nothing to say.
    """
    got = section_windows(polyline_feature)
    if got is None:
        return ''
    windows, sect_mode, top_x = got

    lines = [
        '#<_pl_sect_count> = %d' % len(windows),
        '#<_pl_sect_mode> = %d' % sect_mode,
        '#<_pl_sect_top_dia> = %s' % _fmt(top_x),
    ]
    # THE PER-WINDOW DEEPEST-CUT SLOTS, cleared to "nothing cut here yet".
    # 999999 is not a decorative sentinel: lathe_level_pass takes the MAXIMUM
    # over the windows an entry lead crosses, so an uncut neighbour carries the
    # whole comparison and the lead is kept. Clearing to 0 - which is what an
    # untouched numbered parameter reads as - would instead say "cut to the
    # centre" and drop every lead on the part.
    # _pl_wdeep_ok is the guard for exactly that: a project generated before
    # this table existed leaves it 0 (see create_defaults) and the gate stands
    # down rather than reading slots nobody filled in.
    if len(windows) <= (WDEEP_TOP - WDEEP_BASE):
        lines.append('#<_pl_wdeep_ok> = 1')
        for i in range(len(windows)):
            lines.append('#%d = 999999' % (WDEEP_BASE + i))
    else:
        lines.append('(more windows than the deepest-cut table holds - entry)')
        lines.append('(lead gating off for this program, roughing unchanged)')
        lines.append('#<_pl_wdeep_ok> = 0')
    for i, (z_from, z_to, r_lo, r_hi) in enumerate(windows):
        slot = 3400 + i * 4
        lines.append('#%d = %s' % (slot + 1, _fmt(z_from)))
        lines.append('#%d = %s' % (slot + 2, _fmt(z_to)))
        lines.append('#%d = %s' % (slot + 3, _fmt(r_lo)))
        lines.append('#%d = %s' % (slot + 4, _fmt(r_hi)))

    return '\n'.join(lines) + '\n'


def _sections_back_to_front(windows, points):
    """The same windows, visited last-recognised-section first.

    greatEndian's spec for `param_dir` = 1, 2026-08-15: *"rough all long
    passes from last reference to first, then last recognized section rough,
    last recognized section - 1, repeating to first/front section"*.

    THE BANDS KEEP THEIR ORDER. `band_windows` emits highest radius band
    first, and roughing has to keep working downward whichever way it travels
    - a band re-order would have the tool dropping to the deepest levels
    before the stock above them is gone. So only the windows WITHIN a band are
    re-ordered, and the "long passes" - the merged full-length window in the
    topmost band, and Sectioning's own unsectioned phase 1 - stay first by
    construction.

    Back-most first means furthest from the profile's own first point, which
    is the "first reference"; that works whichever way round the polyline was
    drawn. Natural sectioning normally ranks weakest-first inside a band, and
    this replaces that ranking for direction 1 on purpose: greatEndian asked
    for section order, not for diameter order.
    """
    if not windows:
        return windows
    z0 = points[0][0]
    out = []
    i = 0
    while i < len(windows):
        j = i
        band = (windows[i][2], windows[i][3])
        while j < len(windows) and (windows[j][2], windows[j][3]) == band:
            j += 1
        out += sorted(windows[i:j], key=lambda w: -abs(w[0] - z0))
        i = j
    return out


def level_allowance(polyline_feature):
    """The stock a roughing level holds off the profile, in POINTS units.

    This is `lvl_d` in poly_lathe_mill.ngc - `fin_off + prefin_off`, the
    radial allowance the level scan offsets the profile by before looking for
    its crossing - converted to the diameter units `points`, `boundary_height`
    and a window's radius band are all carried in.

    The radial offset, not the axial one: with *Separate Z offset* on the two
    differ, but the level scan is given one number (CALL args 13 and 25) and
    that number is the radial one.
    """
    def _v(name):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else 0.0

    fin_off, _fin_z = stock_pair(polyline_feature)
    pf_on = polyline_feature.get_param('param_pf_on')
    pf_off = _v('param_pf_off')
    if pf_on is not None and _to_float(pf_on.get_ngc_value()) <= 0:
        pf_off = 0.0
    return (fin_off + pf_off) * DIAMETER_MODE


def _boundary_list(sections, points):
    """[(z, height, is_peak)] for every internal section boundary.

    Same spans, same order and the same `boundary_height` band_windows uses -
    these ARE the boundaries it merged away, looked at again.

    `is_peak` is what makes a boundary able to split a level in two: the
    sections on both sides have to reach BELOW it, or there is no second
    interval behind it to reach. A step or a flat-to-rise boundary is a
    boundary all the same and blocks a level just as well, but everything past
    it is above the level too, so the level simply stops there - splitting a
    window on one would only add a window that cuts nothing.
    """
    z_ordered = sorted(sections, key=lambda s: -s[0]) \
        if sections[0][0] > sections[-1][0] else sorted(sections, key=lambda s: s[0])
    spans = [(z_from, z_to) for z_from, z_to, _m in z_ordered]

    def _side_min(span, z_b):
        """The lowest the profile gets in `span`, IGNORING the boundary itself.

        Not `detect_sections`' own min_x: that is taken over the points a
        section RECEIVES, which on a straight rise is just its far end, so a
        boss made of two plain tapers would have the peak as its own minimum
        and be rejected. What decides a peak is whether there is material
        below it on each side, and the boundary vertex is on neither side.
        """
        lo, hi = min(span), max(span)
        xs = [x for z, x in points
              if lo - EPS <= z <= hi + EPS and abs(z - z_b) > EPS]
        return min(xs) if xs else None

    out = []
    for i in range(len(spans) - 1):
        z_b = spans[i][1]
        h = boundary_height(points, z_b)
        left, right = _side_min(spans[i], z_b), _side_min(spans[i + 1], z_b)
        out.append((z_b, h,
                    left is not None and right is not None
                    and left < h - EPS and right < h - EPS))
    return out


def _split_level_intervals(windows, points, sections, allowance):
    """One window per INTERVAL, for the levels a merged window splits in two.

    Direction 1 only. `_sections_back_to_front` orders WINDOWS, so a level
    whose two intervals live in two windows is reversed for free - measured on
    testing_15_6 with Sectioning on, 13 of the 16 multi-interval levels come
    out back-first that way. The other 3 have both intervals inside ONE window
    - the merged full-length one at the top - where the runtime discovers them
    sequentially (cut, `lathe_level_next_start`, cut) and nothing knows the
    second one exists until the first has been emitted. Python is never handed
    two things to order, so it cannot order them. See analysis/056 and 057.

    THE SPLIT IS PER BAND, NOT PER LEVEL, and that is what makes it
    expressible. A boss is tapered, so the Z gap it opens in a level moves
    with the level - on testing_15_6, -28.96..-37.41 at X33.5965 and
    -27.48..-39.61 at X33.0885 - and a window cannot carry a per-level Z. It
    does not have to: the gaps are NESTED. Every level at or below a
    boundary's own height plus the floor allowance is blocked AT that boundary
    - the scan offsets the profile outward by `allowance`, and a normal offset
    at a vertex is never nearer the profile than the radial one - so the
    boundary's own Z sits inside every one of those gaps. One split point, the
    whole sub-band.

    That also fixes where the sub-band ends. A level ABOVE
    `boundary_height + allowance` may run straight through the boundary, and
    splitting the window there would cut it as two spans where it was one -
    the cut set, which is the property this whole direction exists to keep.
    So each window keeps a full-span copy of itself over the band above the
    lowest qualifying threshold, and only the band below it is split.

    Two kinds of boundary are passed over. One whose threshold is at or below
    the window's own band bottom cannot block anything this window cuts. And
    one that is not a PEAK - see `_boundary_list` - has nothing behind it for
    a second interval to reach, so a piece there would cut air; splitting on
    every merged-away boundary instead was measured at 15 windows on
    testing_15_6 where 10 do the work.

    Artificial sectioning is a no-op here by construction: `split_by_length`
    never crosses a natural boundary, so a slice has no boundary inside it.
    """
    if allowance <= EPS or len(sections) < 2 or not windows:
        return windows
    bounds = _boundary_list(sections, points)
    if not bounds:
        return windows
    z0 = points[0][0]

    out = []
    for w in windows:
        z_from, z_to, r_lo, r_hi = w
        lo_z, hi_z = min(z_from, z_to), max(z_from, z_to)
        act = [(z_b, h_b) for z_b, h_b, peak in bounds
               if peak and lo_z + EPS < z_b < hi_z - EPS
               and h_b + allowance > r_lo + EPS]
        if not act:
            out.append(w)
            continue
        # the lowest threshold, so every level in the sub-band is blocked at
        # EVERY split point in it - a level between two thresholds keeps the
        # unsplit window above and is simply left in front-first order
        top = min(min(h_b for _z, h_b in act) + allowance, r_hi)
        if top - r_lo <= EPS:
            out.append(w)
            continue
        if r_hi - top > EPS:
            out.append((z_from, z_to, top, r_hi))
        cuts = sorted((z_b for z_b, _h in act), reverse=z_from > z_to)
        pieces = []
        prev = z_from
        for z_b in cuts:
            pieces.append((prev, z_b, r_lo, top))
            prev = z_b
        pieces.append((prev, z_to, r_lo, top))
        # back-most piece first, the same "furthest from the profile's own
        # first point" rule _sections_back_to_front orders whole windows by
        pieces.sort(key=lambda p: -abs(p[0] - z0))
        out += pieces

    # The table is 200 slots - 50 windows - and nothing above it is spare. A
    # profile that would overflow keeps the unsplit list: the interval order
    # inside a level is a consistency nicety, and a truncated window table is
    # metal left standing.
    if SECT_BASE + 4 * len(out) > FLANK_BASE:
        return windows
    return out


def split_peaks(polyline_feature):
    """([(z, height)], allowance) - the peaks that split a roughing level, or
    ([], 0.0).

    Split out of build_level_split_gcode so the sub-span walk can be worked out
    at generation time from the same peaks the runtime is handed.

    BACK TO FRONT ONLY. Direction 2 shares direction 0's window order and its
    single-span levels; a split table there would re-order intervals that
    direction 0 does not, and the cut set has to match it.
    """
    dir_param = polyline_feature.get_param('param_dir')
    rough_dir = (int(_to_float(dir_param.get_ngc_value()))
                 if dir_param is not None else 0)
    if rough_dir != 1:
        return [], 0.0
    allowance = level_allowance(polyline_feature)
    if allowance <= EPS:
        return [], 0.0
    points = resolve_points(polyline_feature)
    if not points or len(points) < 2:
        return [], 0.0
    sections = detect_sections(points)
    if not sections or len(sections) < 2:
        return [], 0.0
    return [(z_b, h_b) for z_b, h_b, peak in _boundary_list(sections, points)
            if peak], allowance


def build_level_split_gcode(polyline_feature):
    """The #3160 table of split points a level's intervals are ordered by.

    Back to front, the interval order inside one level is Python's decision
    everywhere a WINDOW carries it - `_sections_back_to_front` orders windows
    and `_split_level_intervals` gives each interval of a split level its own
    window. Two sweeps are not window-driven and so were out of that fix's
    reach, and both emitted their intervals front-first (`analysis/057`):

    - Sectioning ON, phase 1 - the unsectioned full-length pass, `w_idx < 0`,
      with its own multi-crossing loop;
    - Sectioning OFF - one full-length window `poly_lathe_mill` builds itself.

    Both discover a boss's two intervals sequentially - cut,
    `lathe_level_next_start`, cut - so nothing knows the second one exists
    until the first has been written.

    THE GEOMETRY IS THE SAME ONE `_split_level_intervals` RUNS ON. The gap a
    boss opens in a level is `{ z : profile(z) + allowance >= level }`, which
    can only GROW as the level drops, so the gaps at every level below a peak
    are nested around the peak's own Z: one split point per peak serves every
    level it blocks, and `peak height + allowance` is the radius at or below
    which it certainly does - a normal offset at a vertex is never nearer the
    profile than the radial one. Above that the level may run straight
    through and must NOT be split, or a span that was cut as one would be cut
    as two and the cut set would move.

    So this emits the peaks, each with its own threshold, and the runtime
    walks the level in sub-spans between the ones that are active at that
    level, back-most first. **The scan still finds where every cut actually
    starts and stops** - a split point is only a bound handed to it, and it
    sits at the peak, safely inside the blocked gap, not at the scan's own
    resume answer which can land just inside a rise (`analysis/058`).

    Peaks only, as in `_split_level_intervals`: a step or a flat-to-rise
    blocks a level just as well, but everything past it is above the level
    too, so a sub-span behind it would cut nothing.

    Returns '' - and changes nothing at all - for front to back, for a profile
    with no peak, and if the table would overflow its 40 slots - 3160 to 3200,
    twenty peaks. NOT 3140: cfg/lathe/polyline.cfg stages its own CALL
    arguments in #3141-#3159, which is why cam_map now has a cfg_scratch check.
    """
    peaks, allowance = split_peaks(polyline_feature)
    if not peaks:
        return ''
    # a truncated table is a level split at the wrong place, which is metal
    # left standing - refuse it and keep the front-first order instead
    if LVLSPLIT_BASE + 2 * len(peaks) > LVLSPLIT_TOP:
        return ''

    lines = [
        '(peaks that split a roughing level into more than one interval, with)',
        '(the radius at or below which each certainly blocks one - its own)',
        '(height plus the floor allowance. Read only back to front, and only)',
        '(by the sweeps no window table orders: Sectioning off, and phase 1.)',
        '#<_pl_p1s_n> = %d' % len(peaks),
    ]
    for i, (z_b, h_b) in enumerate(peaks):
        slot = LVLSPLIT_BASE + i * 2
        lines.append('#%d = %s' % (slot, _fmt(z_b)))
        lines.append('#%d = %s' % (slot + 1, _fmt(h_b + allowance)))
    return '\n'.join(lines) + '\n'


# The level-split table: peaks and the radius each blocks below, two slots per
# peak. 3160-3200, the gap between cfg/lathe/polyline.cfg's own CALL scratch -
# #3141-#3159, and NOT free despite sitting between two declared windows - and
# the entry-ramp table. 20 peaks; every demo project measured has at most 3.
LVLSPLIT_BASE = 3160
LVLSPLIT_TOP = 3200


# Stand-in for "no upper limit" on a window's radius band, in the diameter
# units the whole module works in. Larger than any real workpiece.
BAND_ALL = 1.0e6


# The floor tables. 3200-3400 is free space: the polyline's own argument slots
# stop at #3159 and the sections window table starts at #3400.
#
#   3200  entry ramp, i*4           direction and an anchor point on the
#                                   surface a ramp should follow
#   3380  floor stages, i           the floors the ladder re-anchors on,
#                                   shallowest first - see floor_ladder
SECT_FLOOR_BASE = 3380


def region_floor(min_dia, fin_off, prefin_off, rough_cut, anchored):
    """The roughing floor a region with this deepest diameter is entitled to.

    Radius units out, diameter units in - the same asymmetry the rest of this
    module lives with, because `points` are diameters and a floor is a radius.

    This REPRODUCES poly_lathe_mill.ngc's own arithmetic, deliberately and
    exactly. Anywhere it drifts from that, the table would ask the level loop
    for a floor the loop's own ladder cannot land on, which is the bug this
    whole thing exists to remove:

        rough_target = final + fin_off             the pre-finish surface
        step_target  = rough_target + prefin_off   the roughing floor
        anchored     rough_target stepped OUTWARD by whole depths of cut,
                     taking the first grid level still clear of step_target

    OD only - see floor_regions.
    """
    rough_target = min_dia / DIAMETER_MODE + fin_off
    step_target = rough_target + prefin_off
    if not anchored or rough_cut <= EPS:
        return step_target
    k_min = int(math.ceil((step_target - rough_target) / rough_cut - EPS))
    return rough_target + max(k_min, 0) * rough_cut


def floor_regions(points, fin_off, prefin_off, rough_cut, anchored):
    """[(z_from, z_to, floor_radius)] - the profile split where its floor moves.

    THE POINT OF THIS. A roughing level is one radius held across its whole
    sweep, and the ladder of levels is anchored on a floor. Take that floor
    from the deepest point of the WHOLE part - which is what a single
    `final_radius` does - and every region that is not the deepest gets its
    levels positioned by somebody else's floor.

    Measured on testing_15_4: the front chamfer bottoms at r19 and the
    cylinder behind it at r20, so their own floors are 20.016 and 21.016.
    The difference is 1.000 mm against a 0.508 depth of cut, so **no single
    grid can land on both** - one of them always gets its deepest level as a
    sliver. It was the cylinder, 0.016 mm above its own pre-finish contour.

    Regions come from detect_sections, which already splits the profile
    wherever its trend changes, so each one is monotonic and its `min_x` IS
    that region's deepest material. Neighbours entitled to the same floor are
    merged so a plain cylinder stays one window.

    OD ONLY. On a bore the floor runs the other way and every comparison here
    inverts; ID work is paused (openPoints) and a wrong guess would rough into
    the wall rather than leave a sliver, so it returns [] instead.
    """
    if len(points) < 2 or rough_cut <= EPS:
        return []
    sections = detect_sections(points)
    if not sections:
        return []

    regions = []
    for z_from, z_to, min_x in sections:
        floor = region_floor(min_x, fin_off, prefin_off, rough_cut, anchored)
        if regions and abs(regions[-1][2] - floor) < EPS \
                and abs(regions[-1][1] - z_from) < EPS:
            regions[-1] = (regions[-1][0], z_to, floor)
        else:
            regions.append((z_from, z_to, floor))
    return regions


def region_cut_length(points, z_from, z_to, floor, allowance, samples=24):
    """How much Z a roughing level at `floor` could actually cut in a region.

    A level cuts where the material still stands above it - where the profile
    plus the allowance roughing must leave is still under the level. Sampled
    rather than solved: the profile is a polyline of hundreds of chords here
    and this only has to tell a real surface from a single touching point.
    """
    lo, hi = min(z_from, z_to), max(z_from, z_to)
    total = 0.0
    for (z0, x0), (z1, x1) in zip(points, points[1:]):
        a, b = max(min(z0, z1), lo), min(max(z0, z1), hi)
        if a > b:
            continue
        for k in range(samples):
            zm = a + (b - a) * (k + 0.5) / samples
            x = x0 if abs(z1 - z0) < EPS else \
                x0 + (x1 - x0) * (zm - z0) / (z1 - z0)
            if x / DIAMETER_MODE + allowance < floor:
                total += (b - a) / samples
    return total


def floor_ladder(points, fin_off, prefin_off, rough_cut, anchored):
    """The floors a roughing ladder must land on, shallowest first.

    One entry per DISTINCT floor the profile's own regions are entitled to.
    The ladder does not need to know WHERE each one applies: a level that
    drops past a region's floor simply cannot reach that region any more -
    the stop contour holds it off - so the Z span narrows by itself. What it
    does need is to LAND on each of them, and a single grid cannot:
    testing_15_4's chamfer is entitled to 20.016 and its cylinder to 21.016,
    1.000 apart against a 0.508 depth of cut, so anchoring on either leaves
    the other 0.016 out. Re-anchoring at each floor in turn lands on both.
    """
    regions = floor_regions(points, fin_off, prefin_off, rough_cut, anchored)
    if not regions:
        return []

    # A FLOOR TAKEN FROM A SINGLE POINT IS NOT A FLOOR. A region's floor comes
    # from its deepest material, and where that depth is reached at one point -
    # the tip of a chamfer, the foot of an arc where it meets a cylinder - a
    # level there cuts nothing worth an approach, while the stage it demands
    # breaks the uniform descent for the WHOLE part.
    #
    # Measured on testing_15_4, the Z a level at each floor could cut inside
    # its own region:
    #
    #     chamfer   Z0 .. -1        floor 20.0160     0.2500 mm
    #     cylinder  Z-1 .. -20      floor 21.0160    19.0000 mm
    #     boss      Z-20 .. -32.5   floor 21.7227     0.0301 mm
    #     cylinder  Z-32.5 .. -70.4 floor 21.0160    25.4000 mm
    #
    # The two that broke the descent into 0.3252 / 0.3534 / 0.3534 are exactly
    # the two that cut nothing. One depth of cut of Z is the bar: below that a
    # level costs an approach and a retract to remove a smear.
    allowance = fin_off + prefin_off
    floors = []
    for z_from, z_to, floor in regions:
        if region_cut_length(points, z_from, z_to, floor, allowance) < rough_cut:
            continue
        if not any(abs(floor - f) < EPS for f in floors):
            floors.append(floor)
    # the part's own deepest floor is always the end of the ladder, whether or
    # not any single region earns it - roughing has to stop somewhere, and that
    # is the radius poly_lathe_mill would have used on its own
    deepest = min(f for _a, _b, f in regions)
    if not any(abs(deepest - f) < EPS for f in floors):
        floors.append(deepest)
    floors.sort(reverse=True)

    # FLOORS TOO CLOSE TOGETHER ARE ONE FLOOR. testing_13_arcs is entitled to
    # 22.7805 and 22.762 - 0.0185 apart - and giving each its own stage buys a
    # 0.0185 mm cut, which is a pass that rubs rather than cuts, plus its own
    # approach and retract. Seven such stages made the program heavy enough to
    # run rs274 past its 120 s budget.
    #
    # The SHALLOWER one survives, and that direction is not arbitrary: merging
    # to the deeper floor would cut 0.0185 past what the shallower region is
    # entitled to and eat into its pre-finish allowance, while merging to the
    # shallower leaves that much standing for the pre-finish pass to take -
    # which is what the pass is for.
    #
    # Half the depth of cut is a CHOICE, not a measurement: it is the point
    # below which a level is not worth the approach it costs. Same shape of
    # judgement as the ramp cap in lathe_level_pass.
    merged = []
    for f in floors:
        if not merged or abs(merged[-1] - f) > 0.5 * rough_cut:
            merged.append(f)
    return merged


# The entry-ramp direction table. One (dz, dx) per entry-contour segment,
# in the free space under the sections table.
# The roughing RESUME envelope - see resume_envelope(). Below ERAMP, in the
# space between the record array and the cfg's own CALL scratch at 3141-3159.
RESUME_BASE = 3000
RESUME_TOP = 3140

ERAMP_BASE = 3200
ERAMP_TOP = 3380


def ramp_facing(orient):
    """Which way along Z the insert's cutting edge faces, or 0 for no view.

    The profile-angle ramp exists to arrive PARALLEL to a surface, and it can
    only do that if the tool meets that surface with its CUTTING edge. Approach
    it the other way round and the trailing flank leads instead - the ramp is
    then rubbing its way in, and a plain lead-in is the right move.

    Nothing in the ramp path used to ask this. `entry_ramp_dirs` saw the
    profile alone and `o<pa_side>` in lathe_level_pass tests only that the ramp
    starts on the stock side RADIALLY, which is a different question: it says
    "come in from outside", never "come in from the end the tool can cut".

    The orientation is the whole answer, and NOSE_OFFSET already carries it.
    Its Z component is where the nose centre sits relative to the programmed
    point, so the edge faces the OTHER way: orient 2, (X +1, Z +1), is the
    ordinary right-hand OD tool and cuts toward -Z.

    Reflecting the tool about the X axis negates that Z - orient 2 becomes
    orient 1, (X +1, Z -1) - and the facing flips with it, which is exactly
    greatEndian's catch, 2026-09-01: *"if we have tool which is mirrored in the
    X axis and if we have taper character part we have to create same
    behaviours"*. The mirrored tool keeps every ramp the unmirrored one loses.

    Orientations 6, 8 and 9 have no Z component - facing tools and on-the-point
    - so they express no axial preference and this refuses nothing for them.
    """
    off = NOSE_OFFSET[orient] if 0 < int(orient or 0) < len(NOSE_OFFSET) else None
    if not off:
        return 0
    z = off[1]
    return -1 if z > 0 else (1 if z < 0 else 0)


def entry_ramp_dirs(points, look):
    """Per entry segment, the direction a ramp starting on it should copy.

    The profile-angle approach exists to arrive PARALLEL to the surface the
    pass is about to run along. Where the level crosses the entry contour the
    crossing names that surface itself. Where it does not - a level above the
    contour's own peak - something has to choose, and the segment the pass
    happens to start on is the wrong answer: near the foot of a boss that is a
    short shallow scrap of fillet, and copying it made the ramp 2.9656 long
    where every neighbouring pass runs 2.2004. greatEndian: the parallel
    section behind the boss has to have the same parameters as the others, no
    extra length.

    The surface it will actually run along is the DOMINANT one just ahead -
    the longest segment within `look` of the start. On testing_15_5 that is
    the long taper down the back of the boss, which is what the crossings of
    every deeper level land on, so the fallback and the crossings agree.
    """
    segs = list(zip(points, points[1:]))
    out = []
    for i in range(len(segs)):
        best, travelled = None, 0.0
        for j in range(i, len(segs)):
            (z0, x0), (z1, x1) = segs[j]
            dz = z1 - z0
            if abs(dz) > EPS and (best is None or abs(dz) > abs(best[0])):
                # the direction AND a point on it. A level that never crosses
                # the contour has no crossing to start on, and the line this
                # names is where it WOULD have crossed - which is the line
                # every neighbouring ramp already lies on.
                best = (dz, x1 - x0, z0, x0)
            travelled += abs(dz)
            if travelled > look:
                break
        out.append(best or (0.0, 0.0, 0.0, 0.0))
    return out


def build_entry_ramp_gcode(points, rough_cut):
    """The #3200 ramp-direction table, or '' when there is nothing to say.

    Indexed by entry-contour segment, so the runtime reads the direction for
    the segment it is standing on instead of working one out.
    """
    if not points or len(points) < 3 or rough_cut <= EPS:
        return ''
    dirs = entry_ramp_dirs(points, 10.0 * rough_cut)
    if ERAMP_BASE + len(dirs) * 4 + 3 >= ERAMP_TOP:
        return ''
    lines = ['(the direction a profile-angle ramp should copy, one per entry)',
             '(segment - the dominant surface just ahead of it, which is what)',
             '(a crossing would have named. See entry_ramp_dirs.)',
             '#<_pl_eramp_n> = %d' % len(dirs)]
    for i, (dz, dx, az, ax) in enumerate(dirs):
        slot = ERAMP_BASE + i * 4
        lines.append('#%d = %s' % (slot, _fmt(dz)))
        lines.append('#%d = %s' % (slot + 1, _fmt(dx)))
        lines.append('#%d = %s' % (slot + 2, _fmt(az)))
        lines.append('#%d = %s' % (slot + 3, _fmt(ax)))
    return '\n'.join(lines) + '\n'


def rough_radius_bounds(polyline_feature):
    """(begin, end) radius for the roughing ladder, widened for an extension.

    The ladder runs between `param_b_x` and `param_e_x` - the operation's own
    Begin and End diameters - and NOT between the profile's own extremes. That
    is right until a tangential extension takes the profile past one of them,
    which is exactly what it is for: extending a rising front cone forward
    makes the part smaller than End X, and roughing then stops short while the
    pre-finish and finish passes, which follow the profile, run on out there.

    Measured on testing_15_5 with a front extension of 3.0: the floor, stop and
    entry contours all moved correctly - first point (0.8217, 19.0217) ->
    (2.9430, 16.9003), 3.0 along the 45 degree tangent - while the ladder kept
    its 30 levels and its lowest radius of 20.016, so roughing reached Z2.4284
    against the contour passes' Z3.7071. greatEndian: it "works only in
    prefinish and finish and it should work for the roughing too".

    WITH NO EXTENSION THE PARAMETERS ARE RETURNED UNTOUCHED, so every saved
    project keeps the ladder it has always had - asserted byte-identical.

    Widened only in the direction the profile actually went, and by min/max
    against the parameter rather than replacing it, so an extension can add
    levels but never remove one.
    """
    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    b = x_limit_abs(polyline_feature, 'begin') / DIAMETER_MODE
    e = x_limit_abs(polyline_feature, 'end') / DIAMETER_MODE
    if _p('param_ext_fr') <= EPS and _p('param_ext_bk') <= EPS:
        return b, e

    pts = resolve_points(polyline_feature)          # already extended
    if not pts or len(pts) < 2:
        return b, e
    rs = [x / DIAMETER_MODE for _z, x in pts]
    lo_r, hi_r = min(rs), max(rs)
    # b >= e is OD - the ladder descends from the stock inwards. On a bore both
    # comparisons invert; ID work is paused, so it is written out rather than
    # assumed symmetric.
    if b >= e:
        return max(b, hi_r), min(e, lo_r)
    return min(b, lo_r), max(e, hi_r)


def ext_dz(polyline_feature, end='front'):
    """Signed Z displacement the tangential extension adds at one end, or 0.0.

    NOT the extension length. The extension runs along the segment's own
    tangent, so its Z component is `length * cos(angle)` - on the 45 degree
    front cone of testing_15_5 a 3.0 extension moves Z by 2.121, not 3.0.
    `_pl_begin_z` was adding the raw length, starting roughing 0.88 further
    forward than the profile actually reaches and sweeping that much air.

    The BACK end needs the same number for the opposite reason: the roughing
    sweep takes both its bounds from the RECORD ARRAY - `e_z` is its first
    point and `l_z` its last - and the record array is built from the raw
    polyline items, so it never sees the extension at all. The contours do,
    which is why the pre-finish and finish passes ran out there while roughing
    stopped short.

    A displacement rather than an absolute Z on purpose: it is 0.0 when no
    extension is set, so adding it is byte-identical by construction, and it
    cannot disagree with the record array about where the profile ended.
    """
    plain = resolve_points(polyline_feature, extend=False)
    full = resolve_points(polyline_feature)
    if not plain or not full or len(plain) < 2 or len(full) < 2:
        return 0.0
    i = 0 if end == 'front' else -1
    return full[i][0] - plain[i][0]


def build_rough_bounds_gcode(polyline_feature):
    """Emit the ladder's radius bounds as globals, always.

    Always, not only when an extension is set, so the cfg can read them
    unconditionally and there is one code path rather than two. With no
    extension they are the parameters themselves and nothing moves.

    Emitted from the cfg immediately BEFORE the slots that consume them -
    ordering is the whole point, since these are plain G-code assignments and a
    value read before it is written is zero.
    """
    b, e = rough_radius_bounds(polyline_feature)
    return ('(roughing ladder bounds - the Begin and End diameters, widened to)\n'
            '(cover a tangential extension where one takes the profile past)\n'
            '(them. Equal to the parameters when no extension is set.)\n'
            '#<_pl_rgh_hi_r> = %s\n#<_pl_rgh_lo_r> = %s\n'
            '(how much further in Z the BACK extension reaches - the roughing)\n'
            '(sweep takes its far bound from the record array, which is built)\n'
            '(from the raw items and never sees an extension. 0.0 when off.)\n'
            '#<_pl_ext_bk_dz> = %s'
            % (_fmt(b), _fmt(e), _fmt(ext_dz(polyline_feature, 'back'))))


def floor_stages(polyline_feature, rough_cut=0.0):
    """The floor stages this profile is entitled to, shallowest first, as DATA.

    Split out of build_floor_ladder_gcode so the roughing ladder can be worked
    out at generation time from the same stages the runtime re-anchors on -
    the ladder needs them as numbers, and they existed only as emitted G-code.
    Fewer than two means one floor fits the whole part, which is the common
    case and the one that leaves the ladder exactly as it was.
    """
    points = resolve_points(polyline_feature)
    if not points or len(points) < 2 or rough_cut <= EPS:
        return []

    # THE FLOOR STAGES ARE THE SAME STAGES WHICHEVER WAY ROUGHING TRAVELS.
    # `points` was reversed here for direction 1, so region merging chained
    # the other way and the ladder could come out with different stages - part
    # of the different decomposition analysis/052 measured. One frame now; see
    # rough_frame_dir.

    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    # OD only: the pass starts outside the part and works in. On a bore the
    # floors run the other way and every comparison here inverts; ID work is
    # paused (openPoints) and a wrong guess would rough INTO the wall rather
    # than leave a sliver, so it declines instead.
    if (x_limit_abs(polyline_feature, 'begin')
            <= x_limit_abs(polyline_feature, 'end') + EPS):
        return []

    return floor_ladder(points, _p('param_f_off'), _p('param_pf_off'),
                        rough_cut, _p('param_pass_from') > 0)


def build_floor_ladder_gcode(polyline_feature, rough_cut=0.0):
    """The #3300 floor-stage table, or '' when one floor fits the whole part.

    '' is the common case and it matters: the runtime gate is
    `_pl_floor_n > 1`, so a single-floor profile takes exactly the ladder it
    took before this existed and cannot be changed by it.

    The last entry is the part's own deepest floor, which is where the ladder
    ended before - so this only ever ADDS the intermediate floors it was
    skipping past, and the bottom of the ladder does not move.
    """
    floors = floor_stages(polyline_feature, rough_cut)
    if len(floors) < 2:
        return ''
    if SECT_FLOOR_BASE + len(floors) >= SECT_BASE:
        raise ValueError('%d floor stages will not fit under #%d'
                         % (len(floors), SECT_BASE))

    lines = ['(the floors this profile is entitled to, shallowest first: a)',
             '(level lands on the floor of the region it is cutting, not on)',
             '(the floor of the deepest point of some other region. The)',
             '(ladder re-anchors at each in turn - see floor_ladder.)',
             '#<_pl_floor_n> = %d' % len(floors)]
    for i, floor in enumerate(floors):
        lines.append('#%d = %s' % (SECT_FLOOR_BASE + i, _fmt(floor)))
    return '\n'.join(lines) + '\n'



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
#
# --- the flank is treated as UNBOUNDED for the accessible contour ------------
#
# The shadow ramp leaves the obstruction at the back angle and runs on until it
# meets the drawn profile again, cornering there. It does not release part way.
#
# flank_envelope CAN bound it: give it a flank length and the shadow stops after
# flank_len*cos(90-back) of Z, after which the envelope curves down through the
# remaining obstructions and rejoins the profile early. That was added because
# a real insert is not infinitely long - "we now counting that BACK angle
# surface is infinate in direction +Z .. but in reality every tool have some
# dimension". That premise has since been withdrawn, so the contour ignores the
# length: roughing, the pre-finish pass, the finish pass and the contour drawn
# in the preview all take the unbounded ramp, which is the single surface they
# are all judged against.
#
# PAUSED, not deleted. flank_envelope's flank_len still works and is still
# tested; only the contour builders decline to use it. Flip this to True to put
# the release back everywhere at once - and note the Tool Change's flank length
# is unaffected either way, it still draws the tool silhouette.
FLANK_BOUNDS_CONTOUR = False

# --- and the SHANK, which is a different question entirely ------------------
#
# FLANK_BOUNDS_CONTOUR above bounds the shadow by the INSERT and was withdrawn:
# past the insert it lets the obstruction stop constraining altogether, which
# says the tool ends there. It does not. The HOLDER is behind the insert and is
# bigger, so the honest model has three regimes rather than two:
#
#   d <= insert reach     the wedge binds:  rp - d * kk
#   reach < d <= l1       the BLOCK binds:  rp - drop        (constant)
#   d > l1                nothing binds - the holder has ended
#
# `drop` is the radial distance from the nose to the block's NEAR face, which
# ncam_preview.tool_shank already derives from the insert's far corners, and
# `l1` its overall length. Both are published by to_gcode's walk, the same way
# WORKPIECE_FACE_Z and TOOL_NOSE_R are, because this module imports nothing
# from ncam or from the preview.
#
# WHY IT RECOVERS METAL. drop is ~12 mm on a 25 mm shank while d * kk is 2.3 mm
# at 10 mm behind an obstruction and 8.1 mm at 35 mm, so past the insert the
# block lets the nose sit LOWER than the unbounded wedge allows - the wedge
# ramps away at the flank angle and never releases, the block is a flat floor
# far below it. That is the 10.0899 mm behind the boss on testing_15_2.
#
# OFF BY DEFAULT. It changes which metal is cut, and the last time the shadow
# model changed it was withdrawn again; this ships measured and switchable, not
# assumed.
# The environment override exists so this can be MEASURED without editing the
# file - a generation runs in a subprocess, so a flag flipped in the parent
# would not reach it. It can only turn the model ON; the shipped default stays
# False and nothing reads the variable in normal use.
FLANK_SHANK_BOUNDS = (os.environ.get('NCAM_SHANK_BOUNDS') == '1')

# radial nose-to-block distance, holder length, and the INSERT's own edge
# length - all published by the walk. The edge length is what ends the wedge in
# this model, and it is derived from the shank rather than typed: it is NOT the
# Tool Change's flank length, which is what FLANK_BOUNDS_CONTOUR used and which
# was withdrawn. Using the derived edge keeps this a statement about the tool
# rather than about a number somebody entered for the picture.
TOOL_SHANK_DROP = 0.0
TOOL_SHANK_LEN = 0.0
TOOL_INSERT_EDGE = 0.0


def _shank_band():
    """(drop, l1) when the shank may bound the shadow, else None."""
    if not FLANK_SHANK_BOUNDS:
        return None
    if TOOL_SHANK_DROP <= EPS or TOOL_SHANK_LEN <= EPS:
        return None
    if TOOL_INSERT_EDGE <= EPS:
        return None
    return TOOL_SHANK_DROP, TOOL_SHANK_LEN


def _contour_flank(flank_len):
    """The flank length the accessible contour may use - see above."""
    return _to_float(flank_len) if FLANK_BOUNDS_CONTOUR else 0.0


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


def flank_slope(back_deg, clearance=0.0):
    """Rise in radius per unit of Z along the trailing flank, or None.

    The tool table's BACK angle is measured off the perpendicular, so the ramp
    the flank actually leaves behind a wall sits at 90 - BACK from the Z axis:
    a J75 insert ramps at 15 degrees and needs a long projection in Z to clear
    a wall, not a short one. Using BACK directly gives the complement and a
    shadow far too short.

    `clearance` tilts that wall AWAY from the flank, in degrees. At 0 the
    artificial wall sits exactly along the flank, so the whole length of the
    back cutting edge rubs the stock at once - which chatters. A positive
    clearance makes the wall shallower than the flank by that many degrees, so
    only the nose is in contact and the edge behind it stands off; it leaves
    more material, which the finishing passes then follow.

    Negative is allowed and is the opposite: the wall is steeper than the
    flank, so the edge behind the nose runs into it. Nothing here prevents
    that - it is a legitimate thing to ask for on a tool with more clearance
    than the table claims, and a bad idea otherwise.
    """
    eff = 90.0 - back_deg - clearance
    if eff <= EPS or eff >= 90.0 - EPS:
        return None
    return math.tan(math.radians(eff))


def rough_frame_dir(rough_dir):
    """The direction the roughing DECOMPOSITION is worked out in.

    greatEndian, 2026-08-15: back to front must be *"same Gcode as Front to
    back"*, only *"movement is from last polyline reference to front"*. So
    `param_dir` = 1 is an ORDER, not a second geometry: there is exactly one
    decomposition - the front-to-back one - and the direction changes which
    window is visited first and which way each pass is cut.

    Before this, every table feeding the roughing scans was rebuilt on a
    REVERSED profile for direction 1, and poly_lathe_mill swept the reversed
    record array on top of that. Measured on testing_15_6 with sectioning on,
    that gave 45 level cuts front to back and 40 back to front, with ONE
    shared - two almost disjoint decompositions, which is what greatEndian
    reported as *"mess"*. See analysis/052 and analysis/054.

    DIRECTION 2, "both directions", RIDES THE SAME FRAME - 2026-08-18. It is
    an alternating EMISSION of direction 0's decomposition: the same windows,
    the same levels, the same intervals, each pass cut from the opposite end
    to the one before it. So it maps onto frame 0 exactly as direction 1 does,
    and only `_pl_cut_rev` - toggled per emitted pass by lathe_level_pass -
    differs at runtime.

    Leaving it at 2 was the whole of the second fault measured in
    analysis/060: `flank_sides(2)` used to shadow BOTH sides of every peak, so
    the reachable envelope roughing stops against was the INTERSECTION of the
    two directions' reachable sets rather than either one. On testing_15_6
    that lost the 15 behind-boss level cuts outright and left 7.49 mm of stock
    standing at Z-67. A tool that can approach from both ends reaches MORE,
    not less; the shadow is per PASS, and each pass has one direction.
    """
    return 0 if rough_dir in (1, 2) else rough_dir


def rough_emit_reversed(polyline_feature):
    """True when roughing is emitted back to front - `param_dir` = 1."""
    p = polyline_feature.get_param('param_dir')
    return p is not None and int(_to_float(p.get_ngc_value())) == 1


# WHICH INSERT IS LOADED, for the flank shadow. A per-generation constant: the
# operation runs with one tool, and every function below asks the same question
# about the same tool, so threading it through fifteen signatures would say
# nothing extra and touch every caller. cfg/lathe/polyline.cfg sets it before it
# builds anything, exactly where it already resolves the orientation for the
# nose terms, and 0 - "no idea" - keeps the direction-derived behaviour this
# module has always had.
INSERT_ORIENT = 0


def set_insert_orient(orient):
    """Remember the loaded insert's orientation for the flank shadow."""
    global INSERT_ORIENT
    INSERT_ORIENT = int(orient or 0)
    return ''


def _fup(v):
    """LinuxCNC's FUP: round away from zero to the next whole number."""
    n = math.ceil(abs(v) - EPS)
    return int(n if n >= 1 else 1)


def ladder_consts(start_r, final_r, fin_off, prefin_off, doc,
                  pass_from=False, floors=()):
    """The ladder's head - the scalars poly_lathe_mill works out once, above
    its window loop, before any level exists.

    Split out of `roughing_ladder` so the same numbers can be EMITTED to the
    runtime instead of recomputed there. Every one is a generation-time
    question: the two targets are parameters plus offsets, the pass count is a
    FUP, and the anchoring is arithmetic on a floor.

    `pass_from` is the subtle one and the reason this is worth moving. Anchored
    on the finished contour the ladder is walked in WHOLE depths of cut from a
    floor rounded outward, not in an even division - and it reassigns
    step_target to that rounded floor, which decides where the levels land
    without changing how much stock is left. Conflating those two left roughing
    holding 1.016 off the profile where 0.762 was configured.

    Returns a dict; keys are the O-code's own names.
    """
    dirsign = 1 if start_r >= final_r else -1
    fin_off = max(fin_off, 0.0)
    rough_target = final_r + dirsign * fin_off
    step_target = rough_target + dirsign * prefin_off

    lad_tgt = step_target
    if len(floors) > 1:
        lad_tgt = floors[0]

    passes = 1
    if abs(lad_tgt - start_r) <= EPS:
        cut_step = first_step = 0.0
    else:
        passes = _fup(abs(lad_tgt - start_r) / doc)
        cut_step = (lad_tgt - start_r) / passes
        first_step = cut_step
        if pass_from:
            sgn = -1 if step_target < start_r else 1
            cut_step = sgn * doc
            k_min = _fup(abs(step_target - rough_target) / doc)
            anch_floor = rough_target - sgn * k_min * doc
            step_target = anch_floor
            if len(floors) <= 1:
                lad_tgt = anch_floor
            passes = _fup(abs(lad_tgt - start_r) / doc)
            first_step = (lad_tgt - start_r) - cut_step * (passes - 1)
    return {'dirsign': dirsign, 'rough_target': rough_target,
            'step_target': step_target, 'lad_tgt': lad_tgt,
            'cut_step': cut_step, 'first_step': first_step,
            'rough_passes': passes}


def ladder_phases(start_r, lad_tgt, step_target, cut_step, first_step, doc,
                  dirsign, sect_on, sect_count, sect_top_r=None):
    """(top, p1_step, p1_first, p2_step, p2_first) - the ceiling and the two
    phase step sizes poly_lathe_mill works out above its window loop.

    THE TWO GATES ARE NOT THE SAME GATE, and mirroring that is the whole point
    of taking `sect_on` and `sect_count` separately. The ceiling is resolved
    only when Sectioning is on AND a window table exists; the phase steps are
    computed whenever Sectioning is on at all. A profile with Sectioning on
    that `build_sections_gcode` declined to describe therefore falls to
    `sect_top_r = step_target` and STILL takes phase-1 steps off that span - a
    single conflated flag would quietly give it cut_step instead.

    The ceiling is clamped twice, into the band the ladder actually spans: never
    past the floor it is aiming at, never above the stock it starts from.
    """
    top = step_target
    if sect_on and sect_count > 0 and sect_top_r is not None:
        top = sect_top_r
        if dirsign * (top - step_target) < 0:
            top = step_target
        if dirsign * (top - start_r) > 0:
            top = start_r

    p1_step, p1_first = cut_step, first_step
    p2_step, p2_first = cut_step, first_step
    if sect_on:
        if abs(top - start_r) > EPS:
            p1_n = max(_fup(abs(top - start_r) / doc), 1)
            p1_sgn = -1 if top < start_r else 1
            p1_step = p1_sgn * doc
            p1_first = (top - start_r) - p1_step * (p1_n - 1)
        if abs(lad_tgt - top) > EPS:
            p2_n = max(_fup(abs(lad_tgt - top) / doc), 1)
            # SPREAD, not whole steps - see poly_lathe_mill
            p2_step = (lad_tgt - top) / p2_n
            p2_first = p2_step
    return top, p1_step, p1_first, p2_step, p2_first


def build_ladder_consts_gcode(polyline_feature, rough_cut=0.0):
    """The ladder head as globals, or '' to leave poly_lathe_mill computing.

    The subroutine keeps its own computation as the fallback and these simply
    replace the answers, so a project this cannot describe - and any older one,
    where `_pl_lad_ok` defaults to 0 - is untouched.
    """
    if rough_cut <= EPS:
        return ''

    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    start_r, final_r = rough_radius_bounds(polyline_feature)
    if abs(start_r - final_r) <= EPS:
        return ''
    raw = resolve_points(polyline_feature, trim=False, extend=False)
    if not raw or len(raw) < 2:
        return ''
    raw_ez, raw_lz = raw[0][0], raw[-1][0]
    c = ladder_consts(start_r, final_r, _p('param_f_off'),
                      _p('param_pf_off') * (1 if _p('param_pf_on') else 0),
                      rough_cut, _p('param_pass_from') > 0,
                      floor_stages(polyline_feature, rough_cut))
    # the ceiling and the phase steps, with the O-code's own two gates kept
    # apart - see ladder_phases
    got = section_windows(polyline_feature)
    sect_on = _p('param_sectioning') > 0
    n_win = len(got[0]) if got is not None else 0
    top_r = (got[2] / DIAMETER_MODE) if got is not None else None
    top, p1s, p1f, p2s, p2f = ladder_phases(
        start_r, c['lad_tgt'], c['step_target'], c['cut_step'],
        c['first_step'], rough_cut, c['dirsign'], sect_on, n_win, top_r)
    return '\n'.join([
        '(the ladder head, worked out at generation time: the direction, the)',
        '(two targets, the depth of cut and the first step. poly_lathe_mill)',
        '(still computes these and these replace the answers, so an older)',
        '(project - _pl_lad_ok 0 - keeps exactly the ladder it had.)',
        '#<_pl_lad_ok>    = 1',
        '#<_pl_lad_dsgn>  = %d' % c['dirsign'],
        '#<_pl_lad_rtgt>  = %s' % _fmt(c['rough_target']),
        '#<_pl_lad_stgt>  = %s' % _fmt(c['step_target']),
        '#<_pl_lad_ltgt>  = %s' % _fmt(c['lad_tgt']),
        '#<_pl_lad_cstep> = %s' % _fmt(c['cut_step']),
        '#<_pl_lad_fstep> = %s' % _fmt(c['first_step']),
        '#<_pl_lad_np>    = %d' % c['rough_passes'],
        # THE PROFILE'S RAW Z BOUNDS, as the record array will hold them.
        # resolve_points excludes the polyline's origin for exactly this
        # reason - poly_add_item never stores it either - so the first and
        # last points here are record 1 and record n. Emitted so the runtime
        # can be checked against them; the extension and the Z-limit clamp are
        # applied by poly_lathe_mill afterwards, in that order.
        '#<_pl_lad_ez>   = %s' % _fmt(raw_ez),
        '#<_pl_lad_lz>   = %s' % _fmt(raw_lz),
        '#<_pl_lad_top>   = %s' % _fmt(top),
        '#<_pl_lad_p1s>   = %s' % _fmt(p1s),
        '#<_pl_lad_p1f>   = %s' % _fmt(p1f),
        '#<_pl_lad_p2s>   = %s' % _fmt(p2s),
        '#<_pl_lad_p2f>   = %s' % _fmt(p2f),
    ]) + '\n'


def roughing_ladder(start_r, final_r, fin_off, prefin_off, doc,
                    pass_from=False, floors=(), sectioning=False,
                    sect_top_r=None, sect_mode=0, windows=1,
                    top_override=None):
    """The roughing level radii, per window, worked out at generation time.

    A REPLICA of what poly_lathe_mill computes at runtime, written to be
    compared against it rather than to replace it yet. Nothing reads this in
    the toolpath; `test_ladder_python` asserts every level the program actually
    cuts lies on the ladder this returns, across every project and direction.
    Replacing the O-code without that evidence is how the anisotropic stock to
    leave cost four rounds.

    Everything it needs is known before the program runs: the two radii are cfg
    parameters (resolved through `x_limit_abs`), the offsets and the depth of
    cut are parameters, and the floor stages and section ceiling are tables
    this module already emits. The runtime only decides what each level DOES -
    whether it is skipped as thin, refused as blocked, or split into intervals
    - and none of those change the level SET, which is why this can be a pure
    function.

    Returns [(window_index, [radii])]; window_index is -1 for phase 1 and for
    the unsectioned single pass.
    """
    c = ladder_consts(start_r, final_r, fin_off, prefin_off, doc,
                      pass_from, floors)
    dirsign = c['dirsign']
    rough_target = c['rough_target']
    step_target = c['step_target']
    lad_tgt = c['lad_tgt']
    cut_step = c['cut_step']
    first_step = c['first_step']

    top, p1_step, p1_first, p2_step, p2_first = ladder_phases(
        start_r, lad_tgt, step_target, cut_step, first_step, doc, dirsign,
        sectioning, 1 if sectioning else 0, sect_top_r)

    def walk(lvl_start, lvl_floor, step, first, staged=False):
        # THE LADDER RE-ANCHORS ON EACH FLOOR STAGE. Reaching one is not the
        # end when others lie below it: poly_lathe_mill takes the next stage,
        # divides the remaining distance into whole depths of cut of its own -
        # FUP, then an even step - and carries on. Leaving that out is what the
        # parallel run caught: 15 of 30 configurations had exactly one level
        # off the ladder, always r20.516, which is the first level of the
        # SECOND stage on testing_15_4, _15_5 and _15_6.
        stages = list(floors) if (staged and len(floors) > 1) else []
        fl_i, floor = 0, (stages[0] if stages else lvl_floor)
        out, r, f = [], lvl_start, first
        for _ in range(400):                    # a ladder is never this long
            out.append(r)
            if abs(r - floor) <= 1e-6:
                if fl_i < len(stages) - 1:
                    fl_i += 1
                    floor = stages[fl_i]
                    n = _fup(abs(floor - r) / doc)
                    step = (floor - r) / n
                    f = step
                else:
                    break
            if abs(step) <= EPS and abs(f) <= EPS:
                break
            r = r + f
            f = step
            if start_r > floor and r < floor:
                r = floor
            elif start_r < floor and r > floor:
                r = floor
        return out

    if not sectioning:
        return [(-1, walk(start_r, step_target, cut_step, first_step, True))]

    # WHERE PHASE 2 STARTS AND WHAT ITS STEP IS COME FROM DIFFERENT CEILINGS,
    # and that is the O-code's own behaviour rather than an accident: p1_step
    # and p2_step are worked out ONCE above the window loop from the ceiling
    # Python emitted, while lvl_start reads sect_top_r at the moment the window
    # runs - which the phase-1 handover may have moved. On testing_15_blocked
    # the steps stay +/-0.500, from (36.016 - 31.016)/10 against the ORIGINAL
    # 31.016, while every phase-2 window starts at the MOVED 34.572. Feeding
    # the moved value into both gives 0.4813 and a ladder that matches nothing.
    p2_start = top if top_override is None else top_override

    out = []
    # ARTIFICIAL SECTIONING HAS NO PHASE 1. poly_lathe_mill starts w_idx at 0
    # rather than -1 there - every window takes the full roughing depth in its
    # own Z span, so there is no ceiling pass to emit. Emitting one anyway
    # invented four levels on testing_15_9 - 34.9911, 34.4831, 33.9751,
    # 33.4671, a grid the windows do not share - and gate ONE could not see
    # them: no cut lands on an invented level, so "every cut level is on the
    # ladder" stayed true. The accounting gate caught them as a HOLE.
    if sect_mode != 1 and abs(top - start_r) > EPS:
        p1 = walk(start_r, top, p1_step, p1_first)
        if top_override is not None:
            # phase 1 stopped early: it never walked past the handover radius
            keep = []
            for r in p1:
                keep.append(r)
                if abs(r - top_override) <= 0.002:
                    break
            p1 = keep
        out.append((-1, p1))
    for w in range(windows):
        lvl_start = start_r if sect_mode == 1 else p2_start
        out.append((w, walk(lvl_start, step_target, p2_step, p2_first, True)))
    return out


def level_blocked(floor_contour, level, w_from, w_to, multi_cross=False,
                  mm=1.0):
    """Whether a roughing level can begin at all inside its own window.

    A REPLICA of the answer lathe_level_pass returns in #<_level_blocked>,
    written to be compared against it rather than to replace it yet. Nothing
    in the toolpath reads this; `test_level_blocked` asserts it matches the
    O-code call for call. The ladder went the same way and the parallel run
    caught two faults reading alone had not - see analysis/080 and 081.

    It is a table walk, not a geometry solve. When Python has emitted the
    floor contour - `_pl_flc_n` GT 1, which is every polyline that reaches
    here - BOTH of lathe_level_pass's scans walk only that table and skip the
    record-array offset scan outright (`scan_i = rec_count`). The contour is
    already blended by each surface's own normal with its corners joined, so
    there is no offset arithmetic and no corner connector left to do. Returns
    None when the table is absent, because the scan this does not replicate
    owns that case.

    `multi_cross` picks between the two, and they answer different questions:

    - single crossing: the FIRST place the contour rises to the level. Blocked
      when that crossing is at or before the window start - the profile is
      already above the level before the window begins, so nothing in the
      window is reachable.
    - multi crossing: replays every crossing in order to track whether the
      contour is above or below the level, and freezes that state at the
      window start. Blocked when the state there is "above". A level behind a
      boss crosses several times, and only the state at w_from decides.
    """
    scan = _level_scan(floor_contour, level, w_from, w_to, multi_cross, mm)
    return None if scan is None else scan[0]


def _level_scan(floor_contour, level, w_from, w_to, multi_cross, mm):
    """(blocked, found, zc) - the shared body of the two scans above.

    zc is where the level's cut ENDS: the first qualifying crossing past the
    window start, or the sentinel lathe_level_pass initialises it to when
    there is none. level_stop_z clamps it at the window end."""
    pts = list(floor_contour)
    if len(pts) < 2:
        return None
    z_dir = 1.0 if w_from >= w_to else -1.0
    # the epsilon lets a level sitting exactly on the roughing floor graze it
    l_eff = level + 0.001 * mm

    if not multi_cross:
        found, zc = False, w_to - z_dir
        if pts[0][1] >= l_eff:
            zc, found = pts[0][0], True
        pz, px = pts[0]
        for cz, cx in pts[1:]:
            if not found and px < l_eff <= cx:
                if abs(cx - px) > 0.000001:
                    zc = pz + (cz - pz) * (l_eff - px) / (cx - px)
                else:
                    zc = cz
                found = True
            pz, px = cz, cx
        return (bool(found and z_dir * (zc - w_from) >= -0.0001), found, zc)

    state = 1 if pts[0][1] >= l_eff else 0
    wf_state = -1
    qual_found, zc = False, w_to - z_dir
    pz, px = pts[0]
    for cz, cx in pts[1:]:
        dirup = None
        if px < l_eff <= cx:
            dirup = 1
        elif px >= l_eff > cx:
            dirup = 0
        if dirup is not None:
            if abs(cx - px) > 0.000001:
                tz = pz + (cz - pz) * (l_eff - px) / (cx - px)
            else:
                tz = cz
            if z_dir * (tz - w_from) < -0.0001:
                # past the window start: it cannot move the state there any
                # more, it can only freeze what the state already was - and
                # the first crossing back UP into blocked territory is where
                # the cut has to end
                if wf_state < 0:
                    wf_state = state
                if dirup and not qual_found:
                    qual_found, zc = True, tz
            else:
                state = dirup
        pz, px = cz, cx
    if wf_state < 0:
        wf_state = state
    return (wf_state > 0, qual_found, zc)


def level_stop_z(floor_contour, level, w_from, w_to, oz=0.0,
                 multi_cross=False, mm=1.0):
    """(blocked, z_end) - where one interval of a roughing level ends.

    A REPLICA of what lathe_level_pass exports in #<_pl_level_z_end>, which is
    what the next resume search starts from. z_end is None when the pass is
    blocked: the subroutine returns before exporting one, and poly_lathe_mill
    correctly searches from the interval's own start in that case.

    The cut ends at the crossing, or at the window end, whichever comes first
    in the direction of travel. THE WINDOW END CARRIES THE NOSE TERM and the
    crossing does not - the stop table has carried it since it was built, so
    compensating again would apply it twice. `z_wend` names that bound once
    because comparing zc against a raw w_to while assigning w_to - oz made the
    two disagree over a band one nose term wide, and three levels on
    testing_15_9 ran past the reach their own crossing named.

    NOT REPLICATED: lathe_level_pass then refines z_end against the stop
    contour with a tool-reach clamp (lathe_level_pass.ngc:904). Measured over
    the five test projects it moves z_end on 0 of 1854 cutting calls, so this
    is exact there - but it is carried for cases where it does fire, and those
    are outside the sweep.
    """
    scan = _level_scan(floor_contour, level, w_from, w_to, multi_cross, mm)
    if scan is None:
        return (None, None)
    blocked, _found, zc = scan
    if blocked:
        return (True, None)
    z_dir = 1.0 if w_from >= w_to else -1.0
    z_wend = w_to - oz
    return (False, zc if z_dir * (zc - z_wend) > 0 else z_wend)


def resume_z(resume_env, level, search_from, w_to, mm=1.0):
    """Where this level's NEXT disjoint interval starts, or (False, 0).

    A REPLICA of the answer lathe_level_next_start reports in #<_pl_env_found>
    / #<_pl_env_z>, the one poly_lathe_mill takes whenever the resume envelope
    exists - `_pl_res_n` GT 1. Nothing in the toolpath reads this;
    `test_level_intervals` asserts the whole call sequence it produces matches
    what the O-code walked. Replica, parallel run, migration last.

    A level behind a boss is cut in several disjoint intervals: the pass runs
    until the profile rises above it, and the level then resumes wherever the
    profile drops back below. That resume point is a function of the level
    alone, so Python emits it as an envelope - the table this interpolates.

    Two tests decide whether the answer counts, and they are separate for a
    reason. The candidate has to be genuinely PAST where the search began, by
    more than `resume_margin`, or the joint the previous pass just ended on is
    re-detected as a new interval and the level never terminates. And it has
    to be inside the window, or a level resumes in the next section's
    territory.

    Note the margin is 0.01 x mm and NOT the 0.001 grazing epsilon the level
    scans use - a different question. That one tolerates a level sitting
    exactly on the floor; this one tells a new interval apart from the point
    the walk started at.
    """
    pts = list(resume_env)
    if len(pts) < 2:
        return (False, 0.0)
    z_dir = 1.0 if search_from >= w_to else -1.0
    margin = 0.01 * mm
    # above the envelope's own top there is nothing to resume behind
    if level > pts[0][0] + 0.000001:
        return (False, 0.0)
    re_z = pts[-1][1]
    for i in range(len(pts) - 1):
        l0, z0 = pts[i]
        l1, z1 = pts[i + 1]
        if l1 - 0.000001 <= level <= l0 + 0.000001:
            if abs(l1 - l0) > 0.000001:
                re_z = z0 + (z1 - z0) * (level - l0) / (l1 - l0)
            else:
                re_z = z0
            break
    if (z_dir * (re_z - search_from) < -margin
            and z_dir * (re_z - w_to) >= 0):
        return (True, re_z)
    return (False, 0.0)


def sub_spans(split_table, level, w_from, w_to, z_dirw, dm=2.0, split=True):
    """[(sg_from, sg_to)] - the sub-spans one level is swept in, back to front.

    A REPLICA of poly_lathe_mill's o<wh_seg> loop, the layer that decides where
    each interval walk BEGINS. Nothing in the toolpath reads it; `test_sub_spans`
    asserts the decomposition matches what the O-code walked.

    Walked back to front, a level that a peak certainly blocks must not be swept
    as one span from the window start: it would lead in through the peak. So the
    sweep is broken at every split point the level sits below, taking them from
    the back - `sg_to` of the next sub-span is the `sg_from` of this one - until
    a sub-span reaches the window's own front, which ends the level.

    A split point counts only when all three hold: the level is at or below the
    radius that peak blocks, the point is genuinely past the window start, and
    it is still inside the sub-span currently being filled. The table is read
    ONCE across the whole level - `sg_i` is not reset per sub-span - so each
    peak can break the sweep at most once.

    `split` is the caller's sg_use: front to back leaves the table empty and
    takes a single span, and with Sectioning on only phase 1 reads it, because
    every other sweep is already ordered by the window table.
    """
    out = []
    sg_to = w_to
    sg_i = len(split_table) - 1 if split else -1
    while True:
        sg_from, hit = w_from, False
        while sg_i >= 0:
            z_b, r_b = split_table[sg_i]
            sg_i -= 1
            if (level <= r_b / dm - 0.0001
                    and z_dirw * (z_b - w_from) < -0.0001
                    and z_dirw * (z_b - sg_to) > 0.0001):
                sg_from, hit = z_b, True
                break
        out.append((sg_from, sg_to))
        if not hit:
            # reached the window's own front - there is nothing in front of
            # the first sub-span to cut
            break
        sg_to = sg_from
    return out


def roughing_windows(raw_e_z, raw_l_z, ext_bk_dz=0.0, lim=None,
                     sections=(), sect_mode=0, sectioning=False, dm=2.0):
    """[(w_idx, w_from, w_to, r_lo, r_hi)] - the windows roughing sweeps.

    A REPLICA of poly_lathe_mill's o<wh_w> loop. Nothing in the toolpath reads
    it; `test_roughing_windows` asserts the sequence matches what the O-code
    walked.

    Three shapes, and the index is part of the answer - lathe_level_pass
    records each window's deepest cut at #2800 + w_idx and reads its
    NEIGHBOURS back, so an index is a position along the part and not just a
    counter:

    - **Sectioning off**: exactly ONE window over the whole profile. The
      runtime computes `w_len` as the whole span plus 1 precisely so the first
      window swallows everything - sec_len belongs to Artificial mode and is
      consumed at generation time, and letting it slice here made the
      Sectioning switch look like it did nothing.
    - **Artificial** (`sect_mode` 1): the table windows alone, w_idx from 0.
      There is no ceiling phase - every window takes the full roughing depth
      in its own Z span.
    - **Natural**: a phase-1 window over the whole profile at index -1 first,
      then the table windows.

    The Z bounds are the profile's own first and last, displaced by the back
    extension and THEN clamped into the Z limits - that order on purpose, a
    limit being a hard bound where an extension is a request. `lim` is
    (lo, hi) or None. Skipping this clamp was a safety bug: roughing read the
    RAW record array while every contour read the trimmed tables, so a level
    that did not cross the trimmed profile ran the full bar - measured on
    testing_15_5 at Z-70.8000 against an End Z of -40.

    A window's radius band arrives as a diameter pair and an impossible one -
    high at or below low - means a file written before windows carried bands,
    whose slots 3 and 4 hold the next window's Z pair. Treated as no band, so
    a stale file still roughs the way it used to.
    """
    e_z, l_z = raw_e_z, raw_l_z + ext_bk_dz
    if lim is not None:
        lo, hi = lim
        e_z = min(max(e_z, lo), hi)
        l_z = min(max(l_z, lo), hi)
    z_dirw = 1.0 if e_z >= l_z else -1.0
    if not sectioning or not sections:
        # the single window still has to have somewhere to go
        if z_dirw * (e_z - l_z) <= 0.0001:
            return []
        return [(-1, e_z, l_z, -999999.0, 999999.0)]
    out = []
    if sect_mode != 1:
        out.append((-1, e_z, l_z, -999999.0, 999999.0))
    for i, (z_from, z_to, r_lo, r_hi) in enumerate(sections):
        lo_r, hi_r = r_lo / dm, r_hi / dm
        if hi_r <= lo_r:
            lo_r, hi_r = -999999.0, 999999.0
        out.append((i, z_from, z_to, lo_r, hi_r))
    return out


def phase1_stop(levels, floor_contour, stock_r, doc, e_z, l_z,
                skip_thin=0.0, multi_cross=True, mm=1.0):
    """The radius phase 1 really stops at, or None if it reaches its ceiling.

    A REPLICA of poly_lathe_mill's o<p1_none> branch (line 1035): on the first
    phase-1 level whose pass comes back BLOCKED with nothing yet cut on it and
    the sub-span starting at the window's own start, the runtime does

        sect_top_r = current_radius
        _pl_ph1_front_cut = 0
        break

    - it abandons phase 1 there and hands that exact radius to phase 2.

    THIS IS THE ONE PLACE A RUNTIME OUTCOME FEEDS BACK INTO THE GEOMETRY, and
    for a long time it looked inert: all three of its sites measured 0 fires
    over 30 configurations (analysis/086). They were not inert, the sample was
    too narrow - `testing_15_blocked` leaves the front section at full stock
    diameter, which gives phase 1 real depth while blocking every one of its
    levels at the window start, and moves the ceiling 31.0160 -> 34.5720
    (analysis/088).

    A level only gets a pass if it enters o<lvl_ok>: at or past the stock it is
    skipped, and a level too thin to be worth cutting is skipped as well -
    `_pl_prev_thin` stays at the stock radius through phase 1 precisely because
    nothing has cut yet, which is what makes the thin test predictable here.
    """
    if not levels:
        return None
    prev_thin = stock_r
    dirsign = 1.0 if levels[0] >= levels[-1] else -1.0
    for i, r in enumerate(levels):
        if dirsign * (r - stock_r) >= 0:
            continue                      # at or past the stock: nothing there
        if skip_thin > 0.000001:
            nxt = levels[i + 1] if i + 1 < len(levels) else r
            if (abs(r - prev_thin) < skip_thin
                    and abs(nxt - prev_thin) <= doc + 0.000001):
                continue                  # too thin to be worth a pass
        if level_blocked(floor_contour, r, e_z, l_z, multi_cross, mm):
            return r
        prev_thin = r
    return None


# The roughing level table: a directory of (window index, offset, count)
# followed by the radii themselves. 1000-2600 is the free block below
# WDEEP_BASE - measured completely unreferenced - and a 17-window Artificial
# part at 32 levels needs 544 radii plus 51 directory slots, so it fits with
# room to spare.
LVL_BASE = 1000
LVL_TOP = 2600


def protected_flags(levels, floors, step_target, staged):
    """1 per level that is a PROTECTED FLOOR - one skip_thin may never drop.

    poly_lathe_mill tracks this as `fl_prot`, walking the floor stages as the
    ladder reaches them. The level table already encodes that walk, so the flag
    can simply be emitted per level and the runtime stops rediscovering it.

    `fl_prot` is step_target unless the ladder is walking floor stages, when it
    is the stage currently being AIMED AT - each of those is a real region's
    floor and must not be skipped either. The last stage IS step_target, so
    nothing changes on a part with one floor.

    `staged` mirrors the walk: phase 1 aims at the section ceiling, which is not
    a floor at all, so it protects only step_target - the same discriminator
    the O-code uses when it tests the window's floor against the last stage.
    """
    stages = list(floors) if (staged and len(floors) > 1) else []
    prot = stages[0] if stages else step_target
    fl_i, flags = 0, []
    for r in levels:
        hit = abs(r - prot) <= 0.000001
        flags.append(1 if hit else 0)
        if hit and stages and fl_i < len(stages) - 1:
            fl_i += 1
            prot = stages[fl_i]
    return flags


def level_floors(levels, floors, window_floor):
    """The floor each level is AIMING AT - poly_lathe_mill's `lvl_floor`.

    It is the window's own floor, except that a ladder walking floor stages
    re-anchors on each in turn: the runtime starts on stage 0 when the window's
    floor IS the last stage, and steps to the next each time a level lands on
    the current one. The level table already encodes that walk, so the answer
    can be emitted per level.

    WRITTEN ONLY AT THE ADVANCE, never at the window start. The first attempt
    wrote it at the window start too and BROKE the part - 466 moves against
    472 on testing_15_5 - because that write lands before the stage-arming
    block, which decides whether to arm `fl_i` by testing `lvl_floor` against
    the LAST stage. Overwritten to stage 0 the test fails, the machinery never
    arms, and the ladder breaks at the first floor instead of walking them.
    The window's own floor is still the runtime's, and only the per-level
    stage comes from here. See analysis/095 and 096.
    """
    cur, fl_i = window_floor, -1
    if len(floors) > 1 and abs(window_floor - floors[-1]) <= 0.000001:
        fl_i, cur = 0, floors[0]
    out = []
    for r in levels:
        out.append(cur)
        if abs(r - cur) <= 0.000001 and 0 <= fl_i < len(floors) - 1:
            fl_i += 1
            cur = floors[fl_i]
    return out


def build_level_table_gcode(polyline_feature, rough_cut=0.0):
    """The #1000 roughing level table, or '' to leave poly_lathe_mill computing.

    THE LADDER MOVES OUT OF THE O-CODE HERE. poly_lathe_mill works the level
    radii out at runtime - dirsign, the two targets, FUP pass counts, the
    phase-1/phase-2 split, the floor-stage re-anchoring - and this emits the
    same sequence per window so the subroutine only has to read the next
    number. It is the arithmetic proved against the running O-code across 36
    configurations first: analysis/080, 081 and 089.

    THE NOMINAL LADDER, DELIBERATELY. Where phase 1 is blocked from its own
    window start with nothing cut, poly_lathe_mill REASSIGNS sect_top_r and
    every later window starts somewhere this table does not know about
    (analysis/088). `phase1_stop` predicts that, and it is proved - but on 36
    configurations, not universally, and a table built on a wrong ceiling would
    cut a wrong ladder in metal. So the table stays nominal and the O-code
    switches it OFF at the three sites that do the reassigning, falling back to
    the computation it has always had. Predicting the handover into the table
    is a later step with its own evidence.

    '' whenever anything is missing or would not fit, and the runtime gate is
    `_pl_lvl_n GT 0`, so an older project - or one this cannot describe - takes
    exactly the ladder it took before.
    """
    if rough_cut <= EPS:
        return ''

    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    start_r, final_r = rough_radius_bounds(polyline_feature)
    if abs(start_r - final_r) <= EPS:
        return ''

    got = section_windows(polyline_feature)
    sectioning = got is not None and _p('param_sectioning') > 0
    if sectioning:
        windows, sect_mode, top_x = got
        top_r, n_win = top_x / DIAMETER_MODE, len(windows)
        if n_win < 1:
            return ''
    else:
        sect_mode, top_r, n_win = 0, None, 1

    ladder = roughing_ladder(
        start_r, final_r, _p('param_f_off'),
        _p('param_pf_off') * (1 if _p('param_pf_on') else 0),
        rough_cut, _p('param_pass_from') > 0,
        floor_stages(polyline_feature, rough_cut),
        sectioning, top_r, int(sect_mode), n_win)
    ladder = [(w, radii) for w, radii in ladder if radii]
    if not ladder:
        return ''

    # IDENTICAL RUNS SHARE ONE COPY. Artificial sectioning gives every window
    # the same ladder - 17 windows x 32 levels stored 17 times reached 2683
    # slots against a 2600 ceiling, and would have fallen back silently on
    # testing_15_9. The directory already addresses runs by offset, so two
    # windows can simply point at the same one. Keyed on the radii AND the
    # staged flag, because phase 1 aims at the ceiling rather than a floor and
    # so carries different per-level answers for the same radii.
    runs, index = [], {}
    for w, radii in ladder:
        key = (tuple(radii), not (sectioning and w < 0))
        if key not in index:
            index[key] = len(runs)
            runs.append((radii, key[1]))
    data = LVL_BASE + 3 * len(ladder)
    n_rad = sum(len(radii) for radii, _st in runs)
    flag = data + n_rad
    flr = flag + n_rad
    total = flr + n_rad
    if total > LVL_TOP:
        return ('(WARNING - the roughing level table needs %d parameter slots '
                'and only %d are free, so the levels are computed at runtime '
                'as before.)' % (total - LVL_BASE, LVL_TOP - LVL_BASE))

    lines = ['(the roughing levels, per window - poly_lathe_mill reads the)',
             '(next radius instead of working the ladder out again. Window)',
             '(-1 is phase 1, and the unsectioned single sweep which shares)',
             '(that index. Read the table, move.)',
             '(and, beside each radius, whether it is a floor skip_thin may)',
             '(never drop - poly_lathe_mill tracked that as fl_prot, walking)',
             '(the stages as the ladder reached them)',
             '#<_pl_lvl_n>    = %d' % len(ladder),
             '#<_pl_lvl_base> = %d' % data,
             '#<_pl_lvlf_base> = %d' % flag,
             '#<_pl_lvlz_base> = %d' % flr]
    starts, off = [], 0
    for radii, _st in runs:
        starts.append(off)
        off += len(radii)
    for i, (w, radii) in enumerate(ladder):
        slot = LVL_BASE + 3 * i
        r = index[(tuple(radii), not (sectioning and w < 0))]
        lines.append('#%d = %d' % (slot, w))
        lines.append('#%d = %d' % (slot + 1, starts[r]))
        lines.append('#%d = %d' % (slot + 2, len(radii)))
    off = 0
    for radii, _st in runs:
        for r in radii:
            lines.append('#%d = %s' % (data + off, _fmt(r)))
            off += 1
    off = 0
    stgs = floor_stages(polyline_feature, rough_cut)
    cc = ladder_consts(
        start_r, final_r, _p('param_f_off'),
        _p('param_pf_off') * (1 if _p('param_pf_on') else 0),
        rough_cut, _p('param_pass_from') > 0, stgs)
    stgt = cc['step_target']
    # the CLAMPED ceiling - the raw _pl_sect_top_dia is not it
    top = ladder_phases(start_r, cc['lad_tgt'], stgt, cc['cut_step'],
                        cc['first_step'], rough_cut, cc['dirsign'],
                        sectioning, n_win, top_r)[0]
    for radii, staged in runs:
        # phase 1 aims at the ceiling, which is not a floor - the same
        # discriminator the O-code uses against the last stage
        for f in protected_flags(radii, stgs, stgt, staged):
            lines.append('#%d = %d' % (flag + off, f))
            off += 1
    off = 0
    for radii, staged in runs:
        for z in level_floors(radii, stgs, stgt if staged else top):
            lines.append('#%d = %s' % (flr + off, _fmt(z)))
            off += 1
    return '\n'.join(lines) + '\n'


def level_calls(floor_contour, resume_env, level, sg_from, lv_to, oz=0.0,
                multi_cross=False, mm=1.0, phase1=False):
    """[(from, to)] - every lathe_level_pass call one level makes in one
    sub-span, in order.

    The whole interval walk: the pass runs until the profile rises above the
    level, the resume envelope says where it may begin again, and it is called
    once more - as many times as the profile allows. Proved call for call
    against the running O-code by `test_level_intervals`, which now uses this
    rather than its own copy.

    BLOCKED CALLS ARE PART OF THE SEQUENCE AND MUST NOT BE DROPPED. They emit
    no motion, so leaving them out looks free - but `o<p1_none>` fires exactly
    when a call comes back blocked with nothing yet cut on the level, and that
    is the phase-1 handover, which really does fire and moves the ceiling by
    3.556 mm on testing_15_blocked (analysis/088). A sequence of only the
    cutting intervals would silently stop the handover happening.

    `phase1` is that branch: in phase 1 a first call blocked from the
    sub-span's own start abandons the level outright, where a phase-2 window
    blocked the same way goes looking for a resume.
    """
    calls, l_fr, cut_yet = [], sg_from, False
    for _ in range(200):                 # a level is never split this often
        calls.append((l_fr, lv_to))
        blocked, z_end = level_stop_z(floor_contour, level, l_fr, lv_to, oz,
                                      multi_cross, mm)
        if blocked is None:
            return calls
        if phase1 and blocked and not cut_yet and len(calls) == 1:
            break
        if not blocked:
            cut_yet = True
        found, z = resume_z(resume_env, level,
                            l_fr if blocked else z_end, lv_to, mm)
        if not found:
            break
        l_fr = z
    return calls


def window_calls(levels, protected, floor_contour, resume_env, split_table,
                 w_from, w_to, w_rlo, w_rhi, stock_r, dirsign, doc,
                 skip_thin=0.0, prev_thin0=None, oz=0.0, multi_cross=False,
                 mm=1.0, dm=2.0, z_dirw=1.0, split=False, phase1=False):
    """[(level, why, [(from, to, first, blocked), ...])] - every level of one
    window and every call it makes, with `why` naming what stopped a level that
    made none. `first` marks a sub-span start and `blocked` whether the call
    cut - the emitter places the runtime's state writes from those.

    SKIP_THIN CANNOT BE A FUNCTION OF THE LADDER ALONE, which is why this
    simulates the window rather than answering per level. `_pl_prev_thin` is
    the surface immediately above the level being judged, and it advances only
    where a level ACTUALLY CUTS - so the thin test reads the cut history, the
    cut history reads the blocked answer, and the blocked answer comes from the
    interval walk. They have to be walked together, in order.

    `why` is '' when the level ran. Otherwise: 'band' outside this window's
    radius band, 'stock' at or past the stock, 'thin' too little metal to be
    worth a pass.

    The thin rule refuses in two steps and both matter. A level closer to the
    surface above it than the threshold is a candidate - but it is only dropped
    if doing so leaves the NEXT level within one depth of cut of that surface,
    because `_pl_prev_thin` does not advance on a skip and the level after a
    dropped one is otherwise two steps from the last real cut. Measured on
    testing_15_2: without the second test a 0.600 threshold lost 13 levels and
    opened a 1.0160 gap against a 0.508 depth of cut.

    A PROTECTED FLOOR IS NEVER DROPPED whatever the threshold - it is the
    surface roughing has to leave for the pre-finish pass.
    """
    prev_thin = stock_r if prev_thin0 is None else prev_thin0
    out = []
    for i, r in enumerate(levels):
        nxt = levels[i + 1] if i + 1 < len(levels) else r
        why = ''
        # THE O-CODE'S OWN ORDER, and it is not the obvious one: lvl_thin is
        # computed INDEPENDENTLY of the stock test - o<lvl_ok> requires band
        # AND not-thin AND below-stock - so a level sitting at the stock can
        # carry the thin flag as well. Testing stock first would name 30 levels
        # 'stock' that the runtime calls 'thin'. Both skip the level either
        # way; the order only matters for saying WHY, and the reason is what a
        # reader of a generated program has to trust.
        if r > w_rhi + 0.000001 or r < w_rlo - 0.000001:
            why = 'band'
        elif (skip_thin > 0.000001 and not protected[i]
                and abs(r - prev_thin) < skip_thin
                and abs(nxt - prev_thin) <= doc + 0.000001):
            why = 'thin'
        elif dirsign * (r - stock_r) >= 0:
            why = 'stock'
        if why:
            out.append((r, why, []))
            continue
        calls, cut = [], False
        for sg_from, sg_to in sub_spans(split_table, r, w_from, w_to, z_dirw,
                                        dm, split):
            seq = level_calls(floor_contour, resume_env, r, sg_from, sg_to,
                              oz, multi_cross, mm, phase1)
            for j, (a, b) in enumerate(seq):
                blocked, _ze = level_stop_z(floor_contour, r, a, b, oz,
                                            multi_cross, mm)
                # `first` marks a sub-span start, which is where the runtime
                # resets _pl_level_z_end; `blocked` says whether the call cut,
                # which is where it advances _pl_prev_lvl. The emitter needs
                # both to put the state writes where the loop puts them.
                calls.append((a, b, j == 0, bool(blocked)))
                if blocked is False:
                    cut = True
        if cut:
            prev_thin = r
        out.append((r, '', calls))
    return out


def rough_nose_terms(polyline_feature, nose_r=0.0, orient=0):
    """(ox, oz) - the orientation term roughing carries, already gated.

    Zero unless this polyline actually compensates, which is `_comp_nose`'s
    question. Shared with the emitter so the two cannot answer differently.
    """
    _nr, _or = _comp_nose(polyline_feature, nose_r, orient)
    if _nr > EPS and 0 < int(_or) < len(NOSE_OFFSET):
        vec = NOSE_OFFSET[int(_or)]           # (X, Z), raw - not a unit vector
        return _nr * vec[0], _nr * vec[1]
    return 0.0, 0.0


def roughing_call_plan(polyline_feature, rough_cut, back_deg, nose_r=0.0,
                       flank_len=0.0, clearance=0.0, orient=0):
    """[(w_idx, level, why, [(from, to), ...])] - EVERY roughing call the
    program will make, in order, or None when this cannot be described.

    The capstone. It composes the predictors proved one at a time against the
    running O-code - windows (085), sub-spans (084), the ladder (080/081),
    blocked (082), the interval walk (083/089), protected floors (094), the
    phase-1 handover (089) and skip_thin (098) - into the whole sequence.

    `lathe_level_pass` is THE ONLY THING IN poly_lathe_mill's loop nest THAT
    EMITS MOTION - the four lathe_level_next_start calls are scans and there is
    no bare G-code between them - so a flat sequence making these calls with
    the same arguments and the same global state reproduces the motion exactly.
    That is what makes emitting them as literal G-code sound rather than
    hopeful.

    `why` is '' when the level ran, otherwise 'band', 'stock' or 'thin'.
    """
    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    if rough_cut <= EPS:
        return None
    start_r, final_r = rough_radius_bounds(polyline_feature)
    if abs(start_r - final_r) <= EPS:
        return None
    raw = resolve_points(polyline_feature, trim=False, extend=False)
    if not raw or len(raw) < 2:
        return None
    fc = floor_contour_data(polyline_feature, back_deg, nose_r, flank_len,
                            clearance, orient, rough_cut)
    if fc is None:
        return None
    flc, renv, _rd = fc

    fin = _p('param_f_off')
    pre = _p('param_pf_off') * (1 if _p('param_pf_on') else 0)
    stgs = floor_stages(polyline_feature, rough_cut)
    c = ladder_consts(start_r, final_r, fin, pre, rough_cut,
                      _p('param_pass_from') > 0, stgs)

    got = section_windows(polyline_feature)
    sect_on = _p('param_sectioning') > 0
    sects = list(got[0]) if got is not None else []
    sect_mode = int(got[1]) if got is not None else 0
    top_r = (got[2] / DIAMETER_MODE) if got is not None else None
    sectioning = sect_on and bool(sects)
    top = ladder_phases(start_r, c['lad_tgt'], c['step_target'], c['cut_step'],
                        c['first_step'], rough_cut, c['dirsign'],
                        sect_on, len(sects), top_r)[0]

    wins = roughing_windows(raw[0][0], raw[-1][0],
                            ext_dz(polyline_feature, 'back'),
                            z_limit_band(polyline_feature),
                            sects, sect_mode, sectioning, DIAMETER_MODE)
    if not wins:
        return None

    peaks, allw = split_peaks(polyline_feature)
    split_table = [(z_b, h_b + allw) for z_b, h_b in peaks]
    rough_dir = int(_p('param_dir'))
    z_dirw = 1.0 if wins[0][1] >= wins[0][2] else -1.0
    stock_r = _stock_x(polyline_feature)
    if stock_r is None:
        return None
    stock_r = stock_r / DIAMETER_MODE
    _ox, oz = rough_nose_terms(polyline_feature, nose_r, orient)
    skip_thin = _p('param_skip_thin')

    # the ladder, with the handover it will really take - see phase1_stop
    def _ladder(over=None):
        return roughing_ladder(start_r, final_r, fin, pre, rough_cut,
                               _p('param_pass_from') > 0, stgs, sectioning,
                               top_r, sect_mode, max(len(sects), 1),
                               top_override=over)

    lad = _ladder()
    eff_top = top
    p1 = [r for w, radii in lad if w < 0 for r in radii]
    if p1 and sectioning and sect_mode != 1:
        stop = phase1_stop(p1, flc, stock_r, rough_cut, wins[0][1], wins[0][2],
                           skip_thin, True, 1.0)
        if stop is not None:
            # THE HANDOVER MOVES THE THIN REFERENCE TOO, not just the ladder.
            # A phase-2 window takes _pl_prev_thin from sect_top_r, and where
            # phase 1 handed over that is the MOVED value - so the first level
            # of every later window sits zero from its own reference and is
            # skipped as thin. Feeding the nominal ceiling here emitted three
            # calls the runtime never makes, on testing_15_blocked.
            lad, eff_top = _ladder(stop), stop
    runs = {w: radii for w, radii in lad}

    out = []
    for w_idx, w_from, w_to, r_lo, r_hi in wins:
        radii = runs.get(w_idx if w_idx >= 0 else -1)
        if not radii:
            continue
        phase1 = sectioning and w_idx < 0
        prot = protected_flags(radii, stgs, c['step_target'], not phase1)
        # the thin reference: the surface immediately above this window's
        # levels. Phase 1 has only the bar above it; a phase-2 window has the
        # ceiling phase 1 already took down - unless the clamp made the two
        # the same number, which is the O-code's own discriminator.
        prev0 = stock_r
        if sectioning and abs((eff_top if phase1 else c['step_target'])
                              - eff_top) > 0.000001:
            prev0 = eff_top
        for level, why, calls in window_calls(
                radii, prot, flc, renv, split_table, w_from, w_to,
                r_lo, r_hi, stock_r, c['dirsign'], rough_cut,
                skip_thin=skip_thin, prev_thin0=prev0, oz=oz,
                multi_cross=True, mm=1.0, dm=DIAMETER_MODE, z_dirw=z_dirw,
                split=(rough_dir == 1 and bool(split_table)), phase1=phase1):
            out.append((w_idx, level, why, calls))
    return out


def flat_sub_number(polyline_feature):
    """The numbered subroutine this polyline's flat roughing lives in.

    UNUSED, kept for the record. The plan was one numbered sub per polyline,
    called indirectly as `o[#<n>] call` - which works from the MAIN program.
    It does NOT work from inside a subroutine: LinuxCNC looks a numbered sub up
    in the executing FILE's offset table and then on disk, so
    poly_lathe_mill got "Subroutine 'O90001' not found -- not in offset table".

    NUMBERED SUBS ARE FILE-LOCAL, NAMED SUBS ARE GLOBAL. The flat sub is
    therefore named, which means exactly one per program - see
    build_flat_roughing_gcode's guard.
    """
    digits = ''.join(ch for ch in polyline_feature.get_attr('id') or ''
                     if ch.isdigit())
    return 90000 + (int(digits) if digits else 0)


def build_flat_roughing_gcode(polyline_feature, rough_cut, back_deg,
                              nose_r=0.0, flank_len=0.0, clearance=0.0,
                              orient=0):
    """The polyline's numbered flat-roughing sub, or '' to keep the loop.

    THE LOOPS STOP EXISTING. poly_lathe_mill works the whole nest out at
    runtime - windows, sub-spans, levels, intervals, and the four decisions
    that skip a level - and this emits the answer instead. Every predictor was
    proved against the running O-code first, one at a time (analysis/080-098),
    and then the whole sequence together: 36 configurations, 0 differ
    (analysis/099).

    It is sound because `lathe_level_pass` is THE ONLY THING IN THAT NEST THAT
    EMITS MOTION - the four lathe_level_next_start calls are scans and there is
    no bare G-code between them - so the same calls with the same arguments and
    the same global state give the same motion.

    THREE GLOBALS ARE THE WHOLE STATE. lathe_level_pass reads exactly
    `_pl_w_idx`, `_pl_prev_lvl` and `_pl_level_z_end` of what the loop sets; it
    does NOT read `_pl_prev_thin` or `_pl_ph1_*`, which are poly_lathe_mill's
    own and are what this replaces. So the sub sets the window index, resets
    `_pl_prev_lvl` to the stock at each window and advances it after every
    cutting call, and resets `_pl_level_z_end` at each sub-span start - exactly
    where the loop does.

    The record-array pointer is the ONE argument: `m_pds` and `lvl_d` are each
    assigned once in poly_lathe_mill, so they are constants, and `lvl_d` is
    dirsign * (fin_off + prefin_off), which is known here.

    A skipped level is emitted as a comment saying WHY. That is not decoration:
    a generated program nobody can read back is one nobody can check, and the
    reasons are the part a machinist would want to argue with.
    """
    plan = roughing_call_plan(polyline_feature, rough_cut, back_deg, nose_r,
                              flank_len, clearance, orient)
    if not plan:
        return ''

    def _p(name, default=0.0):
        prm = polyline_feature.get_param(name)
        return _to_float(prm.get_ngc_value()) if prm is not None else default

    start_r, final_r = rough_radius_bounds(polyline_feature)
    fin = _p('param_f_off')
    pre = _p('param_pf_off') * (1 if _p('param_pf_on') else 0)
    dirsign = 1 if start_r >= final_r else -1
    lvl_d = dirsign * (fin + pre)
    stock_r = _stock_x(polyline_feature)
    if stock_r is None:
        return ''
    stock_r = stock_r / DIAMETER_MODE
    leads = ' '.join('[%s]' % _fmt(_p(n)) for n in
                     ('param_li_len', 'param_li_ang', 'param_li_feed',
                      'param_lo_len', 'param_lo_ang', 'param_lo_feed',
                      'param_li_rad', 'param_lo_rad'))

    out = ['o<ncam_flat_rough> sub',
           '(THE ROUGHING PASSES, worked out at generation time. Every call the)',
           '(loop this replaces would have made, in the order it would have)',
           '(made them - see analysis/099. #1 is the record-array pointer.)',
           '#<pds> = #1']
    w_seen = None
    for w_idx, level, why, calls in plan:
        if w_idx != w_seen:
            w_seen = w_idx
            out.append('(window %d)' % w_idx)
            out.append('#<_pl_w_idx> = %d' % w_idx)
            out.append('#<_pl_prev_lvl> = %s' % _fmt(stock_r))
        if why:
            out.append('(level %s skipped - %s)' % (_fmt(level), why))
            continue
        for a, b, first, blocked in calls:
            if first:
                out.append('#<_pl_level_z_end> = %s' % _fmt(a))
            out.append('o<lathe_level_pass> CALL [#<pds>] [%s] [%s] [%s] [%s] '
                       '[#<_rough_feed>] %s'
                       % (_fmt(level), _fmt(lvl_d), _fmt(a), _fmt(b), leads))
            if not blocked:
                out.append('#<_pl_prev_lvl> = %s' % _fmt(level))
    out.append('o<ncam_flat_rough> endsub')
    return '\n'.join(out) + '\n'


def wrong_way_dirs(orient, rough_dir):
    """True when the chosen roughing direction opposes the insert's own.

    The warning added in `analysis/070` fired only for `param_dir` = 2, and
    that is narrower than what the toolpath already believes. `_pl_ramp_face`
    treats BACK TO FRONT with an ordinary right-hand insert exactly the same
    way it treats the alternating mode - measured, testing_15_9 with T2 Q2
    keeps 15 ramps front to back and drops all of them back to front, because
    the tool cannot cut that way. Yet only the alternating mode said so.

    So the question is not "is the mode alternating" but "can this insert cut
    the direction asked for":

      facing -1  cuts toward -Z, so FRONT TO BACK is its direction
      facing +1  cuts toward +Z, so BACK TO FRONT is
      facing  0  neutral - orientations 6, 8 and 9 - and nothing is refused

    Both directions asks for both, so any directional insert is wrong for half
    its passes. A single direction is wrong only when it is the opposite one -
    which also catches a MIRRORED insert used front to back, by the same rule
    and without a second branch.
    """
    face = ramp_facing(orient)
    if not face:
        return False
    d = int(rough_dir or 0)
    if d == 2:
        return True
    return face != (1 if d == 1 else -1)


def insert_flank_side(orient, trailing=True):
    """Which side of a peak this insert's flank shadows, or 0 for "no view".

    WHICH FLANK TRAILS IS A PROPERTY OF THE INSERT, NOT OF THE TRAVEL. The
    tool does not rotate when the cut direction changes: the back flank sits
    behind the cutting edge in the tool's own frame, so the side it shadows is
    fixed by the orientation. `flank_sides` below derives it from the roughing
    direction instead, which is the same assumption the profile-angle ramp
    made until analysis/069 - and it is right only while the insert and the
    direction agree.

    The cutting edge faces `ramp_facing`; the trailing flank is behind it, so
    it shadows the opposite side, and the leading flank shadows the same side
    as the facing.

    Returns 0 for an unknown orientation and for the neutral ones - 6, 8 and 9
    have no axial component - and the caller then keeps the direction-derived
    answer rather than removing the constraint. Dropping the shadow entirely
    for a neutral insert would let roughing reach everywhere, which is a much
    larger claim than this can prove.
    """
    face = ramp_facing(orient)
    if not face:
        return 0
    return -face if trailing else face


def flank_sides(rough_dir):
    """Which side of a peak casts a shadow, from the roughing direction.

    Cutting front to back the tool drives past a boss and the sections BEHIND
    it are the ones it can no longer reach, so only peaks on the +Z side
    constrain. Back to front mirrors that.

    THIS TAKES A FRAME DIRECTION, NOT A USER SETTING - every caller passes
    `rough_frame_dir(...)`, which is 0 or 1 and never 2. Direction 2 used to
    answer `(1, -1)` here, on the reasoning that each pass meets a different
    face of the same boss. That is true of the PASSES and false of the
    ENVELOPE: taking both sides intersects the two reachable sets instead of
    uniting them, so "both directions" reached strictly LESS than either one -
    15 lost level cuts and 7.49 mm standing on testing_15_6, analysis/060. The
    2 branch is gone with the frame mapping that made it reachable.
    """
    return (-1,) if rough_dir == 1 else (1,)


def flank_envelope(points, back_deg, rough_dir=0, flank_len=0.0,
                   clearance=0.0, front_deg=None, orient=None):
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

    def _flank(deg, dirn, trailing=True):
        """[(side, slope, reach)] for one flank, or [] when it constrains
        nothing. Reach is per-flank: two angles project different distances
        along Z, so one shared value would give the shallower flank the
        steeper one's range."""
        kk = flank_slope(deg, clearance)
        if kk is None:
            return []
        rr = None
        if flank_len and flank_len > EPS:
            rr = flank_len * math.cos(math.radians(90.0 - deg - clearance))
            if rr <= EPS:
                return []
        # WITH THE SHANK MODELLED, the wedge ends where the INSERT does - its
        # own edge length, derived from the shank - and the block takes over
        # from there. Without this the wedge stays unbounded, the block branch
        # is unreachable and the whole model does nothing.
        if _shank_band() is not None and TOOL_INSERT_EDGE > EPS:
            er = TOOL_INSERT_EDGE * math.cos(
                math.radians(90.0 - deg - clearance))
            if er > EPS:
                rr = er if rr is None else min(rr, er)
        # THE INSERT DECIDES THE SIDE WHEN IT CAN. flank_sides answers from the
        # roughing direction, and every caller reaches it through
        # rough_frame_dir, which collapses 0, 1 and 2 to 0 - so the shadow has
        # always been hard-wired to the +Z side, which is the right answer for
        # an ordinary right-hand insert and the wrong one for a mirrored one.
        # For orientation 2 this override returns exactly what flank_sides
        # already returned, trailing and leading alike, so nothing moves on any
        # normally-oriented tool.
        # THE ORIENT ARRIVES AS AN ARGUMENT WHEN THE CALLER HAS IT.
        # It used to be read only from the module global that
        # set_insert_orient publishes - which the polyline's own AFTER
        # block sets, so nothing that runs EARLIER than that could build
        # a contour at all. That is what stopped the flat roughing sub
        # being emitted from DEFINITIONS, where it has to live.
        # The global stays as the default so every existing caller is
        # unchanged.
        _or = INSERT_ORIENT if orient is None else int(orient or 0)
        side_ov = insert_flank_side(_or, trailing)
        sides = (side_ov,) if side_ov else flank_sides(dirn)
        return [(side, kk * DIAMETER_MODE, rr) for side in sides]

    # THE LEADING FLANK IS THE SAME DILATION, MIRRORED. Passing it here rather
    # than merging two finished envelopes afterwards is not a style choice: a
    # merge resamples two piecewise-linear curves onto a union of breakpoints
    # and manufactures corners tighter than the nose, which the interpreter
    # refuses outright - "Straight feed in concave corner cannot be reached by
    # the tool without gouging", measured on testing_15_5. Built here, the
    # candidate-Z generation, the outer bound and the collinearity pruning all
    # see both flanks at once and the result is one coherent contour.
    slopes = _flank(back_deg, rough_dir, True)
    if front_deg is not None and front_deg > 0:
        slopes += _flank(front_deg, mirror_dir(rough_dir), False)
    if not slopes:
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
        for side, kk, reach in slopes:
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
            # and where the BLOCK starts and ends. Without these the flat floor
            # between them has no breakpoints to sit on and the collinearity
            # pruning drops it, so the shank would read as doing nothing - the
            # same trap the flank's own release needed both sides of.
            band = _shank_band()
            if band is not None:
                for edge in (reach or 0.0, band[1]):
                    for zc in (zp - side * edge,
                               zp - side * (edge + EPS * 4)):
                        if lo <= zc <= hi:
                            cand.add(zc)

    out = []
    for z0 in sorted(cand):
        best = _outer_x(points, z0)
        if best is None:
            best = points[0][1]
        for zp, rp in points:
            band = _shank_band()
            for side, kk, reach in slopes:
                d = (zp - z0) * side
                if d <= EPS:
                    continue
                if reach is None or d <= reach + EPS:
                    bound = rp - d * kk
                elif band is not None and d <= band[1] + EPS:
                    # past the insert the HOLDER is what clears the wall, and
                    # it is a flat floor rather than a ramp
                    bound = rp - band[0]
                else:
                    continue
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


def mirror_dir(rough_dir):
    """The roughing direction that shadows the OTHER side of every peak.

    `flank_sides` maps 0 -> (1,) and 1 -> (-1,). The LEADING flank is shadowed
    by whatever the trailing flank is not, so this is just the swap.

    A FRAME DIRECTION, like `flank_sides` - callers hand it
    `rough_frame_dir(...)`, which never yields 2. `param_dir` = 2 rides frame
    0 (see `rough_frame_dir`), so its leading flank mirrors to 1 like any
    other frame-0 run. Answering 2 here, as this did, paired with the old
    `flank_sides(2)` to shadow both sides of every peak twice over.
    """
    return 0 if rough_dir == 1 else 1


def front_flank_envelope(points, front_deg, rough_dir=0, flank_len=0.0,
                         clearance=0.0):
    """What the tool's LEADING flank can reach - the mirror of the trailing one.

    THE PHYSICS. An insert's TRAILING flank limits surfaces that RISE as the
    tool travels: drive past a boss and the sections behind it are the ones the
    back of the insert can no longer get into. That is `flank_envelope`, and
    everything roughing scans against is built from it.

    The LEADING flank has its own clearance and limits the opposite thing -
    surfaces that FALL AWAY in front of the tool: a steep face, the near wall
    of a groove, an undercut on the approach side. Same wedge, other end of the
    nose, other side of every peak.

    SO THERE IS ALMOST NO NEW MATHS HERE, deliberately. The dilation is the
    same dilation; only the angle and the shadowed side differ, and
    `flank_sides` already turns a roughing direction into a side. Re-deriving
    the wedge would have meant a second, untested copy of geometry that took
    this project five stacked faults to get right - see analysis/032.

    THE ANGLE CONVENTION, AND THE COMPLEMENT THIS USED TO TAKE TWICE.
    `flank_slope(deg, clr)` is `tan(90 - deg - clr)`: it is written for the
    BACK column, where `J75` correctly becomes a 13 degree ramp at the 2 degree
    default clearance. Handing it the raw `I` complements an angle that is
    already the other edge of the same wedge, so T2's `I15` came out at
    `90 - 15 - 2 = 73` degrees where its own back edge ramps at 13.

    That is wrong on the insert's own symmetry, whichever axis the table
    measures from. T2 is `I15 J75`: centre line 45, included angle 60, so the
    two edges are mirror images 30 degrees either side of the bisector. A
    symmetric insert cannot have one flank ramp at 13 degrees and the other at
    73 - the leading and trailing shadows must be the same size. greatEndian
    reported it as the angle being counted "from opposite side", 2026-08-24,
    `photo/frontAngleRespectIssue_0.png`, and that is exactly a complement.

    So the front angle is turned into the same kind of number the back column
    already is before `flank_slope` takes its complement: `90 - I` in, `tan(I -
    clearance)` out. On T2 both flanks now ramp at 13.00 degrees.

    None of `test_front_flank`'s fixtures move - the steep wall is still
    reported, the rising taper and the cylinder are still silent, and an
    unusable 105 still resolves to None because `90 - 105` is negative and
    `flank_slope` refuses it just the same. What changes is the middle of the
    range, which is where a shadow is a shadow rather than a wall: a 45 degree
    front face went from silent to 2.314 mm of unreachable radius.

    greatEndian confirmed the limitation itself against the reference package
    on 2026-08-13, which is what let this leave lathe_front_flank.py and come
    in here beside the function it mirrors. That confirmation was about
    WHETHER the leading flank limits the part, not about the size of the ramp.
    """
    if front_deg is None:
        return flank_envelope(points, front_deg, mirror_dir(rough_dir),
                              flank_len, clearance)
    return flank_envelope(points, 90.0 - front_deg, mirror_dir(rough_dir),
                          flank_len, clearance)


def build_flank_gcode(polyline_feature, back_deg, nose_r=0.0, flank_len=0.0,
                      clearance=0.0, orient=None):
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
    # THE REACHABLE ENVELOPE IS PART OF THE DECOMPOSITION, so it is built in
    # the one frame - see rough_frame_dir. Which flank shadows which side of a
    # peak is direction physics, but back to front is an emission order here,
    # not a second geometry, and roughing must stop against the same surface
    # in both directions or the cut sets cannot match.
    rough_dir = rough_frame_dir(
        int(_to_float(d_param.get_ngc_value())) if d_param is not None else 0)
    # flank_len comes from the TOOL CHANGE, not from this feature - it
    # describes the insert, so one polyline could not sensibly hold a
    # different value from the next under the same tool. _contour_flank then
    # decides how much of it the contour is allowed to use, which is currently
    # none: roughing stops on the same unbounded ramp the finishing passes
    # trace, so the two cannot describe different surfaces
    env = flank_envelope(points, back_deg, rough_dir,
                         _contour_flank(flank_len), clearance, orient=orient)
    # the scans walk records in profile order, so hand the envelope back the
    # same way round the profile was drawn rather than sorted ascending
    if points[0][0] > points[-1][0]:
        env = list(reversed(env))
    if len(env) == len(points) and all(
            abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) < EPS
            for a, b in zip(sorted(env), sorted(points))):
        return ''

    # Cleaned exactly as the finishing contour is, and for the same reason.
    # Roughing stops against THIS surface while the contour passes follow the
    # cleaned one; if the two differ, roughing eats into the pre-finish
    # allowance at every sawtooth valley - which is what put the behind-boss
    # levels inside the pre-finish band. One surface, both users.
    env = _min_segment(_clean_ramp(env, points), 2.4 * nose_r)

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
# multiples of the nose radius. ONE table, in lathe_comp - it used to be
# written out here, in ncam_preview, in ncam_app_actions and by hand inside
# tip_comp_vec.ngc, and four transcriptions of a table whose diagonal entries
# are R*sqrt2 rather than R is a gouge waiting to happen.
NOSE_OFFSET = lathe_comp.NOSE_OFFSET


def _unit(dz, dx):
    n = math.hypot(dz, dx)
    return (dz / n, dx / n) if n > EPS else (0.0, 0.0)


def stock_pair(polyline_feature):
    """(radial, axial) stock to leave, in whatever units the feature holds.

    One number unless *Separate Z offset* is on, in which case the diameters
    keep `param_f_off` and the walls take `param_f_off_z`. Returning the pair
    equal when the switch is off is what keeps every saved project bit-for-bit
    where it was - `stock_at_normal` then reduces to the single value for
    every normal.
    """
    def _v(name):
        p = polyline_feature.get_param(name)
        return _to_float(p.get_ngc_value()) if p is not None else 0.0
    off_x = _v('param_f_off')
    sep = polyline_feature.get_param('param_f_off_sep')
    if sep is None or _to_float(sep.get_ngc_value()) <= 0:
        return off_x, off_x
    return off_x, _v('param_f_off_z')


# The turn, in degrees, at or below which a vertex is taken to be INTERIOR TO A
# CURVE rather than a corner between two surfaces.
#
# Derived, not guessed: _densify_arc holds each sub-chord's sagitta under
# MESH_MAX_SAG, which gives 2*acos(1 - sag/R) per chord - 3.2 degrees on an
# R12.66 arc, 11.4 on R1, 16.2 on R0.5. So every arc this system draws arrives
# as turns under about 16, and a real corner between two surfaces is 30 or
# more. 20 sits between them with room either side.
#
# MIS-CLASSIFYING IS SAFE IN BOTH DIRECTIONS, which is why a cut this blunt is
# tolerable. Call a curve vertex a corner and it keeps today's behaviour there.
# Call a shallow corner a curve and the two surfaces' allowances get blended -
# but a shallow corner is one where the normals are nearly equal, so their
# allowances are nearly equal too, and the blend changes almost nothing. The
# damage only grows with the angle, and by then the vertex is firmly a corner.
CURVE_TURN_DEG = 20.0


def curve_offsets(pts, side, nose_r, off_x, off_z):
    """Per segment, the two offset endpoints and the larger of its allowances.

    An allowance that depends on the surface normal is CONSTANT along a chord
    and jumps at every vertex, so the offset of a chorded arc is a staircase.
    Measured on a 40 chord arc with a radial 0.508 and an axial 2.000: 80
    direction reversals, and 0.35660 mm from the same contour built at 8x the
    sampling, against 0.00019 mm for the isotropic case.

    The offset of a smooth curve is `p + d(n)*n` evaluated with the CURVE'S OWN
    normal. On a chorded arc that normal is the bisector of the two chords
    meeting at a vertex - so at a vertex INTERIOR TO A CURVE both sides offset
    along that bisector and land on the SAME point, and the result is a
    polyline on the true offset curve rather than a staircase around it.

    At a CORNER each surface keeps its own normal and its own allowance.
    Bisecting everywhere was tried and is wrong: it bleeds a wall's axial
    allowance into the diameter beside it, and the diameter then carried 0.3744
    where 0.500 was asked for. test_stock_to_leave caught it. THE ALLOWANCE
    BELONGS TO THE SURFACE; only a vertex that is not a corner has no surface
    of its own to belong to.

    With off_x == off_z every allowance is the same number, every offset is
    parallel to its chord and the corners are the ones they always were, so the
    isotropic path is untouched by construction.
    """
    segs = []
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        uz, ur = _unit(z1 - z0, r1 - r0)
        if abs(uz) < EPS and abs(ur) < EPS:
            segs.append(None)
            continue
        nz, nr = ur * side, -uz * side
        segs.append(((uz, ur), (nz, nr),
                     nose_r + stock_at_normal(nz, nr, off_x, off_z)))

    def plain(i):
        (z0, r0), (z1, r1) = pts[i], pts[i + 1]
        _u, (nz, nr), roll = segs[i]
        return ((z0 + roll * nz, r0 + roll * nr),
                (z1 + roll * nz, r1 + roll * nr), roll)

    if abs(off_x - off_z) < EPS:
        return [plain(i) if segs[i] else None for i in range(len(segs))]

    # a vertex is INTERIOR TO A CURVE when the turn across it is small - see
    # CURVE_TURN_DEG for why the cut is where it is
    cut = math.cos(math.radians(CURVE_TURN_DEG))
    joint = {}
    for j in range(1, len(pts) - 1):
        a, b = segs[j - 1], segs[j]
        if not a or not b:
            continue
        if a[0][0] * b[0][0] + a[0][1] * b[0][1] < cut:
            continue
        nz, nr = _unit(a[1][0] + b[1][0], a[1][1] + b[1][1])
        if abs(nz) < EPS and abs(nr) < EPS:
            continue
        d = nose_r + stock_at_normal(nz, nr, off_x, off_z)
        joint[j] = (pts[j][0] + d * nz, pts[j][1] + d * nr)

    out = []
    for i in range(len(segs)):
        if not segs[i]:
            out.append(None)
            continue
        a, b, roll = plain(i)
        out.append((joint.get(i, a), joint.get(i + 1, b), roll))
    return out


def stock_at_normal(nz, nr, off_x, off_z):
    """The allowance a surface with this outward normal is entitled to.

    Stock to leave is TWO numbers, not one: a radial allowance held on the
    diameters and an axial one held on the walls. A surface between the two
    gets a blend of them, and the blend is not a guess - it is what the normal
    already says.

    Displace the surface by the vector (nz * off_z, nr * off_x): a horizontal
    run has normal (0, 1) and moves off_x radially; a wall has normal (1, 0)
    and moves off_z axially. The perpendicular distance that displacement
    produces is its projection on the normal,

        d = nz^2 * off_z + nr^2 * off_x

    which is off_x on a diameter, off_z on a wall, and their mean at 45
    degrees. That is exactly the interpolation the reference package describes:
    "for surfaces that are not exactly horizontal, the program interpolates
    between the Axial Stock value (wall) and the Radial Stock values".

    (nz, nr) is the UNIT outward normal in (z, radius). With off_x == off_z
    this returns that value for every normal, so the isotropic path is
    unchanged to the last bit.
    """
    if abs(off_x - off_z) < EPS:
        return off_x
    return nz * nz * off_z + nr * nr * off_x


def offset_contour(points, nose_r, orient, side=1, extra=0.0, extra_z=None):
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

    `extra` is an allowance held ON TOP of the nose - a pre-finish stock, a
    pass step-down. IT SCALES THE NORMAL BUT NOT THE ORIENTATION TERM, which
    is the rule the interpreter follows and the one lathe_comp.offset_vector
    implements: the allowance moves the surface, the nose geometry does not
    change with it. Folding it into nose_r instead scales both, and on a
    surface parallel to an axis the two then cancel exactly - the allowance
    vanishes and every pass lands on the finished contour. Measured on
    testing_15_2: the pre-finish pass sat 0.0890 mm from the finish pass
    instead of 0.508, and in places 0.4389 mm INSIDE it.
    """
    if extra_z is None:
        extra_z = extra
    if not points or len(points) < 2 or nose_r + max(extra, extra_z) <= EPS:
        return list(points)
    roll = nose_r + extra

    off = NOSE_OFFSET[orient] if 0 < orient < len(NOSE_OFFSET) else None
    # the table is (X, Z); this module works in (z, radius)
    ozd, oxd = (off[1], off[0]) if off else (0.0, 0.0)

    # work in true radius: a normal is not scale invariant, so doing this on
    # diameters would be wrong by exactly a factor of two
    pts = [(z, x / DIAMETER_MODE) for z, x in points]

    segs = []
    coffs = curve_offsets(pts, side, nose_r, extra, extra_z)
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
        # The allowance belongs to the SURFACE, so it is the segment's own
        # everywhere except at a vertex INTERIOR TO A CURVE, where the two
        # sides offset along the curve's own normal and meet - see
        # curve_offsets. With one allowance this is the parallel offset it has
        # always been.
        a, b, seg_roll = coffs[i]
        segs.append({'v0': (z0, r0), 'v1': (z1, r1), 'u': (uz, ur),
                     'roll': seg_roll, 'a': a, 'b': b,
                     'ud': _unit(b[0] - a[0], b[1] - a[1])})
    if not segs:
        return list(points)

    out = _join_offsets(segs, side, roll, 'v1')

    # everything above is the NOSE CENTRE path - which is where the corner
    # geometry belongs, since it is the nose centre that rolls around a vertex
    # at exactly roll. The control point is that path shifted by the constant
    # orientation vector, applied once here.
    res = [(z - nose_r * ozd, (r - nose_r * oxd) * DIAMETER_MODE) for z, r in out]
    # drop repeats the joins can leave behind
    dedup = [res[0]]
    for p in res[1:]:
        if abs(p[0] - dedup[-1][0]) > EPS or abs(p[1] - dedup[-1][1]) > EPS:
            dedup.append(p)
    return dedup


def _seg_len(seg):
    return math.hypot(seg['b'][0] - seg['a'][0], seg['b'][1] - seg['a'][1])


def _consumed(hit, seg):
    """True when the trim point lies past the FAR END of seg's offset.

    An inside corner trims both offsets back to where they cross. When the
    segment after the corner is shorter than the offset itself, that crossing
    lands beyond the whole of it: the nose never touches that piece of the
    profile at all, it is swallowed by the corner. Joining to it anyway walks
    BACKWARD - out of the corner and into the part - and that reversal is the
    bump greatEndian reported at Z-20 on testing_15_2, where a 0.508 offset met
    the 0.005 mm first chord of the arc and dipped 0.187 mm below the wall.

    The offset segment is parallel to the profile segment, so seg['u'] is its
    direction too and the projection is exact rather than approximate.
    """
    t = ((hit[0] - seg['a'][0]) * seg['u'][0]
         + (hit[1] - seg['a'][1]) * seg['u'][1])
    return t > _seg_len(seg) + EPS


def _join_offsets(segs, sign, roll, vkey='v'):
    """Walk the offset segments and join them corner by corner.

    CORNERS ARE JOINED, NOT BUTTED TOGETHER. Emitting both ends of every offset
    segment and letting the next start where it likes leaves a connector that
    runs back behind an inside corner and forward again.

    - An EXTERNAL corner - the offsets diverge - is rounded. Both ends already
      sit exactly `roll` from the vertex, so the join is an arc of that radius
      about it and the nose rolls around the corner. A miter would hold the
      nose roll*(sqrt(2)-1) too far out at 90 degrees and leave material.
    - An INTERNAL corner - the offsets converge - is trimmed to the crossing,
      so the nose stops short and leaves a fillet of its own radius. That is
      what a real nose does in an inside corner and it is unavoidable.

    Two things bound the trim, and both were bugs before they were guards:
    the crossing must be within TRIM_REACH of the offset (two near-parallel
    segments cross arbitrarily far away - unguarded this put a point 17.83 mm
    off a contour offset by 0.5), and it must not lie beyond the segment it
    trims to - see _consumed. A segment the corner swallows is DROPPED and the
    trim recomputed against the one after it, which is what makes the result a
    single forward path instead of an offset with a loop in it.

    `sign` is the side convention of the caller (+1/-1); `vkey` names the key
    holding the shared vertex, since the two callers build their segment dicts
    with different names.
    """
    out = [segs[0]['a']]
    i = 0
    while i < len(segs):
        cur = segs[i]
        if i + 1 >= len(segs):
            out.append(cur['b'])
            break
        nxt = segs[i + 1]
        # each segment may carry its own roll, when the stock to leave is
        # anisotropic - see stock_at_normal. Falls back to the caller's single
        # value, so the isotropic path is untouched.
        r_cur = cur.get('roll', roll)
        r_nxt = nxt.get('roll', roll)
        r_max = max(r_cur, r_nxt)
        # A CURVE VERTEX NEEDS NO JOIN AT ALL. When the allowance tapers -
        # curve_offsets sharing the curve normal at a vertex interior to an arc -
        # offset ends land on the SAME point, and there is nothing to round or
        # to trim. Running the corner machinery there anyway is what was left
        # of the staircase: the arc branch draws about the raw vertex at
        # r_cur while the ends sit at the AVERAGED roll, so every vertex got a
        # little wrong-radius arc and the offset sawed 10.25 degrees either
        # way against 2.21 for a smooth one. Guarded before the cross test so
        # the near-parallel trim cannot fire on it either.
        if (abs(cur['b'][0] - nxt['a'][0]) < EPS
                and abs(cur['b'][1] - nxt['a'][1]) < EPS):
            out.append(cur['b'])
            i += 1
            continue
        (uz0, ur0), (uz1, ur1) = cur['u'], nxt['u']
        cross = (uz0 * ur1 - ur0 * uz1) * sign
        if cross > EPS:
            out.append(cur['b'])
            out.extend(_corner_arc(cur[vkey], cur['b'], nxt['a'], r_cur))
        elif cross < -EPS:
            # THE OFFSET SEGMENT'S OWN DIRECTION, not the chord's. With a
            # varying allowance the offset is not parallel to the chord any
            # more - it tapers - so intersecting on the chord direction
            # answers a slightly wrong question and the trims alternate,
            # leaving the staircase halved rather than gone. Identical to 'u'
            # whenever the allowance is constant.
            hit = _isect(cur['a'], cur.get('ud', cur['u']),
                         nxt['a'], nxt.get('ud', nxt['u']))
            if hit is not None and (
                    math.hypot(hit[0] - cur['b'][0], hit[1] - cur['b'][1])
                    > TRIM_REACH * r_max
                    or math.hypot(hit[0] - nxt['a'][0], hit[1] - nxt['a'][1])
                    > TRIM_REACH * r_max):
                hit = None
            if hit is not None and _consumed(hit, nxt):
                if i + 2 < len(segs):
                    del segs[i + 1]       # swallowed whole: drop it and retry
                    continue
                hit = None                # nothing left to trim to; butt them
            out.append(hit if hit is not None else cur['b'])
        else:
            out.append(cur['b'])          # collinear, nothing to join
        i += 1
    return out


def _corner_arc(vertex, start, end, radius):
    """Chords around an external corner, from start to end about vertex.

    Both ends normally lie `radius` from the vertex; this fills the sweep
    between them, taking the short way round, subdivided so each chord's
    sagitta stays under MESH_MAX_SAG.

    WHEN THE TWO ENDS ARE AT DIFFERENT RADII the corner is not an arc at all.
    That happens with an anisotropic stock to leave: the wall and the diameter
    meeting at the corner are entitled to different allowances, so the offset
    leaves the vertex at one distance and rejoins at another. The radius is
    interpolated across the sweep, which blends the two allowances through the
    corner instead of stepping between them. With equal ends this is the plain
    arc it always was.
    """
    vz, vr = vertex
    a0 = math.atan2(start[1] - vr, start[0] - vz)
    a1 = math.atan2(end[1] - vr, end[0] - vz)
    r0 = math.hypot(start[0] - vz, start[1] - vr)
    r1 = math.hypot(end[0] - vz, end[1] - vr)
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= 2 * math.pi
    while sweep < -math.pi:
        sweep += 2 * math.pi
    if abs(sweep) < 1e-9 or radius <= MESH_MAX_SAG:
        return [end]
    step = 2.0 * math.acos(max(1.0 - MESH_MAX_SAG / radius, -1.0))
    n = max(int(math.ceil(abs(sweep) / max(step, 1e-6))), 1)
    return [(vz + (r0 + (r1 - r0) * k / n) * math.cos(a0 + sweep * k / n),
             vr + (r0 + (r1 - r0) * k / n) * math.sin(a0 + sweep * k / n))
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
CAM_BASE = 4600
# Numbered parameters above roughly #5060 are LinuxCNC's own - #5061+ are probe
# results, #5161+ home positions, #5221+ the coordinate-system offsets, #5401+
# the tool table. Writing a table through them would corrupt live machine state,
# so a profile that does not fit under this refuses instead.
# 4984, not 5000: poly_add_item uses #4984-#4999 as scratch on every machine,
# so a table allowed to grow past 4984 would be overwritten by the very
# subroutine that builds the record array. Found by cam_map's collision check;
# the worst real usage measured is 290 slots, reaching 4890, so nothing had
# been corrupted - the declared cap was simply wrong and nothing could see it.
CAM_TOP = 4984


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


def build_cam_comp_gcode(polyline_feature, nose_r, orient, back_deg=None,
                         flank_len=0.0, clearance=0.0):
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
    points, _soft = finish_profile(polyline_feature, back_deg, 0.0, flank_len,
                                   clearance)
    if not points or len(points) < 2:
        return _refuse('the profile does not resolve to at least two points')

    s_param = polyline_feature.get_param('param_side')
    side = -1 if (s_param is not None
                  and int(_to_float(s_param.get_ngc_value())) == 1) else 1

    def _off(pname):
        p = polyline_feature.get_param(pname)
        return _to_float(p.get_ngc_value()) if p is not None else 0.0

    fin_off, fin_off_z = stock_pair(polyline_feature)
    pf_off = _off('param_pf_off') * (1 if _off('param_pf_on') else 0)
    offsets = cam_pass_offsets(fin_off, pf_off, _off('param_f_pass'))

    # each pass steps its allowance down proportionally, and the axial one has
    # to step with it or the walls would keep their full stock while the
    # diameters lost theirs. Scaled by the pass's own share of fin_off.
    def _z_for(extra):
        if abs(fin_off_z - fin_off) < EPS or fin_off <= EPS:
            return extra
        return fin_off_z * (extra / fin_off)

    # THE OFFSET MUST DEPEND ON THE PART, NOT ON THE DIRECTION OF CUT.
    # offset_contour takes its normal from each segment's direction - nz, nr =
    # ur*side, -uz*side - so handing it the profile REVERSED flips every normal
    # and the path offsets the wrong way. On a bore that puts the nose centre
    # at wall + R instead of wall - R: a gouge of exactly 2R, the whole nose
    # diameter into the wall.
    # finish_profile returns its points in the FINISHING direction, which for a
    # right-hand boring bar runs the other way round the profile than it does
    # for an OD tool - so testing_14_inside_bar came out reversed and every
    # In-CAM bore with that tool was cut 0.8 mm oversize. Measured: reversed
    # input gives the mouth control point at r17.8 against the correct r17.0,
    # matching the emitted program exactly. See analysis/107.
    # Offset in the drawn order and put the result back the way it came, so the
    # cut direction is preserved and only the geometry is corrected.
    _ref = resolve_points(polyline_feature)
    _rev = (len(points) > 1 and len(_ref) > 1
            and (points[0][0] - points[-1][0])
            * (_ref[0][0] - _ref[-1][0]) < 0)
    _src = list(reversed(points)) if _rev else points
    paths = [offset_contour(_src, nose_r, int(orient), side, extra,
                            _z_for(extra))
             for extra in offsets]
    if _rev:
        paths = [list(reversed(p)) for p in paths]
    if any(len(p) < 2 for p in paths):
        return _refuse('the offset path collapsed - the nose radius is too '
                       'large for this profile')

    # EACH PASS MAY BECOME SEVERAL SUB-PATHS, split where the contour meets a
    # perpendicular X wall - see split_contour_at_walls. The directory below is
    # a flat list of sub-paths and `owner` says which pass each belongs to, so
    # the pass loops walk their own entries and nothing else changes shape. A
    # profile with no wall, or the feature off, yields exactly one sub-path per
    # pass and the identical directory this emitted before.
    xw_mode, xw_front, xw_back, xw_tol = xw_settings(polyline_feature)
    subs, owner = [], []
    for k, p in enumerate(paths):
        parts = (split_contour_at_walls(p, xw_tol, xw_front, xw_back,
                                        2.0 * nose_r,
                                        _stock_x(polyline_feature), nose_r)
                 if xw_mode == 2 and xw_front > 0 else [p])
        for part in parts:
            subs.append(part)
            owner.append(k)

    # THE OWNER TABLE ONLY EXISTS WHEN SOMETHING SPLIT, and that is not tidiness
    # - it is the slot budget. Carrying an owner slot in the directory itself
    # cost one per entry on EVERY project, and testing_13_arcs was already at
    # 384 of 384: it needed 386 and refused to compensate at all. So the
    # directory stays two slots per sub-path exactly as it was, entry k is
    # pass k when nothing split, and the owners are appended after the points
    # only when they are needed. A project without walls pays nothing.
    split = len(subs) != len(paths)

    # directory first, then the points; the base of each table depends on how
    # long every table before it turned out to be
    ptr = CAM_BASE + 2 * len(subs)
    ptrs = []
    for p in subs:
        ptrs.append(ptr)
        ptr += 2 * len(p)
    own_base = 0
    if split:
        own_base = ptr
        ptr += len(subs)
    if ptr > CAM_TOP:
        return _refuse('the offset path needs %d parameter slots and only %d '
                       'are safe to use - reduce the number of finish passes, '
                       'or use Native LinuxCNC' % (ptr - CAM_BASE,
                                                   CAM_TOP - CAM_BASE))

    lines = ['(nose compensation done in CAM: these are already-offset control)',
             '(point paths, so the machine runs uncompensated - see _tip_cam)',
             '#<_pl_cam_dir> = %d' % CAM_BASE,
             '#<_pl_cam_n>   = %d' % len(subs),
             '#<_pl_cam_own> = %d' % own_base,
             '#<_pl_cam_max> = %d' % max(len(p) for p in subs)]
    for k, (p, base) in enumerate(zip(subs, ptrs)):
        lines.append('#%d = %d' % (CAM_BASE + 2 * k, base))
        lines.append('#%d = %d' % (CAM_BASE + 2 * k + 1, len(p)))
    for k, (p, base) in enumerate(zip(subs, ptrs)):
        lines.append('(%s%s, allowance %s + nose %s, %d points)'
                     % ('pre-finish pass' if owner[k] == 0
                        else 'finish pass %d' % owner[k],
                        '' if owner.count(owner[k]) == 1
                        else ' part %d of %d' % (owner[:k + 1].count(owner[k]),
                                                 owner.count(owner[k])),
                        _fmt(offsets[owner[k]]), _fmt(nose_r), len(p)))
        for i, (z, x) in enumerate(p):
            lines.append('#%d = %s' % (base + 2 * i, _fmt(z)))
            lines.append('#%d = %s' % (base + 2 * i + 1, _fmt(x / DIAMETER_MODE)))
    if split:
        lines.append('(which pass each sub-path belongs to, 0 the pre-finish)')
        for k, o in enumerate(owner):
            lines.append('#%d = %d' % (own_base + k, o))
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
#   2800  per-window deepest cut  i     - WRITTEN AT RUNTIME by
#                                         lathe_level_pass, one slot per
#                                         window, cleared to 999999 here
#   3400  sections window table   i*4
#   3600  flank envelope          i*2, capped below
#   3700  floor contour           i*2 - where a roughing LEVEL stops
#   4000  finish soft contour     i*2, capped below
#   4400  In-CAM offsets          directory + points, capped at CAM_TOP
#
# test_table_layout in test_sections.py asserts they stay disjoint.
# The only table here that Python does not fill in: lathe_level_pass writes the
# deepest level each window actually CUT, and reads its neighbours' back to
# decide whether an entry lead has any metal to enter. It has to be runtime -
# the ladder lives in the O-code and a Python guess at what each window reaches
# would be a second answer that could disagree with the real one.
# 1000-2999 was measured to be completely unreferenced - by cfg/, lib/, ncam.py
# and lathe_sections alike, and by the whole generated program, whose lowest
# numbered parameter is 3000 - so this takes room from nothing. 200 slots
# against the window table's own 50-window ceiling, so it can never be the
# binding limit: greatEndian, 2026-08-15, *"there could come any files with any
# number of points .. therefore the should not be limit that low"*.
WDEEP_BASE = 2800
WDEEP_TOP = 3000
SECT_BASE = 3400
FLANK_BASE = 3600
# the flank envelope has never needed more than 58 slots of its 400, measured
# across four projects, so 100 is left to it and the rest goes to the floor
# contour - which is built from the RAW profile and so has more points than the
# tables built from the simplified reachable one: 226 slots on testing_15_2,
# where 200 was not enough and it silently fell back to the old scan
FLANK_TOP = 3700
FLOORC_BASE = 3700
FLOORC_TOP = 4000
FC_BASE = 4000
FC_TOP = 4200
# the ENTRY contour - see entry_contour(). It shares 4000-4400 with the finish
# contour, which was given 200 points and has never needed more than 20; both
# are bounded and both refuse rather than run into their neighbour.
ENTRY_BASE = 4200
ENTRY_TOP = 4400
# the STOP contour - see build_stop_contour_gcode. Carved out of the
# In-CAM range, which had 600 slots and has never needed more than 200.
STOP_BASE = 4400
STOP_TOP = 4600


# How far an inside-corner trim may reach, as a multiple of the offset. Two
# segments meeting at a shallow angle cross a long way off, and the runaway is
# unbounded as they approach parallel. Measured: a real trim on testing_15_2's
# end wall needs more than 1x, and the failure it has to reject was 35x.
TRIM_REACH = 4.0


def entry_contour(points, dist, rough_dir=0, nose_r=0.0, orient=0,
                  dist_z=None):
    """The contour offset outward by `dist`, as a (z, radius) polyline.

    This is where a roughing level may BEGIN cutting. The level stops on the
    floor allowance - by then it is already down on the floor - but it does not
    have to wait that long to start: against the shallow ramp the back angle
    leaves behind a peak, the floor allowance costs its own length divided by
    the sine of the ramp angle before the cut even begins. On testing_15_2 that
    is 4.51 mm per level and 36.1 mm of metal left standing.

    Computed HERE rather than in the subroutine on purpose. The .ngc already
    reconstructs an offset profile at runtime - normals, corner connectors,
    fold-back guards - and doing it a second time at a second allowance needed
    an extra CALL argument the interpreter refuses to accept ("Command too
    long") and a second scan nobody can unit-test. Python offsets it once, at
    generation time, and the subroutine is handed a table to walk.

    The rule is deliberately IDENTICAL to lathe_level_pass's own: each segment
    is offset along its outward normal, and consecutive offset ends are joined
    by a straight connector - which is what emitting both endpoints of every
    segment, in order, produces. Matching it matters: the entry point and the
    stop are compared against each other, so they have to be measured off the
    same construction.

    **`points` must be in RADIUS, not in the diameters resolve_points works
    in.** A perpendicular offset is not the same construction in the two
    spaces: the ramp that measures 13 degrees in radius measures 24.78 in
    diameter, so offsetting there and halving afterwards gives 1.129 mm of Z
    where 2.258 is wanted. That is the same trap flank_slope documents when it
    scales its slope by DIAMETER_MODE, and it cost this function a silent
    factor of two - the entry landed at Z-48.161 against the Z-49.203 the
    interpreter's own scan produces at the same allowance.

    `dist` is a radius. `rough_dir` picks the outward side the way flank_sides
    does, so front-to-back and back-to-front both come out right.

    `nose_r` and `orient` compensate it. ROUGHING CARRIES NO INTERPRETER
    COMPENSATION IN ANY MODE - lathe_level_pass has no tip_comp_* call at all
    - so when compensation is on, the nose geometry has to be applied here, to
    the table the subroutine walks. Same shape as taper.ngc uses for its
    roughing and lathe_poly_pass for its entry: geometry we own, applied to
    the points.

    The normal carries `dist + nose_r`; the orientation term is subtracted
    once at the end and scales with the BARE nose radius. That asymmetry is
    the rule - see lathe_comp.offset_vector. Folding the nose into `dist`
    would scale both and cancel on any surface parallel to an axis, which is
    exactly how the pre-finish pass collapsed onto the finish contour, twice,
    in analysis/004.

    A LEVEL'S OWN DIAMETER NEEDS NO OFFSET and gets none: a level cut runs
    parallel to Z, and there the two terms cancel. What moves is where the
    level STARTS and STOPS against the contour, which is what this decides.
    """
    if dist_z is None:
        dist_z = dist
    roll = dist + nose_r
    if not points or len(points) < 2 or max(dist, dist_z) + nose_r <= 0:
        return list(points)
    ox, oz = (NOSE_OFFSET[orient] if 0 < orient < len(NOSE_OFFSET)
              else (0.0, 0.0))
    ozr, oxr = nose_r * oz, nose_r * ox
    z_dir = -1 if rough_dir == 1 else 1

    segs = []
    coffs = curve_offsets(points, z_dir, nose_r, dist, dist_z)
    for i, ((z0, x0), (z1, x1)) in enumerate(zip(points, points[1:])):
        dz, dx = z1 - z0, x1 - x0
        n = math.hypot(dz, dx)
        if n < EPS:
            continue
        uz, ux = dz / n, dx / n
        nz, nx = z_dir * ux, -z_dir * uz
        a, b, seg_roll = coffs[i]
        segs.append({'a': a, 'b': b, 'u': (uz, ux), 'v': (z1, x1),
                     'roll': seg_roll,
                     'ud': _unit(b[0] - a[0], b[1] - a[1])})
    if not segs:
        return list(points)

    # Corners are joined rather than butted together, by the same rules the
    # contour offset uses - see _join_offsets, which both call. Butting them
    # left a connector running BACK behind an inside corner and forward again:
    # four reversals on testing_15_2, one at -20.000 -> -19.492 where the wall
    # meets the taper. greatEndian: the line has to be straight until the
    # radius starts rising.
    out = _join_offsets(segs, z_dir, roll, 'v')
    res = [(z - ozr, x - oxr) for z, x in out]

    # THE ORIENTATION SHIFT MOVES THE OPEN ENDS TOO, and there it takes away
    # coverage instead of placing the tool. The back wall of testing_15_2 runs
    # up to r30.0000, the stock; shifted, the stop contour's wall tops out at
    # r29.6000 - and the highest roughing level sits at r29.6520, just above
    # it. That level then never crosses the wall at all: it stopped 0.5080
    # short of the pre-finish, never touched it, and rapided away, which is
    # greatEndian's photo/leadOutIssue_1.png. Off was correct throughout, so
    # the fault arrived with compensation and only on the terminal segment.
    #
    # Both terminal segments are therefore extended back along their own
    # direction by the shift, restoring the span the contour had before it
    # moved. Over-extending slightly is harmless here - this is a STOP/ENTRY
    # reference, and a level above the stock has nothing to cut anyway - while
    # under-extending silently drops a whole pass.
    shift = math.hypot(ozr, oxr)
    if shift > EPS and len(res) >= 2:
        res[0] = _extend_end(res[1], res[0], shift)
        res[-1] = _extend_end(res[-2], res[-1], shift)
    return res


def _extend_end(prev, end, dist):
    """`end` pushed further along the prev->end direction by `dist`."""
    dz, dx = end[0] - prev[0], end[1] - prev[1]
    n = math.hypot(dz, dx)
    if n < EPS:
        return end
    return (end[0] + dz / n * dist, end[1] + dx / n * dist)



def _comp_nose(polyline_feature, nose_r, orient):
    """(nose_r, orient) when this polyline compensates, (0, 0) when it does not.

    Roughing has no interpreter compensation in any mode, so the tables it
    walks carry the nose themselves - but only when the operation is actually
    compensating. With Tool nose comp off they must come out exactly as before,
    or every existing project's roughing moves for no reason.
    """
    p = polyline_feature.get_param('param_n_comp')
    if p is None or int(_to_float(p.get_ngc_value())) not in (1, 2):
        return 0.0, 0
    if nose_r is None or nose_r <= EPS or not 0 < int(orient) < 10:
        return 0.0, 0
    return float(nose_r), int(orient)

def build_rough_nose_gcode(polyline_feature, nose_r=0.0, orient=0):
    """The orientation term roughing carries, ALREADY GATED. Always emitted.

    A roughing level begins at the window start whenever the entry contour
    never crosses it - every level above the part - and the window is a raw
    profile Z. So the level's tip started where the SURFACE starts and the
    nose, which trails the tip by the orientation vector, began cutting 0.4 mm
    past it: measured on testing_15_2, the drawn segment starts at Z+1.0000 and
    green began its cut at Z+1.4000, in all three modes. The level's STOP has
    carried the nose since the stop table was built, so one end of every
    roughing pass was compensated and the other was not - the same asymmetry
    analysis/009 found at the two ends of the contour pass.

    Gated HERE and not in the .ngc, so lathe_level_pass subtracts a number
    rather than deciding anything: _pl_nose_oz from lathe_comp is the tool's
    term whatever the mode, and roughing must take it only when this polyline
    actually compensates. That is exactly _comp_nose's question, and it is the
    same one the entry and stop tables already ask.

    Emitted unconditionally - unlike the entry contour, which is skipped when
    the roughing depth is 0 - because a level starts somewhere regardless.
    """
    oz, ox = 0.0, 0.0
    _nr, _or = _comp_nose(polyline_feature, nose_r, orient)
    if _nr > EPS and 0 < int(_or) < len(NOSE_OFFSET):
        vec = NOSE_OFFSET[int(_or)]           # (X, Z), raw - not a unit vector
        ox, oz = _nr * vec[0], _nr * vec[1]
    # WHICH WAY ALONG Z THIS INSERT CAN CUT, for the profile-angle ramp.
    # Taken from the RAW orientation, not the gated one: the ramp is a
    # question about the tool's geometry, which is true whether or not this
    # polyline compensates, where oz/ox above are a compensation offset and
    # must stay zero when it does not.
    return '\n'.join([
        '(the orientation term ROUGHING carries: zero unless this polyline)',
        '(compensates, so a level start needs no gate of its own)',
        '#<_pl_rgh_oz> = %s' % _fmt(oz),
        '#<_pl_rgh_ox> = %s' % _fmt(ox),
        '(the Z direction this insert cuts in: +1, -1, or 0 for a facing or)',
        '(on-the-point tool that expresses no axial preference. The)',
        '(profile-angle ramp is armed only where the pass TRAVELS this way -)',
        '(see the pa_face gate in lathe_level_pass. See ramp_facing.)',
        '#<_pl_ramp_face> = %d' % ramp_facing(orient)])


def build_entry_contour_gcode(polyline_feature, back_deg, nose_r=0.0,
                              flank_len=0.0, clearance=0.0, entry_off=0.0, orient=0):
    """The entry contour as a point table, or '' when there is nothing to say.

    Emitted next to the finishing contour and read the same way. The runtime
    gate is _pl_entry_n > 0, so '' leaves roughing exactly as it was.
    """
    if entry_off is None or _to_float(entry_off) <= 0:
        return ''
    pts, _soft = finish_profile(polyline_feature, back_deg, nose_r, flank_len,
                                clearance)
    if not pts or len(pts) < 2:
        return ''
    d = polyline_feature.get_param('param_dir')
    # one decomposition frame - see rough_frame_dir
    rough_dir = rough_frame_dir(
        int(_to_float(d.get_ngc_value())) if d is not None else 0)
    # into RADIUS before offsetting - see entry_contour. The table is written
    # in radius too, so there is no second conversion on the way out.
    _nr, _or = _comp_nose(polyline_feature, nose_r, orient)

    # ONE DEPTH OF CUT ABOVE THE FLOOR, not above the finished shape. This was
    # `entry_off` alone - the roughing depth of cut - so the surface a level
    # may begin cutting on sat one depth of cut from the FINAL contour whatever
    # allowance had been asked for. Two of greatEndian's reports are that one
    # fault: with the pre-finish offset zeroed the yellow entry line did not
    # move, because it never depended on it; and with the offset at 1.0 the
    # entry sat NEARER THE Z AXIS THAN THE PRE-FINISH SURFACE - inside the
    # material it is supposed to stand off - because 1.0 is more than a depth
    # of cut.
    #
    # The floor already stands `fin + prefin` off the profile, so the entry
    # belongs at `fin + prefin + one depth of cut`. Anisotropic on the two
    # allowances the same way the floor is, and the depth of cut added to both:
    # it is one cut's worth of clearance in whatever direction the surface
    # faces, not a radial-only quantity.
    fin_off, fin_off_z = stock_pair(polyline_feature)
    pf = polyline_feature.get_param('param_pf_off')
    pf_on = polyline_feature.get_param('param_pf_on')
    pf_off = _to_float(pf.get_ngc_value()) if pf is not None else 0.0
    if pf_on is not None and _to_float(pf_on.get_ngc_value()) <= 0:
        pf_off = 0.0
    _e = _to_float(entry_off)
    env = entry_contour([(z, x / DIAMETER_MODE) for z, x in pts],
                        fin_off + pf_off + _e, rough_dir, _nr, _or,
                        fin_off_z + pf_off + _e)
    if len(env) < 2:
        return ''
    top = ENTRY_BASE + 2 * len(env)
    if top > ENTRY_TOP:
        return ('(WARNING - the entry contour needs %d parameter slots and '
                'only %d are free, so roughing levels will start on the floor '
                'allowance as before.)' % (top - ENTRY_BASE,
                                           ENTRY_TOP - ENTRY_BASE))
    lines = ['(where a roughing level may BEGIN cutting: the reachable)',
             '(contour offset by one roughing depth of cut. The level still)',
             '(STOPS on the floor allowance - by then it is already down on)',
             '(the floor - but it need not wait that long to start)',
             '#<_pl_entry_base> = %d' % ENTRY_BASE,
             '#<_pl_entry_n>    = %d' % len(env)]
    for i, (z, x) in enumerate(env):
        lines.append('#%d = %s' % (ENTRY_BASE + 2 * i, _fmt(z)))
        lines.append('#%d = %s' % (ENTRY_BASE + 2 * i + 1, _fmt(x)))
    # and the ramp direction per segment of that same contour, so the runtime
    # reads the angle to arrive at instead of choosing one - it rides along
    # with the contour it indexes rather than needing a call of its own, which
    # also means no saved project has to migrate to get it
    ramp = build_entry_ramp_gcode(env, _to_float(entry_off))
    if ramp:
        lines.append(ramp.rstrip('\n'))
    return '\n'.join(lines)


def floor_contour_data(polyline_feature, back_deg, nose_r=0.0,
                              flank_len=0.0, clearance=0.0, orient=0,
                              rough_cut=0.0):
    """(env, renv, rough_dir) - the floor contour and the resume
    envelope as DATA, or None.

    Split out of build_floor_contour_gcode so the interval walk can be
    worked out at generation time from the same two tables the runtime
    is handed. Both come from ONE `env` here, which is what stops them
    drifting - see the emitter for what that cost when they did.

    Originally: where a roughing LEVEL stops - the profile offset by the
    floor allowance.

    The subroutine used to work this out itself, offsetting every segment of
    the record array perpendicular by one scalar at runtime. That cannot hold
    two allowances, and it showed: with X 0.508 and Z 2.000 roughing stopped
    **0.762** from testing_15_2's end wall instead of 2.000, because 0.762 is
    `fin_off + prefin_off` and nothing there knew about the axial value. The
    stop table could not rescue it either - that one is bounded to EXTENDING a
    cut and never pulls one back.

    So the floor becomes a table like the entry and stop contours beside it,
    and the scan walks it. Two things come free with the move:

    - **the allowance is anisotropic**, because `entry_contour` blends by the
      surface normal;
    - **the corners are joined** - inside ones trimmed to their crossing,
      outside ones rounded - which is what the runtime scan's gap-connector
      hack exists to paper over, because independently offset segments leave
      gaps at a corner.

    The pre-finish allowance stays isotropic: it is a depth of cut for the
    pass that follows, not a face-versus-diameter choice.
    """
    fin_off, fin_off_z = stock_pair(polyline_feature)
    pf = polyline_feature.get_param('param_pf_off')
    pf_on = polyline_feature.get_param('param_pf_on')
    pf_off = _to_float(pf.get_ngc_value()) if pf is not None else 0.0
    if pf_on is not None and _to_float(pf_on.get_ngc_value()) <= 0:
        pf_off = 0.0
    floor_x, floor_z = fin_off + pf_off, fin_off_z + pf_off
    if max(floor_x, floor_z) <= 0:
        return None

    # THE RAW PROFILE, not the reachable one. The scan this replaces walks the
    # record array, which is the polyline as drawn; the back-angle shadow is a
    # separate table the level pass consults on its own. Building this from
    # finish_profile instead changed which surface roughing stops against and
    # cost testing_15_2 nine of its 29 levels - the only thing that may change
    # here is the ALLOWANCE.
    pts, _soft = finish_profile(polyline_feature, back_deg, nose_r,
                                flank_len, clearance, orient)
    if not pts or len(pts) < 2:
        return None
    d = polyline_feature.get_param('param_dir')
    # one decomposition frame - see rough_frame_dir
    rough_dir = rough_frame_dir(
        int(_to_float(d.get_ngc_value())) if d is not None else 0)
    _nr, _or = _comp_nose(polyline_feature, nose_r, orient)
    env = entry_contour([(z, x / DIAMETER_MODE) for z, x in pts],
                        floor_x, rough_dir, _nr, _or, floor_z)
    if len(env) < 2:
        return None
    if FLOORC_BASE + 2 * len(env) > FLOORC_TOP:
        return ('(WARNING - the floor contour needs %d parameter slots and only '
                '%d are free, so roughing works its own floor out as before and '
                'a separate Z offset will not reach it.)'
                % (2 * len(env), FLOORC_TOP - FLOORC_BASE))
    li_len = polyline_feature.get_param('param_li_len')
    li_ang = polyline_feature.get_param('param_li_ang')
    lead_z = 0.0
    if li_len is not None:
        _l = _to_float(li_len.get_ngc_value())
        _a = _to_float(li_ang.get_ngc_value()) if li_ang is not None else 45.0
        lead_z = abs(_l * math.cos(math.radians(_a)))
    renv = resume_envelope(env, 1 if rough_dir == 0 else -1, lead_z,
                           rough_cut)
    return env, renv, rough_dir


def build_floor_contour_gcode(polyline_feature, back_deg, nose_r=0.0,
                              flank_len=0.0, clearance=0.0, orient=0,
                              rough_cut=0.0):
    """The #3700 floor contour and the #3000 resume envelope."""
    got = floor_contour_data(polyline_feature, back_deg, nose_r,
                            flank_len, clearance, orient, rough_cut)
    if got is None:
        return ''
    env, renv, rough_dir = got
    if FLOORC_BASE + 2 * len(env) > FLOORC_TOP:
        return ('(WARNING - the floor contour needs %d parameter slots and only '
                '%d are free, so roughing works its own floor out as before and '
                'a separate Z offset will not reach it.)'
                % (2 * len(env), FLOORC_TOP - FLOORC_BASE))
    lines = ['(where a roughing LEVEL stops: the profile offset by the floor)',
             '(allowance, joined at its corners and blended between the radial)',
             '(and axial values by each surface own normal. The scan walks this)',
             '(instead of offsetting the record array by one number at runtime.)',
             '#<_pl_flc_base> = %d' % FLOORC_BASE,
             '#<_pl_flc_n>    = %d' % len(env)]
    for i, (z, x) in enumerate(env):
        lines.append('#%d = %s' % (FLOORC_BASE + 2 * i, _fmt(z)))
        lines.append('#%d = %s' % (FLOORC_BASE + 2 * i + 1, _fmt(x)))

    # THE RESUME ENVELOPE, built HERE from the very same points. The bug this
    # exists for was two scans reading two sources: the stop scan moved onto
    # this contour and lathe_level_next_start kept offsetting the record array
    # by a scalar, so they disagreed about where the boss is and a level that
    # stopped in front of it was never resumed behind it - testing_15_5 lost
    # two passes and took a 1.524 mm bite against a 0.508 depth of cut.
    # Emitting both tables from one `env` is what makes them unable to drift.
    if renv and RESUME_BASE + 2 * len(renv) <= RESUME_TOP:
        lines += ['(where a blocked level may plunge back in, per level. Monotone)',
                  '(by construction: a level never resumes in front of the one)',
                  '(above it, so the rapid cannot pass through standing metal.)',
                  '#<_pl_res_base> = %d' % RESUME_BASE,
                  '#<_pl_res_n>    = %d' % len(renv)]
        for i, (lev, rz) in enumerate(renv):
            lines.append('#%d = %s' % (RESUME_BASE + 2 * i, _fmt(lev)))
            lines.append('#%d = %s' % (RESUME_BASE + 2 * i + 1, _fmt(rz)))
    elif renv:
        lines.append('(WARNING - the resume envelope needs %d parameter slots '
                     'and only %d are free, so the resume scan falls back to '
                     'the record array.)'
                     % (2 * len(renv), RESUME_TOP - RESUME_BASE))
    return '\n'.join(lines)


def resume_envelope(contour, z_dir=1, lead_z=0.0, rough_cut=0.0):
    """Where each roughing LEVEL may plunge back in, as a function of the level.

    A level blocked by a boss cuts up to it, retracts, and rapids down again
    behind it. Two things have to be true of that plunge Z, and only one of
    them is local:

    - the floor has dropped back below the level there - a per-level question,
      answered by the first above-to-below crossing of the floor contour;
    - **every level ABOVE has already cut there** - a LADDER-WIDE question that
      no single subroutine call can see, because each call knows one level.

    The second is why this is a table and not a scan. Following the true
    contour, the raw crossings are not monotonic: on test_rough_ends level
    31.1760 crossed at Z-40.7954 while 31.6840 directly above it crossed at
    Z-40.8518, so a plunge there went through 0.4700 mm of standing metal.
    Sweeping the levels from the top and never letting a resume move FORWARD
    fixes both ends at once - the material above is gone by then, and the floor
    is already below this level, so starting later gouges nothing.

    `lead_z` is the Z reach of the lead-in, and it is not a detail. The rapid
    does not land on the resume point - it lands where the LEAD-IN starts,
    `lead_z` in FRONT of it, and a clamp that only makes the resume points
    monotone leaves that landing spot unguarded. Measured on testing_15_2: the
    level resumed at Z-43.5302, monotone and correct, while its 45 degree
    lead-in began at Z-42.8231 where the level above had not yet cut, and the
    plunge went through 0.4700 mm of metal. So the condition is
    `R(L) + lead_z` behind `R(L_above)`, not `R(L)` behind it.

    Returns (level, resume_z) breakpoints, level descending, resume_z monotone.
    The breakpoints are the contour's own vertex radii: between two of them the
    first crossing stays on one segment, so the function is linear there and
    the walker can interpolate. A level ABOVE the first breakpoint is never
    blocked and has no resume - that is the empty answer, not the deepest one,
    and reading it as the deepest is a mistake this returns no value for.
    """
    levels = sorted({x for _z, x in contour}, reverse=True)
    out = []
    back = None
    prev_lev = levels[0] if levels else 0.0
    for lev in levels:
        pz, px = contour[0]
        hit = None
        for cz, cx in contour[1:]:
            if px >= lev > cx:
                hit = (pz + (cz - pz) * (lev - px) / (cx - px)
                       if abs(cx - px) > EPS else cz)
                break
            pz, px = cz, cx
        if hit is None:
            continue
        # Behind the level above by at least the lead-in's own reach, so the
        # RAPID's landing point is in cut space and not merely the resume
        # point. IT IS A RATE, not a fixed step: these breakpoints are contour
        # VERTICES, tens of times closer together than the 0.508 depth of cut,
        # and subtracting a whole lead_z at each one drifted testing_15_5's
        # envelope some 38 mm and cost it the very passes this exists to
        # restore. The condition is lead_z of Z for every rough_cut of level.
        limit = None
        if back is not None:
            span = ((prev_lev - lev) / rough_cut if rough_cut > EPS else 1.0)
            limit = back - z_dir * lead_z * span
        if limit is not None and z_dir * (hit - limit) > 0:
            hit = limit
        back = hit
        prev_lev = lev
        out.append((lev, hit))

    # THE ENVELOPE MUST REACH THE BOTTOM OF THE LAST DESCENT. The crossing test
    # above is strict at a segment's lower end - `px >= lev > cx` - so a
    # descending segment never yields a breakpoint at its OWN bottom; it can
    # only get one from a LATER segment that descends past it. Where the last
    # descent is a long taper, which the back-angle shadow behind a boss always
    # is, nothing comes after it and the envelope stops partway down.
    #
    # Measured on testing_15_6: that taper is ONE segment, Z-36.1330 X33.7997
    # to Z-68.8918 X26.2368. The envelope's lowest breakpoint was 27.2313 - a
    # vertex radius from elsewhere on the profile, whose crossing lands on the
    # taper at Z-64.5839 - and the two levels below it, 27.1120 and 26.6040,
    # fell outside the table. The walker's out-of-range fallback returns the
    # LAST breakpoint's Z, where the floor is 27.2313, so both levels were
    # judged inside the part and cut nothing: greatEndian's missing last passes
    # behind the boss. testing_15_5 escaped only by luck - its lowest
    # breakpoint, 25.5146, happens to sit near its own taper end at 25.2989.
    #
    # Only descents that end BEHIND the last breakpoint count: a deeper descent
    # in front of it is a different feature and would put the resume in front.
    if out:
        deep = None
        pz, px = contour[0]
        for cz, cx in contour[1:]:
            if px > cx + EPS and z_dir * (cz - out[-1][1]) < 0:
                if deep is None or cx < deep[0]:
                    deep = (cx, cz)
            pz, px = cz, cx
        if deep is not None and out[-1][0] > deep[0] + EPS:
            lev, hit = deep
            span = ((prev_lev - lev) / rough_cut if rough_cut > EPS else 1.0)
            limit = back - z_dir * lead_z * span
            if z_dir * (hit - limit) > 0:
                hit = limit
            out.append((lev, hit))

    # COLLAPSE what the walker cannot tell apart. The clamp flattens long runs
    # to one resume_z, and the raw breakpoints are every vertex radius of a
    # densified arc, so most of them sit on the straight line between their
    # neighbours. Dropping those is exact to the tolerance below and is not
    # cosmetic: unsimplified, testing_15_5 needed 176 slots against 140 free
    # and the whole table fell back to the record scan.
    keep = []
    for i, pt in enumerate(out):
        if 0 < i < len(out) - 1:
            (l0, z0), (l1, z1) = keep[-1], out[i + 1]
            if abs(l1 - l0) > EPS:
                t = (pt[0] - l0) / (l1 - l0)
                if abs(z0 + t * (z1 - z0) - pt[1]) <= 1e-4:
                    continue
        keep.append(pt)
    return keep


def build_stop_contour_gcode(polyline_feature, back_deg, nose_r=0.0,
                             flank_len=0.0, clearance=0.0, orient=0):
    """Where a roughing level may STOP: the pre-finish contour.

    The pre-finish pass traces the final shape plus the finish offset, and
    roughing should reach that surface rather than standing off it. It was
    stopping on the ROUGHING FLOOR instead - one whole depth of cut further
    out again, once "Space passes from = Final contour" has rounded the
    pre-finish allowance up - which left a constant gap between every level end
    and the pre-finish pass, right across the part.

    A table rather than a smaller allowance, because the allowance the
    subroutine scans with is not only the stop: the same number drives its
    block test and its multi-crossing scan, and halving it let levels run on
    through material they were being held out of - 487 mm of cut became 875.6
    and ten level ends finished inside the contour. So the scan keeps the floor
    allowance and the stop is looked up here.
    """
    fin_off, fin_off_z = stock_pair(polyline_feature)
    pf = polyline_feature.get_param('param_pf_off')
    pf_on = polyline_feature.get_param('param_pf_on')
    pf_off = _to_float(pf.get_ngc_value()) if pf is not None else 0.0
    if pf_on is not None and _to_float(pf_on.get_ngc_value()) <= 0:
        pf_off = 0.0
    stop_x, stop_z = fin_off + pf_off, fin_off_z + pf_off
    if max(stop_x, stop_z) <= 0:
        return ''
    pts, _soft = finish_profile(polyline_feature, back_deg, nose_r, flank_len,
                               clearance)
    if not pts or len(pts) < 2:
        return ''
    d = polyline_feature.get_param('param_dir')
    # one decomposition frame - see rough_frame_dir
    rough_dir = rough_frame_dir(
        int(_to_float(d.get_ngc_value())) if d is not None else 0)
    _nr, _or = _comp_nose(polyline_feature, nose_r, orient)
    env = entry_contour([(z, x / DIAMETER_MODE) for z, x in pts],
                        stop_x, rough_dir, _nr, _or, stop_z)
    if len(env) < 2:
        return ''
    top = STOP_BASE + 2 * len(env)
    if top > STOP_TOP:
        return ('(WARNING - the stop contour needs %d parameter slots and only '
                '%d are free, so roughing levels will stop on the floor '
                'allowance as before.)' % (top - STOP_BASE,
                                           STOP_TOP - STOP_BASE))
    lines = ['(where a roughing level may STOP: the pre-finish contour, the)',
             '(surface the pre-finish pass itself traces. Reaching it is what)',
             '(closes the constant gap between every level end and that pass)',
             '#<_pl_stop_base> = %d' % STOP_BASE,
             '#<_pl_stop_n>    = %d' % len(env)]
    for i, (z, x) in enumerate(env):
        lines.append('#%d = %s' % (STOP_BASE + 2 * i, _fmt(z)))
        lines.append('#%d = %s' % (STOP_BASE + 2 * i + 1, _fmt(x)))
    return '\n'.join(lines)


def finish_profile(polyline_feature, back_deg, nose_r=0.0, flank_len=0.0,
                   clearance=0.0, orient=None):
    """(points, soft) - the contour the finishing passes should follow.

    Returns the hard contour and soft=False when nothing constrains it: no back
    angle, the flank switch off, or an envelope that comes out identical.
    """
    corners = []
    points = resolve_points(polyline_feature, corners)
    if not points or len(points) < 2:
        return points, False
    if back_deg is None or back_deg <= 0:
        return points, False

    p = polyline_feature.get_param('param_flank')
    if p is not None and _to_float(p.get_ngc_value()) < 1:
        return points, False

    # THE FRAME, not the raw setting. `param_f_dir` offers "Both directions"
    # too, and 2 used to reach `flank_sides` untranslated and shadow both
    # sides of every peak - the same fault analysis/060 measured on the
    # roughing side. Both directions is an alternating emission of the
    # front-to-back frame, so it dilates like frame 0.
    d = polyline_feature.get_param('param_f_dir')
    fin_dir = rough_frame_dir(
        int(_to_float(d.get_ngc_value())) if d is not None else 0)

    # THE LEADING FLANK, ONLY WHEN ASKED FOR. Off by default, and that is not
    # timidity: honouring it removes about a quarter of the moves - 361 to 275
    # on testing_15_2, 484 to 356 on testing_15_5 - because the path stops
    # trying to make regions the front of the insert cannot enter. That is the
    # correct part, and it is also a different part from the one every saved
    # project has been making, so it cannot arrive without being asked for.
    # The trailing flank has had its own switch since it was built, for the
    # same reason; this is its pair.
    fdeg = None
    fp = polyline_feature.get_param('param_front_flank')
    if fp is not None and _to_float(fp.get_ngc_value()) >= 1:
        fdeg = TOOL_FRONT_ANGLE if TOOL_FRONT_ANGLE > 0 else None

    # flank_len belongs to the tool change, so it arrives as an argument -
    # see build_flank_gcode and FLANK_BOUNDS_CONTOUR
    env = flank_envelope(points, back_deg, fin_dir,
                         _contour_flank(flank_len), clearance, fdeg,
                         orient=orient)
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
    return _min_segment(_clean_ramp(env, points), 2.4 * nose_r, corners), True


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


def _min_segment(pts, limit, protect=()):
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

    `protect` holds points that must survive whatever their spacing - the
    profile's real corners, from resolve_points' `vertices`. Keeping only the
    two ENDPOINTS is not enough, and the difference is not small. A densified
    arc's last chord is whatever the sweep leaves over, so it is routinely
    shorter than the limit; drop that point and the path runs from the last
    chord vertex straight to the NEXT ITEM'S far end, cutting the corner off.
    Measured on testing_13_arcs, three arcs, all three truncated:

        R4   16 x 5.625 deg densified, kept every 3rd, remainder 0.3925 mm
        R6   20 x 4.500 deg densified, kept every 3rd, remainder 0.9423 mm
        R10  25 x 3.600 deg densified, kept every 2nd, remainder 0.6282 mm

    against a limit of 2.4 x 0.4 = 0.960 mm. The R6 misses by 18 um and costs
    0.9386 mm of radius: its 90 degree sweep stopped at 81 degrees and the
    following 19 mm cylinder at r 28.000 was cut as a ramp from r 27.061. That
    is what made In CAM look 0.8875 mm worse than Native on that project when
    Native was the one in the wrong.
    """
    if limit <= 0 or len(pts) < 3:
        return list(pts)
    safe = set(protect)
    keep = [pts[0]]
    for q in pts[1:-1]:
        if q in safe or math.hypot(q[0] - keep[-1][0],
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


def spans_between(hard, soft, tol=0.01):
    """Runs of Z where `soft` stands proud of `hard` by more than `tol`.

    Shared by both flanks. It was inline in `unreachable_spans` until the
    LEADING flank needed the identical walk - the same 400 steps, the same
    units, the same halving of the diameter difference to give a RADIUS gap.
    Two copies of this would have been two things to keep in step, and the
    front and back cases have to be comparable to be reported together.
    """
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


def reentrant_spans(points, tol=0.01):
    """[(z_from, z_to, depth)] where the profile doubles back under itself.

    greatEndian's rule, 2026-08-13: *"Xlevel of segment -1 is less than Xactive
    or Xsegment -2"* - walking in cut order, a region is re-entrant where an
    EARLIER segment's radius lies below the running maximum, i.e. the profile
    has come back up and what lies between is a pocket reachable only from
    outside. A groove, a neck, the far side of a boss.

    This is the same knowledge the behind-the-boss machinery already acts on,
    said as a property of the profile rather than as a scan state. Cross-checked
    against it: on testing_15_5 this reports Z-34.4..-69.6, and that is exactly
    the span whose roughing arrives as disjoint intervals.

    A PROPERTY, NOT A WARNING. Every one of the 15_x and 9_x demo projects has a
    pocket, because that is what those parts are - so reporting "this profile is
    re-entrant" to an operator would fire on nearly every job and teach them to
    ignore it. It is exposed for code that needs to know WHERE the pockets are;
    what an operator needs to be told is whether the tool can REACH, and the two
    flank warnings already say that.
    """
    if not points or len(points) < 3:
        return []
    run_max = points[0][1]
    out, open_at, floor = [], None, None
    for z, x in points[1:]:
        if x < run_max - tol:
            if open_at is None:
                open_at, floor = z, x
            floor = min(floor, x)
        else:
            if open_at is not None:
                out.append((open_at, z, run_max - floor))
                open_at = None
            run_max = max(run_max, x)
    # A DIP THAT NEVER COMES BACK UP IS NOT A POCKET. It is the end of the part
    # getting smaller, cut from outside like anything else. greatEndian's rule
    # needs an ACTIVE segment standing above the earlier one - without the
    # profile rising again there is nothing enclosing it, and nothing for a
    # disjoint interval to be disjoint from. The first version closed the
    # trailing span here and reported a plain step-down as a groove; the
    # falling-profile control caught it.
    return out


def unreachable_spans(polyline_feature, back_deg, tol=0.01, flank_len=0.0,
                      clearance=0.0):
    """[(z_from, z_to, worst_radius_gap)] the TRAILING flank cannot make.

    What the validation message reports, and what the preview colours.
    """
    hard = resolve_points(polyline_feature)
    soft, is_soft = finish_profile(polyline_feature, back_deg, 0.0, flank_len,
                                   clearance)
    if not is_soft:
        return []
    return spans_between(hard, soft, tol)


def front_unreachable_spans(polyline_feature, front_deg, tol=0.01,
                            flank_len=0.0, clearance=0.0):
    """[(z_from, z_to, worst_radius_gap)] the LEADING flank cannot make.

    The mirror of `unreachable_spans`, and reported beside it - greatEndian
    confirmed on 2026-08-13 that the limitation is real and that the reference
    package leaves the same regions, so these numbers describe the part rather
    than a modelling artefact.

    Built from `front_flank_envelope` directly rather than from
    `finish_profile`, because that one applies the BACK angle on the way past
    and would mix the two flanks into one answer. An empty list means the
    leading flank reaches everything, which must be the answer on a profile
    with no steep front-facing wall or the warning would cry wolf on every part.
    """
    # A MISSING ANGLE IS UNKNOWN, NOT ZERO. `get_tool_front_angle` answers 0.0
    # for a tool table with no I column at all, and 0 degrees is not a tool -
    # it is the absence of a measurement. Warning on it would be inventing a
    # limitation out of a blank field, and with a back clearance of 2 the ramp
    # comes out at tan(88), which dilates hugely and reports metres of nothing:
    # measured on testing_3 and testing_4, both 0/0 tools, 1.32 and 1.10 mm of
    # entirely fictional unreachable radius. `finish_profile` already refuses
    # the same way for the trailing flank, and the two must agree.
    if front_deg is None or front_deg <= 0:
        return []
    hard = resolve_points(polyline_feature)
    if not hard or len(hard) < 2:
        return []
    d = polyline_feature.get_param('param_dir')
    # one decomposition frame - see rough_frame_dir
    rough_dir = rough_frame_dir(
        int(_to_float(d.get_ngc_value())) if d is not None else 0)
    env = front_flank_envelope(hard, front_deg, rough_dir, flank_len,
                               clearance)
    return spans_between(hard, env, tol)


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


def build_prefinish_contour_gcode(polyline_feature, back_deg, nose_r=0.0,
                                  flank_len=0.0, clearance=0.0):
    """The pre-finish pass's own contour, offset by the finishing allowance.

    NATIVE COMPENSATION CANNOT CARRY AN ALLOWANCE IN THE D WORD. With a
    non-zero L the interpreter takes D/2 to BE the nose radius and scales the
    orientation term by it as well, so `D = 2*allowance + nose_dia` cancels
    itself on any surface parallel to an axis: measured on testing_15_2, the
    pre-finish pass sat 0.0890 mm from the finish pass instead of 0.508, and in
    places 0.4389 mm INSIDE it - cutting the finished surface. See
    analysis/004.

    So the allowance moves the CONTOUR instead and the D word carries the bare
    nose. This is that contour: a pure geometric offset, nose_r 0 so no
    orientation term, which is what leaves the interpreter free to apply the
    real nose comp on top.

    Emitted into the CAM window. The two are mutually exclusive - _pl_cam_* is
    read only under nose_comp 2 and this only under nose_comp 1 - so they can
    share, and no other table has to move.
    """
    p = polyline_feature.get_param('param_n_comp')
    if p is None or int(_to_float(p.get_ngc_value())) != 1:
        return ''                      # native only; Off and In CAM are right
    allowance, allowance_z = stock_pair(polyline_feature)
    if max(allowance, allowance_z) <= EPS:
        return ''
    pts, _soft = finish_profile(polyline_feature, back_deg, nose_r, flank_len,
                               clearance)
    if not pts or len(pts) < 2:
        return ''
    _nr, orient = 0.0, 0
    tp = polyline_feature.get_param('param_side')
    side = -1 if (tp is not None
                  and int(_to_float(tp.get_ngc_value())) == 1) else 1
    out = offset_contour(pts, 0.0, orient, side, allowance, allowance_z)
    if not out or len(out) < 2:
        return ''
    top = CAM_BASE + 2 * len(out)
    if top > CAM_TOP:
        return ('(WARNING - the pre-finish contour needs %d parameter slots '
                'and only %d are free, so the pre-finish pass will fall back '
                'to the finish contour and leave no stock.)'
                % (top - CAM_BASE, CAM_TOP - CAM_BASE))
    lines = ['(the pre-finish contour: the finishing one offset by the)',
             '(allowance, because native comp cannot hold an allowance in D)',
             '#<_pl_pf_base> = %d' % CAM_BASE,
             '#<_pl_pf_n>    = %d' % len(out)]
    for i, (z, x) in enumerate(out):
        lines.append('#%d = %s' % (CAM_BASE + 2 * i, _fmt(z)))
        lines.append('#%d = %s' % (CAM_BASE + 2 * i + 1,
                                   _fmt(x / DIAMETER_MODE)))
    return '\n'.join(lines)


def build_finish_contour_gcode(polyline_feature, back_deg, nose_r=0.0,
                               flank_len=0.0, clearance=0.0):
    """The soft contour as a point table, or '' when the hard one will do.

    Runtime gate is _pl_fc_n > 0, so '' leaves the contour passes exactly as
    they were.
    """
    pts, is_soft = finish_profile(polyline_feature, back_deg, nose_r, flank_len,
                                  clearance)
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


# ---------------------------------------------------------------------------
# perpendicular X walls: cut from outside, and clean what stopping short left
# ---------------------------------------------------------------------------
# greatEndian, 2026-08-26, on testing_15_8. The old "Outside to inside" branch
# in g123_lathe.ngc ran the pass right into the wall, RAPIDED out over metal
# that was still there, dived back toward centre and led out - the wrong shape,
# and a rapid through material.
#
# The wanted shape, in their words: stop in front of the wall, lead out, lift
# in X to the lead-in level from OUTSIDE the envelope, come back down the wall
# face by the contour rule, and when the pass X level is reached feed along Z
# to take the strip that stopping short left, then lead out and retract.
#
# THE STOP-SHORT IS WHY THIS IS IN PYTHON AT ALL. g123_lathe sees one segment
# at a time, so by the time the wall record arrives the Z move that should have
# stopped short has already been cut. Only generation time can see a wall
# coming, which is the standing Python-first rule reaching the same answer.


def x_wall_indices(points, tol_deg, min_rise=0.0, rising_only=True):
    """Indices i where points[i] -> points[i+1] is a perpendicular X wall.

    PERPENDICULARITY IS AN ANGLE, NOT A LENGTH. The branch this replaces tested
    `ABS[to_z - from_z] LT 0.0005`, which does not scale with the wall: 1 degree
    off perpendicular over a 5 mm rise is 0.087 in Z, seventeen times that
    limit, so a wall a machinist would call perpendicular read as a taper.
    `tol_deg` is measured off the X axis, so 0 is exactly perpendicular and
    greatEndian's 2 degrees admits the quasi-perpendicular ones.

    `rising_only` keeps the original branch's `to_x GT from_x` sense: a wall
    that ASCENDS is the one the tool has to come at from outside.

    `min_rise` IS WHAT SEPARATES A WALL FROM A CORNER, and it is not optional
    on real geometry. An offset path carries short exactly-perpendicular
    connectors where one feature runs into the next: on testing_15_8 the
    cylinder meets the boss arc through a **0.626 mm** vertical step, against
    real walls of 19.24 and 20.52 mm. That step is dead perpendicular - dz is
    0.0000, so no angle tolerance can tell it apart - and treating it as a wall
    put a whole detour in the middle of an arc. greatEndian, 2026-08-27:
    "at boss segment start point of arc it generates infinite long orange stand
    still line".

    The threshold is physical rather than tuned: callers pass the tool's nose
    DIAMETER. A step shorter than that is not a wall the tool could cut from
    outside anyway - the nose rolls through it as a corner blend - so there is
    nothing for the detour to do there.
    """
    if tol_deg is None or tol_deg < 0:
        return []
    out = []
    for i, ((z0, x0), (z1, x1)) in enumerate(zip(points, points[1:])):
        dz, dx = z1 - z0, x1 - x0
        if abs(dx) < EPS:
            continue                      # no X travel: not a wall at all
        if rising_only and dx <= 0:
            continue
        if abs(dx) < min_rise - 1e-9:
            continue                      # a corner blend, not a wall
        if math.degrees(math.atan2(abs(dz), abs(dx))) > tol_deg + 1e-9:
            continue
        out.append(i)
    return out


def x_wall_moves(z_wall, x_base, x_top, approach, front, lead_x):
    """The detour for one perpendicular X wall, as (kind, z, x) in order.

    `approach` is +1 when the pass travels toward increasing Z into the wall
    and -1 the other way, so the stop always lands on the side the tool came
    from. `kind` is 'feed' or 'rapid' and maps straight onto the record `dir`
    field g123_lathe already branches on - 1 feeds, 0 rapids.

    THE CLEAN-UP IS TWICE THE STAND-OFF, and that is greatEndian's correction
    rather than a rounding choice: a move of one stand-off ends exactly on the
    stop point, leaving the two cuts merely touching, and anything the nose
    radius does there leaves a sliver standing. Two carries it a full stand-off
    PAST the stop, so the strip is covered with overlap.
    """
    d = 1 if approach >= 0 else -1
    z_stop = z_wall - d * front
    return [
        # 1. stop short of the wall - the pass's own feed ends here
        ('feed', z_stop, x_base),
        # 2. out in X to the lead-in level. Rapid: this is clear of the work
        ('rapid', z_stop, lead_x),
        # 3. across to the wall, still outside the envelope
        ('rapid', z_wall, lead_x),
        # 4. down the wall face to the corner - cutting, so a feed
        ('feed', z_wall, x_base),
        # 5. and back along Z at the corner radius, twice the stand-off, so it
        #    sweeps through the stop point and a stand-off beyond it
        ('feed', z_wall - d * 2.0 * front, x_base),
    ]


def check_x_wall_moves(moves, z_wall, x_base, x_top, approach, front, lead_x):
    """Every rule the detour has to obey. [] means it holds; else the failures.

    This is the validator greatEndian asked to be built alongside the geometry
    rather than after it. It states the rules the shape has to satisfy so a
    change that breaks one is caught by a number instead of by eye.
    """
    bad = []
    d = 1 if approach >= 0 else -1
    z_stop = z_wall - d * front

    def near(a, b):
        return abs(a - b) < 1e-6

    if len(moves) != 5:
        return ['expected 5 moves, got %d' % len(moves)]
    (k1, z1, x1), (k2, z2, x2), (k3, z3, x3), (k4, z4, x4), (k5, z5, x5) = moves

    if not (near(z1, z_stop) and near(x1, x_base)):
        bad.append('stop is at Z%.4f X%.4f, wanted Z%.4f X%.4f'
                   % (z1, x1, z_stop, x_base))
    if k1 != 'feed':
        bad.append('the stop move is %s, must be a feed - it is still cutting'
                   % k1)
    # the tool must never rapid while inside the material
    if k2 != 'rapid' or k3 != 'rapid':
        bad.append('the lift and traverse are %s/%s, both must be rapids' % (k2, k3))
    if lead_x <= x_top + 1e-9:
        bad.append('lead level X%.4f is not outside the wall top X%.4f'
                   % (lead_x, x_top))
    if not (near(x2, lead_x) and near(x3, lead_x)):
        bad.append('the traverse leaves the lead level: X%.4f then X%.4f'
                   % (x2, x3))
    if not near(z2, z_stop):
        bad.append('the lift moved in Z as well as X, to Z%.4f' % z2)
    if k4 != 'feed':
        bad.append('the descent down the wall face is %s, must be a feed' % k4)
    if not (near(z4, z_wall) and near(x4, x_base)):
        bad.append('the descent ends at Z%.4f X%.4f, wanted the corner Z%.4f X%.4f'
                   % (z4, x4, z_wall, x_base))
    if k5 != 'feed':
        bad.append('the clean-up is %s, must be a feed' % k5)
    if not near(x5, x_base):
        bad.append('the clean-up left the corner radius, at X%.4f' % x5)
    # THE RULE THAT MATTERS: twice the stand-off, and past the stop point
    travel = abs(z5 - z4)
    if not near(travel, 2.0 * front):
        bad.append('the clean-up travels %.4f, wanted twice the %.4f stand-off'
                   % (travel, front))
    if d * (z_stop - z5) <= 0:
        bad.append('the clean-up stops at Z%.4f without passing the stop at '
                   'Z%.4f, so the strip is only touched, not overlapped'
                   % (z5, z_stop))
    return bad


def _stock_x(polyline_feature):
    """The stock envelope in the same units the point tables carry, or None."""
    return x_stock_ref(polyline_feature, 'begin')


def xw_settings(polyline_feature):
    """(mode, stand-off, tolerance) for the perpendicular-X-wall detour.

    mode is param_xw_dir: 0 "With pass" leaves the contour alone, 2 "Outside to
    inside" is the one greatEndian asked to fix and the only one this touches.
    The stand-off is how far SHORT of the wall the pass stops; the overlap is
    how far the clean-up runs PAST that stop. They were one number - the
    clean-up was twice the stand-off - until greatEndian asked for the two to
    be settable separately, 2026-08-28.
    A stand-off of 0 is off, so an existing project that has never seen these
    parameters keeps exactly the contour it has today.
    """
    def _f(name, default=0.0):
        p = polyline_feature.get_param(name)
        return _to_float(p.get_ngc_value()) if p is not None else default
    return (int(_f('param_xw_dir')), _f('param_xw_front'),
            _f('param_xw_back'), _f('param_xw_tol'))


def _back_along(points, i, dist):
    """Walk back along the path from points[i], covering `dist` measured in Z.

    Returns (walked, keep) - the points travelled, points[i] first and the far
    end interpolated onto the segment it falls in; and `keep`, the number of
    ORIGINAL points from the start of the path that are still in front of it.

    THE SURFACE INTO A WALL IS NOT ALWAYS A CYLINDER. greatEndian, 2026-08-27:
    behind a boss the tool meets the artificial back-angle ramp, and elsewhere
    an arc or a taper - *"movement have to be in all axis together"*. Holding X
    at the corner radius and moving in pure Z, which is what this did, is right
    only where the incoming surface is parallel to Z; on a ramp it leaves the
    stop point off the contour and drags the clean-up through the material or
    through air. So both ends of the detour are interpolated ALONG the path.

    Segments with no Z extent are stepped over rather than measured: they make
    no progress toward `dist` and dividing by their length would not end well.
    """
    walked = [points[i]]
    acc, j = 0.0, i
    while j > 0:
        z1, x1 = points[j]
        z0, x0 = points[j - 1]
        seg = abs(z1 - z0)
        if seg <= 1e-12:
            walked.append((z0, x0))
            j -= 1
            continue
        if acc + seg >= dist - 1e-12:
            t = (dist - acc) / seg
            walked.append((z1 + (z0 - z1) * t, x1 + (x0 - x1) * t))
            return walked, j
        acc += seg
        walked.append((z0, x0))
        j -= 1
    return walked, 0


def split_contour_at_walls(points, tol_deg, front, back=None, min_rise=0.0,
                           stock_x=None, nose_r=0.0, rising_only=True):
    """The contour cut into sub-paths at every perpendicular X wall.

    Returns a list of point lists. One entry means no wall was found and the
    contour is unchanged - the caller then emits exactly what it emitted
    before, so a profile without walls cannot move.

    WHY SUB-PATHS AND NOT A PER-POINT RAPID FLAG. greatEndian, 2026-08-27:
    *"there could come any files with any number of points .. therefore the
    should not be limit that low"*. Carrying a feed/rapid flag would have meant
    three slots per point instead of two, and the finish-contour table lives in
    a FIXED 200-slot window - 100 points would have become 66. A cap that low
    on arbitrary input is not acceptable, and any fixed table caps it.

    Splitting costs 2 slots per sub-path in a directory instead, and walls are
    few. The point tables keep stride 2, so no profile gets a smaller ceiling
    than it has today.

    It is also a better fit for what was asked for. The described motion ends
    *"lead out and retract to property selected retraction behaviour"* - that
    IS a pass ending and another starting, so each sub-path runs through the
    existing lead-in, lead-out and retract machinery and no new motion concept
    is needed. The rapids between sub-paths are the existing inter-pass
    retract, which is already outside the material by construction.

    Sub-path B is the wall itself: lead in at the wall TOP from outside, feed
    down the face to the corner, then feed along Z by the stand-off plus the
    overlap - so it sweeps through the stop point and carries on past it. With
    no overlap it would end exactly on the stop, the two cuts would merely
    meet, and the nose radius would leave a sliver standing there.

    There is deliberately no lead level argument. B simply STARTS at the wall
    top, and the pass machinery's own lead-in brings the tool onto that point
    from outside with the configured length and angle - which is what "yes
    existing" meant. A lead level passed in here would be a second opinion
    about geometry the lead code already owns.
    """
    if front <= 0 or tol_deg is None or tol_deg < 0 or len(points) < 2:
        return [list(points)]
    # THE CLEAN-UP IS THE STAND-OFF PLUS THE OVERLAP. It was twice the
    # stand-off, which is the same thing with the two locked together; they are
    # separate numbers now so the overlap can be set for the material rather
    # than inherited from where the pass stopped. `back` None keeps the old
    # coupling, which is what every caller that has not been told about the new
    # parameter still gets.
    over = front if back is None else back
    reach = front + over
    walls = x_wall_indices(points, tol_deg, min_rise, rising_only)
    if not walls:
        return [list(points)]

    out, start = [], 0
    for i in walls:
        (z0, x0), (z1, x1) = points[i], points[i + 1]
        # which way the pass is travelling into the wall, from the segment
        # before it. With no earlier segment there is no approach to stop.
        if i == 0:
            continue
        z_prev = points[i - 1][0]
        if abs(z0 - z_prev) < EPS:
            continue                      # arrived radially: nothing to stop
        # BOTH ENDS FOLLOW THE CONTOUR - see _back_along. The stop is the point
        # `front` back along the surface, carrying whatever X that surface has
        # there, and the clean-up retraces twice that distance the same way, so
        # a ramp, an arc or a taper is cut along rather than across.
        approach, keep = _back_along(points, i, front)
        clean, _k2 = _back_along(points, i, reach)
        if len(approach) < 2 or len(clean) < 2:
            continue
        prefix = list(points[start:keep]) + [approach[-1]]
        if len(prefix) < 2:
            continue
        out.append(prefix)
        # THE FACE STARTS AT THE STOCK ENVELOPE, NOT A NOSE RADIUS INSIDE IT.
        # The stored path is control points, shifted in by the tip
        # compensation, so a wall running out to the bar has its top at
        # envelope - nose: the nose CONTACTS the envelope at exactly one point
        # and the cut only touches it. greatEndian, 2026-08-28: *"from
        # mathematical point of view we reach this point 100%, but in reality
        # everything have some stiffness and rigidity and everything will
        # somehow bend"* - and what is left is a small sharp tip at the
        # outside. Measured on testing_15_8: the top sat at 34.6000 radius
        # against a 35.0000 envelope.
        # The pass END already does this - _ex_tgt adds the nose term to run
        # out to the envelope - and only the start was missing it, which is
        # the asymmetry.
        # Guarded so it cannot lift a wall that stops INSIDE the part: the
        # contact has to be reaching the envelope already before the control
        # point is moved out onto it.
        top = x1
        if (stock_x is not None and x1 < stock_x
                and x1 + 2.0 * nose_r >= stock_x - 1e-6):
            top = stock_x
        out.append([(z0, top)] + clean)
        start = i + 1
    if start < len(points):
        out.append(list(points[start:]))
    return [p for p in out if len(p) >= 2] or [list(points)]
