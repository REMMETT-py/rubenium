import random, collections, json, sys, time
exec(open('/tmp/park/gen.py').read().split("rand_puzzle")[0].rsplit("def solve",1)[0])
exec("def rand_puzzle"+open('/tmp/park/gen.py').read().split("def rand_puzzle")[1].split("rng=random.Random")[0])
def hardest(s, cap=60000):
    seen={s}; q=[s]; adj={}
    i=0
    while i<len(q):
        x=q[i]; i+=1
        nb=[y for _,y in moves(x)]; adj[x]=nb
        for y in nb:
            if y not in seen: seen.add(y); q.append(y)
        if len(q)>cap: return None
    goals=[x for x in q if solved(x)]
    if not goals: return None
    dist={g:0 for g in goals}; dq=collections.deque(goals)
    while dq:
        x=dq.popleft()
        for y in adj[x]:
            if y not in dist: dist[y]=dist[x]+1; dq.append(y)
    far=max(dist, key=dist.get)
    return far, dist[far], dist
rng=random.Random(11); levels={}; t0=time.time()
bands={(5,9):10,(10,15):14,(16,24):12,(25,60):8}; got=collections.Counter()
while time.time()-t0<500 and sum(got.values())<sum(bands.values()):
    p=rand_puzzle(rng, rng.randint(9,13))
    r=hardest(p)
    if not r: continue
    far,n,dist=r
    # also take states of medium distance from the same family for easier bands
    for (a,b),k in bands.items():
        if got[(a,b)]>=k: continue
        cand=[x for x,d in dist.items() if a<=d<=b and not solved(x)]
        if cand:
            x=max(cand,key=dist.get) if (a,b)==(25,60) else rng.choice(cand)
            if x not in levels: levels[x]=dist[x]; got[(a,b)]+=1
            break
out=sorted(levels.items(), key=lambda x:x[1]); print(len(out), [n for _,n in out], round(time.time()-t0))
json.dump(out, open('/tmp/park/levels.json','w'))
