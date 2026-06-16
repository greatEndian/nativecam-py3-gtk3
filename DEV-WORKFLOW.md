# DEV-WORKFLOW — universal development template (LinuxCNC fork)

A reusable, living playbook so each new increment doesn't need re-explaining.
Distilled from the working pattern across this project. **Claude: load this at
the start of relevant work, follow the phases, and APPEND to the LEARNINGS LOG
whenever something useful is discovered.** Pointer in MEMORY.md.

Default unit of work = ONE small, gated, reversible increment. Big jobs = a
numbered series of these (I1, I2, ... like MC31 / the AC/BC RTCP).

================================================================================
## THE PHASES  (study → research → mark → consult → build → test → verify → post)
================================================================================

### 1. SCOPE & STUDY
 [ ] Read session memory (MEMORY.md + topic files) FIRST — it's ground truth.
 [ ] Read the relevant existing code/docs; find the EXACT edit sites (grep).
 [ ] Derive any math/behavior from the SOURCE OF TRUTH, not memory
     (e.g. kins forward matrix -> the inverse formula).
 [ ] Find the proven PATTERN to mirror (a prior similar feature) — copy its
     structure, naming, idioms, guards.
 [ ] List: files to touch, what changes, why. State the smallest correct change.

### 2. ONLINE RESEARCH  (only when domain knowledge is needed)
 [ ] WebSearch/WebFetch for industrial standards / how others solved it.
 [ ] Map findings to OUR context; cite sources.
 [ ] Identify the common/standard approach before inventing one.

### 3. MARK DOWN  (durable, before coding the hard parts)
 [ ] Write the plan/derivation to a design/status doc (repo or cnc-dev).
 [ ] Flag CRITICAL POINTS: ⚠️ = safety/correctness, ★ = a decision for the user.
 [ ] List OPEN DECISIONS + a per-point test/verify strategy.

### 4. CONSULT  (the user's calls are the user's)
 [ ] Present options + a clear RECOMMENDATION + the open decisions.
 [ ] AskUserQuestion for genuine forks (scope, approach, validation target).
 [ ] WAIT for direction on real decisions; don't barrel past them.
 [ ] For self-resolvable choices, pick the sensible default and say so.

### 5. IMPLEMENT
 [ ] Mirror the proven pattern; match surrounding code style/comment density.
 [ ] D7 GOLDEN RULE: default/single-channel path stays bit-identical to stock
     (gate it on the new behavior, e.g. `if (num_channels>1)` / `count>0`).
 [ ] Conflicts/extensions: prefer ADDITIVE "keep-both" resolutions.
 [ ] Risky/irreversible ops: work on COPY branches; keep originals untouched.
 [ ] Prefer setters / append-at-end over growing shared shm structs (ABI).

### 6. BUILD
 [ ] `make -j$(nproc)` in src (RIP: `src/configure --with-realtime=uspace`).
 [ ] Scan for real `error:` (ignore macro `note:` lines). Confirm the link.
 [ ] Rebuild EXTERNAL binaries that embed shared structs (e.g. mchan-chmap)
     whenever the struct layout changed.

### 7. TEST / VALIDATE  (deterministic first, flaky last)
 [ ] OFFLINE NUMERIC PROOF first: exhaustive, cheap, deterministic
     (round-trip / forward==inverse over a grid + random, ~1e-12).
 [ ] The GATE: `runtests basic tlo abort mdi-queue mchan-tp-budget` = 9/9
     + tp-budget tripwire + D7 (num_channels=1 bit-identical). Every commit.
 [ ] Code-path test: rs274/interp-level or halrun unit (no GUI/rsh) when possible.
 [ ] Live rig last (subject to OP3/OP4 rsh flakiness). Clear shm + kill stale
     procs before runtests. Environmental flake != code failure — diagnose.

### 8. VERIFY  (discriminating + edges)
 [ ] Discriminating test: it DOES the thing AND does NOT break the other side
     (e.g. ch0 moves while ch1 idle; same index refused ch0 / allowed ch1).
 [ ] Edge cases: singularity, G53, G91, zero-length, abort/estop mid-op, N=1.
 [ ] Cross-checks: local==remote, forward(inverse)==input, before==after pose.

### 9. POST / RECORD
 [ ] Commit with a THOROUGH message: root cause, fix, gate result, D7 note.
 [ ] SAVE TO MEMORY after EVERY completed increment (not at session end).
 [ ] Update the status/design doc (+ visual if useful).
 [ ] BACKUP before anything destructive: bundle --all + tar + push (3 copies),
     `git bundle verify`. Restore-test if high stakes.
 [ ] Push / outward-facing actions ONLY with the user's go-ahead.
 [ ] Report FAITHFULLY: what passed, what's blocked, what's a residual (OPx/APx).

================================================================================
## CROSS-CUTTING PRINCIPLES & HARD-WON RULES
================================================================================
 - Never `kill -9 rtapi_app`. Never `pkill -f <pattern>` that matches your own
   command (causes exit 144 / lost work) — kill by exact name or PID.
 - Before runtests: `halrun -U` + clear shm keys (0x64/0x48414c32/0x48484c34) +
   kill stale milltask/rtapi/halui/svr by PID. A wedged halui blocks the gate.
 - Don't grow emcmot_command_t / emcmotStruct lightly: any field before the
   per-channel mailboxes shifts their offset -> rebuild mchan-chmap, or it
   times out ("command N timeout channel 1"). Prefer an exported setter
   (tpSetNumChannels pattern) for cross-module data.
 - gitignore/`.git/info/exclude` generated artifacts so `git add -A` can't
   sweep them into a commit (the build man-page lesson).
 - Pushing a branch that carries .github/workflows changes needs a PAT with the
   `workflow` scope (or SSH).
 - Migration/rebase: work on *-upstream COPY branches; `rerere` on; auto-handle
   doc/config conflicts (reconstruct fork docs / `--ours` for sim configs),
   stop only on real code conflicts; resolve additively.
 - "Done" means built + gated + verified. Say plainly what's proven vs pending.
 - DOC & COMMENT COMMUNITY SHAPE: feature docs = AsciiDoc in docs/src/ (g-code.adoc / ini-config.adoc / man), match existing style; code comments = LinuxCNC idiom + GPL headers. Upstream-acceptable, not fork-local .md, for canonical docs.

================================================================================
## LEARNINGS LOG  (append-only — add a dated line whenever something helps)
================================================================================
 - 2026-06-15  Offline exhaustive numeric proof (2M+ random vectors, ~1e-15)
   gives far higher confidence than a couple of rig runs AND dodges rsh
   flakiness — do it first for any math/derivation feature.
 - 2026-06-15  rs274 standalone interp + a tiny INI (set the feature's config)
   tests the CODE PATH end-to-end without a GUI/RT session — ideal middle tier
   between offline proof and live rig.
 - 2026-06-15  When the rig is flaky, a single clean discriminating observation
   (e.g. M64 P2 refused ch0 / allowed ch1) proves a feature better than a full
   acceptance suite that never goes all-green.
 - 2026-06-15  Check for an existing upstream PR of your own work before
   migrating/rebasing (PR #4154) — avoids duplicating commits onto upstream.
 - 2026-06-15  Headless 5-axis tip-hold validation: run the kins' vismach sim
   config with DISPLAY=linuxcncrsh (drop PYVCP/POSTGUI/HALUI), add the feature's
   INI key, home via rsh `set home 0..N`, run a G43.5 program that tilts the tool
   at a FIXED tip, and read joint.* - orientation reached + linear joints
   compensated (tip held) = full-pipeline RTCP proof without a GUI.
 - 2026-06-15  ALWAYS clear shm + kill procs and VERIFY clean BEFORE launching a
   sim (single-instance too) - a leftover-shm race gives "command N timeout /
   emcTrajInit failed". Bit BC bring-up until the clean-slate retry.
 - 2026-06-15  Headless sim for a kins whose pivot/param comes from a GUI/vismach
   component: replace `loadusr -W <gui>` with a `setp <kins>.<param> <value>`
   HAL line - lets the kins run headless. (5axiskins pivot-length.)
 - 2026-06-15  Commit ONLY explicit code files (git add <files>), NOT -A, when
   test scaffolding/generated files sit in the working tree - or move scaffolding
   out of the repo first. (BCHEAD sim files in configs/ would have been swept.)
 - 2026-06-15  A sign/convention param the interpreter can't read from a kins HAL
   pin (e.g. trt conventional-directions) needs its OWN INI knob, defaulted to
   match the kins default so existing configs are unchanged. Derive the FULL
   forward rotation matrix (not just the tool-axis column) so BOTH the inverse
   AND the offset transform get the sign right; prove BOTH parameter values
   offline before touching the interp. (G43.5 con=+/-1.)
