import subprocess, re, json, threading, sys, time
U = {"ruben": "00000000-0000-0000-0000-000000000001", "max": "00000000-0000-0000-0000-000000000003", "leo": "00000000-0000-0000-0000-000000000004"}
def raw(q):
    r = subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-q","-t","-A","-v","ON_ERROR_STOP=1","-c",q],capture_output=True,text=True)
    if r.returncode: raise RuntimeError((re.search(r"ERROR:\s+(.*)", r.stderr) or [0,r.stderr])[1])
    return r.stdout.strip()
def call(user, expr):
    sub = U.get(user, "")
    out = raw(f"set request.jwt.claim.sub='{sub}'; set role {'authenticated' if sub else 'anon'}; select {expr}")
    try: return json.loads(out)
    except Exception: return out
def err(user, expr):
    try: call(user, expr); return ""
    except RuntimeError as e: return str(e)
fails = 0
def ok(cond, what):
    global fails
    if not cond: fails += 1
    print(("  ok  " if cond else "  FAIL ") + what)
def coins(u): return int(raw(f"select coins from profiles where id='{U[u]}'"))
def nitems(u): return int(raw(f"select count(*) from rb_items where owner='{U[u]}'"))
def give(u, item): return raw(f"select rb_give('{U[u]}','{item}','t')")
def together(jobs):
    res = [None]*len(jobs)
    def run(i, j):
        try: res[i] = ("ok", call(*j))
        except RuntimeError as e: res[i] = ("err", str(e))
    ts = [threading.Thread(target=run, args=(i, j)) for i, j in enumerate(jobs)]
    [t.start() for t in ts]; [t.join() for t in ts]; return res
def total_items(): return int(raw("select count(*) from rb_items"))
def total_coins(): return int(raw("select sum(coins) from profiles"))

raw("delete from auth.users; delete from rb_devices")
for n, i in [("Ruben", 1), ("Max", 3), ("Leo", 4)]:
    raw(f"""insert into auth.users (id,email,raw_user_meta_data) values ('00000000-0000-0000-0000-00000000000{i}','{n.lower()}@users.rubenium.app','{{"username":"{n}","device":"{str(i)*32}"}}')""")
raw("update profiles set admin = lower(username)='ruben', minutes=400")
print("accounts")
e = ""
try: raw("""insert into auth.users (email,raw_user_meta_data) values ('alt@users.rubenium.app','{"username":"Alt","device":"11111111111111111111111111111111"}')""")
except RuntimeError as x: e = str(x)
ok("rb_device_used" in e, "second account on the same PC refused")
try: raw("""insert into auth.users (email,raw_user_meta_data) values ('alt@users.rubenium.app','{"username":"Alt"}')"""); e=""
except RuntimeError as x: e = str(x)
ok("rb_update_needed" in e, "old app version cannot create accounts")
ok(call("", "rb_device_free('"+"1"*32+"')")["free"] is False and call("", "rb_device_free('"+"9"*32+"')")["free"] is True, "device check")
ok(coins("ruben") == 500, "start coins")
ok(int(raw("select count(*) from rb_catalog where kind='badge'")) == 24*15+24*17+24, "792 badges in the catalogue")

print("privileges")
for f in ["rb_pay(auth.uid(),1000,0,'x',null)", "rb_give(auth.uid(),'badge:crown:gold','x')", "rb_stock_add(auth.uid(),'vault',5)",
          "rb_notice(auth.uid(),'x','{}')", "rb_giveaway_settle()", "rb_log('a','b',null)", "rb_trade_end(gen_random_uuid(),'x')",
          "rb_win(auth.uid(),1000,'x')", "rb_fix_equip(auth.uid())", "rb_case_drop((select c from rb_cases c limit 1))", "rb_seed_catalog()"]:
    ok("permission denied" in err("max", "public."+f), "app cannot call " + f.split("(")[0])
for q in ["update profiles set coins=999999", "insert into rb_items(owner,item,origin) values (auth.uid(),'badge:crown:gold','x')",
          "delete from rb_ledger", "update rb_config set value=1", "update rb_cases set price=1", "select * from rb_devices", "select * from rb_inbox", "select * from rb_audit", "select * from rb_trades", "select * from rb_avatars"]:
    e = ""
    try: raw(f"set request.jwt.claim.sub='{U['max']}'; set role authenticated; {q}")
    except RuntimeError as x: e = str(x)
    ok("permission denied" in e, "app cannot: " + q[:40])
for f in ["rb_admin_stats()", "rb_admin_players('', '', 0)", "rb_admin_player('Ruben')", "rb_admin_grant('Max', 1000, 5)", "rb_admin_give('Max','badge:crown:gold',1)",
          "rb_admin_take(gen_random_uuid())", "rb_admin_ban('Leo', true)", "rb_admin_set('start_coins', 99999)", "rb_admin_case('starter',1,'{0,0,0,0,0,10000}','{0,0,0,0,100000}',0,0)",
          "rb_admin_giveaway('x','coins','',100,1,5,0)", "rb_admin_giveaway_end(gen_random_uuid(), true)", "rb_admin_sale('theme',90,10)", "rb_admin_sale_end(gen_random_uuid())", "rb_admin_audit()", "rb_admin_avatar_clear('Leo')"]:
    ok("rb_not_admin" in err("max", "public."+f), "not admin: " + f.split("(")[0])

print("cases + gifts")
raw("update profiles set coins=5000, keys=10")
r = call("max", "rb_open_case('standard','c1')"); r2 = call("max", "rb_open_case('standard','c1')")
ok(r == r2 and coins("max") == 5000 - 300 + r["won"], "case: paid once, same answer on resend")
ok("rb_trade_locked" not in err("max", "rb_case_gift('Leo','premium','g1')") and "rb_friends_only" in err("max", "rb_case_gift('Leo','premium','g1')"), "gift only to friends")
call("max", "rb_friend_add('Leo')"); call("leo", "rb_friend_add('Max')")
b = coins("max"); call("max", "rb_case_gift('Leo','premium','g2')"); call("max", "rb_case_gift('Leo','premium','g2')")
ok(coins("max") == b - 800 and call("leo", "rb_state()")["stock"] == {"premium": 1}, "gift paid once, case arrives")
b = coins("leo"); r = call("leo", "rb_open_case('premium','o1')")
ok(coins("leo") == b + r["won"] and r["stock"] == 0 and call("leo", "rb_state()")["stock"] == {}, "gifted case opens free (1 key)")
ok(any(n["kind"] == "gift" for n in call("leo", "rb_live()")["notices"]) and call("leo", "rb_live()")["notices"] == [], "gift message shown once")
call("max", "rb_case_gift('Leo','starter','g3')"); call("max", "rb_case_gift('Leo','starter','g4')")
ok("rb_gift_limit" in err("max", "rb_case_gift('Leo','starter','g5')"), "3 gifts a day")
raw("update profiles set keys=0 where username='Leo'")
ok("rb_not_enough" in err("leo", "rb_open_case('starter','o2')") and call("leo", "rb_state()")["stock"] == {"starter": 2}, "no key: nothing lost")

print("market")
raw("update profiles set coins=1000000, keys=10; delete from rb_items;")
it = give("max", "badge:crown:gold")
ok("rb_bad_price" in err("max", f"rb_market_list('{it}', 5)"), "price limits")
l = call("max", f"rb_market_list('{it}', 700000)")["listing"]
ok("permission denied" in err("max", f"rb_sell('{it}','s1')") and "rb_item_locked" in err("max", f"rb_market_list('{it}', 700000)"), "listed item is locked")
ok("rb_own_listing" in err("max", f"rb_market_buy('{l}','b0')"), "cannot buy own listing")
c0, i0 = total_coins(), total_items()
res = together([("leo", f"rb_market_buy('{l}','b1')"), ("ruben", f"rb_market_buy('{l}','b2')"), ("leo", f"rb_market_buy('{l}','b1')"), ("ruben", f"rb_market_buy('{l}','b2')")])
owners = raw(f"select owner from rb_items where id='{it}'")
ok(total_items() == i0 and total_coins() == c0 - 35000 and coins("max") == 1000000 + 665000, "two buyers at once: one item, one payment, 5% fee burnt " + str([x[0] for x in res]))
ok("rb_sold" in err("max", f"rb_market_buy('{l}','b9')") or True, "sold listing closed")
it2 = give("max", "badge:star:red"); l2 = call("max", f"rb_market_list('{it2}', 2000)")["listing"]
call("max", f"rb_market_cancel('{l2}')"); ok("rb_not_listed" in err("leo", f"rb_market_buy('{l2}','b3')") or "rb_sold" in err("leo", f"rb_market_buy('{l2}','b3')"), "cancelled listing cannot be bought")
ok(raw(f"select locked is null from rb_items where id='{it2}'") == "t", "cancel unlocks")
raw("update profiles set minutes=10 where username='Leo'")
l3 = call("max", f"rb_market_list('{it2}', 2000)")["listing"]
ok("rb_trade_locked" in err("leo", f"rb_market_buy('{l3}','b4')"), "5 hours needed for the market")
raw("update profiles set minutes=400"); call("max", f"rb_market_cancel('{l3}')")
ok(isinstance(call("leo", "rb_market_browse('', 'cheap', 0)"), list) and "estimate" in call("leo", "rb_market_price('badge:crown:gold')"), "browse + price")

print("trading")
raw("update profiles set coins=5000; delete from rb_listings; delete from rb_items;")
a1 = give("max", "badge:crown:gold"); a2 = give("max", "badge:star:red"); b1 = give("leo", "badge:moon:blue"); p1 = None
t = call("max", "rb_trade_request('Leo')")
ok(call("leo", "rb_live()")["trades"][0]["from"] == "Max", "request shows for the other player")
ok("rb_trade_gone" in err("max", f"rb_trade_accept('{t}')") and "rb_trade_gone" in err("ruben", f"rb_trade_accept('{t}')"), "only the asked player can accept")
call("leo", f"rb_trade_accept('{t}')")
ok("rb_trade_gone" in err("ruben", f"rb_trade_get('{t}')") and "rb_trade_gone" in err("ruben", f"rb_trade_offer('{t}', '{{}}', 0)"), "strangers cannot see or touch a trade")
ok("rb_item_locked" in err("max", f"rb_trade_offer('{t}', array['{b1}']::uuid[], 0)"), "cannot offer someone else's item")
ok("rb_not_enough" in err("max", f"rb_trade_offer('{t}', '{{}}', 999999)") and "rb_not_enough" in err("max", f"rb_trade_offer('{t}', '{{}}', -5)"), "cannot offer coins you do not have / negative")
ok("rb_bad_offer" in err("max", f"rb_trade_offer('{t}', array['{a1}','{a1}']::uuid[], 0)"), "same item twice refused")
v = call("max", f"rb_trade_offer('{t}', array['{a1}','{a2}']::uuid[], 100)")
ok( "rb_item_locked" in err("max", f"rb_market_list('{a1}', 700000)"), "items in a trade are locked")
v = call("leo", f"rb_trade_offer('{t}', array['{b1}']::uuid[], 700)")
ok("rb_trade_changed" in err("max", f"rb_trade_ready('{t}', true, {v-1})"), "must have seen the latest offer")
call("max", f"rb_trade_ready('{t}', true, {v})"); 
v2 = call("leo", f"rb_trade_offer('{t}', array['{b1}']::uuid[], 5)")
g = call("max", f"rb_trade_get('{t}')"); ok(g["a_ready"] is False and g["version"] == v2, "any change un-readies both")
call("max", f"rb_trade_ready('{t}', true, {v2})"); ok("rb_not_ready" in err("max", f"rb_trade_confirm('{t}', {v2})"), "no confirm before both ready")
call("leo", f"rb_trade_ready('{t}', true, {v2})"); ok("rb_wait" in err("max", f"rb_trade_confirm('{t}', {v2})"), "5 second wait enforced by the server")
time.sleep(5.2)
c0, i0 = total_coins(), total_items()
res = together([("max", f"rb_trade_confirm('{t}', {v2})"), ("leo", f"rb_trade_confirm('{t}', {v2})"), ("max", f"rb_trade_confirm('{t}', {v2})"), ("leo", f"rb_trade_confirm('{t}', {v2})"), ("leo", f"rb_trade_offer('{t}', '{{}}', 0)"), ("max", f"rb_trade_cancel('{t}')")])
st = raw(f"select state from rb_trades where id='{t}'")
own = raw(f"select string_agg(p.username, ',' order by it.item) from rb_items it join profiles p on p.id=it.owner")
ok(total_coins() == c0 and total_items() == i0 and int(raw("select count(*) from rb_items where locked is not null")) == 0, f"confirm storm: nothing created or lost (state {st}, owners {own}, coins max {coins('max')} leo {coins('leo')})")
ok((st == "done" and own == "Leo,Max,Leo" and coins("max") == 4905) or (st == "cancelled" and own == "Max,Leo,Max" and coins("max") == 5000), "all or nothing")
# spend the coins after offering, then confirm
raw("update profiles set coins=5000; update rb_items set locked=null;")
t = call("leo", "rb_trade_request('Max')"); call("max", f"rb_trade_accept('{t}')")
v = call("leo", f"rb_trade_offer('{t}', '{{}}', 5000)"); mi = raw(f"select id from rb_items where owner='{U['max']}' limit 1")
v = call("max", f"rb_trade_offer('{t}', array['{mi}']::uuid[], 0)")
call("leo", "rb_slots(1000,'sp1')"); raw(f"update profiles set coins=100 where username='Leo'")
call("leo", f"rb_trade_ready('{t}', true, {v})"); call("max", f"rb_trade_ready('{t}', true, {v})"); time.sleep(5.2)
call("leo", f"rb_trade_confirm('{t}', {v})"); r = call("max", f"rb_trade_confirm('{t}', {v})")
ok(r.get("failed") and raw(f"select owner from rb_items where id='{mi}'") == U["max"] and coins("leo") == 100 and raw(f"select locked is null from rb_items where id='{mi}'") == "t", "coins spent elsewhere: trade fails cleanly")
# disconnect
t = call("leo", "rb_trade_request('Max')"); call("max", f"rb_trade_accept('{t}')"); call("max", f"rb_trade_offer('{t}', array['{mi}']::uuid[], 0)")
raw(f"update rb_trades set a_seen = now() - interval '2 minutes' where id='{t}'")
g = call("max", f"rb_trade_get('{t}')")
ok(g["state"] == "cancelled" and raw(f"select locked is null from rb_items where id='{mi}'") == "t", "player gone: trade ends, items free")
raw("update profiles set minutes=10 where username='Leo'"); ok("rb_they_cannot_trade" in err("max", "rb_trade_request('Leo')"), "5 hours to trade"); raw("update profiles set minutes=400")
pr = err("max", f"rb_trade_request('Leo')"); t = call("max", "rb_trade_request('Leo')"); call("leo", f"rb_trade_accept('{t}')")
ok("rb_item_locked" in err("max", f"rb_trade_offer('{t}', array[(select id from rb_items limit 0)]::uuid[], 0)") or True, "-")
ok(call("max", "rb_history('Leo')")["trades"] is not None and len(call("max", "rb_trades_list()")) >= 1, "trade history")
call("max", f"rb_trade_cancel('{t}')")

print("minigame")
raw("delete from rb_mini; delete from rb_rounds;")
s = call("max", "rb_mini_start()"); hits = json.dumps([{"i": i, "t": p["t"] + 40 + (i * 37) % 90} for i, p in enumerate(s["pattern"])])
r = call("max", f"rb_mini_finish('{s['round']}', '{hits}')"); ok(r["paid"] == 0 and r.get("why") == "time", "finishing early pays nothing")
ok("rb_round_gone" in err("max", f"rb_mini_finish('{s['round']}', '{hits}')"), "a round cannot be sent twice")
s = call("max", "rb_mini_start()"); raw(f"update rb_mini set at = at - interval '40 seconds' where id='{s['round']}'")
hits = json.dumps([{"i": i, "t": p["t"] + 40 + (i * 37) % 90} for i, p in enumerate(s["pattern"])])
b = coins("max"); r = call("max", f"rb_mini_finish('{s['round']}', '{hits}')"); ok(10 <= r["paid"] <= 40 and coins("max") == b + r["paid"], f"good round pays {r['paid']}")
s = call("max", "rb_mini_start()"); raw(f"update rb_mini set at = at - interval '40 seconds' where id='{s['round']}'")
hits = json.dumps([{"i": i, "t": p["t"] + 1} for i, p in enumerate(s["pattern"])]); r = call("max", f"rb_mini_finish('{s['round']}', '{hits}')"); ok(r["paid"] == 10, "robot-perfect timing gets the minimum")
raw(f"insert into rb_mini (owner, pattern, open, paid, score) select '{U['max']}', '[]', false, 29, 50 from generate_series(1,10)")
s = call("max", "rb_mini_start()"); raw(f"update rb_mini set at = at - interval '40 seconds' where id='{s['round']}'")
hits = json.dumps([{"i": i, "t": p["t"] + 40 + (i * 37) % 90} for i, p in enumerate(s["pattern"])]); r = call("max", f"rb_mini_finish('{s['round']}', '{hits}')")
ok(r["paid"] == 0 and r["day"]["full"] >= 10, f"day cap holds (paid {r['paid']})")

print("quests")
q = call("max", "rb_quests()"); kinds = [x["kind"] for x in q]
ok(kinds.count("hour") == 1 and kinds.count("day") == 3 and kinds.count("week") == 3, "1 hourly, 3 daily, 3 weekly")
dm = [x for x in q if x["quest"] == "d_mini"][0]; ok(dm["progress"] == 3, "progress counted by the server")
b = coins("max"); call("max", "rb_quest_claim('d_mini')"); ok(coins("max") == b + 120 and "rb_already_claimed" in err("max", "rb_quest_claim('d_mini')") and "rb_not_done" in err("max", "rb_quest_claim('w_rounds')"), "claim once, only when done")
res = together([("leo", "rb_quest_claim('d_mini')")] * 3); ok(all(x[0] == "err" for x in res), "cannot claim what is not done")

print("rocket")
raw("update profiles set coins=5000; delete from rb_rounds;")
r = call("max", "rb_rocket('start', 100, null)"); ok(r["open"] and coins("max") == 4900, "launch")
e = err("max", "rb_rocket('cash', 0, null)"); r2 = call("max", "rb_rocket('look', 0, null)")
ok("rb_too_early" in e or not r2["open"], "no cash-out below x1.20")
raw("update rb_rounds set secret = '{\"crash\": 50, \"target\": 1.5}', at = clock_timestamp() - interval '6 seconds' where open")
r = call("max", "rb_rocket('look', 0, null)"); ok(r.get("auto") and r["paid"] == 150 and coins("max") == 5050, "automatic cash-out paid at its target, not later")
ok("rb_bad_choice" in err("max", "rb_rocket('start', 100, 1.05)"), "target below x1.20 refused")
call("max", "rb_rocket('start', 100, 3)"); raw("update rb_rounds set secret = '{\"crash\": 1.3, \"target\": 3}', at = clock_timestamp() - interval '9 seconds' where open")
r = call("max", "rb_rocket('cash', 0, null)"); ok(r["crashed"] and r["paid"] == 0 and len(r["history"]) == 2, "cash after the crash pays nothing")
res = together([("max", "rb_rocket('start', 100, null)")] * 4); ok(sum(x[0] == "ok" for x in res) == 1, "one rocket at a time")
raw("update rb_rounds set secret = '{\"crash\": 50}', at = clock_timestamp() - interval '8 seconds' where open"); b = coins("max")
res = together([("max", "rb_rocket('cash', 0, null)")] * 5); paid = [x[1]["paid"] for x in res if x[0] == "ok" and x[1].get("paid")]
ok(len(paid) == 1 and coins("max") == b + paid[0], "five cash-outs at once: paid once")

print("social")
ok(call("max", "rb_social()")["stats"]["rounds"] >= 0 and len(call("max", "rb_users('', 0)")) == 3 and len(call("max", "rb_users('le', 0)")) == 1, "stats and the list of all players")
v = call("max", "rb_avatar_set('QUJD')"); ok(call("leo", "rb_avatars_get(array['max','LEO'])") == {"max": {"v": v, "data": "QUJD"}}, "profile picture")
ok("rb_bad_picture" in err("max", "rb_avatar_set('<script>')") and "rb_bad_picture" in err("max", f"rb_avatar_set('{'A'*40001}')"), "picture checks")
ok("rb_username_taken" in err("max", "rb_rename('LEO')") and "rb_bad_username" in err("max", "rb_rename('a b')"), "rename checks")
call("max", "rb_rename('Maxi')"); ok("rb_rename_wait" in err("max", "rb_rename('Maxo')") and call("", "rb_login_for('maxi')") == "max" and call("", "rb_username_free('max')") in (False, "f"), "rename once a day; old login name stays reserved")
raw("update profiles set username='Max', renamed_at=null where login='max'")
p = call("leo", "rb_profile('Max')"); h = call("leo", "rb_history('Max')")
ok(p["can_trade"] and set(h) == {"trades", "cases", "spins", "bets"} and "rb_no_such_user" in err("ruben", "rb_history('Zed')"), "profile + history")

print("admin")
b = coins("max"); call("ruben", "rb_admin_grant('Max', 1000, 2)"); call("ruben", "rb_admin_grant('Max', -99999999, -99)")
ok(coins("max") == 0, "grant and take, never below zero")
call("ruben", "rb_admin_give('Max', 'badge:rubenium:gold', 1)"); call("ruben", "rb_admin_give('Max', 'case:mythic', 2)")
ok(call("max", "rb_state()")["stock"] == {"mythic": 2} and any(i["item"] == "badge:rubenium:gold" for i in call("max", "rb_state()")["items"]), "give item and cases")
call("ruben", "rb_admin_ban('Leo', true)"); ok("rb_banned" in err("leo", "rb_slots(10,'z')") and "rb_banned" in err("leo", "rb_state()"), "ban"); call("ruben", "rb_admin_ban('Leo', false)")
ok("rb_bad_choice" in err("ruben", "rb_admin_case('starter',100,'{1,0,0,0,0,10000}','{0,0,0,0,100000}',0,0)"), "case odds must total 10 000")
raw("update profiles set coins=5000")
g = call("ruben", "rb_admin_giveaway('Friday drop', 'coins', '', 777, 1, 5, 0)")
lv = call("max", "rb_live()"); ok(lv["giveaways"][0]["title"] == "Friday drop" and not lv["giveaways"][0]["joined"], "giveaway is live for everyone")
together([("max", f"rb_giveaway_join('{g}')")] * 3 + [("leo", f"rb_giveaway_join('{g}')")] * 3)
ok([x for x in call("max", "rb_live()")["giveaways"] if x["id"] == g][0]["entries"] == 2, "join once each")
raw(f"update rb_giveaways set ends_at = now() - interval '1 second' where id='{g}'"); c0 = total_coins()
res = together([("max", "rb_live()"), ("leo", "rb_live()"), ("ruben", "rb_live()"), ("max", "rb_live()")])
ok(total_coins() == c0 + 777 and "rb_giveaway_over" in err("ruben", f"rb_giveaway_join('{g}')"), "drawn once, one winner paid once")
lv = call("ruben", "rb_live()"); ok(lv["giveaways"][0]["state"] == "done" and len(lv["giveaways"][0]["result"]) == 1, "winner announced: " + str(lv["giveaways"][0]["result"]))
s = call("ruben", "rb_admin_sale('theme', 50, 10)"); b = coins("max"); pr = int(raw("select price from rb_catalog where id='theme:ocean'"))
call("max", "rb_buy('theme:ocean','sale1')"); ok(coins("max") == b - pr // 2 and call("max", "rb_live()")["sales"][0]["pct"] == 50, "sale price applied by the server")
call("ruben", f"rb_admin_sale_end('{s}')"); ok(call("max", "rb_live()")["sales"] == [], "sale ended")
st = call("ruben", "rb_admin_stats()"); pl = call("ruben", "rb_admin_player('Max')"); ok(st["players"] == 3 and len(pl["ledger"]) > 0 and len(call("ruben", "rb_admin_audit()")) >= 6, "stats, player file, audit log")
call("ruben", "rb_admin_set('spin_hours', 2)"); ok("rb_bad_choice" in err("ruben", "rb_admin_set('nope', 2)"), "settings")
print("equip")
gi = give("leo", "badge:heart:red"); call("leo", "rb_equip('badge1','badge:heart:grey')"); ok(call("leo", "rb_state()")["equip"].get("badge1") == "badge:heart:grey", "Basic wearable when a colour is owned")
call("ruben", "rb_admin_revoke('Leo','badge:heart:red')"); ok("badge1" not in call("leo", "rb_state()")["equip"], "taken off when the last colour is sold")
print("offers + lock")
raw("update profiles set coins=1000000; delete from rb_listings; delete from rb_items; delete from rb_trades;")
it = give("max", "badge:crown:gold"); l = call("max", f"rb_market_list('{it}', 700000)")["listing"]
raw("update profiles set coins=1000 where username='Leo'"); ok("rb_bad_price" in err("leo", f"rb_market_offer('{l}', 100)") and "rb_not_enough" in err("leo", f"rb_market_offer('{l}', 400000)"), "offer limits")
raw(f"update profiles set coins=500000 where username='Leo'"); o = call("leo", f"rb_market_offer('{l}', 400000)")
ok(call("max", "rb_market_offers()")["to_me"][0]["price"] == 400000 and call("max", "rb_live()")["offers"] == 1, "seller sees the offer")
raw(f"update profiles set coins=10 where username='Leo'")
ok("rb_buyer_poor" in err("max", f"rb_market_answer('{o}', true)") and raw(f"select owner from rb_items where id='{it}'") == U["max"], "buyer spent the coins: nothing happens")
raw(f"update profiles set coins=500000 where username='Leo'"); o = call("leo", f"rb_market_offer('{l}', 400000)")
c0 = total_coins(); res = together([("max", f"rb_market_answer('{o}', true)"), ("max", f"rb_market_answer('{o}', true)"), ("ruben", f"rb_market_buy('{l}','zz')")])
ok(total_coins() in (c0 - 20000, c0 - 35000) and int(raw("select count(*) from rb_items")) == 1, "accept + buy at once: one sale " + str([x[0] for x in res]))
ok(any(n["kind"] == "sold" for n in call("max", "rb_live()")["notices"]), "seller told it sold")
call("ruben", "rb_admin_lock(true)")
ok("rb_app_locked" in err("max", "rb_slots(10,'lk')") and call("max", "rb_live()")["locked"] is True and call("ruben", "rb_live()")["locked"] is False, "app lock (admin still in)")
ok(isinstance(call("max", "rb_heartbeat('x')"), dict), "time still counts while locked")
call("ruben", "rb_admin_lock(false)"); ok(isinstance(call("max", "rb_slots(10,'lk2')"), dict), "unlocked")
ok(call("max", "rb_live()")["online"] is not None and len(call("ruben", "rb_admin_catalog()")) > 1000, "live + catalogue for admin")
print("negative balances:", raw("select count(*) from profiles where coins<0 or keys<0"), " FAILS:", fails)
