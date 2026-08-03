#!/usr/bin/env python3
# coding: utf-8
"""Lathe tool nose radius compensation geometry, in one place.

GTK-free and importing nothing from `ncam`, the same shape as
lathe_sections.py and for the same reason: it can be unit-tested with plain
`python3`, and there is no circular import to work around.

Everything here was previously written out more than once - the orientation
table in four places, the comp side rule in five - and the copies had already
begun to disagree. See `/tnrc` for the theory the numbers come from.

The one rule the whole module is about:

    control point = surface point + r * normal - R * orientation_vector

with `r` the nose radius plus whatever allowance is being held and `R` the bare
nose radius. On a wall parallel to Z with an orientation-2 tool those two terms
cancel in X, so the compensated point sits ON the surface with no radial shift.
Expecting "+R everywhere" is what put lathe_poly_pass's entry 0.4 mm out and
tapered the first cut of every finish pass.
"""
import math

# Where the nose sits relative to the programmed control point, as (X, Z)
# multiples of the nose radius. LinuxCNC's own table, from rs274/glcanon.py
# StatCanon.lathe_shapes.
#
# THIS IS A RAW VECTOR, NOT A UNIT ONE. Entries 1-4 are diagonal and have
# magnitude R*sqrt(2); normalising them to R * unit mis-measures the offset for
# every corner tool, which is most of them.
NOSE_OFFSET = [None,
               (1, -1), (1, 1), (-1, 1), (-1, -1),
               (0, -1), (1, 0), (0, 1), (-1, 0),
               (0, 0)]

# The same table in (Z, x) order, for the modules that plot rather than
# compute. Derived rather than written out again.
NOSE_DIR = [None] + [(z, x) for x, z in NOSE_OFFSET[1:]]

# G-code words. 41 = compensation left of travel, material on the right;
# 42 = right of travel, material on the left.
LEFT = 41
RIGHT = 42

EPS = 1e-9


def nose_offset(orient):
    """(X, Z) raw offset multiples for an orientation, or (0, 0)."""
    o = int(orient or 0)
    if 0 < o < len(NOSE_OFFSET):
        return NOSE_OFFSET[o]
    return (0, 0)


def offset_vector(side, dz, dx, nose_r, orient, extra=0.0):
    """(off_z, off_x) to ADD to a programmed point, in RADIUS units.

    `side` is 41 or 42, `dz`/`dx` the direction of travel along the surface
    (dx in radius units), `nose_r` the tool nose radius, `orient` 0-9, `extra`
    any additional allowance being held on top of the nose.

    Returns (0.0, 0.0) when there is nothing to compensate - a zero-length
    direction, no radius - so a caller can apply it unconditionally and get its
    original path back.

    The normal is scaled by `nose_r + extra` and the orientation term by the
    BARE `nose_r`. That asymmetry is deliberate and it is the LinuxCNC rule:
    the allowance moves the surface, the nose geometry does not change with it.
    lib/lathe/tip_comp_vec.ngc has always done this; offset_contour scaled both
    by nose_r + extra, which agrees only while extra is 0 - as it was at every
    call site, which is why the two never visibly disagreed.

    The side convention was measured against rs274, not derived:
    G42 -> normal is (u_x, -u_z), G41 -> (-u_x, u_z).
    """
    n = math.hypot(dz, dx)
    if n < 1e-6:
        return (0.0, 0.0)
    r = float(nose_r) + float(extra)
    if r < 1e-6:
        return (0.0, 0.0)
    uz, ux = dz / n, dx / n
    if int(side) == RIGHT:
        nz, nx = ux, -uz
    else:
        nz, nx = -ux, uz
    ox, oz = nose_offset(orient)
    return (r * nz - nose_r * oz, r * nx - nose_r * ox)


def lead_width(nose_dia, diameter_mode=2.0):
    """The minimum radial clearance a compensation entry or exit needs.

    A start-up move must be a straight feed longer than the nose RADIUS. This
    is the nose DIAMETER as an X word - deliberately twice the interpreter's
    minimum, because the margin costs one rapid and the failure costs a part.
    """
    return max(float(nose_dia), 0.0) * float(diameter_mode)


# --------------------------------------------------------------------------
# which side each operation compensates to
#
# Five near-identical copies of this lived in taper.ngc, taper_id.ngc,
# boring.ngc, facing.ngc and lathe_poly_pass.ngc, and the OD and ID rules are
# INVERTED, so copying one to another op is a real and easy mistake.
#
# A row is (default side, name of the flip test). `turning` and `radius_od`
# are deliberately absent: they still carry their own pre-existing G41/G42,
# proven geometrically rather than rewritten. Adding them is a row here plus a
# Tool nose comp parameter on their .cfg - not a refactor. That is the whole
# point of the table.
OPS = {
    'taper':     {'side': RIGHT, 'flip': 'begin_z_lt_end_z', 'id': False},
    'taper_id':  {'side': LEFT,  'flip': 'begin_z_lt_end_z', 'id': True},
    'boring':    {'side': LEFT,  'flip': 'begin_z_lt_end_z', 'id': True},
    'facing':    {'side': RIGHT, 'flip': 'z_factor_gt_0',    'id': False},
    'polyline':  {'side': LEFT,  'flip': 'z_dir_gt_0',       'id': None},
}


def comp_side(op, flip=False, bore=False):
    """41 or 42 for an operation, or None when the op does not compensate.

    `flip` is the op's own condition already evaluated by the caller - the
    conditions differ per op and are named in OPS so the caller can see which
    one it is answering. `bore` inverts the result for an operation whose side
    depends on which way the material lies (the polyline, which does both).
    """
    row = OPS.get(op)
    if row is None:
        return None
    side = row['side']
    if flip:
        side = LEFT if side == RIGHT else RIGHT
    if bore and row['id'] is None:
        # material is outside the profile on a bore, so the offset goes the
        # other way - the inversion boring.ngc makes against taper.ngc
        side = 83 - side
    return side


def free_side(side):
    """Which side of the profile the tool body is on, for a tangency proof.

    A single profile line is tangent from BOTH sides, so a proof that does not
    say which side is free passes a wrong answer. 41 puts the material on the
    right of travel, so the tool is on the left.
    """
    return 'left' if int(side) == LEFT else 'right'


def orient_terms_gcode(nose_r, orient, prefix='_pl_nose'):
    """Literal G-code for the ORIENTATION TERM of the offset, as globals.

    The one part of the offset that needs the nine-way table. Emitting it as
    two numbers at generation time is what lets a subroutine place a
    compensated entry point without a hand-transcribed copy of the table
    inside it - the copy that was already a fourth transcription, and the kind
    a Python test can never see.

    The NORMAL is deliberately left to the caller: it turns on the direction of
    the first segment of whichever record array a pass was handed, which is a
    runtime fact. Rotating a unit vector is arithmetic; knowing where the nose
    sits for orientation 6 is a table, and only the table belongs here.
    """
    ox, oz = nose_offset(orient)
    r = max(float(nose_r or 0.0), 0.0)
    return ('#<%s_r>  = %.8f (nose radius)\n'
            '#<%s_oz> = %.8f (orientation term, Z)\n'
            '#<%s_ox> = %.8f (orientation term, radius)'
            % (prefix, r, prefix, r * oz, prefix, r * ox))
