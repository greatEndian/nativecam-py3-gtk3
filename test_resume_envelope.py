import sys; sys.path.insert(0,'/home/user/nativeCamDev')
import lathe_sections as L
FAIL=[]
def ck(n,c,d=''):
    print(('PASS  ' if c else 'FAIL  ')+n+(('  '+d) if d and not c else ''))
    if not c: FAIL.append(n)
# a boss: floor rises then falls, then a far end wall
# a STEPPED boss, so several radii are breakpoints - a two-radius contour
# has exactly one and would prove nothing about the shape of the table
c=[(0.0,20.0),(-10.0,20.0),(-11.0,22.0),(-12.0,24.0),(-13.0,26.0),
   (-14.0,26.0),(-15.0,24.0),(-16.0,22.0),(-17.0,20.0),(-40.0,20.0)]
e=L.resume_envelope(c,1)
ck('an envelope is produced', len(e)>=2, '%d breakpoints'%len(e))
ck('levels descend', all(e[i][0]>e[i+1][0] for i in range(len(e)-1)))
ck('IT NEVER MOVES FORWARD as the level descends',
   all(e[i+1][1]<=e[i][1]+1e-9 for i in range(len(e)-1)),
   'a level resuming in front of the one above it is a rapid through metal')
ck('every level under the boss top resumes BEHIND the boss',
   all(z <= -13.0 for _l, z in e), repr(e))
ck('   and a deeper level resumes further back than a shallower one',
   e[-1][1] <= e[0][1], repr(e))
# monotone must survive a NON-monotone raw contour - the real failure
c2=[(0.0,20.0),(-10.0,20.0),(-12.0,26.0),(-13.0,25.0),(-13.2,25.4),
    (-14.0,26.0),(-16.0,20.0),(-40.0,20.0)]
e2=L.resume_envelope(c2,1)
ck('   and still never moves forward on a wobbly contour',
   all(e2[i+1][1]<=e2[i][1]+1e-9 for i in range(len(e2)-1)), repr(e2))
ck('a flat contour has no resume at all', L.resume_envelope(
    [(0.0,20.0),(-10.0,20.0)],1)==[])
ck('the table fits its window',
   L.RESUME_BASE+2*len(e)<=L.RESUME_TOP)
print()
if FAIL:
    print('FAILED: %d'%len(FAIL)); sys.exit(1)
print('The resume envelope is monotone, so a plunge cannot pass through metal.')
