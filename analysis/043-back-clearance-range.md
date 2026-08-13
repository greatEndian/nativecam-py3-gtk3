# 043 — The back angle clearance range, and a bound that does not migrate

2026-08-13, branch `liveTooling`. greatEndian: *"set this as user writable
property as 0.01 - 10 degrees spectur with default value 2deg"*.

## It was already writable

`[PARAM_BACK_CLEAR]` in `cfg/lathe/tool-change.cfg` has been a user parameter on
the Tool Change feature all along — `value = 2.0`, `digits = 2`, on the tool
geometry header. So this was a **range** change, not new plumbing:

```
minimum_value   -45.0  ->   0.01
maximum_value    45.0  ->  10.0
value             2.0       2.0     unchanged
```

`tool-change.cfg` → **1.23**.

## The negative case was dropped deliberately

The old tooltip documented it: *"Negative tilts it the other way, into the
flank, which is only sensible on a tool with more clearance than the tool table
claims."* A minimum of 0.01 removes that, so the tooltip no longer describes it.
Dropped at greatEndian's request, not by accident.

The floor is **0.01 rather than 0** for a reason worth keeping in the text: at
exactly 0 the artificial wall sits along the flank and the whole back edge rubs
at once, which is the chatter the parameter exists to avoid.

## THE FINDING: a narrowed bound does not reach a saved project

Asked what happens to a saved project holding a value outside the new range.
**The stale bound wins, silently.** Measured, not read:

```
cfg 1.23 declares :  min 0.01     max 10.0
saved project has :  min -45.0    max 45.0
AFTER migration   :  min -45.0    max 45.0
```

`testing_15_5.xml` really does carry the bounds — every saved `param` element
has `minimum_value` and `maximum_value` written into it — and
`update_features` copies them back over the cfg's:

```python
if 'minimum_value' in p.attr and 'minimum_value' in q.attr :
    q.attr['minimum_value'] = p.attr['minimum_value']
```

So on every existing project the operator can still type −45. Only a Tool Change
added **after** this change gets 0.01…10.

### The code already knows this is wrong

The comment above those lines says so:

> *"Every minimum/maximum in cfg/ is a static declaration, so a saved copy is
> just a snapshot of what the cfg said when the project was saved - and copying
> it back unconditionally meant a cfg could never relax a bound: the stale limit
> kept winning on every existing project, so the change only ever reached newly
> added features."*

The guard that was added — `and 'minimum_value' in q.attr` — only covers the cfg
**dropping** a bound. It does not cover the cfg **changing** one, which is this
case. By the comment's own reasoning (a saved bound is a snapshot of a static
declaration) the cfg should always win.

### Why it was not fixed here

Letting the cfg win is a one-line change to that copy-loop, and it would touch
**every bound of every parameter of every migrating feature** — far outside a
range change, and exactly the kind of quiet, wide edit this repo has paid for
before. It wants its own task, its own measurement of what moves across the
demo projects, and its own commit. Recorded in `openPoints.md`.

Note the value itself is a separate question from the bound: nothing clamps a
stored value on load, so a project holding −45 keeps cutting with −45 until
someone edits that field.

## Verified

Every demo project still generates and runs (`test_all_projects`, which is the
test that exercises the migration path), plus `test_lathe_validation`,
`test_leftover`, `test_x_continuity`, `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_behind_boss_ladder`, `test_rough_overlay`,
`test_ladder`, `test_floor_ladder`, `test_ramps`, `test_section_length`,
`test_resume_envelope`, `test_end_z`, `test_z_datum`, `test_extension`,
`test_peck`, `test_below_inner_radius`, `test_front_flank`,
`test_front_flank_path`, `test_pane_layout`, `cam_map`, flake8 both lists.
