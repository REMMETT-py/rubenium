"""Writes supabase/migrations/087_v92_golf_bots.sql from overhaul/golf/bot_odds.json (made by bots.py)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "supabase", "migrations", "087_v92_golf_bots.sql")
LEVELS = ("easy", "medium", "hard", "pro")

HEAD = """-- Rubenium 9.2: Mini Golf bots with four levels. Made by overhaul/golf/make_087.py from overhaul/golf/bot_odds.json
-- (do not edit by hand: run overhaul/golf/bots.py, then make_087.py). Safe to run twice.
--
-- Whoever opens a Mini Golf room picks the level of the bots in the empty seats: Easy, Medium, Hard or Professional
-- (rb_golf_parties.bot_level 0-3; a bot seat's skill is its level). The strokes a bot takes on a hole come from
-- rb_golf_bot_odds: every hole was played many times with the real ball physics by a bot of each level that searches
-- its shots (Hard and Professional look one shot ahead and go for the shots that still drop when hit a little off)
-- and then hits them with the error of its level. Holes 101-160 are the same holes mirrored, so they share the odds.
-- Bots never take the pot, as before.
begin;

create table if not exists public.rb_golf_bot_odds (hole integer not null, level text not null, p smallint[] not null,
                                                     primary key (hole, level));
alter table public.rb_golf_bot_odds enable row level security;
revoke all on public.rb_golf_bot_odds from public, anon, authenticated;
truncate public.rb_golf_bot_odds;
insert into public.rb_golf_bot_odds (hole, level, p) values
%s;

alter table public.rb_golf_parties add column if not exists bot_level smallint not null default 1;

-- a bot's plan for a hole: how many strokes (drawn from the hole's odds for its level) and how fast it plays
create or replace function public.rb_party_bot_plan2(hid integer, skill double precision) returns jsonb
language plpgsql volatile security definer set search_path to '' as $$
declare lv integer := greatest(0, least(3, round(coalesce(skill, 1))::int)); odds smallint[]; r float8; acc float8 := 0;
        tot float8; n integer := 6;
begin
    select p into odds from public.rb_golf_bot_odds
     where hole = coalesce(hid, 0) %% 100 and level = (array['easy', 'medium', 'hard', 'pro'])[lv + 1];
    if odds is null then return public.rb_party_bot_plan(skill); end if;
    tot := (select sum(x) from unnest(odds) x);
    r := public.rb_rand() * greatest(tot, 1);
    for k in 1 .. 6 loop
        acc := acc + odds[k];
        if r < acc then n := k; exit; end if;
    end loop;
    return jsonb_build_object('n', n, 'every', (array[4.5, 4.0, 3.5, 3.0])[lv + 1] + public.rb_rand() * (array[4.5, 3.5, 2.5, 1.5])[lv + 1],
                              'level', lv);
end $$;

-- the live party functions: bot seats get the room's level and plans from the odds
do $patch$
declare src text; out_ text;
begin
    select pg_get_functiondef('public.rb_party_start(uuid)'::regprocedure) into src;
    out_ := replace(src, 'names[k + 1], public.rb_rand(), array_fill', 'names[k + 1], g.bot_level::float8, array_fill');
    out_ := replace(out_, 'set plan = public.rb_party_bot_plan(skill) where', 'set plan = public.rb_party_bot_plan2(g.holes[1], skill) where');
    if out_ <> src then execute out_; end if;
    select pg_get_functiondef('public.rb_party_tick(uuid)'::regprocedure) into src;
    out_ := replace(src, 'then public.rb_party_bot_plan(skill) end', 'then public.rb_party_bot_plan2(g.holes[g.hole + 1], skill) end');
    if out_ <> src then execute out_; end if;
    select pg_get_functiondef('public.rb_party_json(uuid, uuid)'::regprocedure) into src;
    if position('''bot_level''' in src) = 0 then
        execute replace(src, '''holes'', to_jsonb(g.holes),', '''holes'', to_jsonb(g.holes), ''bot_level'', g.bot_level,');
    end if;
    select pg_get_functiondef('public.rb_party_list()'::regprocedure) into src;
    if position('''bot_level''' in src) = 0 then
        execute replace(src, '''size'', g.size, ''bet'', g.bet,', '''size'', g.size, ''bet'', g.bet, ''bot_level'', g.bot_level,');
    end if;
end $patch$;

-- open a room with a bot level (the old three-argument call keeps Medium)
create or replace function public.rb_party_create(size integer, bet integer, holes integer, bot_level integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare r jsonb;
begin
    if bot_level is null or bot_level not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
    r := public.rb_party_create(size, bet, holes);
    update public.rb_golf_parties set bot_level = rb_party_create.bot_level where id = (r ->> 'id')::uuid;
    return public.rb_party_json((r ->> 'id')::uuid, auth.uid());
end $$;

revoke all on function public.rb_party_bot_plan2(integer, double precision) from public, anon, authenticated;
revoke all on function public.rb_party_create(integer, integer, integer, integer) from public, anon;
grant execute on function public.rb_party_create(integer, integer, integer, integer) to authenticated;

commit;
"""


def main() -> None:
    d = json.load(open(os.path.join(HERE, "bot_odds.json")))
    rows = []
    for hid, levels in sorted(d["odds"].items(), key=lambda kv: int(kv[0])):
        for lv in LEVELS:
            rows.append("(%d, '%s', '{%s}')" % (int(hid), lv, ",".join(str(int(x)) for x in levels[lv])))
    open(OUT, "w").write(HEAD % ",\n".join(rows))
    print(OUT, len(rows), "rows")


if __name__ == "__main__":
    main()
