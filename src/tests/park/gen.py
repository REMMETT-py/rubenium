import random, collections, json
N=6
def parse(s):
    cars={}
    for i,ch in enumerate(s):
        if ch!='.': cars.setdefault(ch,[]).append(i)
    out={}
    for k,c in cars.items():
        horiz = c[1]-c[0]==1
        out[k]=(horiz, len(c), c[0])
    return out
def render(cars):
    g=['.']*36
    for k,(h,l,p) in cars.items():
        for j in range(l): g[p+(j if h else j*6)]=k
    return ''.join(g)
def moves(s):
    cars=parse(s)
    for k,(h,l,p) in cars.items():
        r,c=divmod(p,6)
        for d in (-1,1):
            step=1
            while True:
                if h:
                    nc=c+d*step
                    if nc<0 or nc+l>6: break
                    cell = r*6+(nc if d<0 else nc+l-1)
                else:
                    nr=r+d*step
                    if nr<0 or nr+l>6: break
                    cell=(nr if d<0 else nr+l-1)*6+c
                if s[cell]!='.': break
                nc2=dict(cars); nc2[k]=(h,l,p+(d*step if h else d*step*6))
                yield (k,d*step), render(nc2)
                step+=1
def solved(s): return s[16]=='A' and s[17]=='A'
def solve(s):
    seen={s:None}; q=collections.deque([s])
    while q:
        x=q.popleft()
        if solved(x):
            path=[];
            while seen[x]: x,m=seen[x]; path.append(m)
            return path[::-1]
        for m,y in moves(x):
            if y not in seen: seen[y]=(x,m); q.append(y)
    return None
def rand_puzzle(rng, ncars):
    g=['.']*36; cars={}
    c=rng.randint(0,2); g[12+c]=g[13+c]='A'
    letters="BCDEFGHIJKLMNOPQ"; li=0
    tries=0
    while li<ncars and tries<400:
        tries+=1
        h=rng.random()<0.5; l=3 if rng.random()<0.3 else 2
        if h:
            r=rng.choice([0,1,3,4,5]); c=rng.randint(0,6-l); cells=[r*6+c+j for j in range(l)]
        else:
            r=rng.randint(0,6-l); c=rng.randint(0,5); cells=[(r+j)*6+c for j in range(l)]
        if all(g[x]=='.' for x in cells):
            for x in cells: g[x]=letters[li]
            li+=1
    return ''.join(g)
rng=random.Random(7); levels=[]
want={(6,10):12,(11,16):14,(17,24):10,(25,60):6}
got=collections.Counter()
for _ in range(60000):
    p=rand_puzzle(rng, rng.randint(8,13))
    if solved(p): continue
    sol=solve(p)
    if not sol: continue
    n=len(sol)
    for (a,b),k in want.items():
        if a<=n<=b and got[(a,b)]<k and p not in [l[0] for l in levels]:
            got[(a,b)]+=1; levels.append((p,n)); break
    if sum(got.values())>=sum(want.values()): break
levels.sort(key=lambda x:x[1])
print(len(levels), [n for _,n in levels])
json.dump(levels, open('/tmp/park/levels.json','w'))
