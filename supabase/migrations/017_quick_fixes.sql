-- Rubenium 017 (3.0.0 fixes): the OG tag can no longer be earned (owners keep it), the OG event is over (rewards
-- already given are kept), item worth follows the shop price everywhere (trades, collection worth, leaderboards,
-- the market), quick sell pays more for badges, and 16 mini golf holes (each can also be played mirrored).
-- Run it once in Supabase -> SQL Editor (after 016). Running it again changes nothing.

-- ================================================================ no new OG tags, no more OG event
insert into public.rb_config (key, value) values ('og_until', 0), ('og_event_until', 0), ('quick_worth_share', 0.05)
on conflict (key) do update set value = excluded.value;

-- ================================================================ what an item is worth (same rule as the app)
-- sold in the shop: its shop price. Titanium and Gold badges: 50 x their value. Mythic badges: 400 x their value.
create or replace function public.rb_worth(what text) returns bigint
language sql stable security definer set search_path = '' as $$
    select coalesce(c.price::bigint,
                    c.value::bigint * case when c.kind = 'badge' and c.rarity = 'exotic' then 400
                                           when c.kind = 'badge' and c.cls >= 3 then 50 else 1 end)
      from public.rb_catalog c where c.id = what $$;

-- market estimate: recent sales, else the worth
create or replace function public.rb_estimate(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select least(200000000, coalesce((select percentile_disc(0.5) within group (order by s.price)
                       from (select l.price from public.rb_listings l
                              where l.what = rb_estimate.what and l.state = 'sold'
                              order by l.sold_at desc limit 15) s),
                    public.rb_worth(what), 0))::int $$;

-- collection worth (profiles) and the Worth leaderboard
do $$ declare f text; src text; begin
    foreach f in array array['rb_stats', 'rb_leaders'] loop
        select pg_get_functiondef(p.oid) into src from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = f;
        if src is not null and position('sum(c.value)' in src) > 0 then
            execute replace(src, 'sum(c.value)', 'sum(public.rb_worth(c.id))');
        end if;
    end loop;
end $$;

-- quick sell: a quarter of the value, or 5% of the worth for badges, whichever is more
do $$ declare src text; begin
    select pg_get_functiondef(p.oid) into src from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'rb_quick_value';
    if src is not null and position('quick_worth_share' in src) = 0 then
        execute replace(src, E'pay := floor(c.value * public.rb_cfg(''quick_share''))::int;',
            E'pay := least(2000000000, greatest(floor(c.value * public.rb_cfg(''quick_share'')),\n'
            || E'           case when c.kind = ''badge'' then floor(public.rb_worth(c.id) * coalesce(public.rb_cfg(''quick_worth_share''), 0)) else 0 end))::int;');
    end if;
end $$;

-- ================================================================ mini golf: 16 holes, each one also mirrored
create or replace function public.rb_golf_pick() returns integer[]
language sql volatile security definer set search_path = '' as $$
    select array_agg(h) from (
        select h + case when public.rb_rand() < 0.5 then 100 else 0 end as h
          from generate_series(1, 16) h order by public.rb_rand() limit 3) x $$;

do $$ declare src text; begin
    select pg_get_functiondef('public.rb_golf_invite(text, integer)'::regprocedure) into src;
    if position('rb_golf_pick' in src) = 0 then
        execute replace(src,
            'select array_agg(h) into hs from (select h from generate_series(1, 8) h order by public.rb_rand() limit 3) x;',
            'hs := public.rb_golf_pick();');
    end if;
end $$;

do $$ declare f text; begin
    foreach f in array array['rb_worth(text)', 'rb_golf_pick()'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
end $$;

insert into public.rb_config (key, value) values ('min_build', 2026111710)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
