# 113 — sweeping every project: three have been failing unnoticed

**Asked**: greatEndian, 2026-09-08 — *"i do not know how to interact with you
now because I do not have time to manually check anything"*.

Fair. Every question I had been asking - which project, which settings, which
tool - was work handed back. This finds it without asking.

## The sweep

`test_project_sweep.py` generates and runs **all 46** lathe projects and reports
only what breaks. No arguments, no input.

```
46 projects: 42 clean, 4 broken (1 expected)
  default_template.xml        the program produced no motion       expected
  testing_13_arc_first.xml    Straight feed in concave corner
  testing_13_arc_first_0.xml  cannot be reached by the tool
  testing_13_arc_first_1.xml  without gouging
```

`default_template` is the blank starting point and legitimately produces
nothing; it is whitelisted **on the message**, not the kind - keying on the kind
whitelisted nothing and the gate called its own expected case a failure.

## The real failure

**Three projects abort at runtime** on LinuxCNC's own cutter-compensation gouge
check, thrown from `g123_lathe.ngc`. The program stops; nothing runs.

All three carry `n_comp = 0` - compensation OFF on the polyline - so the error
comes from another operation in the project, and all three are `arc_first`
variants, so it is tied to a profile that begins with an arc. `CLAUDE.md`
already records that `turning` and `radius_od` "error with a large nose
(concave corner cannot be reached without gouging)", which is the same message
from the same class of check.

**Not caused by this session.** Rolled `lathe_sections.py` and
`lathe_poly_pass.ngc` back to `dad4f7e` - before today's ID work - and both
reproduce identically. Checked because these projects are NOT in the 36-config
gate set and the `offset_contour` fix is not ID-gated, so it could have reached
them.

## Why nothing noticed

Every other gate here runs a hand-picked list: `test_ladder_python` and its
siblings all sweep the same six `testing_15_*` projects, and `prove_cam_comp`
takes one project at a time. A project that aborts outright is invisible until
somebody opens it. These three have been dead for some time.

## What the sweep is not

A program that RUNS is not a program that cuts the right shape. This catches
only total failures - will not generate, aborts, no motion, stops part way.
Correctness still needs the specific gates.
