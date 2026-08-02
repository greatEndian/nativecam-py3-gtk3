#!/usr/bin/env python3
# coding: utf-8
"""Checks the tool-body collision detector.

Standalone, like the other test_*.py here - run it directly, no pytest. Pure
geometry against a simulated stock field, so it needs no rs274.

The failure mode this guards against is the one that looks like success: a
detector that never fires. So every case here comes in a pair - a clean
program that must report nothing, and a deliberately broken one that must
report it - and the broken one is checked for WHERE and HOW DEEP, not just
that something came back.

Two faults are separated on purpose:

  - a RAPID with any part of the tool in metal. On a real machine that is a
    crash, and the nose counts.
  - the tool BODY in metal during a feed. The nose is meant to be in the
    metal - that is the cut - and so is the front edge, where the chip comes
    off. Only the back flank and the tail behind it are a fault. Testing the
    whole outline instead reported 21 collisions on a clean roughing program,
    every one of them the front edge doing its job.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ncam_preview as P  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


# A bar 60 mm long at radius 20, and a tool whose silhouette is small enough
# to reason about: a 6 mm flank on a 60 degree insert.
STOCK = (-60.0, 0.0, 0.0, 20.0)
NOSE, ORIENT, FRONT, BACK, FLANK = 0.4, 2, 15.0, 75.0, 6.0


def path(moves):
    tp = P.Toolpath()
    tp.moves = [P.Move(kind, a, b, 'Turning', 1, None, ()) for kind, a, b in moves]
    return tp


def find(tp, **kw):
    return P.collisions(tp, STOCK, NOSE, ORIENT, FRONT, BACK, FLANK, **kw)


def main():
    # --- 1. clear air is clear ---------------------------------------------
    clear = path([
        ('rapid', (25.0, 0.0, 2.0), (25.0, 0.0, -50.0)),
        ('rapid', (25.0, 0.0, -50.0), (25.0, 0.0, 2.0)),
    ])
    check('a program that never touches the bar reports nothing',
          not find(clear), str(find(clear)[:1]))

    # --- 2. a rapid driven through the bar ---------------------------------
    # THE negative control. Same two moves, 5 mm under the skin.
    crash = path([
        ('rapid', (15.0, 0.0, 2.0), (15.0, 0.0, -50.0)),
    ])
    hits = find(crash)
    check('a rapid driven through the bar is caught', bool(hits),
          'the detector never fires - which is what success looks like')
    if hits:
        h = hits[0]
        check('and it is reported as a rapid, not as a body contact',
              h.kind == P.RAPID_HIT, h.kind)
        check('at the right depth', abs(h.depth - 5.0) < 0.6,
              '%.3f mm, expected about 5' % h.depth)
        check('and inside the bar, not off the end',
              -60.0 < h.pos[0] < 0.0, 'Z%.3f' % h.pos[0])
        check('with a position along the program to mark on the timeline',
              0.0 <= h.at <= 1.0, str(h.at))

    # --- 3. a feed is allowed to cut ---------------------------------------
    # a plain turning pass: rapid clear, plunge to depth, cut along Z, retract
    turn = path([
        ('rapid', (25.0, 0.0, 2.0), (19.0, 0.0, 2.0)),
        ('feed', (19.0, 0.0, 2.0), (19.0, 0.0, -40.0)),
        ('rapid', (19.0, 0.0, -40.0), (25.0, 0.0, -40.0)),
    ])
    check('a cutting pass is not a collision', not find(turn),
          str(find(turn)[:2]))

    # --- 4. the body, where the nose is not ---------------------------------
    # Cut a deep channel, then run the tool back along the bottom of it toward
    # the wall. The nose stays in its own channel the whole way - it is on
    # size, it is cutting nothing it should not - while the tail, which stands
    # off at the back angle, is buried in the full-diameter wall ahead of it.
    # That is the fault the back-angle shadow exists to prevent, and nothing
    # in the program itself says it is happening.
    back_first = path([
        ('rapid', (25.0, 0.0, -40.0), (10.0, 0.0, -40.0)),
        ('feed', (10.0, 0.0, -40.0), (10.0, 0.0, -30.0)),
        ('feed', (10.0, 0.0, -30.0), (10.0, 0.0, -22.0)),
    ])
    hits = find(back_first)
    body = [h for h in hits if h.kind == P.BODY_HIT]
    check('the body dragging through uncut stock is caught', bool(body),
          '%d hit(s), kinds %s' % (len(hits), {h.kind for h in hits}))

    # --- 5. the tested path is the back flank and nothing else -------------
    # Case 3 is the behavioural proof - a cutting pass came back clean, and it
    # did not before. This pins the geometry that makes it so, because the
    # slice is by position in the outline and a change to tool_silhouette's
    # point order would move it silently.
    poly = P.tool_silhouette((25.0, 0.0, -10.0), NOSE, ORIENT, FRONT, BACK,
                             FLANK)
    check('the silhouette is built at all', poly is not None)
    if poly:
        ncz, ncx = P._nose_c(NOSE, ORIENT)
        tail = list(poly[-3:])
        check('the tested path is three points: back tangent, back edge, cap',
              len(tail) == 3)
        # the silhouette was built with the control point at Z-10, r25, so
        # the nose centre is that plus the orientation offset
        cz, cx = -10.0 + ncz, 25.0 + ncx
        check('none of it is inside the cutting nose',
              all(math.hypot(z - cz, x - cx) >= NOSE * 0.999 for z, x in tail),
              'a tested point sits inside the nose circle')
        arc = poly[:-3]
        check('and the whole nose arc is left out of it',
              len(arc) > 3 and all(p not in tail for p in arc),
              '%d arc points, %d tested' % (len(arc), len(tail)))

    # --- 5b. the holder shank ----------------------------------------------
    # The block behind the insert is the thing that actually fouls a shoulder,
    # and it reaches far further than any insert: 160 mm for a 25 mm shank
    # against a 12 mm cutting edge. Tested 40 mm clear of the bar end so
    # NOTHING of the insert can reach the metal - if this fires, it is the
    # block and only the block.
    SHANK = 25.0
    far = path([('rapid', (5.0, 0.0, -100.0), (5.0, 0.0, -95.0))])
    check('the insert alone cannot reach 40 mm past the end of the bar',
          not find(far), str(find(far)[:1]))
    blk = find(far, shank_h=SHANK)
    check('but the holder behind it is driven straight through the bar',
          bool(blk), 'the block is never tested - which looks like success')
    if blk:
        check('and it is inside the bar, not off the end',
              -60.0 < blk[0].pos[0] < 0.0, 'Z%.2f' % blk[0].pos[0])
        check('at a radius the block covers, not the tip radius',
              blk[0].pos[1] > 5.0 + NOSE, 'r%.2f' % blk[0].pos[1])

    check('a clean pass stays clean once the holder is included',
          not find(turn, shank_h=SHANK), str(find(turn, shank_h=SHANK)[:2]))
    check('and so does a program that never touches the bar',
          not find(clear, shank_h=SHANK))
    # Anchoring the block on the TOOL TIP instead of on the insert put its top
    # face at the cutting radius, so it swept the whole part behind the tool:
    # 50 hits on the demo lathe program, which has none, and the same 50 for a
    # 12 mm shank as for a 25 mm one. The insert stands proud of its pocket.
    check('the block does not sit at the cutting radius',
          min(x for _z, x in P.tool_shank((0.0, 0.0, 0.0), NOSE, ORIENT,
                                          FRONT, BACK, SHANK)) > NOSE,
          'its top face is level with the tip, so it sweeps the finished size')

    # --- 6. it refuses rather than guesses ---------------------------------
    check('no tool angles, no report', not P.collisions(crash, STOCK, NOSE,
                                                        ORIENT, None, None,
                                                        FLANK))
    check('no flank length, no report',
          not P.collisions(crash, STOCK, NOSE, ORIENT, FRONT, BACK, 0.0))
    check('no stock, no report',
          not P.collisions(crash, None, NOSE, ORIENT, FRONT, BACK, FLANK))
    check('an empty program reports nothing',
          not find(path([])))

    # --- 7. the noise floor ------------------------------------------------
    # The swept nose is sampled at column centres, so the tool reads as
    # R - sqrt(R^2 - (dz/2)^2) into its own groove. Below that the report is
    # quantisation, and on a real program it was 0.02 mm on every pass.
    deep = find(crash, min_depth=0.0)
    shallow = find(crash, min_depth=100.0)
    check('a floor of 0 reports at least as much as the default', len(deep) >= 1)
    check('and an absurd floor silences everything', not shallow,
          '%d hit(s) survived a 100 mm floor' % len(shallow))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Collisions are caught, and cutting is not called a collision.')


if __name__ == '__main__':
    main()
