-- ================================================================ Rubenium 5.3: luck fixed, fresh start
-- Applied on the live server on 21/11/2026. One transaction; every part is safe to run again (the reset happens once).
--
--   * Badge cases: the rarity of the design and the finish are rolled apart. Basic is the usual finish, Painted is
--     common enough, Shiny is rare (about 1 in 500 to 1 in 6 000 opens, 1 in 60 in the Shiny Case), Titanium very rare,
--     Gold extremely rare, Prismatic (Mythic only) the rarest of all. Every design has its own rarity: the best design
--     of each rarity is 10 times rarer than the most common one, and worth more. A case pays back about 75-90% of its
--     price on average and pays more than its price only about 1 open in 7 to 1 in 20.
--   * Cosmetics: from the least to the most special, prices only go up, and nothing is cheap. Cosmetic cases follow.
--   * Shop tax 33% (was 20%). Lucky case coins: 5% of opens, x2 (was 6%, x3). The daily case's badge is mostly Basic.
--   * Wave Rush: the first 100 m pay nothing (the start is walked for you).
--   * Jackpot: bots fill at most 2 seats with smaller stakes; the winner takes back their items and picks a third of the
--     others' items; what is taken from bots is worth at most 2 times what the winner put in. Entries 500 - 250 000.
--   * Fresh start (once): coins, keys, items, cases, levels, XP, market, trades, coinflips and jackpots start again.
--     Kept: accounts, friends, messages, hours played, streaks, every game score and leaderboard (Wave Rush, Block
--     Blast, mini games), the OG tag. OG players: 1 500 coins and the level 5 coupon, then the Prismatic Chest again
--     (5 000 coins, 25 keys, 750 XP) until 24/11/2026 00:00 Paris, only in the 5.3 app.
begin;

-- ================================================================ settings
insert into public.rb_config (key, value) values ('og_chest_coins', 5000), ('og_chest_keys', 25),
    ('jackpot_bot_seats', 2), ('jackpot_cap_x', 2), ('jackpot_max_worth', 250000), ('wave_free_x', 10000)
on conflict (key) do nothing;
update public.rb_config set value = 0.33 where key = 'shop_tax';
update public.rb_config set value = 5 where key = 'case_lucky_pct';
update public.rb_config set value = 2 where key = 'case_lucky_x';
update public.rb_config set value = 750 where key = 'og_chest_xp';
update public.rb_config set value = 500 where key = 'jackpot_min_worth';
update public.rb_catalog set value = 750 where id = 'coupon:ogchest';

-- ================================================================ catalog (once: cat_053)
do $$
begin
    if coalesce(public.rb_cfg('cat_053'), 0) <> 0 then return; end if;
    create table if not exists public.rb_bak53_catalog as select * from public.rb_catalog;
    alter table public.rb_bak53_catalog enable row level security;
    revoke all on public.rb_bak53_catalog from anon, authenticated;

    -- badges: every design has its own rarity. Inside each rarity the designs are ranked by worth; the most common is
    -- 10 times as likely as the best one. Worth follows the rarity (rarer designs are worth more; the average stays).
    with d as (
        select rarity, base, min(worth) filter (where cls = 0) bw, max(weight) filter (where cls = 0) gw
          from public.rb_catalog where kind = 'badge' and rarity in ('standard', 'rare', 'special', 'epic') and not limited
         group by rarity, base),
    r as (select *, row_number() over (partition by rarity order by bw, base) - 1 rk, count(*) over (partition by rarity) n from d),
    m as (select *, power(0.10, rk::numeric / greatest(1, n - 1)) mult from r),
    s as (select *, mult / sum(mult) over (partition by rarity) share from m),
    f as (select *, power(1 / share, 0.40) wf from s),
    z as (select *, sum(share * wf) over (partition by rarity) norm from f)
    update public.rb_catalog c
       set weight = z.mult * c.weight / z.gw,
           worth = round(c.worth * z.wf / z.norm, case when c.worth < 100000 then -1 else -3 end)
      from z where c.kind = 'badge' and c.rarity = z.rarity and c.base = z.base and not c.limited;

    -- cosmetics: from the least to the most special, prices only go up. Worth is 60% of the shop price.
    with lad(kind, rarity, lo, hi) as (values
        ('ball', 'standard', 300, 700), ('ball', 'rare', 1000, 2400), ('ball', 'special', 3000, 7500), ('ball', 'epic', 10000, 24000),
        ('line', 'standard', 300, 700), ('line', 'rare', 1000, 2400), ('line', 'special', 3000, 7500), ('line', 'epic', 10000, 24000),
        ('font', 'standard', 400, 800), ('font', 'rare', 1200, 2600), ('font', 'special', 3500, 7000), ('font', 'epic', 10000, 20000),
        ('theme', 'rare', 6000, 9000), ('theme', 'special', 15000, 22000), ('theme', 'epic', 40000, 60000),
        ('banner', 'standard', 2500, 4000), ('banner', 'rare', 7000, 11000), ('banner', 'special', 20000, 30000),
        ('banner', 'epic', 50000, 80000),
        ('frame', 'standard', 2000, 3500), ('frame', 'rare', 6000, 9500), ('frame', 'special', 18000, 26000),
        ('frame', 'epic', 45000, 70000)),
    d as (
        select c.kind, c.rarity, c.base, min(c.price) bp, coalesce(min(c.price), min(c.worth) * 5) k
          from public.rb_catalog c join lad using (kind, rarity) group by 1, 2, 3),
    r as (select d.*, row_number() over (partition by kind, rarity order by k, base) - 1 rk,
                 count(*) over (partition by kind, rarity) n from d),
    p as (select r.*, lad.lo * power(lad.hi::numeric / lad.lo, rk::numeric / greatest(1, n - 1)) dp from r join lad using (kind, rarity)),
    q as (select c.id, case when c.price is not null and p.bp is not null then p.dp * c.price / p.bp
                            when c.limited then p.dp * 1.25 else p.dp end v, c.price is not null had
            from public.rb_catalog c join p using (kind, rarity, base)),
    v as (select id, had, round(v, case when v < 1000 then -1 when v < 20000 then -2 else -3 end)::int pr from q)
    update public.rb_catalog c set price = case when v.had then v.pr else c.price end, worth = round(v.pr * 0.6, -1)
      from v where c.id = v.id;

    insert into public.rb_config (key, value) values ('cat_053', 1) on conflict (key) do update set value = 1;
end $$;

-- ================================================================ badge cases: one table per case (billionths of an open)
update public.rb_cases c set price = v.price, grid = v.grid, coin_min = v.cmin, coin_max = v.cmax, odds = v.odds,
       variants = v.vars
  from (values
('pocket', 100, array[39600000, 5400000, 0, 0, 0, 4400000, 600000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 15, 65, array[9500, 450, 50, 0, 0, 0], array[88000, 12000, 0, 0, 0]),
('starter', 200, array[55760000, 9840000, 0, 0, 0, 12240000, 2160000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 40, 150, array[9200, 656, 144, 0, 0, 0], array[85000, 15000, 0, 0, 0]),
('lucky', 250, array[59670000, 10530000, 0, 0, 0, 16065000, 2835000, 0, 0, 0, 765000, 135000, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 50, 170, array[9100, 702, 189, 9, 0, 0], array[85000, 15000, 0, 0, 0]),
('standard', 500, array[92062988, 23015747, 120000, 0, 1200, 30687663, 7671916, 40000, 0, 400, 4475284, 1118821, 5833, 0, 58, 639326, 159832, 833, 0, 8]::bigint[], 70, 280, array[8400, 1152, 384, 56, 8, 0], array[79916, 19979, 104, 0, 1]),
('gamble', 600, array[0, 0, 0, 0, 0, 47070286, 5227810, 214285, 0, 2500, 13174080, 1463787, 60000, 5600, 700, 2509349, 278817, 11429, 1067, 133]::bigint[], 20, 360, array[9300, 0, 525, 147, 28, 0], array[89622, 9955, 408, 10, 5]),
('premium', 1200, array[130462357, 36770579, 248000, 0, 2480, 56814252, 16012994, 108000, 0, 1080, 18924448, 5337665, 36000, 13636, 360, 4205433, 1186148, 8000, 3030, 80]::bigint[], 180, 600, array[7299, 1675, 729, 243, 54, 0], array[77890, 21955, 148, 6, 1]),
('painter', 1500, array[0, 81871036, 785714, 0, 4583, 0, 49122621, 471429, 0, 2750, 0, 14852310, 142857, 33333, 833, 0, 2970462, 28571, 6667, 167]::bigint[], 250, 900, array[8497, 827, 496, 150, 30, 0], array[0, 99016, 951, 27, 6]),
('giftbox', 2000, array[162860463, 45909148, 305556, 0, 2750, 88832980, 25041353, 166667, 0, 1500, 35513192, 10016541, 66667, 20000, 600, 8878298, 2504135, 16667, 5000, 150]::bigint[], 400, 1200, array[6199, 2091, 1140, 456, 114, 0], array[77888, 21958, 146, 7, 1]),
('titan', 3500, array[157739346, 44461739, 374999, 0, 3000, 115675521, 32605275, 274999, 0, 2200, 59551784, 16796657, 141666, 38636, 1133, 17515230, 4940193, 41667, 11364, 333]::bigint[], 700, 2000, array[5498, 2026, 1486, 765, 225, 0], array[77855, 21948, 185, 11, 1]),
('vault', 4000, array[103784158, 30982683, 272725, 0, 2143, 145297822, 43375756, 381815, 0, 3000, 76064732, 22720634, 199998, 43650, 1571, 20744927, 6196537, 54545, 11905, 429]::bigint[], 800, 2400, array[5499, 1350, 1891, 990, 270, 0], array[76841, 22943, 202, 12, 2]),
('cosmos', 4500, array[86467588, 25812895, 249997, 0, 2083, 145265547, 43365664, 419995, 0, 3500, 89873766, 26845411, 259997, 52525, 2167, 24196783, 7227611, 69999, 14141, 583]::bigint[], 900, 2600, array[5499, 1125, 1891, 1170, 315, 0], array[76823, 22938, 222, 15, 2]),
('elite', 6000, array[36396219, 11487695, 124999, 0, 1000, 163782985, 51694627, 562497, 0, 4500, 127321952, 40206932, 437498, 64814, 3500, 36377701, 11487695, 124999, 18518, 1000]::bigint[], 1200, 3500, array[5200, 480, 2160, 1680, 480, 0], array[75793, 23928, 260, 17, 2]),
('mythic', 10000, array[0, 0, 0, 0, 0, 149433365, 49783345, 799955, 0, 5333, 164285040, 54761680, 879950, 91661, 5866, 59740015, 19913338, 319982, 33331, 2133]::bigint[], 2800, 7500, array[5000, 0, 2000, 2200, 800, 0], array[74683, 24889, 400, 25, 3]),
('shiny', 12000, array[0, 115145154, 4999929, 0, 7500, 0, 161203216, 6999901, 0, 10500, 0, 84282639, 3666615, 157141, 5500, 0, 22986174, 999986, 42857, 1500]::bigint[], 4000, 10000, array[5995, 1202, 1682, 881, 240, 0], array[0, 95783, 4161, 50, 6]),
('royal', 25000, array[0, 0, 0, 0, 0, 34426595, 14738382, 833310, 0, 4000, 189142574, 81061103, 4583203, 203698, 21999, 120363456, 51584338, 2916584, 129626, 14000]::bigint[], 11000, 24000, array[5000, 0, 500, 2750, 1750, 0], array[68783, 29475, 1667, 67, 8])
  ) v(id, price, grid, cmin, cmax, odds, vars) where c.id = v.id;

-- cosmetic cases: priced to match what is inside (about 80% back on average)
update public.rb_cases c set price = v.price, odds = v.odds, coin_min = v.cmin, coin_max = v.cmax
  from (values
    ('style', 1200, array[3000, 4300, 2000, 600, 100, 0], 300, 900),
    ('themes', 8000, array[4500, 0, 4000, 1250, 250, 0], 3000, 8000),
    ('frames', 4500, array[3600, 3800, 2000, 500, 100, 0], 1500, 4500),
    ('profile', 5000, array[3600, 3800, 2000, 500, 100, 0], 2000, 6000),
    ('banners', 5500, array[3600, 3800, 2000, 500, 100, 0], 2000, 6500),
    ('winter', 10000, array[4000, 0, 4300, 1700, 0, 0], 3500, 9000)
  ) v(id, price, odds, cmin, cmax) where c.id = v.id;

-- ================================================================ the drop (jackpot case pays a quarter less)
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
 returns record language plpgsql security definer set search_path to '' as $function$
declare r double precision; roll bigint; i integer;
begin
    tier := 0; klass := 0; coins := 0;
    roll := floor(public.rb_rand() * 1000000000)::bigint;
    if c.myth_ppb > 0 and roll < c.myth_ppb and c.mode = '' then
        tier := 5;
        klass := (array[3, 4, 5])[public.rb_roll(array[10, 4, 3]) + 1];
        item := public.rb_pick_mythic(klass);
        return;
    end if;
    if c.grid is not null and c.mode = '' then
        roll := roll - c.myth_ppb;
        for i in 1 .. 20 loop
            if roll < c.grid[i] then
                tier := (i - 1) / 5 + 1; klass := (i - 1) % 5;
                item := public.rb_pick_badge(tier, klass);
                if item is not null then return; end if;
                tier := 0; klass := 0; exit;
            end if;
            roll := roll - c.grid[i];
        end loop;
        coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
        if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
            coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
        end if;
        return;
    end if;
    tier := public.rb_roll(c.odds);
    if tier = 5 then tier := 0; end if;
    if tier > 0 and c.mode like 'kinds:%' then
        item := public.rb_pick_weighted(string_to_array(substr(c.mode, 7), ','), tier, null);
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier > 0 and c.mode like 'items:%' then
        select k.id into item from public.rb_catalog k
         where k.id = any (string_to_array(substr(c.mode, 7), ','))
           and k.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
         order by -ln(greatest(public.rb_rand(), 1e-12)) / k.weight limit 1;
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier = 0 then
        if c.mode = 'jackpot' then
            r := public.rb_rand();
            coins := floor(c.price * 0.75 * case when r < 0.66 then 0.12 + public.rb_rand() * 0.33
                                                 when r < 0.90 then 0.8 + public.rb_rand() * 0.8
                                                 when r < 0.97 then 2.5 + public.rb_rand() * 1.5
                                                 when r < 0.995 then 6.5 + public.rb_rand() * 3.5
                                                 else 20 + public.rb_rand() * 12 end)::int;
        else
            coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
            if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
                coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
            end if;
        end if;
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$;

-- ================================================================ the daily case: its badge is mostly Basic
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_daily_case()'::regprocedure), chr(13), '');
    out_ := regexp_replace(src, 'daily_grid bigint\[\] := array\[[0-9, ]+\]',
        'daily_grid bigint[] := array[139748124, 38113125, 76226, 0, 0, 71144500, 5005524, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]');
    if position('139748124' in out_) = 0 then raise exception 'rb_daily_case changed'; end if;
    if out_ <> src then execute out_; end if;
end $$;

-- ================================================================ Wave Rush: nothing for the first 100 m
create or replace function public.rb_wave_pay_for(x integer) returns integer
language sql stable set search_path = '' as $$
    select (greatest(0, x - coalesce(public.rb_cfg('wave_free_x'), 10000)::int) / 1000) * 5 $$;

-- ================================================================ Jackpot 5.3: smaller bot seats, a third of the pot, a cap
-- the most the winner may take from bots: jackpot_cap_x times what they put in
create or replace function public.rb_jackpot_cap(j public.rb_jackpots) returns bigint
language sql stable security definer set search_path to '' as $$
    select coalesce((select e.value from public.rb_jackpot_entries e where e.id = j.winner_entry and e.owner is not null), 0)
           * coalesce(public.rb_cfg('jackpot_cap_x'), 2)::bigint $$;

-- the winner's picks, checked: only keys from the pool, no repeats, bot items within the cap. Returns the keys kept.
create or replace function public.rb_jackpot_auto(j public.rb_jackpots) returns text[]
language plpgsql stable security definer set search_path to '' as $$
declare x jsonb; got text[] := '{}'; botv bigint := 0; cap bigint := public.rb_jackpot_cap(j);
begin
    for x in select y from jsonb_array_elements(public.rb_jackpot_pool(j)) y loop
        exit when coalesce(array_length(got, 1), 0) >= j.picks_allowed;
        if x ->> 'key' like 'bot:%' then
            continue when botv + (x ->> 'worth')::bigint > cap;
            botv := botv + (x ->> 'worth')::bigint;
        end if;
        got := got || (x ->> 'key');
    end loop;
    return got;
end $$;

create or replace function public.rb_jackpot_finish(jid uuid, keys text[]) returns void
language plpgsql security definer set search_path to '' as $$
declare j public.rb_jackpots%rowtype; w public.rb_jackpot_entries%rowtype; k text; e record; pool jsonb; lost jsonb;
        botv bigint := 0; cap bigint; x jsonb; kept text[] := '{}';
begin
    select * into j from public.rb_jackpots where id = jid for update;
    if not found or j.state not in ('locked', 'picking') then return; end if;
    select * into w from public.rb_jackpot_entries where id = j.winner_entry;
    pool := public.rb_jackpot_pool(j);
    cap := public.rb_jackpot_cap(j);
    if w.owner is null then
        select coalesce(jsonb_agg(it.item), '[]'::jsonb) into lost from public.rb_items it where it.locked = 'jackpot:' || j.id;
        delete from public.rb_items where locked = 'jackpot:' || j.id;
        insert into public.rb_audit (admin, action, target, detail) values (null, 'jackpot_bot_win', j.id::text,
            jsonb_build_object('items', lost, 'bot', w.bot_name));
    else
        keys := coalesce(keys, '{}');
        foreach k in array keys loop
            continue when k = any (kept);
            exit when coalesce(array_length(kept, 1), 0) >= j.picks_allowed;
            select y into x from jsonb_array_elements(pool) y where y ->> 'key' = k;
            continue when x is null;
            if k like 'bot:%' then
                continue when botv + (x ->> 'worth')::bigint > cap;
                botv := botv + (x ->> 'worth')::bigint;
                perform public.rb_give(w.owner, x ->> 'item', 'jackpot');
            else
                update public.rb_items set owner = w.owner, locked = null, origin = 'jackpot'
                 where id::text = k and locked = 'jackpot:' || j.id and owner <> w.owner;
            end if;
            kept := kept || k;
        end loop;
        update public.rb_items set locked = null where locked = 'jackpot:' || j.id and owner = w.owner;
        insert into public.rb_seen (owner, item)
            select w.owner, it.item from public.rb_items it where it.owner = w.owner and it.origin = 'jackpot'
            on conflict do nothing;
        delete from public.rb_items where locked = 'jackpot:' || j.id;
        perform public.rb_xp_add(w.owner, coalesce(public.rb_cfg('jackpot_xp'), 150)::int, 'jackpot', j.id::text, false);
    end if;
    for e in select distinct owner from public.rb_jackpot_entries where jackpot = j.id and owner is not null loop
        perform public.rb_fix_equip(e.owner);
        perform public.rb_notice(e.owner, 'jackpot_end', jsonb_build_object('id', j.id, 'won', coalesce(e.owner = w.owner, false),
                                 'winner', coalesce(w.bot_name, (select username from public.profiles where id = w.owner)),
                                 'total', j.total));
    end loop;
    update public.rb_jackpots set state = 'done', picked = to_jsonb(kept) where id = j.id;
end $$;

create or replace function public.rb_jackpot_advance(jid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare j public.rb_jackpots%rowtype; n integer; avg_ bigint; k integer; tgt bigint; whats text[]; free_c integer[];
        r_ double precision; acc bigint := 0; e record; names text[]; nm text; seats integer;
begin
    select * into j from public.rb_jackpots where id = jid for update;
    if not found then return; end if;
    if j.state = 'open' and now() >= j.lock_at then
        select count(*), coalesce(avg(value), 0)::bigint into n, avg_ from public.rb_jackpot_entries where jackpot = j.id;
        if n = 0 then
            update public.rb_jackpots set state = 'empty' where id = j.id;
            return;
        end if;
        select array_agg(c order by random()) into free_c from generate_series(0, 5) c
         where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id);
        select array_agg(b.name order by random()) into names from public.rb_flip_bots() b;
        -- 5.3: one or two bots (never more than 6 players), each putting in less than the players did
        seats := least(6 - n, 1 + floor(public.rb_rand() * coalesce(public.rb_cfg('jackpot_bot_seats'), 2))::int);
        for k in 1 .. seats loop
            tgt := greatest(100, (avg_ * (0.35 + 0.55 * random()))::bigint);
            whats := public.rb_flip_bot_items(tgt, 1 + floor(random() * 2)::int);
            continue when coalesce(array_length(whats, 1), 0) = 0;
            nm := names[k];
            insert into public.rb_jackpot_entries (jackpot, owner, bot_name, colour, whats, value, join_at)
                values (j.id, null, nm, free_c[k], whats, (select sum(public.rb_worth(x)) from unnest(whats) x),
                        j.lock_at + make_interval(secs => 1.6 * k));
        end loop;
        select sum(value) into j.total from public.rb_jackpot_entries where jackpot = j.id;
        r_ := public.rb_rand() * j.total;
        for e in select id, value from public.rb_jackpot_entries where jackpot = j.id order by join_at, id loop
            acc := acc + e.value;
            if r_ < acc then j.winner_entry := e.id; exit; end if;
        end loop;
        update public.rb_jackpots set state = 'locked', total = j.total, winner_entry = j.winner_entry,
               roll = r_ / greatest(1, j.total) where id = j.id;
        return;
    end if;
    if j.state = 'locked' and now() >= j.result_at then
        if (select owner from public.rb_jackpot_entries where id = j.winner_entry) is null then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        n := jsonb_array_length(public.rb_jackpot_pool(j));
        if n = 0 then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        update public.rb_jackpots set state = 'picking', picks_allowed = greatest(1, (n + 2) / 3) where id = j.id;
        return;
    end if;
    if j.state = 'picking' and now() >= j.pick_until then
        perform public.rb_jackpot_finish(j.id, public.rb_jackpot_auto(j));
    end if;
end $$;

-- the state now also says the cap and the most one entry may be worth
create or replace function public.rb_jackpot_json(j public.rb_jackpots, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object(
        'id', j.id, 'state', j.state, 'now', extract(epoch from now()),
        'opens_at', extract(epoch from j.slot), 'lock_at', extract(epoch from j.lock_at),
        'spin_at', extract(epoch from j.spin_at), 'result_at', extract(epoch from j.result_at),
        'pick_until', extract(epoch from j.pick_until),
        'next_at', extract(epoch from j.slot) + coalesce(public.rb_cfg('jackpot_every_s'), 900),
        'total', (select coalesce(sum(value), 0) from public.rb_jackpot_entries e where e.jackpot = j.id and e.join_at <= now()),
        'min_join', greatest(coalesce(public.rb_cfg('jackpot_min_worth'), 500)::bigint,
                             (select coalesce(sum(value), 0) from public.rb_jackpot_entries e where e.jackpot = j.id)
                             * coalesce(public.rb_cfg('jackpot_min_pct'), 1) / 100)::bigint,
        'max_join', coalesce(public.rb_cfg('jackpot_max_worth'), 250000)::bigint,
        'cap', case when j.winner_entry is not null and now() >= j.result_at then public.rb_jackpot_cap(j) end,
        'entries', coalesce((select jsonb_agg(jsonb_build_object(
                         'id', e.id, 'name', coalesce(p.username, e.bot_name), 'bot', e.owner is null, 'me', e.owner = me,
                         'colour', e.colour, 'value', e.value, 'items', to_jsonb(e.whats), 'join_at', extract(epoch from e.join_at))
                         order by e.join_at, e.id)
                     from public.rb_jackpot_entries e left join public.profiles p on p.id = e.owner
                    where e.jackpot = j.id and e.join_at <= now()), '[]'::jsonb),
        'winner', case when now() >= j.spin_at then j.winner_entry end,
        'roll', case when now() >= j.spin_at then j.roll end,
        'mine', exists (select 1 from public.rb_jackpot_entries e where e.jackpot = j.id and e.owner = me),
        'i_won', now() >= j.result_at and exists (select 1 from public.rb_jackpot_entries e where e.id = j.winner_entry and e.owner = me),
        'picks_allowed', j.picks_allowed, 'picked', j.picked,
        'pool', case when j.state = 'picking' and exists (select 1 from public.rb_jackpot_entries e
                                                           where e.id = j.winner_entry and e.owner = me)
                     then public.rb_jackpot_pool(j) end) $$;

create or replace function public.rb_jackpot_pick(jid uuid, keys text[]) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; j public.rb_jackpots%rowtype; pool jsonb; botv bigint;
begin
    p := public.rb_lock_me();
    perform public.rb_jackpot_advance(jid);
    select * into j from public.rb_jackpots where id = jid for update;
    if not found or j.state <> 'picking' then raise exception 'rb_jackpot_closed'; end if;
    if (select owner from public.rb_jackpot_entries where id = j.winner_entry) is distinct from p.id then
        raise exception 'rb_bad_choice';
    end if;
    pool := public.rb_jackpot_pool(j);
    if coalesce(array_length(keys, 1), 0) not between 1 and j.picks_allowed
       or (select count(distinct k) from unnest(keys) k) <> array_length(keys, 1)
       or exists (select 1 from unnest(keys) k where not exists (select 1 from jsonb_array_elements(pool) x
                                                                  where x ->> 'key' = k)) then
        raise exception 'rb_bad_choice';
    end if;
    select coalesce(sum((x ->> 'worth')::bigint), 0) into botv from jsonb_array_elements(pool) x
     where x ->> 'key' = any (keys) and x ->> 'key' like 'bot:%';
    if botv > public.rb_jackpot_cap(j) then raise exception 'rb_jackpot_cap'; end if;
    perform public.rb_jackpot_finish(j.id, keys);
    return jsonb_build_object('done', true);
end $$;
revoke all on function public.rb_jackpot_pick(uuid, text[]) from public, anon;
grant execute on function public.rb_jackpot_pick(uuid, text[]) to authenticated;
revoke all on function public.rb_jackpot_cap(public.rb_jackpots), public.rb_jackpot_auto(public.rb_jackpots)
    from public, anon, authenticated;

-- joining: at most jackpot_max_worth in one entry
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_jackpot_join(uuid[], text)'::regprocedure), chr(13), '');
    if position('jackpot_max_worth' in src) > 0 then return; end if;
    out_ := replace(src, '    if val < minj then raise exception ''rb_jackpot_too_small''; end if;',
                         '    if val < minj then raise exception ''rb_jackpot_too_small''; end if;
    if val > coalesce(public.rb_cfg(''jackpot_max_worth''), 250000) then raise exception ''rb_jackpot_too_big''; end if;');
    if out_ = src then raise exception 'rb_jackpot_join changed'; end if;
    execute out_;
end $$;

-- ================================================================ OG Prismatic Chest again (5 000 coins, 25 keys, 750 XP), 5.3 app only
create or replace function public.rb_og_chest() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype; ends double precision := coalesce(public.rb_cfg('og_event_until'), 0);
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then return json_build_object('due', false); end if;
    return json_build_object(
        'due', p.og_event_at is null and extract(epoch from now()) < ends and coalesce(p.build, 0) >= 2026112101
               and exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og'),
        'claimed', p.og_event_at is not null, 'ends', ends,
        'coins', coalesce(public.rb_cfg('og_chest_coins'), 5000)::int, 'keys', coalesce(public.rb_cfg('og_chest_keys'), 25)::int,
        'xp', coalesce(public.rb_cfg('og_chest_xp'), 750));
end $$;

create or replace function public.rb_og_chest_claim(req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; new_id uuid;
        c int := coalesce(public.rb_cfg('og_chest_coins'), 5000)::int; k int := coalesce(public.rb_cfg('og_chest_keys'), 25)::int;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if p.og_event_at is not null then
        return jsonb_build_object('claimed', true, 'already', true, 'coins', p.coins, 'keys', p.keys);
    end if;
    if extract(epoch from now()) >= coalesce(public.rb_cfg('og_event_until'), 0) then raise exception 'rb_og_over'; end if;
    if coalesce(p.build, 0) < 2026112101 then raise exception 'rb_update_needed'; end if;
    if not exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og') then
        raise exception 'rb_og_only';
    end if;
    update public.profiles set og_event_at = now() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'og_chest', null);
    new_id := public.rb_give(p.id, 'coupon:ogchest', 'og_chest');
    perform public.rb_log('og_chest', p.username, jsonb_build_object('coins', c, 'keys', k, 'coupon', new_id));
    return public.rb_remember(p.id, req, jsonb_build_object('claimed', true, 'coins', p.coins + c,
                              'keys', p.keys + k, 'id', new_id, 'item', 'coupon:ogchest'));
end $$;

-- the OG coupon to level 5 again, once, only to the 5.3 app
create or replace function public.rb_hello2(pc text, build bigint) returns json
language plpgsql security definer set search_path to '' as $function$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hello(pc);
    update public.profiles set build = coalesce(rb_hello2.build, 0) where id = me;
    if extract(epoch from now()) < coalesce(public.rb_cfg('og_until'), 0) then
        perform public.rb_og_give(me);
    end if;
    if coalesce(rb_hello2.build, 0) >= 2026112101
       and exists (select 1 from public.rb_items i where i.owner = me and i.item = 'tag:og')
       and not (select og_coupon_50 from public.profiles where id = me) then
        update public.profiles set og_coupon_50 = true where id = me;
        insert into public.rb_items (owner, item, origin) values (me, 'coupon:og', 'og');
        insert into public.rb_seen (owner, item) values (me, 'coupon:og') on conflict do nothing;
    end if;
    perform public.rb_fix_equip(me);
    return json_build_object('min_build', public.rb_cfg('min_build')::bigint,
                             'update', coalesce(build, 0) < public.rb_cfg('min_build'));
end $function$;

-- ================================================================ the 5.3 fresh start (once, ever). Game scores stay.
do $$
declare og uuid[];
begin
    if coalesce(public.rb_cfg('reset_053'), 0) <> 0 then return; end if;
    create table if not exists public.rb_bak53_profiles as select *, now() as saved_at from public.profiles;
    create table if not exists public.rb_bak53_items as select * from public.rb_items;
    create table if not exists public.rb_bak53_stock as select * from public.rb_case_stock;
    create table if not exists public.rb_bak53_listings as select * from public.rb_listings;
    create table if not exists public.rb_bak53_ledger as select * from public.rb_ledger;
    create table if not exists public.rb_bak53_xp_log as select * from public.rb_xp_log;
    alter table public.rb_bak53_profiles enable row level security;
    alter table public.rb_bak53_items enable row level security;
    alter table public.rb_bak53_stock enable row level security;
    alter table public.rb_bak53_listings enable row level security;
    alter table public.rb_bak53_ledger enable row level security;
    alter table public.rb_bak53_xp_log enable row level security;
    revoke all on public.rb_bak53_profiles, public.rb_bak53_items, public.rb_bak53_stock, public.rb_bak53_listings,
                  public.rb_bak53_ledger, public.rb_bak53_xp_log from anon, authenticated;

    select coalesce(array_agg(distinct owner), '{}') into og from public.rb_items where item = 'tag:og';

    -- scores stay: finished rounds of the mini games, Block Blast and Wave Rush runs. Anything in play or bought goes.
    delete from public.rb_rounds where open or game like 'case%' or game in ('scratch', 'spin', 'wheel', 'gold_wheel');
    delete from public.rb_mg where open;
    truncate public.rb_offers, public.rb_listings, public.rb_trade_items, public.rb_trades, public.rb_duels,
             public.rb_mem, public.rb_park, public.rb_mini, public.rb_flips,
             public.rb_golf, public.rb_golf_solo, public.rb_wave_duels, public.rb_pawn,
             public.rb_rigs, public.rb_giveaway_entries, public.rb_jackpot_entries, public.rb_jackpots,
             public.rb_items, public.rb_seen, public.rb_case_stock,
             public.rb_case_stats, public.rb_set_claims, public.rb_quest_claims, public.rb_requests, public.rb_inbox,
             public.rb_advent_claims, public.rb_xp_log, public.rb_wear, public.rb_ledger;
    if to_regclass('public.rb_deal_buys') is not null then execute 'truncate public.rb_deal_buys'; end if;
    if to_regclass('public.rb_rate_hits') is not null then execute 'truncate public.rb_rate_hits'; end if;
    if to_regclass('public.rb_trash') is not null then execute 'truncate public.rb_trash'; end if;
    update public.rb_giveaways set state = 'cancelled', ends_at = least(ends_at, now()) where state = 'live';

    update public.profiles
       set coins = public.rb_cfg('start_coins')::bigint, keys = public.rb_cfg('start_keys')::int,
           coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           spin_at = null, spin_prize = null, daily_at = null, scratch_at = null,
           gold_keys = 0, og_event_at = null, gold_wheels = 0, rig_gold = false, og_coupon_50 = false,
           xp = 0, level = 0, level_badge = -1, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb,
           xp_hr = null, xp_hr_src = '{}'::jsonb,
           equip = coalesce((select jsonb_object_agg(e.key, e.value) from jsonb_each(coalesce(equip, '{}'::jsonb)) e
                              where e.value #>> '{}' like 'prog:%'), '{}'::jsonb);

    perform public.rb_og_give(x) from unnest(og) x;
    update public.profiles set coins = public.rb_cfg('og_start_coins')::bigint where id = any (og) and not bot;

    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, coins::int, keys, 'reset', '5.3' from public.profiles;
    insert into public.rb_config (key, value) values ('reset_053', 1) on conflict (key) do update set value = 1;
end $$;
update public.rb_config set value = 1795474800 where key = 'og_event_until';      -- 24/11/2026 00:00 Paris

commit;
