-- Rubenium 019 (3.1 fixes): the Royal Case pays less, style cases need no key, and the market's usual price is never
-- far below what an item is worth (old cheap sales from before 3.0.0 pulled it down).
-- Run it once in Supabase -> SQL Editor (after 018). Running it again changes nothing.

-- Royal Case: more plain coins, fewer big badges, smaller coin drops (about 95% back at quick sell)
update public.rb_cases set odds = '{8300,0,900,600,190,10}', coin_min = 8000, coin_max = 44000 where id = 'royal';

-- style cases (balls, lines, fonts, themes, banners, frames): coins only, no key
do $$ declare src text; begin
    select pg_get_functiondef(p.oid) into src from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'rb_open_case';
    if position('kinds:%%'' then 0' in src) = 0 and position('case when gifted then 0 else -1 end' in src) > 0 then
        execute replace(src, 'case when gifted then 0 else -1 end',
                        'case when gifted or c.mode like ''kinds:%%'' then 0 else -1 end');
    end if;
end $$;

-- the usual price: recent sales, but never below the item's worth
create or replace function public.rb_estimate(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select least(200000000, greatest(
        coalesce((select percentile_disc(0.5) within group (order by s.price)
                    from (select l.price from public.rb_listings l
                           where l.what = rb_estimate.what and l.state = 'sold'
                           order by l.sold_at desc limit 15) s), 0),
        coalesce(public.rb_worth(what), 0)))::int $$;

insert into public.rb_config (key, value) values ('min_build', 2026111712)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
