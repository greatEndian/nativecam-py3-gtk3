"""The Z limits are only HALF validated - the two cases that fall through.

openPoints.md: "The crossed case is refused. NOT checked: a limit that falls
outside the profile entirely (it silently does nothing), and limits that leave
too little to machine. Both need the resolved profile, which the [VALIDATION]
block cannot have - they belong in the [AFTER] block or in Python at
generation time." (WORKPIECE_FACE_Z/OD/ID and the tool's rough_cut/nose_r are
module-level state on lathe_sections and ncam.TOOL_TABLE, filled in as
to_gcode() walks the tree in document order - see ncam_project_io.py's
recursive() - so a project whose Workpiece or Tool Change precedes the
polyline only has real numbers to check by generation time, not at
[VALIDATION].)

A separate module rather than growing lathe_sections.py, on greatEndian's own
instruction: lathe_sections.py has exactly one writer at a time (SONNET-LANES
rule 4), and nearly every geometry task needs to touch it. This one does not -
it only READS the profile lathe_sections.py already resolves.

Standalone like lathe_sections.py itself: no GTK, no import of ncam, so it is
unit-testable with plain python3. Called from cfg/lathe/polyline.cfg's [AFTER]
via <exec>print(...)</exec>, same convention as every build_*_gcode function in
lathe_sections.py.

Keep every returned message free of parentheses, same rule as
lathe_sections.profile_problem: callers put it straight into a G-code comment,
and LinuxCNC treats a nested paren as an unclosed one.
"""
import lathe_sections as LS

EPS = 0.0001


def _typed(polyline_feature, which):
    """The raw value the operator typed for a Z limit, or None if off."""
    sw = polyline_feature.get_param(
        'param_fr_z_on' if which == 'front' else 'param_e_z_on')
    val = polyline_feature.get_param(
        'param_fr_z' if which == 'front' else 'param_e_z')
    if sw is None or val is None or LS._to_float(sw.get_ngc_value()) <= 0:
        return None
    return LS._to_float(val.get_ngc_value())


def _label(which):
    return 'Front Z' if which == 'front' else 'End Z'


def outside_profile_problems(polyline_feature):
    """Plain-language reasons a Z limit sits outside the profile it should
    trim, in the order resolve_points() itself applies the trims - front
    first, then end - so a limit only pushed outside by the OTHER one's own
    trim is caught too, not only the simple case against the raw profile.

    trim_to_front_z/trim_to_end_z are each active only when the limit falls
    STRICTLY inside the current profile - "at or beyond either end it does
    nothing", by their own docstrings - which is exactly the silent gap this
    checks for.
    """
    pts = LS.resolve_points(polyline_feature, trim=False)
    if pts is None or len(pts) < 2:
        return []
    out = []
    cur = pts
    for which, resolver, trimmer in (
            ('front', 'front', LS.trim_to_front_z),
            ('end', 'end', LS.trim_to_end_z)):
        lim = LS.z_limit_abs(polyline_feature, resolver)
        if lim is None:
            continue
        zs = [z for z, _x in cur]
        lo, hi = min(zs), max(zs)
        if lo < lim < hi:
            cur = trimmer(cur, lim)
            continue
        typed = _typed(polyline_feature, which)
        note = ''
        if typed is not None and abs(typed - lim) > EPS:
            note = ', resolved from its datum to Z%.3f,' % lim
        out.append(
            'the %s limit you typed, %.3f,%s is outside the profile here - '
            'it runs from Z%.3f to Z%.3f. The limit does nothing. Move it '
            'inside that range, or turn it off'
            % (_label(which), typed if typed is not None else lim, note,
               lo, hi))
    return out


def min_machinable_span(rough_cut, nose_r):
    """The least Z span worth machining between two active limits.

    Two geometric quantities, not a picked number:

    - the tool nose is round, radius nose_r, and CLAUDE.md's own comp-entry
      rule is "a straight feed of at least the nose radius, in free air" to
      establish contact without gouging. A Z-limited span is walled at BOTH
      ends, not the one a single comp-entry move assumes, so it needs that
      clearance TWICE - once to enter clear of the near wall, once to leave
      clear of the far one: 2 * nose_r.
    - one roughing depth of cut (TOOL_TABLE.get_rough_cut()), because a span
      that cannot take even a single roughing level is not "thin roughing" -
      PARAM_SKIP_THIN and PARAM_MIN_PASS already have a threshold for that -
      it is a span roughing cannot enter at all.

    Either being unknown (0.0 - no tool change yet, or a nose radius neither
    the tool table nor the override supplies) drops its own term to 0 rather
    than refusing the whole check, so a project with no tool data yet is not
    flagged for a tool it has not chosen.
    """
    return 2.0 * max(nose_r, 0.0) + max(rough_cut, 0.0)


def too_little_problem(polyline_feature, rough_cut=0.0, nose_r=0.0):
    """Plain-language reason the Z-limited span is too short to machine, or
    None.

    Only fires when at least one limit actually trimmed the profile -
    outside_profile_problems above already covers a limit that trims
    nothing, and a project with no Z limit at all is not this check's
    business at all.
    """
    pts = LS.resolve_points(polyline_feature, trim=False)
    if pts is None or len(pts) < 2:
        return None
    fz = LS.z_limit_abs(polyline_feature, 'front')
    ez = LS.z_limit_abs(polyline_feature, 'end')
    if fz is None and ez is None:
        return None

    cur = pts
    trimmed_by = []
    for which, lim, trimmer in (('front', fz, LS.trim_to_front_z),
                                 ('end', ez, LS.trim_to_end_z)):
        if lim is None:
            continue
        zs = [z for z, _x in cur]
        if min(zs) < lim < max(zs):
            cur = trimmer(cur, lim)
            trimmed_by.append(which)
    if not trimmed_by:
        return None

    zs = [z for z, _x in cur]
    lo, hi = min(zs), max(zs)
    span = hi - lo
    need = min_machinable_span(rough_cut, nose_r)
    if need <= EPS or span >= need - EPS:
        return None

    which_txt = ' and '.join(_label(w) for w in trimmed_by)
    return (
        'the Z limits leave only %.3f to machine here, from Z%.3f to '
        'Z%.3f - trimmed by %s. That is less than %.3f, twice this tool '
        'nose radius %.3f plus one roughing depth of cut %.3f. Loosen a '
        'limit, use a smaller nose radius, or a lighter depth of cut'
        % (span, lo, hi, which_txt, need, nose_r, rough_cut))


def z_limit_problems(polyline_feature, rough_cut=0.0, nose_r=0.0):
    """Every Z-limit problem this module knows to check, as plain-language
    strings - possibly empty."""
    msgs = outside_profile_problems(polyline_feature)
    tlp = too_little_problem(polyline_feature, rough_cut, nose_r)
    if tlp:
        msgs.append(tlp)
    return msgs


def build_z_limit_span_gcode(polyline_feature, rough_cut=0.0, nose_r=0.0):
    """G-code WARNING comments for every problem found, '' when none.

    Called from polyline.cfg's [AFTER] via <exec>print(...)</exec>. This is
    validation, not geometry - it reports, and never changes a coordinate any
    builder or the toolpath reads.
    """
    msgs = z_limit_problems(polyline_feature, rough_cut, nose_r)
    return '\n'.join('(WARNING - Lathe Polyline Z limits: %s)' % m
                      for m in msgs)
