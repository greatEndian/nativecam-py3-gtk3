#!/usr/bin/env python3
# coding: utf-8
"""Checks the icon accent recolouring in ncam.py.

Standalone, like the other test_*.py here - run it directly, no pytest.

The thing worth protecting is that recolouring moves ONLY the accent and
leaves every other colour in an icon untouched, because the icon set carries
reds, yellows and blues that must survive a user's colour choice.
"""
import sys
import os
import colorsys

sys.argv = ['ncam.py', '-c', 'lathe']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ncam  # noqa: E402
from gi.repository import GdkPixbuf  # noqa: E402

GRAPHICS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'graphics')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def pixels(pb):
    """Yield (r, g, b, a) for every pixel, honouring rowstride."""
    n, st, d = pb.get_n_channels(), pb.get_rowstride(), pb.get_pixels()
    for y in range(pb.get_height()):
        for x in range(pb.get_width()):
            i = y * st + x * n
            yield d[i], d[i + 1], d[i + 2], (d[i + 3] if n > 3 else 255)


def hue_buckets(pb):
    out = {}
    for r, g, b, a in pixels(pb):
        if a < 20:
            continue
        mx, mn = max(r, g, b), min(r, g, b)
        if mx == 0 or (mx - mn) / mx < 0.12:
            continue
        h = int(colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)[0] * 360)
        out[h // 10 * 10] = out.get(h // 10 * 10, 0) + 1
    return out


def load(name, size=48):
    return GdkPixbuf.Pixbuf.new_from_file_at_size(
        os.path.join(GRAPHICS, name), size, size)


def main():
    accent = load('items.png')          # accent only
    mixed = load('lathe-tool.png')      # accent plus other colours

    # 1 - every accent pixel lands on the requested hue
    for target in ((220, 60, 60), (60, 90, 230), (255, 170, 0)):
        out = ncam.recolour_pixbuf(accent, target)
        th = colorsys.rgb_to_hsv(*[c / 255.0 for c in target])[0] * 360
        got = hue_buckets(out)
        ok = bool(got) and all(abs(((h - th + 180) % 360) - 180) <= 15 for h in got)
        check('every accent pixel lands on the target hue for rgb%s' % (target,),
              ok, 'buckets=%s target=%.0f' % (sorted(got), th))

    # an achromatic target has no hue to land on - the accent must go grey
    # instead, not stay coloured. Picking white or black is a legitimate choice
    # and must not leave the old accent showing through.
    for target in ((255, 255, 255), (30, 30, 30)):
        out = ncam.recolour_pixbuf(accent, target)
        check('an achromatic target rgb%s desaturates the accent' % (target,),
              hue_buckets(out) == {}, 'leftover hues=%s' % sorted(hue_buckets(out)))

    # 1b - the base accent colour itself maps exactly onto the target
    from gi.repository import GdkPixbuf as _P
    probe = _P.Pixbuf.new(_P.Colorspace.RGB, True, 8, 2, 2)
    probe.fill((ncam.ICON_BASE_RGB[0] << 24) | (ncam.ICON_BASE_RGB[1] << 16) |
               (ncam.ICON_BASE_RGB[2] << 8) | 0xFF)
    for target in ((220, 60, 60), (60, 90, 230), (255, 170, 0)):
        got = list(pixels(ncam.recolour_pixbuf(probe, target)))[0][:3]
        check('base accent maps exactly to rgb%s' % (target,),
              all(abs(a - b) <= 1 for a, b in zip(got, target)), 'got rgb%s' % (got,))

    # 2 - nothing outside the accent hue window is altered
    before = list(pixels(mixed))
    after = list(pixels(ncam.recolour_pixbuf(mixed, (220, 60, 60))))
    moved = kept = 0
    for (r0, g0, b0, a0), (r1, g1, b1, a1) in zip(before, after):
        mx, mn = max(r0, g0, b0), min(r0, g0, b0)
        is_accent = (a0 >= 20 and mx > 0 and (mx - mn) / mx >= 0.12 and
                     ncam.ICON_HUE_LO <= colorsys.rgb_to_hsv(
                         r0 / 255.0, g0 / 255.0, b0 / 255.0)[0] <= ncam.ICON_HUE_HI)
        if is_accent:
            moved += 1
        else:
            kept += ((r0, g0, b0, a0) == (r1, g1, b1, a1))
    non_accent = len(before) - moved
    check('non-accent pixels are byte-identical', kept == non_accent,
          '%d of %d unchanged, %d accent pixels moved' % (kept, non_accent, moved))

    # 3 - geometry and alpha survive
    out = ncam.recolour_pixbuf(mixed, (10, 10, 200))
    check('size, channels and alpha preserved',
          (out.get_width(), out.get_height(), out.get_n_channels(),
           out.get_has_alpha()) ==
          (mixed.get_width(), mixed.get_height(), mixed.get_n_channels(),
           mixed.get_has_alpha()))
    check('alpha channel untouched',
          [p[3] for p in pixels(out)] == [p[3] for p in pixels(mixed)])

    # 4 - set_icon_accent: base colour means "as drawn", and the cache is dropped
    ncam.PIXBUF_DICT['sentinel'] = object()
    ncam.set_icon_accent(ncam.ICON_BASE_RGB)
    check('choosing the base colour disables recolouring',
          ncam.ICON_ACCENT_RGB is None)
    check('changing the accent clears the pixbuf cache',
          'sentinel' not in ncam.PIXBUF_DICT)
    ncam.set_icon_accent((200, 30, 30))
    check('a different colour is stored', ncam.ICON_ACCENT_RGB == (200, 30, 30))
    ncam.set_icon_accent(None)
    check('None restores as-drawn', ncam.ICON_ACCENT_RGB is None)

    # 5 - recolouring is never cumulative: same input always gives same output
    a = list(pixels(ncam.recolour_pixbuf(accent, (200, 30, 30))))
    b = list(pixels(ncam.recolour_pixbuf(accent, (200, 30, 30))))
    check('recolour is deterministic and non-cumulative', a == b)

    # 6 - the preference round-trip, including malformed input
    for text, want in (('', None), (None, None), ('68,230,68', (68, 230, 68)),
                       ('200,30,30', (200, 30, 30)), (' 10 , 20 , 30 ', (10, 20, 30)),
                       ('bad', None), ('1,2', None), ('1,2,3,4', None),
                       ('-1,0,0', None), ('0,0,256', None)):
        check('preference %-16r parses to %s' % (text, want),
              ncam.accent_from_pref(text) == want,
              'got %s' % (ncam.accent_from_pref(text),))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All icon colour tests passed.')


if __name__ == '__main__':
    main()
