-- Rubenium 012 (2.6.1): the case balance. Run it once in Supabase, after 011: SQL Editor > New query > paste everything > Run.
-- Safe to run again (it sets the same numbers).
--
-- Two kinds of case:
--   COIN CASES (Starter, Standard, Premium, Jackpot, Titanium): mostly coins. On average they pay back a little more than
--   they cost (+4 to +10%), but about half the opens give less than the price (Jackpot: 7 times out of 10). Few rare badges.
--   RARE HUNTS (All or Nothing, Painter's, Legend Vault, Mythic Hunt): the real chance at rare badges. They cost coins on
--   average (you get back about half): rare badges are paid for.
-- Every case still needs 1 key, and keys come from time (1 an hour), so cases can never be farmed.
-- The chance of each rarity per case was never raised: the rare hunts cost about twice as much as before, and the coin
-- cases have far fewer rare badges. Rare and Mythic badges are harder to get than before, not easier.
-- Badges in the shop now cost much more than trying your luck in cases (the rarer and the luckier, the higher).

insert into public.rb_config (key, value) values ('case_lucky_pct', 6), ('case_lucky_x', 3)
on conflict (key) do nothing;

-- ================================================================ cases (price, order, chances, coins)
update public.rb_cases set pos = 1, price = 200, odds = array[7600, 1950, 400, 45, 5, 0], coin_min = 80, coin_max = 400, variants = array[76000, 23500, 480, 0, 20] where id = 'starter';
update public.rb_cases set pos = 2, price = 500, odds = array[7200, 2100, 600, 85, 14, 1], coin_min = 200, coin_max = 1100, variants = array[74000, 25400, 550, 30, 20] where id = 'standard';
update public.rb_cases set pos = 3, price = 1200, odds = array[6900, 2100, 820, 140, 38, 2], coin_min = 500, coin_max = 2700, variants = array[72000, 27250, 650, 70, 30] where id = 'premium';
update public.rb_cases set pos = 4, price = 2000, odds = array[10000, 0, 0, 0, 0, 0], coin_min = 240, coin_max = 64000, variants = array[100000, 0, 0, 0, 0] where id = 'jackpot';
update public.rb_cases set pos = 5, price = 3500, odds = array[7000, 1700, 1000, 220, 76, 4], coin_min = 1200, coin_max = 7900, variants = array[69000, 29800, 800, 360, 40] where id = 'titan';
update public.rb_cases set pos = 6, price = 600, odds = array[5600, 0, 3000, 1150, 245, 5], coin_min = 60, coin_max = 600, variants = array[70000, 29300, 620, 50, 30] where id = 'gamble';
update public.rb_cases set pos = 7, price = 1200, odds = array[3400, 4400, 1750, 380, 70, 0], coin_min = 350, coin_max = 2900, variants = array[0, 99000, 900, 70, 30] where id = 'painter';
update public.rb_cases set pos = 8, price = 4000, odds = array[3400, 0, 3500, 2300, 775, 25], coin_min = 1150, coin_max = 9200, variants = array[70000, 29150, 750, 70, 30] where id = 'vault';
update public.rb_cases set pos = 9, price = 10000, odds = array[3800, 0, 0, 4300, 1800, 100], coin_min = 2400, coin_max = 19000, variants = array[68000, 31050, 820, 90, 40] where id = 'mythic';

-- what a case gives: coins (6% of coin drops are a lucky x3), or a badge. Jackpot coins scale with its price.
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
language plpgsql security definer set search_path = '' as $$
declare r double precision;
begin
    tier := public.rb_roll(c.odds); klass := 0; coins := 0;
    if tier = 0 then
        if c.mode = 'jackpot' then
            r := public.rb_rand();
            coins := floor(c.price * case when r < 0.66 then 0.12 + public.rb_rand() * 0.33
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
    elsif tier = 5 then                                   -- Mythic: Titanium, rarely Prismatic, almost never Gold
        klass := (array[3, 5, 4])[public.rb_roll(array[90000, 9500, 500]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $$;

-- ================================================================ shop prices of badges
-- 1.5 times the coins you would lose on average in the best case to get one of that rarity and finish, and at least
-- 8 times its value. Titanium, Gold and Mythic badges are still never sold.
update public.rb_catalog set price = 1200 where kind = 'badge' and rarity = 'standard' and cls = 0;
update public.rb_catalog set price = 1900 where kind = 'badge' and rarity = 'standard' and cls = 1;
update public.rb_catalog set price = 80000 where kind = 'badge' and rarity = 'standard' and cls = 2;
update public.rb_catalog set price = 3600 where kind = 'badge' and rarity = 'rare' and cls = 0;
update public.rb_catalog set price = 5750 where kind = 'badge' and rarity = 'rare' and cls = 1;
update public.rb_catalog set price = 210000 where kind = 'badge' and rarity = 'rare' and cls = 2;
update public.rb_catalog set price = 9600 where kind = 'badge' and rarity = 'special' and cls = 0;
update public.rb_catalog set price = 15500 where kind = 'badge' and rarity = 'special' and cls = 1;
update public.rb_catalog set price = 585000 where kind = 'badge' and rarity = 'special' and cls = 2;
update public.rb_catalog set price = 24500 where kind = 'badge' and rarity = 'epic' and cls = 0;
update public.rb_catalog set price = 58000 where kind = 'badge' and rarity = 'epic' and cls = 1;
update public.rb_catalog set price = 2750000 where kind = 'badge' and rarity = 'epic' and cls = 2;

-- ================================================================ the market can go up to the shop price
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_market_price(text)'::regprocedure) into src;
    if position('greatest(floor' in src) = 0 then
        src := replace(src, 'floor(public.rb_estimate(what) * public.rb_cfg(''market_max_mult''))',
            'greatest(floor(public.rb_estimate(what) * public.rb_cfg(''market_max_mult'')), coalesce((select k.price from public.rb_catalog k where k.id = what), 0))');
        execute src;
    end if;
    select pg_get_functiondef('public.rb_market_list(uuid, integer)'::regprocedure) into src;
    if position('greatest(floor' in src) = 0 then
        src := replace(src, 'price > floor(est * public.rb_cfg(''market_max_mult''))',
            'price > greatest(floor(est * public.rb_cfg(''market_max_mult'')), coalesce(c.price, 0))');
        execute src;
    end if;
end $$;

-- ================================================================ a gifted case costs its price and 1 key (keys stay the limit)
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_case_gift(text, text, text)'::regprocedure) into src;
    if position('-c.price, -1,' in src) = 0 then
        src := replace(src, 'perform public.rb_pay(p.id, -c.price, 0, ''gift''', 'perform public.rb_pay(p.id, -c.price, -1, ''gift''');
        src := replace(src, 'jsonb_build_object(''coins'', p.coins - c.price)', 'jsonb_build_object(''coins'', p.coins - c.price, ''keys'', p.keys - 1)');
        execute src;
    end if;
end $$;
