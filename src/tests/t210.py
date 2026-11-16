import json, sys, time
sys.argv=['x']
src=open('/tmp/t200.py').read(); exec(src[:src.index('print("accounts")')])
exec(open('/tmp/park/gen.py').read().split("rng=random.Random")[0])
raw("delete from auth.users; delete from rb_devices")
for n,i in (("Ruben",1),("Max",3)):
    raw(f"""insert into auth.users (id,email,raw_user_meta_data) values ('00000000-0000-0000-0000-00000000000{i}','{n.lower()}@users.rubenium.app','{{"username":"{n}","device":"{str(i)*32}"}}')""")
lv=json.loads(raw("select json_agg(json_build_object('id',id,'layout',layout,'best',best) order by id) from rb_park_levels"))
bad=0
for l in lv:
    sol=solve(l["layout"]); mv=json.dumps([{"c":c,"d":d} for c,d in sol])
    n=int(raw(f"select rb_park_play('{l['layout']}', '{mv}')"))
    if n!=l["best"] or len(sol)!=l["best"]: bad+=1
ok(bad==0, f"all {len(lv)} levels: computer solution accepted with the best move count")
L=lv[0]["layout"]
ok(raw(f"""select rb_park_play('{L}', '[{{"c":"A","d":5}}]')""")=="-1", "driving through cars refused")
ok(raw(f"""select rb_park_play('{L}', '[]')""")=="-1", "not solved = refused")
ok(raw(f"""select rb_park_play('{L}', '[{{"c":".","d":1}}]')""")=="-1", "empty square is not a car")
ok("permission denied" in err("max","rb_park_play('x','[]')"), "app cannot call the checker directly")
s=call("max","rb_park_start(1)"); sol=solve(s["layout"]); mv=json.dumps([{"c":c,"d":d} for c,d in sol])
r=call("max",f"rb_park_finish('{s['round']}', '{mv}')"); ok(r["paid"]==0 and r["why"]=="time", "instant solve (robot) pays nothing")
ok("rb_round_gone" in err("max",f"rb_park_finish('{s['round']}', '{mv}')"), "a round counts once")
s=call("max","rb_park_start(3)"); sol=solve(s["layout"]); mv=json.dumps([{"c":c,"d":d} for c,d in sol])
raw(f"update rb_park set at = at - interval '60 seconds' where id='{s['round']}'")
b=coins("max"); r=call("max",f"rb_park_finish('{s['round']}', '{mv}')"); ok(r["paid"]==40 and coins("max")==b+40, f"hard level solved perfectly pays 40 ({r['paid']})")
s=call("max","rb_park_start(2)"); sol=solve(s["layout"]); waste=[{"c":c,"d":d} for c,d in sol]
# add useless back-and-forth moves
c0=sol[0][0]; waste=[{"c":c0,"d":sol[0][1]},{"c":c0,"d":-sol[0][1]}]*3+waste
raw(f"update rb_park set at = at - interval '60 seconds' where id='{s['round']}'")
r=call("max",f"rb_park_finish('{s['round']}', '{json.dumps(waste)}')"); ok(15<=r["paid"]<30, f"extra moves pay less ({r['paid']} for {r['moves']} moves, best {r['best']})")
ok(any(q["quest"] in ("h_mini","d_mini") for q in call("max","rb_quests()")), "quests still there")
dm=[q for q in call("max","rb_quests()") if q["quest"]=="d_mini"][0]; ok(dm["progress"]==2, "Parking counts for the mini game quest")
ok(raw("select count(*) from rb_catalog where variant='gold' and kind in ('ball','line','font')")=="0", "no gold balls, lines or fonts in the shop")
print("FAILS", fails)
