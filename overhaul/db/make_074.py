"""Builds 074_v80_security.sql from overhaul/db/074_template.sql, overhaul/golf/sim.sql and the holes in Rubenium.py.
Usage: python overhaul/db/make_074.py OUT_DIR"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "golf"))
import holes  # noqa: E402

out_dir = sys.argv[1]
tpl = open(os.path.join(HERE, "074_template.sql"), encoding="utf-8").read()
sim = open(os.path.join(HERE, "..", "golf", "sim.sql"), encoding="utf-8").read()
sql = tpl.replace("@@SIM@@", sim.strip()).replace("@@HOLES@@", holes.sql_rows())
path = os.path.join(out_dir, "074_v80_security.sql")
open(path, "w", encoding="utf-8").write(sql)
print(path, len(sql), "bytes")

# 074_down.sql: the functions exactly as the live server had them (private snapshot), the grants from rb_bak74_grants.
BASE = os.environ.get("RB_FUNCTIONS", "/mnt/project-files/overhaul/private/baseline/functions.json")
import json  # noqa: E402

defs = {x["s"]: x["d"] for x in json.load(open(BASE))}
old = ["rb_golf_shot(uuid,integer,double precision,double precision,double precision,double precision,double precision,double precision,boolean)",
       "rb_party_shot(uuid,integer,double precision,double precision,double precision,double precision,double precision,double precision,boolean)",
       "rb_golf_solo_shot(uuid,integer,double precision,double precision,boolean)",
       "rb_done(uuid,text)", "rb_reset_ask(text,text,text)", "rb_need_admin()"]
body = "\n\n".join(defs[s].rstrip().rstrip(";") + ";" for s in old)
down = f"""-- Undoes 074_v80_security.sql: the functions as they were, the grants as they were (kept in rb_bak74_grants).
-- One transaction, safe to run twice. Made by overhaul/db/make_074.py.
begin;
{body}

drop function if exists public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                 double precision, double precision, double precision, boolean);
drop function if exists public.rb_golf_roll(integer, jsonb, float8, float8, float8, float8);
drop function if exists public.rb_golf_sim(integer, float8, float8, float8, float8);
drop table if exists public.rb_golf_hole_defs;
drop function if exists public.rb_admin_step_status();
drop function if exists public.rb_admin_step_check(text);
drop function if exists public.rb_admin_step_set(text, text);
drop function if exists public.rb_admin_step_session();
drop table if exists public.rb_admin_step;
delete from public.rb_config where key = 'admin_step_all';

alter default privileges in schema public grant execute on functions to anon;
alter default privileges in schema public grant insert, update, delete, truncate, references, trigger on tables to anon, authenticated;
do $g$
declare r record;
begin
    if to_regclass('public.rb_bak74_grants') is null then return; end if;
    for r in select * from public.rb_bak74_grants where kind = 'function' and role in ('public', 'anon')
               and to_regprocedure(obj) is not null loop
        execute format('grant execute on function %s to %s', r.obj, r.role);
    end loop;
    for r in select * from public.rb_bak74_grants where kind = 'table' and to_regclass(obj) is not null loop
        execute format('grant %s on %s to %I', r.priv, r.obj, r.role);
    end loop;
    if to_regclass('public.rb_bak63_cases') is not null then
        execute 'alter table public.rb_bak63_cases disable row level security';
    end if;
    if to_regclass('public.rb_bak63_case_stock') is not null then
        execute 'alter table public.rb_bak63_case_stock disable row level security';
    end if;
end $g$;
alter table public.rb_swaps drop constraint if exists rb_swaps_safe_names;
drop table if exists public.rb_bak74_grants;
commit;
"""
path = os.path.join(out_dir, "074_down.sql")
open(path, "w", encoding="utf-8").write(down)
print(path, len(down), "bytes")
