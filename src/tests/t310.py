import os, sys, time, shutil, json, subprocess, traceback
src=open('/tmp/t300.py').read()
head=src[:src.index('pump(3000); ec.poll_live()')]
exec(head.replace('O="/tmp/shots300/"','O="/tmp/shots310/"'))
exec(open('/tmp/park/gen.py').read().split("rng=random.Random")[0])
pump(3000); ec.poll_live(); pump(800)
w.expand(); pump(900); w.goto("themes"); pump(1300); shot("01_theme")
w.goto("games"); pump(1300); shot("02_lobby")
w.page()._show_park(True); pump(2500); shot("03_parking")
pk=w.page().park; print("park:", pk.state, pk.best, pk.layout_)
sol=solve(pk.layout_)
for c,d in sol[:-1]:
    cells=pk.cars()[c]; h=cells[1]-cells[0]==1; st=1 if h else 6
    for x in cells: pk.grid[x]="."
    for x in cells: pk.grid[x+d*st]=c
    pk.moves.append({"c":c,"d":d})
pk.update(); pump(300); shot("04_parking_mid")
sql(f"update rb_park set at = at - interval '90 seconds' where id='{pk.round}'")
c,d=sol[-1]; cells=pk.cars()[c]; h=cells[1]-cells[0]==1; st=1 if h else 6
for x in cells: pk.grid[x]="."
for x in cells: pk.grid[x+d*st]=c
pk.moves.append({"c":c,"d":d}); pk._out(); pump(2500); shot("05_parking_done"); print("park result:", pk.result)
w.page()._show_park(False); pump(600)
sql("update rb_rounds set at=now()")
w.goto("friends"); pump(1500); w.page().open_profile("Max"); pump(3000); shot("06_max")
w.goto("admin"); pump(1500); a.admin_tab=1; a.admin_player="Max"; a.reload_page(); pump(2500)
pg=w.page(); b=[x for x in pg.findChildren(A.Button) if x._text in ("Coins / keys",)][0]; b.click(); pump(400)
f=a._form; print("form open:", f.isVisible()); f.edits["c"].setText("777"); f.edits["k"].setText("3"); f._go(); pump(2500)
print("Max coins/keys:", sql("select coins||'/'||keys from profiles where username='Max'"))
a.admin_item="badge:sun:lava"; pg=w.page(); b=[x for x in pg.findChildren(A.Button) if x._text=="Give item or case"][0]; b.click(); pump(400)
f=a._form; f.edits["n"].setText("2"); f._go(); pump(2500)
print("Max sun lava:", sql("select count(*) from rb_items i join profiles p on p.id=i.owner where p.username='Max' and item='badge:sun:lava'"))
a.admin_tab=4; a.admin_item=""; a.reload_page(); pump(1200); pg=w.page()
pg._new_giveaway(); pump(300); f=a._form; f.edits["k"].setText("pièces"); f._go(); pump(2500)
print("giveaways:", sql("select count(*) from rb_giveaways"))
pg=w.page(); pg._new_sale(); pump(300); f=a._form; f._go(); pump(2000); print("sales:", sql("select count(*) from rb_sales"))
a.shop_tab=1; a.shop_kind=0; a.shop_design="orbit"; w.goto("themes"); pump(1500); shot("07_orbit_colours")
print("gold variants offered:", [k for k in ec.catalog if k.startswith("ball:orbit:")])
print("ERRORS:", len(errors)); [print(e[-1200:]) for e in errors[:4]]
a.shutdown()
