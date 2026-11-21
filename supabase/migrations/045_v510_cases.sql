-- 5.10: cases that mean something. Themed cases (Medieval, Nature, Cosmic) only hold badges of their theme, with
-- 11 new designs you can only get there. "All or Nothing", "Coin Rush", "Jackpot" and "Vault" are no longer sold
-- (the ones people own still open). And every case you buy costs a little more until Saturday 12:00 (Paris).

-- 1. the new designs: each one copies the colours, finishes, worth and weight of a design of the same rarity
create temporary table _new_designs (base text, tmpl text) on commit drop;
insert into _new_designs values
    ('scroll', 'feather'), ('goblet', 'cherry'), ('flower', 'heart'),         -- Common
    ('helmet', 'club'), ('bow', 'spade'), ('butterfly', 'mushroom'), ('cactus', 'tree'),   -- Rare
    ('axe', 'sword'), ('lotus', 'star'),                                    -- Epic
    ('castle', 'crown'), ('rainbow', 'sunburst');                           -- Legendary
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select 'badge:' || n.base || ':' || c.variant, c.kind, n.base, c.variant, c.rarity, c.price, c.value, c.tradeable, c.cls,
       c.worth, c.weight, true, c.base_worth
  from _new_designs n join public.rb_catalog c on c.kind = 'badge' and c.base = n.tmpl
on conflict (id) do nothing;

-- 2. themed cases draw from their pool only (limited designs included)
create or replace function public.rb_pick_theme(pool text[], tier integer, klass integer) returns text
    language sql security definer set search_path = '' as $$
    select c.id from public.rb_catalog c
     where c.kind = 'badge' and c.base = any (pool) and c.cls = klass
       and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
     order by -ln(greatest(public.rb_rand(), 1e-12)) / c.weight limit 1 $$;

create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text,
                                               out coins integer) returns record
    language plpgsql security definer set search_path = '' as $$
declare r double precision; roll bigint; i integer; pool text[];
begin
    tier := 0; klass := 0; coins := 0;
    if c.mode like 'theme:%' then pool := string_to_array(substr(c.mode, 7), ','); end if;
    roll := floor(public.rb_rand() * 1000000000)::bigint;
    if c.myth_ppb > 0 and roll < c.myth_ppb and (c.mode = '' or pool is not null) then
        tier := 5;
        klass := (array[3, 4, 5])[public.rb_roll(array[10, 4, 3]) + 1];
        item := public.rb_pick_mythic(klass);
        return;
    end if;
    if c.grid is not null and (c.mode = '' or pool is not null) then
        roll := roll - c.myth_ppb;
        for i in 1 .. 20 loop
            if roll < c.grid[i] then
                tier := (i - 1) / 5 + 1; klass := (i - 1) % 5;
                item := case when pool is null then public.rb_pick_badge(tier, klass) else public.rb_pick_theme(pool, tier, klass) end;
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
end $$;

-- 3. the line-up
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode, limited,
                             kind, min_level, grid, myth_ppb)
select 'nature', 7, 1200, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants,
       'theme:clover,paw,fish,drop,cherry,cat,flower,mushroom,tree,wave,snowflake,mountain,sun,moon,butterfly,cactus,flame,bolt,star,lotus,sunburst,goldenstar,rainbow',
       false, 'theme', 0, grid, myth_ppb from public.rb_cases where id = 'premium'
on conflict (id) do nothing;
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode, limited,
                             kind, min_level, grid, myth_ppb)
select 'medieval', 8, 3500, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants,
       'theme:dice,feather,heart,scroll,goblet,club,spade,diamond,ghost,mountain,helmet,bow,sword,shield,rook,key,quill,skull,trident,axe,crown,trophy,hourglass,castle',
       false, 'theme', 0, grid, myth_ppb from public.rb_cases where id = 'titan'
on conflict (id) do nothing;
update public.rb_cases set kind = 'theme', pos = 9,
       mode = 'theme:moon,sun,eye,ghost,star,bolt,flame,comet,saturn,alien,rocket,shootingstar,planet,goldenstar,sunburst',
       grid = array[0, 0, 0, 0, 0] || grid[6:20]                 -- no Common space badges: those opens pay coins
 where id = 'cosmos';
update public.rb_cases set limited = true where id in ('gamble', 'lucky', 'jackpot', 'vault');

-- 4. prices that climb: +10 / +25 / +50 coins for every case you bought this week, back to normal Saturday 12:00
alter table public.rb_cases add column if not exists step integer not null default 0;
update public.rb_cases set step = case when price >= 3000 then 50 when price >= 800 then 25 else 10 end;

create table if not exists public.rb_case_week (
    owner uuid not null references public.profiles (id) on delete cascade,
    case_id text not null,
    week timestamptz not null,
    n integer not null default 0,
    primary key (owner, case_id, week));
alter table public.rb_case_week enable row level security;

create or replace function public.rb_case_week_start() returns timestamptz
    language sql stable set search_path = '' as $$
    -- the last Saturday 12:00 in Paris
    select (date_trunc('day', l) + interval '12 hours' - make_interval(days => ((extract(dow from l)::int + 1) % 7))
            - case when date_trunc('day', l) + interval '12 hours' - make_interval(days => ((extract(dow from l)::int + 1) % 7)) > l
                   then interval '7 days' else interval '0 days' end) at time zone 'Europe/Paris'
      from (select now() at time zone 'Europe/Paris' l) z $$;

create or replace function public.rb_case_bought(who uuid, cid text) returns integer
    language sql stable security definer set search_path = '' as $$
    select coalesce((select n from public.rb_case_week where owner = who and case_id = cid
                       and week = public.rb_case_week_start()), 0) $$;

create or replace function public.rb_case_cost(c public.rb_cases, bought integer, how_many integer) returns bigint
    language sql immutable set search_path = '' as $$
    select how_many::bigint * c.price + c.step::bigint * (how_many::bigint * bought + how_many::bigint * (how_many - 1) / 2) $$;

create or replace function public.rb_case_count(who uuid, cid text, how_many integer) returns void
    language sql security definer set search_path = '' as $$
    insert into public.rb_case_week as w (owner, case_id, week, n) values (who, cid, public.rb_case_week_start(), how_many)
        on conflict (owner, case_id, week) do update set n = w.n + how_many $$;

create or replace function public.rb_case_prices() returns jsonb
    language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return jsonb_build_object(
        'resets', extract(epoch from public.rb_case_week_start() + interval '7 days'),
        'bought', coalesce((select jsonb_object_agg(case_id, n) from public.rb_case_week
                             where owner = me and week = public.rb_case_week_start()), '{}'::jsonb));
end $$;

create or replace function public.rb_case_buy(which text, how_many integer, req text) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; cost bigint; have integer; b integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('cases');
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    if p.level < c.min_level then raise exception 'rb_level_needed'; end if;
    how_many := coalesce(how_many, 1);
    if how_many < 1 or how_many > coalesce(public.rb_cfg('case_buy_max'), 10) then raise exception 'rb_bad_choice'; end if;
    b := public.rb_case_bought(p.id, c.id);
    cost := public.rb_case_cost(c, b, how_many);
    if cost > 2000000000 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_pay(p.id, -cost::int, 0, 'case_buy', c.id || ':' || how_many);
    perform public.rb_case_count(p.id, c.id, how_many);
    perform public.rb_stock_add(p.id, c.id, how_many);
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id;
    return public.rb_remember(p.id, req, jsonb_build_object('case', c.id, 'stock', have, 'coins', p.coins - cost,
                                                            'bought', b + how_many, 'paid', cost));
end $$;

create or replace function public.rb_case_gift(name text, which text, req text) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; cost bigint;
begin
    perform public.rb_rate(auth.uid(), 'gift', 10);
    perform public.rb_need_feature('gifts');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
    if not public.rb_is_friend(p.id, them.id) then raise exception 'rb_friends_only'; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    if (select count(*) from public.rb_ledger where owner = p.id and reason = 'gift' and at >= date_trunc('day', now()))
       >= public.rb_cfg('gift_day') then
        raise exception 'rb_gift_limit';
    end if;
    cost := public.rb_case_cost(c, public.rb_case_bought(p.id, c.id), 1);   -- a gift counts as one you bought
    perform public.rb_pay(p.id, -cost::int, 0, 'gift', c.id || ':' || them.username);
    perform public.rb_case_count(p.id, c.id, 1);
    perform public.rb_stock_add(them.id, c.id, 1);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - cost, 'keys', p.keys));
end $$;

revoke all on function public.rb_case_bought(uuid, text) from public, anon, authenticated;
revoke all on function public.rb_case_count(uuid, text, integer) from public, anon, authenticated;
revoke all on function public.rb_pick_theme(text[], integer, integer) from public, anon, authenticated;
grant execute on function public.rb_case_prices() to authenticated;

create or replace function public.rb_case_gift_n(name text, which text, n integer, req text) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; left_ integer;
        cost bigint; b integer; i integer;
begin
    perform public.rb_rate(auth.uid(), 'gift', 10);
    perform public.rb_need_feature('gifts');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if n is null or n < 1 or n > 10 then raise exception 'rb_bad_choice'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
    if not public.rb_is_friend(p.id, them.id) then raise exception 'rb_friends_only'; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    left_ := public.rb_cfg('gift_day')::int - (select count(*)::int from public.rb_ledger where owner = p.id and reason = 'gift'
             and at >= date_trunc('day', now()));
    if n > left_ then raise exception 'rb_gift_limit'; end if;
    b := public.rb_case_bought(p.id, c.id);
    cost := public.rb_case_cost(c, b, n);
    if p.coins < cost then raise exception 'rb_not_enough'; end if;
    for i in 1 .. n loop                                      -- one ledger line per gift: the daily limit counts them
        perform public.rb_pay(p.id, -(c.price + c.step * (b + i - 1)), 0, 'gift', c.id || ':' || them.username);
    end loop;
    perform public.rb_case_count(p.id, c.id, n);
    perform public.rb_stock_add(them.id, c.id, n);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id, 'n', n));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - cost, 'keys', p.keys, 'left', left_ - n,
                                                            'bought', b + n));
end $$;
