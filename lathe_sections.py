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

Only resolves "poly-line-to" items. Any other item type in the polyline
(arc-to, arc-ij, polar, ...) makes resolve_points() abort and return None,
so build_sections_gcode() emits nothing - poly_lathe_mill.ngc's own
_pl_sect_count > 0 gate then falls back to plain (Sectioning-off) windowing.
A wrong-but-plausible section list is more dangerous than no section list at
all, since an unmodeled item could reach a radius the analysis never saw.
"""

import math

EPS = 0.0001


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _fmt(val):
    return '%0.6f' % val


def resolve_points(polyline_feature):
    """Ordered list of (z, x) absolute points for each active Line-To
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

    Returns None if any child item isn't a plain Line-To (arc/polar items
    need real curve math this module doesn't attempt) or if a param is
    missing - callers must treat None as "can't safely analyze this
    profile", not as an empty result.
    """
    b_z_param = polyline_feature.get_param('param_b_z')
    b_x_param = polyline_feature.get_param('param_b_x')
    if b_z_param is None or b_x_param is None:
        return None

    prev_z = _to_float(b_z_param.get_ngc_value())
    prev_x = _to_float(b_x_param.get_ngc_value())
    points = []
    merges = []

    for child in getattr(polyline_feature, 'child_features', []):
        if child.get_attr('type') != 'poly-line-to':
            return None

        act_param = child.get_param('param_act')
        if act_param is not None and _to_float(act_param.get_ngc_value()) <= 0:
            continue

        type_param = child.get_param('param_type')
        z_param = child.get_param('param_z')
        x_param = child.get_param('param_x')
        if type_param is None or z_param is None or x_param is None:
            return None

        item_type = int(_to_float(type_param.get_ngc_value()))
        z = _to_float(z_param.get_ngc_value())
        x = _to_float(x_param.get_ngc_value())

        if item_type == 0:
            new_z, new_x = prev_z + z, prev_x + x
        elif item_type == 10:
            new_z, new_x = prev_z + z, x
        elif item_type == 11:
            new_z, new_x = z, prev_x + x
        else:
            new_z, new_x = z, x

        points.append((new_z, new_x))
        prev_z, prev_x = new_z, new_x

        style_param = child.get_param('param_m_style')
        r_param = child.get_param('param_m_r')
        style = int(_to_float(style_param.get_ngc_value())) if style_param is not None else 0
        radius = _to_float(r_param.get_ngc_value()) if r_param is not None else 0.0
        merges.append(radius if style == MERGE_STYLE_RADIUS and radius > 0 else 0.0)

    return apply_merge_radii(points, merges)


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
