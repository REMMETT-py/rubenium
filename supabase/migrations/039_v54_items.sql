-- ================================================================ Rubenium 5.4: six new Mythics and six new banners
-- Run when the 5.4 app is published (older apps draw these as plain circles). Safe to run again.
begin;
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select 'badge:' || b.base || ':' || v.var, 'badge', b.base, v.var, 'exotic', null, v.val, true, v.cls,
       round(v.lo + (v.hi - v.lo) * b.k, -3)::bigint, 0.9, false, v.bw
  from (values ('eclipse', 0.05), ('supernova', 0.2), ('infinity', 0.35), ('thunder', 0.5), ('omega', 0.65), ('vortex', 0.8)) b(base, k),
       (values ('black', 3, 15000, 10600000, 13000000, 6000000), ('white', 3, 15000, 10640000, 13040000, 6000000),
               ('gold', 4, 45000, 15000000, 18000000, 18000000), ('prime', 5, 240000, 21000000, 24000000, 96000000)) v(var, cls, val, lo, hi, bw)
on conflict (id) do nothing;

-- twelve Mythic designs; the Rubenium R stays 4 times rarer than any other
create or replace function public.rb_pick_mythic(klass integer)
 returns text language plpgsql security definer set search_path to '' as $function$
declare names text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium',
                              'eclipse', 'supernova', 'infinity', 'thunder', 'omega', 'vortex'];
        base text; var text;
begin
    base := names[public.rb_roll(array[4, 4, 4, 4, 4, 1, 4, 4, 4, 4, 4, 4]) + 1];
    var := case klass when 4 then 'gold' when 5 then 'prime'
                      else (array['black', 'white'])[floor(public.rb_rand() * 2)::int + 1] end;
    return 'badge:' || base || ':' || var;
end $function$;

insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
values ('banner:sunrise', 'banner', 'sunrise', '', 'standard', 3300, 400, true, 0, 1980, 0.85, false, 400),
       ('banner:bubbles', 'banner', 'bubbles', '', 'standard', 3400, 400, true, 0, 2040, 0.82, false, 400),
       ('banner:plasma', 'banner', 'plasma', '', 'rare', 9000, 1200, true, 0, 5400, 0.82, false, 1200),
       ('banner:rain', 'banner', 'rain', '', 'rare', 9200, 1200, true, 0, 5520, 0.8, false, 1200),
       ('banner:fireworks', 'banner', 'fireworks', '', 'special', 25000, 3500, true, 0, 15000, 0.8, false, 3500),
       ('banner:hyperspace', 'banner', 'hyperspace', '', 'epic', 66000, 9000, true, 0, 39600, 0.78, false, 9000)
on conflict (id) do nothing;
commit;
