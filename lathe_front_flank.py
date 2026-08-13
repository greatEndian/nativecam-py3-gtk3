#!/usr/bin/env python3
# coding: utf-8
"""What the tool's LEADING flank cannot reach - the mirror of the back angle.

Gap 1 of `POLYLINE-GAPS.md`, the WARNING half. Nothing here moves a toolpath:
it reports, in the same shape `lathe_sections.unreachable_spans` reports the
back-angle case, so the two can be surfaced identically.

THE PHYSICS. An insert's TRAILING flank limits surfaces that RISE as the tool
travels - drive past a boss and the sections behind it are the ones the back of
the insert can no longer get into. That is modelled already: `flank_slope`,
`flank_envelope`, `finish_profile`, `unreachable_spans`, and the validation
warning that names the span in millimetres.

The LEADING flank has its own clearance and limits the opposite thing: surfaces
that FALL AWAY in front of the tool - a steep face, the near wall of a groove,
an undercut on the approach side. Same wedge, other end of the nose, other side
of every peak.

WHY THERE IS ALMOST NO NEW MATHS HERE, deliberately. The dilation is the same
dilation; only the angle and the shadowed side differ. `flank_sides` already
turns the roughing direction into a side - (1,) front-to-back, (-1,) back-to-
front, both for either - so the front flank is the SAME `flank_envelope` call
with the direction mirrored and the front angle in place of the back one.
Re-deriving the wedge would have meant a second, untested copy of geometry that
took this project five stacked faults to get right (analysis/032).

THE ANGLE CONVENTION, and the one thing here that is an assumption. The tool
table's I and J are absolute edge directions, not clearances: the sim tools
carry `T2 I15 J75` and `flank_slope(75)` is tan(15 degrees), which is what
`flank_slope`'s own docstring says a J75 insert ramps at. So the front edge is
read the same way, `90 - I - clearance`. If that reading is wrong the numbers
this reports are wrong with it - which is why `front_spans_both_ways` also
reports the alternative reading, and why nothing is wired to a toolpath until
greatEndian has seen real numbers from a real part.

NOT IN lathe_sections.py, ON PURPOSE. It belongs beside the back-angle
functions it mirrors and should be folded in eventually - but not yet, and the
reason is not tidiness. The numbers it produces are NOT VALIDATED against a real
insert: on the demo projects it reports spans as large as 14.42 mm of radius on
parts that are known to machine correctly, which is either a real limitation
nobody has been warned about or an over-report from the angle convention or the
side mirror. Those cannot be told apart from code. Until one case is checked
against a tool in a hand, this stays outside the file every builder imports, so
it cannot be reached by accident and wired to a toolpath. analysis/040 has the
survey and the discriminating check.
"""
import lathe_sections as L


def mirror_dir(rough_dir):
    """The roughing direction that shadows the OTHER side of every peak.

    `flank_sides` maps 0 -> (1,), 1 -> (-1,), 2 -> (1, -1). The leading flank
    is shadowed by whatever the trailing flank is not, so swapping 0 and 1
    flips the side while 2 - which already takes both - stays as it is.
    """
    if rough_dir == 0:
        return 1
    if rough_dir == 1:
        return 0
    return 2


def _rough_dir(polyline_feature):
    p = polyline_feature.get_param('param_dir')
    return int(L._to_float(p.get_ngc_value())) if p is not None else 0


def front_envelope(points, front_deg, rough_dir=0, flank_len=0.0,
                   clearance=0.0):
    """The profile widened into what the LEADING flank can reach."""
    return L.flank_envelope(points, front_deg, mirror_dir(rough_dir),
                            flank_len, clearance)


def front_unreachable_spans(polyline_feature, front_deg, tol=0.01,
                            flank_len=0.0, clearance=0.0):
    """[(z_from, z_to, worst_radius_gap)] the LEADING flank cannot make.

    The same comparison `unreachable_spans` makes for the trailing flank: walk
    Z, take the profile and the envelope at each step, and collect the runs
    where the envelope stands proud of the drawn shape by more than `tol`.

    An empty list means the leading flank reaches everything - which is the
    answer on a profile with no steep front-facing wall, and must be, or the
    warning would cry wolf on every part.
    """
    hard = L.resolve_points(polyline_feature)
    if not hard or len(hard) < 2:
        return []
    env = front_envelope(hard, front_deg, _rough_dir(polyline_feature),
                         flank_len, clearance)
    return spans_between(hard, env, tol)


def spans_between(hard, env, tol=0.01):
    """Runs of Z where `env` stands proud of `hard` by more than `tol`.

    Lifted from `unreachable_spans` rather than called into it, because that
    one builds its soft contour from the BACK angle inside itself. Same walk,
    same 400 steps, same units - the gap is a RADIUS, so the diameter-unit
    difference is halved exactly as it is there.
    """
    zs = sorted({z for z, _x in hard} | {z for z, _x in env})
    if len(zs) < 2:
        return []
    spans, cur = [], None
    step = max((zs[-1] - zs[0]) / 400.0, 1e-6)
    z = zs[0]
    while z <= zs[-1] + 1e-9:
        h = L._profile_x_at(z, hard)
        s = L._profile_x_at(z, env)
        gap = 0.0 if (h is None or s is None) else (s - h) / L.DIAMETER_MODE
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


def front_spans_both_ways(polyline_feature, front_deg, tol=0.01,
                          flank_len=0.0, clearance=0.0):
    """(mirror_reading, complement_reading) - the assumption, and its opposite.

    The angle convention is the one judgement call in this file. Under the
    reading taken here the ramp is `90 - I`; under the other it is `I` itself.
    Reporting both means a decision about the toolpath is never taken on the
    strength of a convention nobody has checked against a real insert.
    """
    a = front_unreachable_spans(polyline_feature, front_deg, tol, flank_len,
                                clearance)
    b = front_unreachable_spans(polyline_feature, 90.0 - front_deg, tol,
                                flank_len, clearance)
    return a, b
