# Coolant and spindle startup dwell controls

Requested: independent editable waits immediately after coolant and spindle
start, including Outside roughing, with executable `G4 Pseconds` in Flat.

The controls belong to Tool Change. Its spindle start previously used only
the global acceleration preference. Coolant started through either
`set_spindle_rpm` or seven lathe routines plus the Parting template, without
a pressure wait. A field confined to Tool Change's own call would therefore
miss coolant start at the beginning of roughing and subsequent restarts.

Tool Change 1.25 adds adjacent seconds fields. Its per-tool spindle value
feeds the existing speed-up global; migration copies the previous preference
when that field did not exist. Coolant gets one shared transition-aware
routine, with zero default and an EXISTS guard for older standalone drivers.
Parting 1.15 updates saved embedded call templates. Both zero and Off avoid
waits. Repeated starts at unchanged speed with coolant already on do not
wait again; M5/M9 followed by restart does.

Verification: the new driver first failed for missing `spindle_dwell`.
Final serial batch: 10/10 PASS, no retries, skips, timeouts, or dirty-tree
changes. It covers M3/M4, M7/M8, G20/G21, zeros, Off, restart, migration,
serialization and Flat replay. Lint, diff whitespace and all nine cam-map
checks pass. Two test-fixture errors were corrected: the first point must
differ from the origin, and migration needs serialized item paths. Duplicate
fixture features also need distinct child IDs. Unexpected generator dialogs
now fail the driver instead of waiting indefinitely.

The real thomasAuer_0.xml was loaded in a scratch configuration. Baseline and
1.5-second spindle / 0.75-second coolant variants preserve 204 nonzero moves
and 114 cutting blocks with feeds. Both waits replay unchanged from Flat;
saved XML bytes remain unchanged. Artifacts:
`/tmp/ncam_flat_saved_29d5xccc/`. Tangent check: 129131 canon events,
minimum absolute tangent dot 1.00000, PASS. This dot check alone cannot
detect reversals; the ordered 204-move comparison independently checks
direction. Physical spindle acceleration and coolant pressure are unmeasured;
the operator must choose suitable durations.
