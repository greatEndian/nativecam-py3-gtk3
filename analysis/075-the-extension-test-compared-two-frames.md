# 075 — `test_extension` was comparing two frames, not finding a gap

**Asked**: greatEndian, 2026-09-03 — *"chase the extension first, then 1"*,
after the program-completion guard surfaced this failure.

## The failure

```
roughing front Z2.4284 against the contour passes' Z2.8284
```

A 0.4000 mm gap, asserted against a 0.01 tolerance.

## It is the test, not the toolpath

**0.4000 is exactly `_pl_rgh_oz`**, the orientation term roughing carries, and
the arithmetic closes to four decimals:

```
2.4284 + 0.4000 = 2.8284
```

A level's start is `w_from - _pl_rgh_oz`, so the level's **nose** begins where
the surface does rather than its control point. The contour passes carry no
such shift at this end. Comparing the two raw measures a control point against
a contact point and finds a gap of exactly the nose term — which is not metal.

This project has made the same mistake before, and its own analysis notes say
so: *"Nine phantom 0.40 'uncut' gaps — compared control points against a
contact-frame floor table. Contact = control + oz."*

The assertion now adds the term before comparing and says why.

## Attribution — what it took to be sure

Ruled out by measurement, not by argument:

- **The completion guard added the same day** — identical failure with it
  stashed.
- **All of this week's contour work.** A `git worktree` at `9ca60c1`, with its
  `ncam/cfg`, `ncam/lib` and `ncam/graphics` symlinks REPOINTED at the
  worktree, gives `roughing 2.4284, contour 2.8284, gap 0.4000, 34 levels` —
  identical to HEAD. So neither the x-limit resolver, the insert-orientation
  flank work, the Z-limit clamp nor the holder model touched it.

**Two instruments failed before one worked**, and both failures were the same
shape:

1. `git checkout <old> -- lathe_sections.py ncam.py cfg/...` against the
   current tree reported "the project generates with no extension". The saved
   projects had migrated to cfg 1.71 and the old cfg could not serve them. A
   file checkout is not a baseline.
2. A worktree at `f7356af` — the commit that FIXED the extension — dies with
   `Named parameter #<_pl_hf_x> not defined`. The projects are gitignored, so
   they are always CURRENT, and a program written by a newer NativeCAM cannot
   run under older `lib/`. **Bisecting past a project's stored version is not
   possible with these projects**, which is worth knowing before the next
   attempt.

So the honest bound is: it predates `9ca60c1` and cannot be dated more precisely
from here. It did not need to be — the arithmetic identifies it outright.

## And the fix itself read the wrong number first

`re.search` for `#<_pl_rgh_oz>` returns **0.0000**: `create_defaults` emits that
global near the top of every program and the real value later. The corrected
comparison therefore still failed, in two frames, silently. `re.findall(...)[-1]`
is the convention everywhere else in this project and it is the convention here
now.

Had the emitted value happened to be 0, the test would have PASSED for the
wrong reason.

## Gates

`test_extension` passes. The program-completion guard from `8d15e86` is
unaffected either way.

## Still unknown

- Whether roughing's front should carry the nose term AT ALL at an extension.
  It is right that the nose starts where the surface does; whether an extension
  is a "surface" in the same sense is a question about intent, not about
  frames, and nothing here answers it.
