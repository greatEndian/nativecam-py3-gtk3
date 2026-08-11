# 029 — The behind-the-boss pass, lost to two scans reading two sources

2026-08-10, branch `liveTooling`, from `1f7a97b`. greatEndian: *"one issue came
back that are missing first pass behind the boss segment … it has section on or
off there is no change"*, `testing_15_5`.

## Measured

Roughing level cuts lying entirely behind the boss (Z < −33.5):

```
                              topmost such level    count
HEAD, sectioning OFF              32.1920            14
HEAD, sectioning ON               32.1522            14
```

Same both ways, as reported. The level ladder steps 0.508, so between the last
full-length pass at 33.7160 and the first behind-boss pass at 32.1920 there is a
**1.524 mm bite** — three times the depth of cut. Levels **33.2080** and
**32.7000** have a front interval and no behind-boss one.

The geometry says both should exist. From the emitted floor contour (119
points), the boss peaks at **X33.4207**, and behind it the floor drops back
below 33.2080 at Z ≈ −35.24 and below 32.7000 at Z ≈ −37.4, staying below all
the way to the end wall.

## Root cause — found by bisection, not by reading

Disabling `build_floor_contour_gcode` and regenerating:

```
floor contour ON  (HEAD)     topmost behind-boss 32.1920    14 passes
floor contour OFF            topmost behind-boss 33.2080    16 passes
```

So `6fefc09` — *the roughing floor becomes a contour Python builds* — is the
cause. It moved **`lathe_level_pass`'s stop scan** onto the Python floor contour
and left **`lathe_level_next_start`'s resume scan** walking the record array
offset perpendicular by a scalar. `lathe_level_next_start.ngc` contains no
reference to `_pl_flc_*` at all.

Two scans, two sources. They disagree about where an obstruction is **by
construction**, whatever either one says on its own: the stop scan blocks the
level against a boss whose floor peaks at 33.4207, and the resume scan then
looks for the re-entry on a differently-shaped curve and does not find it. The
level is never resumed, and its behind-boss interval is simply lost.

This is the exact class `cam_map` exists for — a table moved in Python, a
consumer left behind — and `cam_map` does **not** catch it: its checks cover
window literals, globals, order names and subroutine definitions, not *which
scan walks which profile*. Noted as a gap in the checker.

## The fix that works, and the one that does not

Giving `lathe_level_next_start` the same floor-contour branch restores every
missing pass:

```
with the branch, sectioning OFF   topmost 33.2080   26 behind-boss passes
                 sectioning ON    topmost 33.1273   26
```

33.2080 resumes at Z−34.2507 and 32.7000 at Z−36.4467, and the resume points
follow the real contour instead of marching back in a straight 2.2 mm per level
line, which is what the scalar offset produced.

**It also breaks `test_rough_ends`, and that is why it is not committed.** Six
failures, all the same shape:

```
Off     the retreat leaves 0.4700 mm standing in a rapid's way:
        Z-42.8230 r31.8160 -> Z-42.8230 r22.2311
Native  0.4482 mm   Z-43.9951 r31.8160 -> Z-43.9951 r22.2311
```

A **rapid plunging through standing metal**. Following the true contour, the
resume points are no longer monotonic — level 31.1760 resumed at Z−40.7954
while 31.6840 directly above it resumed at Z−40.8518, so the plunge went down
where the level above had not yet cut.

A monotonic clamp was written — hold a candidate back to the level above's
start, which is safe at both ends since the material above is gone there and the
floor is already below this level — and it **did not change the failing
numbers at all**, byte for byte. So the offending plunge does not come from
`lathe_level_next_start`; something else in the phase-2/section machinery
produces it. That is where the next session starts.

(One real bug was found and fixed inside that attempt and is worth keeping if it
is rewritten: the guard latched on the FIRST level forever, because it recorded
only when `_pl_res_have` was 0. It has to key on the level changing, or every
level is compared against a stale value far in front of it.)

## State left in the tree

**Reverted.** `lib/lathe/lathe_level_next_start.ngc` and `ncam.py` are back to
`1f7a97b`, the suite is green, and the reported bug is still there. Shipping a
rapid that cuts metal would have been worse than shipping the missing pass.

## What to do next

The standing rule already names it: **the intervals belong in Python.** Level,
floor contour and ladder are all known at generation time, so the whole set of
disjoint intervals per level — including monotonicity of the plunge points,
which is a *ladder-wide* property no single subroutine call can see — is a table
to compute and emit, with the `.ngc` walking it. That also retires the resume
scan rather than teaching a second scan to agree with the first.

Until then the two scans must not be left reading different sources; if the
Python interval table is not built soon, the honest interim is to make the stop
scan fall back to the record array whenever the resume scan cannot follow it.

---

## Addendum — done in Python, and the condition that is still missing, 2026-08-10

greatEndian: *"do it in python then"*.

### What was built

`resume_envelope()` in `lathe_sections.py`, emitted **inside
`build_floor_contour_gcode` from the very same `env`** — which is the whole
point. The bug was two scans reading two sources; building both tables from one
list of points is what makes them unable to drift apart. No `.cfg` change and no
version bump, because that `[AFTER]` exec already runs.

The table answers *where may a level plunge back in*, keyed on the **level
itself**, so it needs no knowledge of poly_lathe_mill's runtime level sequence —
the thing `analysis/026` already warns against reproducing.

Two conditions have to hold at a plunge Z, and only one is local:

- the floor has dropped back below the level — per level, the first
  above-to-below crossing of the floor contour;
- **every level ABOVE has already cut there** — **ladder-wide**, which no
  single subroutine call can see. That is why it is a table and not a scan.

Sweeping the levels top-down and never letting a resume move *forward* makes the
envelope monotone by construction, so a rapid cannot pass through standing
metal. Breakpoints are the contour's own vertex radii; between two of them the
answer is linear.

New window `RESUME_BASE/TOP = 3000..3140`, in the gap between the record array
and the cfg's own CALL scratch at `#3141-#3159`. `cam_map` passes.

**Unsimplified it needed 176 slots against 140 free** and fell back — loudly,
this time. Collapsing breakpoints that sit on the line between their neighbours
(exact to 1e-4) takes testing_15_5 from 88 breakpoints to **54**.

### It fixes the reported bug

```
                        topmost behind-boss level    passes
before, sectioning OFF        32.1920                  14
after,  sectioning OFF        33.2080                  26
after,  sectioning ON         33.1273                  26
```

### And it still fails test_rough_ends — the same six, and now we know why not

```
Off  the retreat leaves 0.4700 mm standing in a rapid's way:
     Z-42.8231 r31.8160 -> Z-42.8231 r22.2311
```

Z**-42.8231** against Z-42.8230 before: the envelope *is* live and moved the
program, so this is not an inert change failing to apply. The plunge is
genuinely unsafe and monotonicity across levels does not save it.

**The condition that is missing is per-SECTION.** The envelope is global across
the whole contour, while that project's levels restart inside each section
window — so a resume computed globally can land where a *different* section's
levels have not cut yet. Monotone across the ladder is necessary and not
sufficient; the envelope has to be built per window, or the plunge has to be
qualified against the section it belongs to.

That is a much sharper statement of what is left than this file could make
before, and it is the reason the walker is not committed.

### State left in the tree

- **Committed and inert**: `resume_envelope()`, its emission, the window, the
  two globals, and `test_resume_envelope.py`. `_pl_res_n` is written and nothing
  reads it, so behaviour is unchanged — verified by `test_rough_ends`,
  `test_all_projects` and `cam_map`.
- **Not committed**: the walker in `lathe_level_next_start.ngc`. It is a
  30-line lookup and is quoted in full in the commit message of this change, so
  it can be lifted back verbatim once the per-section question is answered.

The reported bug is therefore still present. The remaining work is one
well-understood step, not a search.

---

## Addendum 2 — the per-section theory was wrong; it is the LEAD-IN, 2026-08-11

greatEndian: *"do the per section envelope then"*. Building it started with
checking the premise, and the premise was false.

### Sectioning is not the discriminator

`testing_15_2` and `testing_15_4` — the two projects that fail — both have
**Sectioning = 1**. So does `testing_15_5`, which the fix repairs. Sectioning is
on in all three, so it cannot be what separates them.

### What it actually is, read off the motion

```
   rapid  X 31.8160 Z -42.8231 -> X 22.2311 Z -42.8231    <- the plunge
   feed   X 22.2311 Z -42.8231 -> X 21.5240 Z -43.5302    <- a 45 deg lead-in
```

The level resumes at Z**-43.5302** — monotone, correct, exactly what the
envelope promised. **The rapid does not land there.** It lands where the
LEAD-IN starts, 0.7071 mm in FRONT of it, and at that Z the level above has not
cut yet. Monotone resume points guarantee nothing about a point in front of
them.

So the condition is `R(L) + lead_z` behind `R(L_above)`, not `R(L)` behind it,
with `lead_z = li_len · cos(li_ang)`.

### And it is a RATE, which cost a round

Subtracting a whole `lead_z` at each breakpoint sent testing_15_5 straight back
to its broken state — topmost behind-boss level 32.1920 again. The breakpoints
are contour **vertices**, tens of times closer together than the 0.508 depth of
cut, so a fixed step per breakpoint accumulated roughly **38 mm** of drift.

The constraint is `lead_z` of Z for every `rough_cut` of level descent:

```
limit = back - z_dir * lead_z * (prev_lev - lev) / rough_cut
```

`rough_cut` reaches the builder from `TOOL_TABLE.get_rough_cut()`, so
`polyline.cfg` goes to **1.48** for the extra argument.

### Measured, with the walker wired

```
testing_15_5  topmost behind-boss   32.1920 -> 33.2080    the reported bug, fixed
              sectioning ON         32.1522 -> 33.1273
test_rough_ends                     6 failures -> PASS    the plunge is safe
```

**Both at once**, which neither previous attempt managed.

### Why it is still not wired

Two other tests then fail, and they are a different fault:

```
test_stock_to_leave  the deepest level stops 0.7300 from the Z-70.4 wall
                     with the axial value set to 2.000  (was 2.0000)
test_rough_comp      r24.5720 stops at Z-69.6380, 0.2540 short of the wall
```

Both are about where a level **ENDS**, and the envelope only decides where one
**STARTS**. The link is that `lathe_level_next_start`'s answer also drives
`_pl_ph1_front_cut` and `sect_top_r` in `poly_lathe_mill` — it is what
discovers the phase-1/phase-2 boundary live. Changing which levels find a
resume therefore moves that boundary, and the deepest levels end somewhere else.

That is a third consumer of this subroutine's output that nothing in the plan
accounted for: it is not only "where does this level resume", it is also "is
this the level where phase 1 stops". Those two questions have been answered by
one flag, and separating them is the next step.

### State left in the tree

**Committed inert**: the lead-aware rate clamp, `rough_cut` plumbed through,
`polyline.cfg` 1.48. `_pl_res_n` is written and nothing reads it, so behaviour
is unchanged — `test_stock_to_leave`, `test_rough_comp`, `test_all_projects`,
`test_resume_envelope`, `cam_map` and flake8 all green.

**Not wired**: the walker, again — now for a reason that has nothing to do with
resuming. The envelope itself is finished and proven against both projects.

---

## Addendum 3 — the flag is split, and the third fault it uncovered, 2026-08-11

greatEndian: *"split the flag then"*. Done, and it works — one fault fewer, one
fault left, and both are now named precisely.

### Where the split goes

`poly_lathe_mill` asks `lathe_level_next_start` one question and uses the answer
for two. The dividing line is already in the file:

```
o<ph1_chk> if [[#<_pl_sectioning> GT 0] AND [#<w_idx> LT 0]]   <- PHASE 1
        ... sets sect_top_r and _pl_ph1_front_cut               <- the BOUNDARY
o<ph1_chk> else                                                <- phase 2 / plain
        ... sets l_fr only                                      <- where an interval STARTS
```

So the phase-1 branch keeps the record-array scan's answer, untouched, and only
the else branch takes the envelope's. `lathe_level_next_start` now reports both:
`_pl_resume_found`/`_pl_resume_z` from the scan as before, and
`_pl_env_found`/`_pl_env_z` from the table.

### It fixes what it was supposed to fix

```
testing_15_5   topmost behind-boss   32.1920 -> 33.2080   sectioning OFF
                                     32.1522 -> 33.1273   sectioning ON
test_rough_ends                      FAIL -> PASS         the plunge is safe
test_rough_comp                      PASS                 the boundary held
```

`test_rough_comp` passing is the proof the split did its job: that was one of the
two "where a level ENDS" failures, and holding the phase boundary fixed it.

### The third fault, which is none of the previous two

`test_stock_to_leave` still fails, and identically:

```
the deepest level stops 0.7300 from the Z-70.4 wall with the axial
value set to 2.000
```

Not the plunge, not the boundary. **The intervals the envelope creates end
against the FLOOR contour instead of the stop table.** 0.7300 is about
`fin_off + prefin_off`, which is exactly the number `analysis/024` addendum 2
recorded for a cut that never got the stop table's extension — the table that
is *bounded to extending a cut and never retracting it*. A resumed interval is
reaching its floor and stopping there instead of being carried out to the
anisotropic stop contour.

That overcuts the axial allowance by **1.27 mm**. It leaves the part wrong
rather than crashing the machine, but it is a regression against today's
2.0000, so it is not shipped.

### Three faults, three causes, none of them the first guess

Worth stating together, because the pattern is the lesson:

1. the resume scan read a different profile from the stop scan — **fixed**, the
   envelope;
2. the rapid lands at the LEAD-IN start, not the resume point, and the clamp is
   a **rate** — **fixed**, `8fcabae`;
3. one flag answered both "where does this level resume" and "is this where
   phase 1 stops" — **fixed**, this addendum;
4. and now: a resumed interval ends on the floor instead of the stop table.

Each was invisible until the one before it was fixed. The per-section theory in
addendum 2 was wrong; so was the phase-boundary theory as a complete
explanation. What has held up every time is measuring the actual motion.

### State left in the tree

**Reverted to inert again** — `lib/lathe/poly_lathe_mill.ngc` and
`lathe_level_next_start.ngc` are back at `8fcabae`. `test_stock_to_leave`,
`test_rough_comp`, `cam_map` green. The `_pl_env_found`/`_pl_env_z` defaults
stay in `ncam.py`: they cost nothing and the walker needs them when it returns.

The next step is small and specific: make a resumed interval consult the stop
table the same way a first interval does. That is one question, in one place,
with one number to check - 2.0000 against 0.7300.

---

## Addendum 4 — the stop gate was NOT it, 2026-08-11

greatEndian: *"fix the stop table one then"*. Attempted, failed, reverted, and
the negative result is worth as much as the fix would have been.

### The hypothesis

`lathe_level_pass` applies the stop table under

```
o<stp> if [[#<_pl_stop_n> GT 0] AND [#<found>]]
```

so a pass that meets **no crossing** never consults it and runs to the end of
its window. That fits the symptom exactly: a resumed interval behind a boss
finds no crossing either, so it would run past where the axial allowance says it
must stop — and it was invisible before, because every no-crossing pass used to
be a first interval reaching the part's end, where the window end *is* the right
answer.

### The measurement says no

Gate opened to `o<stp> if [#<_pl_stop_n> GT 0]`, with the walker and the split
wired:

```
the deepest level stops 0.7300 from the Z-70.4 wall   -- unchanged, to the digit
```

Byte-identical to the gated version, so the resumed interval is **not** reaching
that end by skipping the stop block. Something else sets it. Reverted, along
with the walker and the split; `test_stock_to_leave`, `test_rough_comp` and
`cam_map` green.

### What this rules out, and what is left to look at

Ruled out: the `found` gate, the phase boundary (addendum 3 fixed that and
`test_rough_comp` proved it), the plunge (addendum 2), and the source mismatch
(the envelope). Fault 4 is none of those.

Still to look at, in the order I would try them:

- **`w_to` itself.** The interval's window end is passed in by
  `poly_lathe_mill`, and a resumed interval gets a *different* `w_to` from a
  first one. If the stop block clamps against `w_to` and `w_to` is already past
  the stop contour, opening the gate changes nothing — which is exactly what was
  observed. This is the first thing to instrument.
- **`s_reach` and the clamped-candidate rule** (`s_cl`/`s_bcl`): a candidate
  further than `s_reach` from `z_end` is clamped, and `z_end` for a resumed
  interval starts somewhere else entirely, so the same candidate can be rejected
  there and accepted on a first interval.
- **The floor contour's own end.** It stops at Z-69.6380 — `0.762` from the
  Z-70.4 wall, which is suspiciously close to the 0.7300 seen. If a resumed
  interval is ending on the contour's last point rather than on any computed
  stop, that is the answer and it is in the walk, not the stop block.

The third is the one I would measure first: print the interval's `z_end` before
and after the `o<stp>` block for that one pass. One number distinguishes all
three.

### The pattern, stated for the record

Four hypotheses about this fault so far - per-section, phase boundary, the
`found` gate - and **the first guess has been wrong every single time**. The
three that were right were all found by reading the emitted motion, never by
reasoning about the code. That is now a five-round result and it should govern
how the next attempt starts: instrument the failing pass first, theorise second.
