---
name: security-audit
description: "Use before declaring done any change touching subprocess/shell calls, file paths built from external input (filenames, XML/.cfg attributes, imported project files), or dynamic code execution (eval/exec). Scans the diff for this codebase's actual risk surface - not a generic web-app OWASP checklist, most of which doesn't apply to a desktop GTK app with no network/DB surface."
---

# /security-audit

This is a standalone desktop app (GTK3, no server, no DB, no auth, no network-facing input) — the generic OWASP top 10 (SQLi, XSS, CSRF, SSRF, auth bypass) mostly doesn't apply. What actually matters here, confirmed present in this codebase today:

## Real risk surface in this repo

1. **`exec()`/`eval()` on data loaded from `.cfg`/project XML files** — `ncam.py` runs `exec(self.attr['on_change'])`, `exec(self.attr['value_changed'])`, `exec(self.attr['init'])`, `eval(qualified)`, `eval(m.group(2), globals(), {"self":self})`, `eval(s.strip('[]'))`, and `exec(s)` (search `ncam.py` and `ncam_project_io.py` for exact lines — line numbers shift). These execute strings that ultimately come from `.cfg` template files and imported/opened project `.xml` files, not compiled code. This is a **known, accepted, existing architectural pattern** (features declare `on_change`/`init` Python snippets), not something to "fix" reflexively — but any new code that constructs one of these strings from something less trusted than the project's own shipped `.cfg` files (e.g. from a user-typed value, a network fetch, an unvalidated import) is a real code-injection path and must be flagged, not waved through.
2. **`subprocess.call([...], shell=True)` with interpolated data** — e.g. `ncam_project_io.py`'s `action_open_project`: `subprocess.call(["xdg-open '%s'" % filename], shell=True)` where `filename` comes from a `GtkFileChooserDialog` result. A filename containing `'; rm -rf ~; '`-style content run through a real shell is a real shell-injection path. Flag any `shell=True` combined with string formatting/concatenation of external data; the fix is `shell=False` with an argument list, or `shlex.quote()` if a shell is genuinely required.
3. **Path handling** — `os.path.join(NCAM_DIR, ...)` patterns with a component taken from external data (a filename, an imported XML attribute) — check for path traversal (`../`) before joining, or that the joined result is checked to stay under the intended directory.
4. **Secrets** — hardcoded API keys/tokens/passwords in any diff. This project currently has none (no network services, no third-party API integration in `ncam.py` itself), so finding one in a diff is unusual enough to always flag.

## Steps

1. `git diff` (or the specific files changed this session) — scan only the actual diff, not the whole repo from scratch each time.
2. For each of the 4 categories above, report every match with file:line, not just a yes/no.
3. For each match, state whether the *data reaching it* is trusted (shipped `.cfg`/catalog file, same trust level as the rest of the codebase) or came from somewhere less trusted (user-typed field, imported file, network) in this specific change. Only the second case is an actual new finding — don't re-flag the existing 7 known `exec`/`eval` call sites every time unless the diff changed what feeds them.
4. If a genuine new finding exists, don't silently fix it as a drive-by — report it and let the user decide (per CLAUDE.md's "ask first" bucket, this is exactly the kind of thing that needs a conscious decision, not a reflexive patch).

## Gotchas & Edge Cases

- Don't apply web-app OWASP categories that have no analog here (SQLi, XSS, CSRF, session fixation) — reporting "N/A, no DB/no web server" for these wastes the user's time reading a checklist against a threat model that doesn't exist for this app.
- The existing `exec`/`eval` call sites are load-bearing application architecture (feature `on_change`/`init` scripting), not bugs — don't recommend removing them; recommend tightening only the specific new data path a change introduces, if any.
- `git diff` with no arguments only shows unstaged changes — if the change was already staged or committed this session, use `git diff HEAD~1` or `git diff --staged` as appropriate, or you'll silently audit nothing.
