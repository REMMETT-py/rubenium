-- 9.1: five tiers kept once reached, the forge by tier, animation versions need the base, one account per PC ever,
-- needs_live_snapshot (the catalog, the cases and the tables in play come from the live server)
-- and the 9.1 fresh start (0 coins and keys, only Common and Rare basic items and the OG tag kept, equip fixed).
begin;
do $$
declare a uuid := t.player('Alice', 0, 0); b uuid := t.player('Bob', 0, 0); r jsonb; err text; f jsonb;
begin
    -- tiers
    perform t.act(a);
    r := public.rb_my_tier();
    reset role;
    assert r ->> 'name' = 'Poor' and (r ->> 'next')::numeric = 10000, 'starts Poor: ' || r::text;
    update public.profiles set coins = 80000 where id = a;
    perform t.act(a);
    r := public.rb_my_tier();
    reset role;
    assert r ->> 'name' = 'Investor' and (r ->> 'mult')::numeric = 1.8, 'Investor at 80 000: ' || r::text;
    assert (r -> 'forge' ->> 'cap')::int = 8 and (r -> 'forge' ->> 'price')::int = 400, 'forge by tier: ' || r::text;
    update public.profiles set coins = 100 where id = a;
    r := public.rb_tier(a);
    assert r ->> 'name' = 'Investor', 'the tier is kept below its line: ' || r::text;
    assert (select tier_floor from public.profiles where id = a) = 2, 'floor saved';
    assert public.rb_tier_mult(a) = 1.8, 'the multiplier is kept too';

    -- animations: a version needs the base, cases never give versions
    update public.profiles set coins = 2000000 where id = a;
    perform t.act(a);
    err := t.try('select public.rb_buy(''anim:rift-gold'', ''x1'')');
    assert err like '%rb_need_base%', 'version needs the base: ' || err;
    perform public.rb_buy('anim:rift', 'x2');
    r := public.rb_buy('anim:rift-gold', 'x3');
    reset role;
    assert (r ->> 'item') = 'anim:rift-gold', 'version bought after the base';
    assert (select price from public.rb_catalog where id = 'anim:rift-gold') = 240000, 'gold is 4x';
    assert (select rarity from public.rb_catalog where id = 'anim:eclipse') = 'exotic', 'Eclipse is Mythic';
    assert (select count(*) from generate_series(1, 400) g
             where position('-' in coalesce(public.rb_pick_weighted(array['anim'], 3, null), '')) > 0) = 0,
           'cases never pick a version';

    -- cases
    assert (select price from public.rb_cases where id = 'profile') = 20000, 'Crown Vault 20 000';
    assert exists (select 1 from public.rb_cases where id = 'lines' and mode = 'kinds:line'), 'Line Case';
    assert (select mode from public.rb_cases where id = 'style') = 'kinds:ball', 'Ball Case';

    -- one account per PC, ever
    insert into public.rb_devices (device, owner) values ('a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4', null)
        on conflict (device) do update set owner = null;
    assert (public.rb_device_free('a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4') ->> 'free')::boolean = false, 'a used PC stays used';

    -- the fresh start
    update public.profiles set xp = 5000, level = 7, keys = 9, equip = '{"frame": "frame:wings-lime", "tag": "tag:og"}'
     where id = b;
    insert into public.rb_items (owner, item, origin) values (b, 'frame:wings-lime', 'shop'), (b, 'tag:og', 'og'),
        (b, 'badge:cat:grey', 'case'), (b, 'badge:cat:pink', 'case');
    insert into public.rb_items (owner, item, origin)
        select b, c.id, 'shop' from public.rb_catalog c where c.rarity = 'standard' and c.kind = 'banner' limit 1;
    insert into public.rb_items (owner, item, origin)
        select b, c.id, 'shop' from public.rb_catalog c where c.rarity = 'special' and c.kind = 'banner' limit 1;
    perform t.act(a);
    err := t.try('select public.rb_reset_economy_91()');
    assert err like '%permission denied%', 'players cannot reset: ' || err;
    reset role;
    r := public.rb_reset_economy_91();
    assert t.coins(a) = 0 and t.coins(b) = 0, 'everyone at 0 coins';
    assert (select keys = 0 and level = 7 and xp = 5000 and tier_floor = 0 from public.profiles where id = b), 'level kept';
    assert (select tier_floor from public.profiles where id = a) = 0, 'tiers start again';
    assert exists (select 1 from public.rb_items where owner = b and item = 'tag:og'), 'OG tag kept';
    assert exists (select 1 from public.rb_items where owner = b and item = 'badge:cat:grey'), 'basic Common kept';
    assert not exists (select 1 from public.rb_items where owner = b and item = 'badge:cat:pink'), 'coloured gone';
    assert not exists (select 1 from public.rb_items where owner = b and item = 'frame:wings-lime'), 'Legendary gone';
    assert not exists (select 1 from public.rb_items i join public.rb_catalog c on c.id = i.item
                        where i.owner = b and c.rarity = 'special'), 'Epic gone';
    assert exists (select 1 from public.rb_items i join public.rb_catalog c on c.id = i.item
                    where i.owner = b and c.rarity = 'standard' and c.kind = 'banner'), 'Common banner kept';
    assert not exists (select 1 from public.rb_items where owner = a and item like 'anim:%'), 'animations gone';
    assert (select equip from public.profiles where id = b) = '{"tag": "tag:og"}'::jsonb,
           'gone items taken off: ' || (select equip::text from public.profiles where id = b);
    assert (select count(*) from public.rb_bak91_items where owner = b) = 6, 'backup kept';
    err := t.try('select public.rb_reset_economy_91()');
    assert err like '%rb_already_done%', 'only once: ' || err;
end $$;
rollback;
