# Flat must select the work coordinate system

Reported: Flat contains G54 only when a manual G-code feature supplies it.

Root cause: flatten_canon discarded every SET_G5X_OFFSET event. Coordinates
remained expressed in the source program's work frame, but exported programs
never selected that frame. Prior round trips used the same remembered G54
and mostly compared part coordinates, masking the failure when another WCS
was active. The old header's offset explanation did not establish a mode.

The exporter now emits the interpreter's actual G54..G59.3 selection before
motion and on changes. Its tracked current position follows frame translation
so an arc immediately after G54/G55 retains correct relative I/K. Unit changes
rescale the tracked position and frame offsets and are emitted whenever the
unit mode changes, including returning from inches to millimetres. Work offset
values remain on the controller; the fix does not write a G10 table snapshot.

test_flat_program.py now seeds G55 as the initial mode and gives all nine
WCSs distinct, nonzero X/Z offsets. It verifies active selectors before motion
and independently reconstructs physical endpoints and arc centres from source
and replay canon. Before the production fix, selectors were missing and an
arc replay failed with r1=32.2025 versus r2=5.0000. The fixture uses a separate
parameter-copy directory for each interpreter run; reusing the source variable
file's own directory could change the scratch seed and invalidate the test.

Final results: 10/10 selected regression drivers PASS without retries, skips,
timeouts or tracked-file writes. The strengthened inch-to-metric case passed
again separately. Full selected lint, diff whitespace, and nine cam-map checks
pass. No new shell execution or externally constructed path enters production.

The latest thomasAuer_0.xml was loaded without modifying it. A scratch variant
removes its manual reset feature, starts with G55 selected and nonzero G55
offsets, and still exports executable G54 before motion. Source and Flat
preserve all 204 nonzero moves, feeds and feed modes. Original XML bytes remain
unchanged. Artifacts: /tmp/ncam_flat_work_offsets_saved_wb8t5x1e/.
The independent Flat tangent check parsed 238 canon events, minimum absolute
tangent dot 1.00000, PASS. Ordered source/replay motion comparison supplements
that check because absolute tangent dot alone cannot detect a reversal.
Physical hardware was not run. This change preserves WCS selection; it does
not add a general exporter for arbitrary G10 table edits or rotated frames.
