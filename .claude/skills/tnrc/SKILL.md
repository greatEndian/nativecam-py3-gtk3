# /tnrc

Tool nose radius compensation — the theory, the LinuxCNC specifics, and this
project's own measured facts, held **locally** so a session does not go back to
the web for the same ground twice.

Also the pattern to follow for anything else that has to be looked up: research
it once from several sources, cross-check, write it down, compress it, query it
offline from then on.

## Usage

```
/tnrc                            list the packs and their sections
/tnrc <terms>                    print every section matching all the terms
/tnrc quadrant orientation       e.g. where the nose sits for each Q number
/tnrc start-up entry             e.g. the rules for switching comp on
```

Behind it:

```bash
python3 .claude/skills/tnrc/scripts/kb.py                  # index
python3 .claude/skills/tnrc/scripts/kb.py arcs concave     # sections
python3 .claude/skills/tnrc/scripts/kb.py --list           # headings only
```

No network, no API key, no model. `kb.py` decompresses the pack and prints
whole sections — half a compensation rule is worse than none.

## When to use it

Before touching anything under `lib/lathe/tip_comp_*`, the `n_comp` parameters,
`lathe_sections.offset_contour`, or the entry and exit of any compensated pass.
The pack answers, with numbers:

- where the nose sits for each orientation 0-9, and which are the outside-turning
  quadrants
- the offset rule, and why a Z-parallel wall gets **no radial shift** on an
  orientation-2 tool
- what the offset does to an arc, and why a concave corner smaller than the nose
  cannot be cut at all
- the start-up block rules, and why breaking them tapers the first segment of a
  cut instead of erroring
- this project's `#<_tip_*>` global contract and per-op comp side table
- the measured surface each mode leaves, and the two defects that were inflating
  each other's numbers

## When the pack does not know

That is the point of the skill, not a failure of it. Do this, in order:

1. **Search several independent sources.** One hit is an anecdote. Control
   vendor documentation, the LinuxCNC docs, a CAM or machining reference, and
   the research literature disagree in useful ways — where they agree you can
   rely on it, where they differ, say so in the pack.
2. **Cross-check against this repo.** A claim that survives the web but not
   `rs274` is wrong here. Measure it.
3. **Write a new `## ` section** into the pack. Keep the house style: numbers
   rather than adjectives, and the failure mode stated as well as the rule.
4. **Add the URLs** to the `## SOURCES` section so a claim can be traced.
5. **Recompress**:

```bash
python3 - <<'PY'
import gzip, pathlib
p = pathlib.Path('.claude/skills/tnrc/knowledge/tnrc.md.gz')
text = gzip.decompress(p.read_bytes()).decode()
# ... edit `text` ...
p.write_bytes(gzip.compress(text.encode(), 9))
PY
```

A new subject gets its own pack — drop `<name>.md.gz` in `knowledge/` and
`kb.py` picks it up with no code change.

## What goes in a pack, and what does not

**In**: rules that will still be true next year, the numbers that make them
checkable, the failure mode each one produces, and where the claim came from.
This project's own measured constants belong here too — they are exactly what a
future session needs and they are not on the web.

**Out**: anything the repo already records. Code structure, git history, what a
function currently does — those change, and a stale copy in a compressed file is
worse than no copy. Point at the file instead.

## Gotchas

- Sections are split on `## ` at the start of a line. A line inside a fenced
  code block that begins `## ` would split a section in two; there are none
  today, and there is no fence parsing.
- The pack is gzipped, so `grep` will not find it. That is deliberate — it is
  compressed to be carried, and `kb.py` is how it is read.
- `kb.py` requires **all** terms to appear in a section, so it narrows fast.
  Start with one term.
- The pack is version-controlled as a binary. A change shows up in `git` as an
  opaque blob, so say what changed in the commit message.
