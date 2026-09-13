#!/usr/bin/env python3
# coding: utf-8
"""Batch C of the lathe_sections.py unit-coverage series.

Batch C's 17 named functions (SONNET-PROMPT-UNITS-C.md lists them as
"nineteen"; the table it gives has 17 distinct names - see analysis/170)
were each read in full and checked against the standing rule carried from
batch A/B: "if a function requires a Feature to call, skip it - faking one
is out of scope and produces tests that assert the fake, not the code."

EVERY ONE OF THE 17 NEEDS A FEATURE. This file does not contain direct
behavioural coverage for any of them, because none exists to write without
breaking that rule - see analysis/170 for the full per-function reading.

What it contains instead is the EVIDENCE for that skip, made permanent and
re-checked automatically rather than left as one session's prose claim:

  - a small AST call-graph walker (transitive, not just "does this function
    itself call get_param") that answers, from the actual source on disk,
    whether a function's own call tree ever reaches Feature/Parameter
    methods (get_param, get_attr) or the two functions another session
    rewrote (detect_sections, floor_regions);
  - sanity controls proving the walker actually discriminates pure from
    impure, using functions already directly unit-tested in earlier
    batches (ceiling, boundary_height, ramp_facing, apply_merge_radii - all
    confirmed Feature-free there) - a walker that answered True for
    everything would make every assertion below meaningless;
  - one assertion per batch-C function, run fresh against lathe_sections.py
    every time this file runs. If a future refactor ever drops a function's
    Feature dependency, THIS TEST FAILS - which is the point: it turns
    "still needs a Feature" from something a worker re-derives from scratch
    each time into a fact this suite defends, and flags exactly the moment
    the skip should be revisited for direct coverage.

This is a structural/dependency check, not a geometry check - it asserts
nothing about what any function COMPUTES. That is exactly why it belongs in
its own file rather than diluting the geometry-property tests in
test_profile_units.py / test_window_units.py.
"""
import ast
import os
import sys

failures = []

LATHE_SECTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'lathe_sections.py')

FEATURE_METHODS = {'get_param', 'get_attr'}
REWRITE_TARGETS = {'detect_sections', 'floor_regions'}


def _build_call_graph(path):
    """{function_name: {names called anywhere in its own body, including
    inside its own nested helper closures}} for every MODULE-LEVEL def.

    Keyed by module-level name only (not nested helpers like the many
    `_p(name, default=0.0)` closures repeated across this module under the
    same local name) - walking a module-level function's own AST subtree
    already picks up everything its nested closures call, so recording
    those closures as separate graph nodes would only invite name
    collisions between unrelated functions that happen to name a local
    helper the same thing.
    """
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)
    top_defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    graph = {}
    for name, node in top_defs.items():
        called = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                fn = n.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        graph[name] = called
    return graph, set(top_defs)


_GRAPH, _TOP_NAMES = _build_call_graph(LATHE_SECTIONS_PATH)


def reaches(fn_name, target_names, _seen=None):
    """True if fn_name's call tree reaches any name in target_names, at any
    depth through other module-level functions (never through nested
    closures by name - see _build_call_graph)."""
    if _seen is None:
        _seen = set()
    if fn_name in _seen:
        return False
    _seen.add(fn_name)
    for called in _GRAPH.get(fn_name, ()):
        if called in target_names:
            return True
        if called in _TOP_NAMES and reaches(called, target_names, _seen):
            return True
    return False


def check(name, got, want):
    ok = got == want
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# SANITY CONTROLS - prove the walker discriminates, using functions already
# directly unit-tested (without any Feature) in test_geometry_primitives.py
# and test_ramp_direction.py. If any of these read True, the walker itself
# is broken and every skip-verdict below is worthless.
# ---------------------------------------------------------------------------
for pure_fn in ('ceiling', 'boundary_height', 'ramp_facing', 'apply_merge_radii'):
    check('control: %s is Feature-free (already covered directly elsewhere)'
          % pure_fn,
          reaches(pure_fn, FEATURE_METHODS), False)

# And the walker must correctly follow INDIRECT reach, not just literal
# top-level calls - profile_problem never calls get_param itself, it calls
# resolve_points(polyline_feature), which is where the get_param lives.
check('control: the walker follows indirect (transitive) reach, not just '
      'a function\'s own literal calls',
      reaches('profile_problem', FEATURE_METHODS), True)


# ---------------------------------------------------------------------------
# BATCH C - all 17 need a Feature. One assertion per function; a comment
# names the exact call that requires it, confirmed by reading the function
# body (not just by this walker - see analysis/170 for the reading).
# ---------------------------------------------------------------------------

NEEDS_FEATURE = [
    # own get_param/resolve_points(polyline_feature) call
    ('resolve_points_untrimmed', "resolve_points(polyline_feature, trim=False)"),
    ('z_limit_band', "z_limit_abs(polyline_feature, ...)"),
    ('profile_problem', "resolve_points(polyline_feature) (indirect)"),
    ('level_allowance', "polyline_feature.get_param('param_pf_on'/etc)"),
    ('rough_radius_bounds', "polyline_feature.get_param(...), x_limit_abs(...)"),
    ('ext_dz', "resolve_points(polyline_feature, extend=...)"),
    ('rough_emit_reversed', "polyline_feature.get_param('param_dir')"),
    ('rough_nose_terms', "_comp_nose(polyline_feature, ...) -> get_param"),
    ('flat_sub_number', "polyline_feature.get_attr('id')"),
    ('facing_rough_offset', "feature.get_param(...) x6"),
    ('finish_profile', "polyline_feature.get_param('param_flank'/'param_f_dir'/...)"),
    ('unreachable_spans', "resolve_points/finish_profile need the Feature"),
    ('xw_settings', "polyline_feature.get_param(...) x4"),
    # needs a Feature AND (still) reaches the rewritten functions -
    # the detect_sections fix (f610fbd) lifted the SECOND reason only
    ('section_windows', "polyline_feature.get_param(...) x4, PLUS reaches "
                        "detect_sections (now-fixed, but Feature need stands)"),
    ('split_peaks', "polyline_feature.get_param('param_dir'), PLUS reaches "
                    "detect_sections (now-fixed, but Feature need stands)"),
    ('floor_stages', "polyline_feature.get_param(...), PLUS reaches "
                     "floor_regions (now-fixed, but Feature need stands)"),
    ('roughing_call_plan', "a dozen polyline_feature.get_param calls, PLUS "
                           "reaches floor_regions/detect_sections"),
]

check('batch C: exactly 17 functions named in the prompt\'s own table '
      '(it says "nineteen" - see analysis/170)',
      len(NEEDS_FEATURE), 17)

for fn_name, why in NEEDS_FEATURE:
    check('SKIP (needs Feature): %s - %s' % (fn_name, why),
          reaches(fn_name, FEATURE_METHODS), True)

# The four that are ALSO no longer blocked by the (now-fixed) rewrite -
# confirmed here so a future reader does not have to re-run the AST walk to
# see that this reason, specifically, is gone.
STILL_REACHES_REWRITE_TARGETS = [
    'section_windows', 'split_peaks', 'floor_stages', 'roughing_call_plan']
for fn_name in STILL_REACHES_REWRITE_TARGETS:
    check('%s still transitively reaches detect_sections/floor_regions '
          '(fixed in f610fbd, no longer a blocker on its own)' % fn_name,
          reaches(fn_name, REWRITE_TARGETS), True)

# NEGATIVE CONTROL for that second group: everything else in the batch must
# NOT reach the rewrite targets - if one of the "just needs a Feature"
# functions turned out to reach detect_sections/floor_regions too, the
# per-function reasons given above (and in analysis/170) would be wrong.
for fn_name, _why in NEEDS_FEATURE:
    if fn_name in STILL_REACHES_REWRITE_TARGETS:
        continue
    check('control: %s does NOT reach detect_sections/floor_regions '
          '(Feature is its only blocker)' % fn_name,
          reaches(fn_name, REWRITE_TARGETS), False)


if failures:
    print('\n%d FAILURE(S): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('\nAll batch-C purity-census checks passed (0 of 17 directly '
      'coverable without faking a Feature - see analysis/170).')
