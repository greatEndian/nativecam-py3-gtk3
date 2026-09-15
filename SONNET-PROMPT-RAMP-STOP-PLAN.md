# Task: plan moving the ramp and stop machinery out of O-code — PLAN ONLY

Read `/home/user/nativeCamDev/CLAUDE.md`, then
`/home/user/nativeCamDev/SONNET-LANES.md`. **Lane: PLAN, main tree.** You
write exactly one file, your analysis. You do not edit `lib/`, `cfg/`, or any
`.py`. Analysis range: **`analysis/300`–`309`**.

## Why

`openPoints.md`, search *"The ramp and stop machinery is still runtime
O-code"*: `s_reach`, the slope term, the flat-boundary clamp, the
clamped-candidate rule, and the level scan's own perpendicular offset still
compute geometry at runtime in `lib/lathe/lathe_level_pass.ngc` (7 references
to `s_reach` alone). `analysis/023` is the first place it cost something;
`analysis/036` is a fault `s_reach` could not stop. The standing rule is
**Python first, O-code last — and backwards, to O-code that already exists**.
This is the largest remaining migration, and `CLAUDE.md`'s blast-radius rule
says it gets planned in full before anyone types.

A GEOMETRY worker is editing `lathe_sections.py` in the same tree while you
read. Read it, never write it.

## What the plan must contain

1. **Every runtime computation** in `lathe_level_pass.ngc` and the subs it
   calls that decides geometry: the line range, what it computes, its inputs
   (which globals/numbered parameters), and whether Python already knows the
   answer at generation time — cite the Python function if so.
2. **Every consumer**, by grep and by `python3 cam_map.py --map` / `CAM-MAP.md`:
   who writes each parameter window it reads, who else walks those windows.
3. **Which can move and which cannot**, with the reason — a value that depends
   on the live tool table at runtime is not the same as one derived from the
   profile.
4. **The resource**: numbered-parameter window slots needed for each new table,
   measured against the worst real project, not assumed (`analysis/` records a
   migration that needed 226 slots where 200 were free).
5. **A staged sequence** — each stage independently committable and
   fingerprint-provable, smallest first, with per stage: the number that
   proves it, the number that proves untouched projects are untouched, and what
   stays as fallback.
6. **Measurements, not reading.** For at least the first stage, instrument the
   current O-code (on a scratch copy, never the live files) and record the
   actual runtime values on testing_15_5, testing_15_6 and testing_15_9, so the
   Python port has a known answer to match. Every `rs274` run under
   `flock /tmp/ncam-rs274.lock`.

## Deliverable

`analysis/300-ramp-stop-migration-plan.md`, committed by explicit path, and
the `openPoints.md` entry pointing at it. No other file changes. Report what
you measured and the proposed stage 1 in under 200 words.
