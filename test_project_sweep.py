#!/usr/bin/env python3
"""Generate and run EVERY lathe project. Report only what breaks.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHY THIS EXISTS. Every other gate in this repo runs a hand-picked list -
test_ladder_python and its siblings all sweep the same six testing_15_*
projects, and prove_cam_comp takes one project at a time. So a project that
stops generating, aborts in the interpreter, or produces no motion at all is
invisible until somebody opens it. Three did: the testing_13_arc_first family
abort at runtime and nothing noticed.

It also needs no input from anyone. Point it at the catalogue and it says which
projects are broken, which is the cheapest possible bug report.

NOT a correctness check - a program that runs is not a program that cuts the
right shape. This only catches the projects that do not run at all.
"""
import os, re, subprocess, sys, tempfile
HERE='/home/user/nativeCamDev'; sys.path.insert(0,HERE)
import ncam_preview as P
INI=os.path.join(HERE,'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN=os.path.join(HERE,'.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
D=os.path.join(HERE,'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects')
projs=sorted(f for f in os.listdir(D) if f.endswith('.xml'))
work=tempfile.mkdtemp(prefix='sweep_')
ok=[];bad=[]
for pr in projs:
    out=os.path.join(work,pr[:-4]+'.ngc')
    r=subprocess.run([sys.executable,GEN,'--ini',INI,'--project',pr,'--out',out,
                      '--config-copy'],capture_output=True,text=True,timeout=600)
    if not os.path.isfile(out):
        bad.append((pr,'DID NOT GENERATE',(r.stderr or r.stdout)[-160:].replace('\n',' ')))
        continue
    # A TABLE THAT DID NOT FIT LEAVES ITS COUNT AT THE DEFAULT-BLOCK ZERO and
    # says nothing. That is how four projects came to run with no ramp-direction
    # table for months: eramp_n is entry_n - 1 on every project that fits, so a
    # 0 beside a non-zero entry_n is the whole signature. Cheap, and it is what
    # actually found the bug - see analysis/118.
    src = open(out).read()
    def _last(name):
        m = [x for x in re.finditer(r'#<%s>\s*=\s*(\d+)' % name, src)]
        return int(m[-1].group(1)) if m else 0
    entry_n, eramp_n = _last('_pl_entry_n'), _last('_pl_eramp_n')
    # > 2, matching build_entry_ramp_gcode's own `len(points) < 3` guard: a
    # two-point entry contour has one segment and no ramp table by design, and
    # testing_12_1 is exactly that. Caught by running the negative control -
    # the threshold that looks right is one the builder disagrees with.
    if entry_n > 2 and eramp_n == 0:
        bad.append((pr, 'TABLE DROPPED',
                    'entry contour has %d points but the ramp-direction table '
                    'is empty - it overflowed its window' % entry_n))
        continue
    tp=P.parse_program(out,INI)
    if tp.error:
        bad.append((pr,'RUN ERROR',str(tp.error)[:160]))
    elif not tp.moves:
        bad.append((pr,'NO MOTION','the program produced no moves'))
    elif not getattr(tp,'completed',True):
        bad.append((pr,'DID NOT REACH END','stopped part way'))
    else:
        ok.append(pr)
# an empty template legitimately produces nothing - it is the blank start point
# matched on the MESSAGE, not the kind: parse_program reports an empty
# program as a RUN ERROR whose text is 'produced no motion', so keying on the
# kind whitelisted nothing and the gate called its own expected case a failure
KNOWN = {'default_template.xml': 'produced no motion'}
real = [b for b in bad if KNOWN.get(b[0], '\0') not in b[2]]
print('%d projects: %d clean, %d broken (%d expected)'
      % (len(projs), len(ok), len(bad), len(bad) - len(real)))
for pr, kind, msg in bad:
    tag = '' if KNOWN.get(pr, '\0') in msg else '  <-- '
    print('  %-34s %-18s %s%s' % (pr, kind, tag, msg))
if not projs:
    print('NO PROJECTS FOUND - the sweep measured nothing')
    sys.exit(1)
sys.exit(1 if real else 0)
