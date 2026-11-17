-- Rubenium 020 (3.2): the ONLINE update.
--   * Keys: 1 every 30 minutes, up to 12. Every account made before this update gets its key wallet filled to 12 (once).
--   * Chat: 300 characters at most, a short pause between messages and no copy-paste spam (checked here, not only in the app).
--   * Every item has its own worth and its own chance. The shop sells at worth + 20% tax; players trade at worth.
--   * Cases are bought with coins only and go to your case inventory. Opening one needs a key (style cases do not).
--     A gifted case costs the giver coins only; the friend who gets it needs a key to open it.
--   * Keys can be traded.
--   * Mini Golf and Coinflip are open lobbies (no invitations): 1 lobby each at a time, gone after 5 minutes if nobody joins.
--     Mini Golf is 5 holes, with 8 new holes.
--   * Coinflip: up to 6 items each, black or white, 49% to 51%, decided and paid by the server only.
--   * Slots are gone; Roulette and Hi-Lo are new.
--   * The advent calendar (1 to 24 December, and a big door on the 25th), new cosmetics and new cases.
-- Run it once in Supabase -> SQL Editor (after 019). Running it again changes nothing.

insert into public.rb_config (key, value) values
    ('key_every_min', 30), ('key_cap', 12), ('shop_tax', 0.2),
    ('chat_max', 300), ('chat_gap_ms', 1500), ('chat_burst', 5), ('chat_burst_s', 10), ('chat_same_s', 60),
    ('lobby_min', 5), ('golf_holes', 5), ('flip_max_items', 6), ('flip_join_s', 30), ('flip_wait_s', 15),
    ('flip_range', 0.10), ('flip_min_chance', 0.49), ('flip_max_chance', 0.51), ('case_buy_max', 10),
    ('hilo_step', 0.985), ('advent_catchup', 0)
on conflict (key) do update set value = excluded.value;

-- ================================================================ the key wallet: filled to 12 once for everyone already here
do $$ begin
    if not exists (select 1 from public.rb_config where key = 'reset_020') then
        update public.profiles set keys = greatest(keys, 12), key_min = 0 where not bot;
        insert into public.rb_config (key, value) values ('reset_020', 1);
    end if;
end $$;

-- ================================================================ mini games: the x1.3 pay of 3.0.0 (never reached the server)
create or replace function public.rb_game_pay(who uuid, g text, pay integer) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1));
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    return greatest(0, least(pay, (w ->> 'cap')::int - (w ->> 'paid')::int));
end $$;

-- ================================================================ chat: length, pace and no repeats, enforced here
create or replace function public.rb_msg_send(name text, body text) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.profiles%rowtype; mid bigint; last public.rb_messages%rowtype;
        gap numeric := coalesce(public.rb_cfg('chat_gap_ms'), 1500) / 1000.0;
begin
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    body := btrim(regexp_replace(coalesce(body, ''), '[\x00-\x09\x0b-\x1f]', '', 'g'));
    if length(body) = 0 then raise exception 'rb_bad_choice'; end if;
    if length(body) > coalesce(public.rb_cfg('chat_max'), 300) then raise exception 'rb_too_long'; end if;
    select * into last from public.rb_messages m where m.a = p.id order by m.id desc limit 1;
    if found and clock_timestamp() - last.at < make_interval(secs => gap) then raise exception 'rb_chat_wait'; end if;
    if (select count(*) from public.rb_messages m where m.a = p.id
          and m.at > now() - make_interval(secs => coalesce(public.rb_cfg('chat_burst_s'), 10)))
       >= coalesce(public.rb_cfg('chat_burst'), 5) then raise exception 'rb_chat_wait'; end if;
    if exists (select 1 from public.rb_messages m where m.a = p.id and m.b = o.id
                 and lower(m.body) = lower(rb_msg_send.body) and m.at > now() - make_interval(secs => coalesce(public.rb_cfg('chat_same_s'), 60))) then
        raise exception 'rb_same_message';
    end if;
    if (select count(*) from public.rb_messages m where m.a = p.id and m.at > now() - interval '1 minute')
       >= public.rb_cfg('msg_per_min') then raise exception 'rb_chat_wait'; end if;
    insert into public.rb_messages (a, b, body) values (p.id, o.id, body) returning id into mid;
    if not exists (select 1 from public.rb_mutes m where m.owner = o.id and m.who = p.id) then
        perform public.rb_notice(o.id, 'message', jsonb_build_object('from', p.username, 'text', left(body, 60)));
    end if;
    return json_build_object('id', mid);
end $$;

-- ================================================================ every item: its own worth and its own chance
alter table public.rb_catalog add column if not exists worth bigint;
alter table public.rb_catalog add column if not exists weight double precision not null default 1;
alter table public.rb_catalog add column if not exists limited boolean not null default false;
alter table public.rb_catalog add column if not exists base_worth bigint;           -- the 3.1 worth, kept to price from
alter table public.rb_cases add column if not exists limited boolean not null default false;
alter table public.rb_cases add column if not exists kind text not null default '';

-- a round, readable price: 1 234 -> 1 230, 12 345 -> 12 300
create or replace function public.rb_nice(x double precision) returns bigint
language sql immutable set search_path = '' as $$
    select case when x < 1000 then (round(x / 5) * 5)::bigint
                when x < 10000 then (round(x / 10) * 10)::bigint
                when x < 100000 then (round(x / 100) * 100)::bigint
                else (round(x / 1000) * 1000)::bigint end $$;

-- How detailed a design is, from 0 (simplest) to 1 (most detailed), inside its own rarity. Listed by hand for the
-- profile looks; balls, lines, fonts and badges follow a fixed order of their own.
create or replace function public.rb_detail(k text, b text) returns double precision
language plpgsql immutable set search_path = '' as $$
declare lst text[]; i integer;
begin
    lst := case k
        when 'banner' then array['dusk', 'mint', 'steel', 'rose', 'slate', 'pastel', 'stripes', 'dots', 'carbon', 'dunes',
                                 'peaks', 'sunset', 'waves', 'ember', 'honeycomb', 'tides', 'canyon', 'comet', 'circuit', 'deepsea', 'snow', 'wreath',
                                 'grid', 'jungle', 'sakura', 'lava', 'prism', 'city', 'neon', 'fireflies', 'koi', 'synthwave', 'aurora', 'hearth',
                                 'galaxy', 'nebula', 'matrix', 'storm', 'vortex', 'supernova', 'dragon', 'northstar']
        when 'frame' then array['silver', 'bronze', 'ink', 'wood', 'dashed', 'twin', 'neon', 'vine', 'frost', 'holly', 'pulse',
                                'laurel', 'crown', 'spikes', 'star', 'thorns', 'snowflake', 'gears',
                                'flame', 'orbit', 'halo', 'rainbow', 'phoenix', 'northstar']
        when 'ball' then array['pixel', 'halo', 'bullseye', 'petal', 'split', 'shard', 'hex', 'gear', 'bubble', 'orbit', 'planet',
                               'spiral', 'ripple', 'nova', 'snowglobe']
        when 'line' then array['dash', 'beads', 'zigzag', 'wave', 'twin', 'pulse', 'chain', 'stars', 'steps', 'ribbon', 'helix',
                               'spark', 'laser', 'lightning', 'garland']
        when 'font' then array['rounded', 'mono', 'serif', 'display', 'script']
        when 'theme' then array['sunset', 'ocean', 'lagoon', 'forest', 'candy', 'midnight', 'storm', 'retro', 'inferno']
        when 'badge' then array['heart', 'drop', 'clover', 'paw', 'cat', 'fish', 'cherry', 'feather', 'note', 'dice', 'headset',
                                'gamepad', 'mushroom', 'tree', 'wave', 'ghost', 'spade', 'club', 'diamond', 'eye', 'snowflake',
                                'mountain', 'moon', 'sun', 'star', 'bolt', 'flame', 'anchor', 'key', 'pickaxe', 'rook', 'shield',
                                'sword', 'skull', 'trident', 'quill', 'hourglass', 'target', 'comet', 'saturn', 'alien', 'rocket',
                                'shootingstar', 'planet', 'crown', 'trophy', 'goldenstar', 'sunburst',
                                'galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium']
        else array[]::text[] end;
    i := array_position(lst, b);
    if i is null then return (abs(hashtext(k || ':' || b)) % 1000) / 999.0; end if;
    return (i - 1)::double precision / greatest(1, array_length(lst, 1) - 1);
end $$;

-- the old rule (shop price when sold, else value x 50 / x 400): the base the individual prices start from
create or replace function public.rb_worth_base(c public.rb_catalog) returns bigint
language sql stable set search_path = '' as $$
    select coalesce(c.price::bigint,
                    c.value::bigint * case when c.kind = 'badge' and c.rarity = 'exotic' then 400
                                           when c.kind = 'badge' and c.cls >= 3 then 50 else 1 end) $$;

-- Worth = base x a factor from the design (0.85 for the simplest to 1.25 for the most detailed of its rarity) x a small
-- one for the colour (0.95 to 1.05). Prices never cross into the next rarity. The chance inside a rarity is the inverse:
-- the more an item is worth, the rarer it drops.
create or replace function public.rb_price_all() returns void
language plpgsql security definer set search_path = '' as $$
declare c public.rb_catalog%rowtype; rank_d double precision; rank_v double precision; f double precision;
        cols text[] := array['grey', 'blue', 'green', 'red', 'yellow', 'orange', 'brown', 'teal', 'lava', 'purple', 'sky',
                             'lime', 'pink', 'beam', 'hotpink', 'royal', 'black', 'white', 'gold', 'prime'];
begin
    update public.rb_catalog k set base_worth = public.rb_worth_base(k) where k.base_worth is null;
    for c in select * from public.rb_catalog where kind not in ('prog', 'tag') loop
        -- position of the design among the designs of its own rarity
        select coalesce((select count(*) from (select distinct x.base from public.rb_catalog x
                                                where x.kind = c.kind and x.rarity = c.rarity and x.cls = c.cls
                                                  and public.rb_detail(x.kind, x.base) < public.rb_detail(c.kind, c.base)) y)::double precision
                        / nullif((select count(distinct x.base) - 1 from public.rb_catalog x
                                   where x.kind = c.kind and x.rarity = c.rarity and x.cls = c.cls), 0), 0.5) into rank_d;
        rank_v := coalesce((array_position(cols, c.variant) - 1)::double precision / (array_length(cols, 1) - 1), 0.5);
        f := (0.85 + 0.40 * rank_d) * (0.95 + 0.10 * rank_v);
        update public.rb_catalog set worth = greatest(5, public.rb_nice(c.base_worth * f)), weight = 1.0 / f
         where id = c.id;
    end loop;
    update public.rb_catalog set worth = 0, weight = 1 where kind in ('prog', 'tag');
    -- items sold in the shop: the price column is the worth; the shop adds the tax when it sells
    update public.rb_catalog set price = worth where price is not null and kind not in ('prog', 'tag');
end $$;

create or replace function public.rb_worth(what text) returns bigint
language sql stable security definer set search_path = '' as $$
    select coalesce(c.worth, public.rb_worth_base(c)) from public.rb_catalog c where c.id = what $$;

-- what the shop asks: worth + tax, minus a sale or a deal
create or replace function public.rb_shop_price(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select greatest(1, ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)) * (100 - public.rb_sale_pct(what)) / 100.0))::int
      from public.rb_catalog c where c.id = what and c.price is not null $$;

create or replace function public.rb_buy(what text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind in ('prog', 'tag') or c.limited then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := public.rb_shop_price(what);
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost, 'paid', cost));
end $$;

-- the market can always go up to the taxed shop price
create or replace function public.rb_market_price(what text) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('estimate', public.rb_estimate(what), 'worth', public.rb_worth(what),
        'min', ceil(public.rb_estimate(what) * public.rb_cfg('market_min_mult')),
        'max', greatest(floor(public.rb_estimate(what) * public.rb_cfg('market_max_mult')), coalesce(public.rb_shop_price(what), 0)),
        'sales', coalesce((select json_agg(s.price) from (select price from public.rb_listings
                            where rb_listings.what = rb_market_price.what and state = 'sold'
                            order by sold_at desc limit 10) s), '[]'::json)) $$;

-- drops: the chance of each item inside its rarity follows its weight (rarer = worth more)
create or replace function public.rb_pick_weighted(k text[], tier integer, klass integer) returns text
language sql security definer set search_path = '' as $$
    select c.id from public.rb_catalog c
     where c.kind = any (k) and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
       and (klass is null or c.cls = klass) and not c.limited
       and (c.kind = 'badge' or c.price is not null)
     order by -ln(greatest(public.rb_rand(), 1e-12)) / c.weight limit 1 $$;

create or replace function public.rb_pick_badge(tier integer, klass integer) returns text
language sql security definer set search_path = '' as $$
    select public.rb_pick_weighted(array['badge'], tier, klass) $$;

-- a case made only of chosen items (limited cases): "items:a,b,c"
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
language plpgsql security definer set search_path = '' as $$
declare r double precision;
begin
    tier := public.rb_roll(c.odds); klass := 0; coins := 0;
    if tier > 0 and c.mode like 'kinds:%' then                -- a style case: one item of that rarity, by weight
        item := public.rb_pick_weighted(string_to_array(substr(c.mode, 7), ','), tier, null);
        if item is not null then return; end if;
        tier := 0;                                            -- nothing of that rarity: coins instead
    end if;
    if tier > 0 and c.mode like 'items:%' then                -- a limited case: its own list, by rarity and weight
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
        klass := (array[3, 5, 4])[public.rb_roll(array[96515, 3300, 185]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $$;

-- ================================================================ the case inventory: buy with coins, open with a key
create or replace function public.rb_case_keyless(c public.rb_cases) returns boolean
language sql immutable set search_path = '' as $$ select c.mode like 'kinds:%' $$;

create or replace function public.rb_case_buy(which text, how_many integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; cost integer; have integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    how_many := coalesce(how_many, 1);
    if how_many < 1 or how_many > coalesce(public.rb_cfg('case_buy_max'), 10) then raise exception 'rb_bad_choice'; end if;
    cost := c.price * how_many;
    perform public.rb_pay(p.id, -cost, 0, 'case_buy', c.id || ':' || how_many);
    perform public.rb_stock_add(p.id, c.id, how_many);
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id;
    return public.rb_remember(p.id, req, jsonb_build_object('case', c.id, 'stock', have, 'coins', p.coins - cost));
end $$;

create or replace function public.rb_open_case(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; d record; new_id uuid; have integer;
        key_cost integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id for update;
    if coalesce(have, 0) < 1 then raise exception 'rb_case_none'; end if;
    key_cost := case when public.rb_case_keyless(c) then 0 else 1 end;
    if p.keys < key_cost then raise exception 'rb_no_key'; end if;
    update public.rb_case_stock set n = n - 1 where owner = p.id and case_id = c.id;
    have := have - 1;
    perform public.rb_pay(p.id, 0, -key_cost, 'case', c.id);
    d := public.rb_case_drop(c);
    if d.tier = 0 then
        perform public.rb_pay(p.id, d.coins, 0, 'case_coins', c.id);
    else
        new_id := public.rb_give(p.id, d.item, 'case:' || c.id);
    end if;
    insert into public.rb_case_stats as st (owner, case_id, opens) values (p.id, c.id, 1)
        on conflict (owner, case_id) do update set opens = st.opens + 1;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'case:' || c.id, c.price,
        jsonb_build_object('item', d.item, 'tier', d.tier), false,
        d.coins + coalesce((select worth from public.rb_catalog where id = d.item), 0));
    return public.rb_remember(p.id, req, jsonb_build_object('tier', d.tier, 'cls', d.klass, 'item', d.item, 'id', new_id,
        'won', d.coins, 'coins', p.coins + d.coins, 'keys', p.keys - key_cost, 'stock', have, 'case', c.id));
end $$;

create or replace function public.rb_open_case_gold(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if p.gold_keys < 1 then raise exception 'rb_no_key'; end if;
    select * into c from public.rb_cases where id = which;
    if not found or public.rb_case_keyless(c) then raise exception 'rb_bad_choice'; end if;
    if coalesce((select n from public.rb_case_stock where owner = p.id and case_id = which), 0) < 1 then raise exception 'rb_case_none'; end if;
    update public.profiles set gold_keys = gold_keys - 1, keys = keys + 1 where id = p.id;
    return public.rb_open_case(which, req);
end $$;

-- a gift: the giver pays the coins (no key); the case lands in the friend's case inventory
create or replace function public.rb_case_gift(name text, which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb;
begin
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
    perform public.rb_pay(p.id, -c.price, 0, 'gift', c.id || ':' || them.username);
    perform public.rb_stock_add(them.id, c.id, 1);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - c.price, 'keys', p.keys));
end $$;

-- ================================================================ keys in trades
alter table public.rb_trades add column if not exists a_keys integer not null default 0;
alter table public.rb_trades add column if not exists b_keys integer not null default 0;

create or replace function public.rb_trade_offer(trade uuid, items uuid[], coins integer, keys integer) returns integer
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; my text; p public.profiles%rowtype; n integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into t from public.rb_trades where id = trade for update;
    if not found or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    my := case when t.a = me then 'a' else 'b' end;
    items := coalesce(items, '{}');
    n := coalesce(array_length(items, 1), 0);
    if n > 8 or n <> (select count(distinct x) from unnest(items) x) then raise exception 'rb_bad_offer'; end if;
    select * into p from public.profiles where id = me;
    if coins is null or coins < 0 or coins > p.coins then raise exception 'rb_not_enough'; end if;
    keys := coalesce(keys, 0);
    if keys < 0 or keys > p.keys or keys > 99 then raise exception 'rb_not_enough'; end if;
    update public.rb_items set locked = null where owner = me and locked = 'trade:' || t.id;
    delete from public.rb_trade_items where rb_trade_items.trade = t.id and rb_trade_items.side = my;
    if n > 0 then
        perform 1 from public.rb_items where id = any (items) order by id for update;
        if (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
             where it.id = any (items) and it.owner = me and it.locked is null and c.tradeable) <> n then
            raise exception 'rb_item_locked';
        end if;
        update public.rb_items set locked = 'trade:' || t.id where id = any (items);
        insert into public.rb_trade_items (trade, side, item, what)
            select t.id, my, it.id, it.item from public.rb_items it where it.id = any (items);
    end if;
    update public.rb_trades set a_coins = case when my = 'a' then rb_trade_offer.coins else a_coins end,
                                b_coins = case when my = 'b' then rb_trade_offer.coins else b_coins end,
                                a_keys = case when my = 'a' then rb_trade_offer.keys else a_keys end,
                                b_keys = case when my = 'b' then rb_trade_offer.keys else b_keys end,
           a_ready = false, b_ready = false, a_ok = false, b_ok = false, ready_at = null,
           version = version + 1, updated = now()
     where id = t.id;
    return t.version + 1;
end $$;

-- the old call (no keys) still works and keeps the keys already offered at 0
create or replace function public.rb_trade_offer(trade uuid, items uuid[], coins integer) returns integer
language sql security definer set search_path = '' as $$ select public.rb_trade_offer(trade, items, coins, 0) $$;

create or replace function public.rb_trade_confirm(trade uuid, seen_version integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; pa public.profiles%rowtype; pb public.profiles%rowtype;
        bad boolean;
begin
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    if t.version <> seen_version then raise exception 'rb_trade_changed'; end if;
    if not (t.a_ready and t.b_ready) or t.ready_at is null then raise exception 'rb_not_ready'; end if;
    if now() < t.ready_at + interval '5 seconds' then raise exception 'rb_wait'; end if;
    if t.a = me then t.a_ok := true; else t.b_ok := true; end if;
    update public.rb_trades set a_ok = t.a_ok, b_ok = t.b_ok, updated = now() where id = t.id;
    if not (t.a_ok and t.b_ok) then return jsonb_build_object('done', false); end if;
    perform 1 from public.profiles where id in (t.a, t.b) order by id for update;
    select * into pa from public.profiles where id = t.a;
    select * into pb from public.profiles where id = t.b;
    perform 1 from public.rb_items where id in (select item from public.rb_trade_items where rb_trade_items.trade = t.id)
      order by id for update;
    select exists (select 1 from public.rb_trade_items ti left join public.rb_items it on it.id = ti.item
                    where ti.trade = t.id
                      and (it.id is null or it.owner <> (case ti.side when 'a' then t.a else t.b end)
                           or it.locked is distinct from 'trade:' || t.id)) into bad;
    if bad or pa.coins < t.a_coins or pb.coins < t.b_coins or pa.keys < t.a_keys or pb.keys < t.b_keys then
        perform public.rb_trade_end(t.id, 'failed');
        return jsonb_build_object('done', false, 'failed', true);
    end if;
    update public.rb_items it set owner = case ti.side when 'a' then t.b else t.a end, locked = null, origin = 'trade'
      from public.rb_trade_items ti where ti.trade = t.id and ti.item = it.id;
    insert into public.rb_seen (owner, item)
        select case ti.side when 'a' then t.b else t.a end, ti.what from public.rb_trade_items ti where ti.trade = t.id
        on conflict do nothing;
    perform public.rb_pay(t.a, t.b_coins - t.a_coins, t.b_keys - t.a_keys, 'trade', t.id::text);
    perform public.rb_pay(t.b, t.a_coins - t.b_coins, t.a_keys - t.b_keys, 'trade', t.id::text);
    perform public.rb_fix_equip(t.a);
    perform public.rb_fix_equip(t.b);
    update public.rb_trades set state = 'done', updated = now() where id = t.id;
    return jsonb_build_object('done', true);
end $$;

create or replace function public.rb_trade_get(trade uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; mine text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_trade_expire(me);
    select * into t from public.rb_trades where id = trade;
    if not found or (t.a <> me and t.b <> me) then raise exception 'rb_trade_gone'; end if;
    mine := case when t.a = me then 'a' else 'b' end;
    if t.state = 'open' then
        update public.rb_trades set a_seen = case when mine = 'a' then now() else a_seen end,
                                    b_seen = case when mine = 'b' then now() else b_seen end where id = t.id;
    end if;
    return json_build_object('id', t.id, 'state', t.state, 'why', t.why, 'version', t.version, 'me', mine,
        'a', (select username from public.profiles where id = t.a), 'b', (select username from public.profiles where id = t.b),
        'a_coins', t.a_coins, 'b_coins', t.b_coins, 'a_keys', t.a_keys, 'b_keys', t.b_keys,
        'a_ready', t.a_ready, 'b_ready', t.b_ready, 'a_ok', t.a_ok, 'b_ok', t.b_ok,
        'wait', case when t.ready_at is null then null
                     else greatest(0, 5 - extract(epoch from (now() - t.ready_at))) end,
        'items', coalesce((select json_agg(json_build_object('side', ti.side, 'id', ti.item, 'item', ti.what,
                                                             'estimate', public.rb_estimate(ti.what), 'worth', public.rb_worth(ti.what)))
                             from public.rb_trade_items ti where ti.trade = t.id), '[]'::json));
end $$;

-- ================================================================ Mini Golf: open lobbies, 5 holes
alter table public.rb_golf alter column b drop not null;
alter table public.rb_golf drop constraint if exists rb_golf_state_check;
alter table public.rb_golf add constraint rb_golf_state_check check (state in ('open', 'asked', 'live', 'done', 'cancelled'));

create or replace function public.rb_golf_pick() returns integer[]
language sql security definer set search_path = '' as $$
    select array_agg(h) from (
        select h + case when public.rb_rand() < 0.5 then 100 else 0 end as h
          from generate_series(1, 24) h order by public.rb_rand()
         limit greatest(1, least(9, coalesce(public.rb_cfg('golf_holes'), 5)::int))) x $$;

-- the most a lobby may bet: 80% of what the host has, and never above the duel maximum
create or replace function public.rb_golf_cap(coins bigint) returns integer
language sql stable set search_path = '' as $$
    select (least(coalesce(public.rb_cfg('duel_max_bet'), 5000), floor(coins * 0.8)) / 10 * 10)::int $$;

create or replace function public.rb_golf_tick(gid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_golf%rowtype; side text; n integer;
begin
    select * into g from public.rb_golf where id = gid for update;
    if not found then return; end if;
    if g.state in ('asked', 'open') and now() - g.at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) then
        update public.rb_golf set state = 'cancelled', why = 'expired' where id = g.id;
        if g.bet > 0 then perform public.rb_pay(g.a, g.bet, 0, 'golf_back', g.id::text); end if;
        return;
    end if;
    if g.state <> 'live' or now() - g.turn_at < make_interval(secs => coalesce(public.rb_cfg('golf_turn_s'), 25)) then return; end if;
    side := case when g.turn = g.a then 'a' else 'b' end;
    if side = 'a' then
        update public.rb_golf set a_miss = a_miss + 1, a_strokes[hole] = a_strokes[hole] + 1, seq = seq + 1,
               a_in = a_in or a_strokes[hole] + 1 >= 6 where id = g.id returning a_miss into n;
    else
        update public.rb_golf set b_miss = b_miss + 1, b_strokes[hole] = b_strokes[hole] + 1, seq = seq + 1,
               b_in = b_in or b_strokes[hole] + 1 >= 6 where id = g.id returning b_miss into n;
    end if;
    if n >= 3 then perform public.rb_golf_end(g.id, g.turn); return; end if;
    perform public.rb_golf_next(g.id);
end $$;

create or replace function public.rb_golf_next(gid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_golf%rowtype; nxt uuid;
begin
    select * into g from public.rb_golf where id = gid for update;
    if g.a_in and g.b_in then
        if g.hole >= coalesce(array_length(g.holes, 1), 3) then perform public.rb_golf_end(g.id, null); return; end if;
        update public.rb_golf set hole = g.hole + 1, pa = null, pb = null, a_in = false, b_in = false,
               turn = case when (g.hole + 1) % 2 = 0 then g.b else g.a end, turn_at = now() where id = g.id;
        return;
    end if;
    nxt := case when g.turn = g.a then (case when not g.b_in then g.b else g.a end)
                else (case when not g.a_in then g.a else g.b end) end;
    update public.rb_golf set turn = nxt, turn_at = now() where id = g.id;
end $$;

-- you are already busy with golf: hosting a lobby, or in a match
create or replace function public.rb_golf_busy(who uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_golf g where (g.a = who and g.state in ('open', 'asked', 'live'))
                                                     or (g.b = who and g.state = 'live')) $$;

create or replace function public.rb_golf_create(bet integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; gid uuid; hs integer[]; n integer; old record;
begin
    p := public.rb_lock_me();
    for old in select id from public.rb_golf where (a = p.id or b = p.id) and state in ('open', 'asked', 'live') loop
        perform public.rb_golf_tick(old.id);
    end loop;
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    hs := public.rb_golf_pick();
    n := array_length(hs, 1);
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf (a, b, bet, holes, state, a_strokes, b_strokes)
        values (p.id, null, bet, hs, 'open', array_fill(0, array[n]), array_fill(0, array[n])) returning id into gid;
    return json_build_object('id', gid, 'coins', p.coins - bet);
end $$;

create or replace function public.rb_golf_join(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; g public.rb_golf%rowtype;
begin
    p := public.rb_lock_me();
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or g.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if g.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if p.coins < g.bet then raise exception 'rb_not_enough'; end if;
    perform public.rb_pay(p.id, -g.bet, 0, 'golf_bet', g.id::text);
    update public.rb_golf set b = p.id, state = 'live', turn = g.a, turn_at = now() where id = g.id;
    perform public.rb_notice(g.a, 'golf_yes', jsonb_build_object('from', p.username, 'id', g.id));
    return json_build_object('state', 'live', 'id', g.id, 'coins', p.coins - g.bet);
end $$;

create or replace function public.rb_golf_cancel(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_golf where id = gid for update;
    if not found or g.a <> me or g.state not in ('open', 'asked') then raise exception 'rb_duel_gone'; end if;
    update public.rb_golf set state = 'cancelled', why = 'taken back' where id = g.id;
    if g.bet > 0 then perform public.rb_pay(g.a, g.bet, 0, 'golf_back', g.id::text); end if;
    return json_build_object('state', 'cancelled');
end $$;

-- invitations are gone: open a lobby instead
create or replace function public.rb_golf_invite(name text, bet integer) returns json
language plpgsql security definer set search_path = '' as $$
begin
    raise exception 'rb_update_needed';
end $$;

create or replace function public.rb_golf_leave(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_golf where id = gid;
    if not found or (g.a <> me and g.b is distinct from me) then raise exception 'rb_duel_gone'; end if;
    if g.state in ('open', 'asked') and g.a = me then return public.rb_golf_cancel(gid); end if;
    if g.state = 'asked' then return public.rb_golf_answer(gid, false); end if;
    if g.state = 'live' then perform public.rb_golf_end(gid, me); end if;
    return json_build_object('state', 'done');
end $$;

create or replace function public.rb_golf_state(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid;
    if not found or (g.a <> me and g.b is distinct from me) then raise exception 'rb_duel_gone'; end if;
    return json_build_object('id', g.id, 'state', g.state, 'me', case when me = g.a then 'a' else 'b' end,
        'a', (select username from public.profiles where id = g.a), 'b', (select username from public.profiles where id = g.b),
        'bet', g.bet, 'holes', g.holes, 'hole', g.hole, 'seq', g.seq, 'n_holes', coalesce(array_length(g.holes, 1), 3),
        'turn', case when g.turn = g.a then 'a' when g.turn = g.b then 'b' end,
        'left', greatest(0, coalesce(public.rb_cfg('golf_turn_s'), 25) - extract(epoch from now() - g.turn_at))::numeric(6, 1),
        'expires', case when g.state = 'open' then greatest(0, ceil(extract(epoch from (g.at
                         + make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) - now()))))::int end,
        'pa', g.pa, 'pb', g.pb, 'a_in', g.a_in, 'b_in', g.b_in, 'a_strokes', g.a_strokes, 'b_strokes', g.b_strokes,
        'shots', g.shots, 'winner', case when g.winner = g.a then 'a' when g.winner = g.b then 'b' end, 'why', g.why);
end $$;

-- the lobby: every open match anyone can join, your own lobby and your matches
create or replace function public.rb_golf_lobbies() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record; p public.profiles%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    for r in select id from public.rb_golf where state in ('open', 'asked') and now() - at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) loop
        perform public.rb_golf_tick(r.id);
    end loop;
    for r in select id from public.rb_golf where (a = me or b = me) and state = 'live' loop
        perform public.rb_golf_tick(r.id);
    end loop;
    return json_build_object(
        'cap', public.rb_golf_cap(p.coins), 'holes', coalesce(public.rb_cfg('golf_holes'), 5),
        'lobbies', coalesce((select json_agg(json_build_object('id', g.id, 'host', h.username, 'bet', g.bet, 'mine', g.a = me,
                     'left', greatest(0, ceil(extract(epoch from (g.at + make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) - now()))))::int)
                     order by g.a = me desc, g.at)
                   from public.rb_golf g join public.profiles h on h.id = g.a where g.state = 'open'), '[]'::json),
        'live', (select g.id from public.rb_golf g where (g.a = me or g.b = me) and g.state = 'live' limit 1),
        'history', coalesce((select json_agg(json_build_object(
                'id', x.id, 'state', x.state, 'bet', x.bet,
                'other', (select username from public.profiles where id = case when x.a = me then x.b else x.a end),
                'me_total', (select sum(v) from unnest(case when x.a = me then x.a_strokes else x.b_strokes end) v),
                'other_total', (select sum(v) from unnest(case when x.a = me then x.b_strokes else x.a_strokes end) v),
                'won', x.winner = me, 'draw', x.state = 'done' and x.winner is null, 'why', x.why, 'at', x.at) order by x.at desc)
              from (select * from public.rb_golf where (a = me or b = me) and state in ('done', 'live') order by at desc limit 8) x), '[]'::json));
end $$;

-- ================================================================ Coinflip: items against items, black or white
create table if not exists public.rb_flips (
    id uuid primary key default gen_random_uuid(),
    a uuid not null references public.profiles (id) on delete cascade,
    b uuid references public.profiles (id) on delete cascade,
    a_side text not null check (a_side in ('black', 'white')),
    state text not null default 'open' check (state in ('open', 'joined', 'locked', 'done', 'cancelled')),
    a_items uuid[] not null default '{}', b_items uuid[] not null default '{}',
    a_what text[] not null default '{}', b_what text[] not null default '{}',
    a_value bigint not null default 0, b_value bigint not null default 0,
    chance_a numeric(6, 4), result text, winner uuid,
    at timestamptz not null default now(), joined_at timestamptz, locked_at timestamptz, flip_at timestamptz,
    done_at timestamptz, why text
);
alter table public.rb_flips enable row level security;
create index if not exists rb_flips_state on public.rb_flips (state);
create index if not exists rb_flips_a on public.rb_flips (a);
create index if not exists rb_flips_b on public.rb_flips (b);

-- items offered: owned, free, tradeable, worth something. Returns (count, total worth, item ids).
create or replace function public.rb_flip_check(who uuid, items uuid[], out n integer, out total bigint, out whats text[])
language plpgsql security definer set search_path = '' as $$
begin
    items := coalesce(items, '{}');
    n := coalesce(array_length(items, 1), 0);
    if n < 1 or n > coalesce(public.rb_cfg('flip_max_items'), 6) or n <> (select count(distinct x) from unnest(items) x) then
        raise exception 'rb_bad_offer';
    end if;
    perform 1 from public.rb_items where id = any (items) order by id for update;
    if (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
         where it.id = any (items) and it.owner = who and it.locked is null and c.tradeable
           and c.kind not in ('prog', 'tag') and coalesce(c.worth, 0) > 0) <> n then
        raise exception 'rb_item_locked';
    end if;
    select sum(public.rb_worth(it.item)), array_agg(it.item order by it.id) into total, whats
      from public.rb_items it where it.id = any (items);
end $$;

create or replace function public.rb_flip_free(f public.rb_flips, why text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    update public.rb_items set locked = null where locked = 'flip:' || f.id;
    update public.rb_flips set state = 'cancelled', why = rb_flip_free.why, done_at = now() where id = f.id;
end $$;

-- the coin has landed: the loser's items go to the winner. Happens once (the row is locked and the state checked).
create or replace function public.rb_flip_settle(fid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare f public.rb_flips%rowtype; loser uuid;
begin
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'locked' or now() < f.flip_at then return; end if;
    loser := case when f.winner = f.a then f.b else f.a end;
    perform 1 from public.rb_items where locked = 'flip:' || f.id order by id for update;
    update public.rb_items set owner = f.winner, locked = null, origin = 'flip'
     where locked = 'flip:' || f.id and owner = loser;
    update public.rb_items set locked = null where locked = 'flip:' || f.id;
    insert into public.rb_seen (owner, item) select f.winner, w from unnest(f.a_what || f.b_what) w on conflict do nothing;
    perform public.rb_fix_equip(loser);
    update public.rb_flips set state = 'done', done_at = now() where id = f.id;
    perform public.rb_notice(f.winner, 'flip_end', jsonb_build_object('id', f.id, 'won', true, 'value', f.a_value + f.b_value));
    perform public.rb_notice(loser, 'flip_end', jsonb_build_object('id', f.id, 'won', false, 'value', f.a_value + f.b_value));
end $$;

-- time passes: an empty lobby closes after 5 minutes, a joiner who does not pick in time is sent away, a flip lands
create or replace function public.rb_flip_tick(fid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare f public.rb_flips%rowtype;
begin
    select * into f from public.rb_flips where id = fid for update;
    if not found then return; end if;
    if f.state = 'joined' and now() - f.joined_at > make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30) + 2) then
        update public.rb_flips set state = 'open', b = null, joined_at = null where id = f.id;
        f.state := 'open';
    end if;
    if f.state = 'open' and now() - f.at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) then
        perform public.rb_flip_free(f, 'expired');
    elsif f.state = 'locked' and now() >= f.flip_at then
        perform public.rb_flip_settle(f.id);
    end if;
end $$;

-- a safety net: an item still marked for a coinflip that is not running any more is given back
create or replace function public.rb_flip_cleanup(who uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare r record;
begin
    for r in select distinct substr(it.locked, 6)::uuid fid from public.rb_items it
              where it.owner = who and it.locked like 'flip:%' loop
        perform public.rb_flip_tick(r.fid);
    end loop;
    update public.rb_items it set locked = null
     where it.owner = who and it.locked like 'flip:%'
       and not exists (select 1 from public.rb_flips f where 'flip:' || f.id = it.locked and f.state in ('open', 'joined', 'locked'));
end $$;

create or replace function public.rb_flip_busy(who uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_flips f where (f.a = who and f.state in ('open', 'joined', 'locked'))
                                                      or (f.b = who and f.state in ('joined', 'locked'))) $$;

create or replace function public.rb_flip_json(f public.rb_flips, me uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('id', f.id, 'state', f.state, 'mine', f.a = me, 'joiner', f.b = me,
        'a', (select username from public.profiles where id = f.a), 'b', (select username from public.profiles where id = f.b),
        'a_side', f.a_side, 'b_side', case when f.a_side = 'black' then 'white' else 'black' end,
        'a_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.a_what) w),
        'b_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.b_what) w),
        'a_value', f.a_value, 'b_value', f.b_value,
        'min', floor(f.a_value * (1 - coalesce(public.rb_cfg('flip_range'), 0.1))),
        'max', ceil(f.a_value * (1 + coalesce(public.rb_cfg('flip_range'), 0.1))),
        'chance_a', f.chance_a,
        'expires', case when f.state = 'open' then greatest(0, ceil(extract(epoch from (f.at
                         + make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) - now()))))::int end,
        'pick_left', case when f.state = 'joined' then greatest(0, ceil(extract(epoch from (f.joined_at
                         + make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)) - now()))))::int end,
        'flip_in', case when f.state = 'locked' then greatest(0, extract(epoch from (f.flip_at - now())))::numeric(6, 2) end,
        -- the result is only told once the coin has landed: nobody can know it early
        'result', case when f.state = 'done' then f.result end,
        'winner', case when f.state = 'done' then (select username from public.profiles where id = f.winner) end,
        'won', case when f.state = 'done' then f.winner = me end,
        'at', f.at) $$;

create or replace function public.rb_flip_create(side text, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; chk record; fid uuid; f public.rb_flips%rowtype; r record;
begin
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if side not in ('black', 'white') then raise exception 'rb_bad_choice'; end if;
    for r in select id from public.rb_flips where (a = p.id or b = p.id) and state in ('open', 'joined', 'locked') loop
        perform public.rb_flip_tick(r.id);
    end loop;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    chk := public.rb_flip_check(p.id, items);
    insert into public.rb_flips (a, a_side, a_items, a_what, a_value)
        values (p.id, side, items, chk.whats, chk.total) returning * into f;
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    return public.rb_flip_json(f, p.id);
end $$;

create or replace function public.rb_flip_cancel(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a <> me then raise exception 'rb_duel_gone'; end if;
    if f.state <> 'open' then raise exception 'rb_flip_locked'; end if;    -- once someone joined, it can no longer be taken back
    perform public.rb_flip_free(f, 'taken back');
    return json_build_object('state', 'cancelled');
end $$;

create or replace function public.rb_flip_join(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; r record;
begin
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    for r in select id from public.rb_flips where (a = p.id or b = p.id) and state in ('open', 'joined', 'locked') loop
        perform public.rb_flip_tick(r.id);
    end loop;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if f.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    update public.rb_flips set b = p.id, state = 'joined', joined_at = now() where id = f.id returning * into f;
    perform public.rb_notice(f.a, 'flip_join', jsonb_build_object('from', p.username, 'id', f.id));
    return public.rb_flip_json(f, p.id);
end $$;

-- the joiner walks away before locking in: the lobby is open again
create or replace function public.rb_flip_leave(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.b is distinct from me or f.state <> 'joined' then raise exception 'rb_duel_gone'; end if;
    update public.rb_flips set state = 'open', b = null, joined_at = null where id = f.id returning * into f;
    return public.rb_flip_json(f, me);
end $$;

-- the joiner locks in: the flip is decided now, cannot be undone, and lands 15 seconds later
create or replace function public.rb_flip_lock(fid uuid, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; chk record; rng double precision; ch double precision;
        a_wins boolean;
begin
    p := public.rb_lock_me();
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.b is distinct from p.id or f.state <> 'joined' then raise exception 'rb_duel_gone'; end if;
    chk := public.rb_flip_check(p.id, items);
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    if chk.total < floor(f.a_value * (1 - rng)) or chk.total > ceil(f.a_value * (1 + rng)) then raise exception 'rb_flip_range'; end if;
    -- bigger share of the pot = slightly better chance, never below 49% or above 51%
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + chk.total)));
    a_wins := public.rb_rand() < ch;
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    update public.rb_flips set b_items = items, b_what = chk.whats, b_value = chk.total, chance_a = round(ch::numeric, 4),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner = case when a_wins then f.a else f.b end, state = 'locked', locked_at = now(),
           flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
     where id = f.id returning * into f;
    perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', p.username, 'id', f.id));
    return public.rb_flip_json(f, p.id);
end $$;

create or replace function public.rb_flip_state(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid;
    if not found then raise exception 'rb_duel_gone'; end if;
    return public.rb_flip_json(f, me);
end $$;

create or replace function public.rb_flip_list() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for r in select id from public.rb_flips where state in ('open', 'joined', 'locked')
               and (now() - at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int)
                    or (state = 'joined' and now() - joined_at > make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)))
                    or (state = 'locked' and now() >= flip_at)) loop
        perform public.rb_flip_tick(r.id);
    end loop;
    perform public.rb_flip_cleanup(me);
    return json_build_object(
        'flips', coalesce((select json_agg(public.rb_flip_json(f, me) order by (f.a = me or f.b = me) desc, f.state = 'open' desc, f.at desc)
                   from (select * from public.rb_flips where state in ('open', 'joined', 'locked')
                         or (state = 'done' and done_at > now() - interval '90 seconds') order by at desc limit 40) f), '[]'::json),
        'mine', (select f.id from public.rb_flips f where ((f.a = me and f.state in ('open', 'joined', 'locked'))
                   or (f.b = me and f.state in ('joined', 'locked'))) limit 1),
        'max_items', coalesce(public.rb_cfg('flip_max_items'), 6), 'range', coalesce(public.rb_cfg('flip_range'), 0.1),
        'history', coalesce((select json_agg(json_build_object('id', f.id, 'won', f.winner = me, 'value', f.a_value + f.b_value,
                     'other', (select username from public.profiles where id = case when f.a = me then f.b else f.a end),
                     'result', f.result, 'at', f.done_at) order by f.done_at desc)
                   from (select * from public.rb_flips where (a = me or b = me) and state = 'done' order by done_at desc limit 8) f), '[]'::json));
end $$;

-- an item in a coinflip that an admin takes or frees: an open lobby closes, a flip that is locked in is left alone
create or replace function public.rb_free_item(item_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare l text; f public.rb_flips%rowtype;
begin
    select locked into l from public.rb_items where id = item_id;
    if l like 'market:%' then
        update public.rb_listings set state = 'cancelled' where id = substr(l, 8)::uuid and state = 'open';
        update public.rb_offers set state = 'gone' where listing = substr(l, 8)::uuid and state = 'open';
    elsif l like 'trade:%' then
        perform public.rb_trade_end(substr(l, 7)::uuid, 'admin');
    elsif l like 'flip:%' then
        select * into f from public.rb_flips where id = substr(l, 6)::uuid for update;
        if found and f.state = 'locked' then return; end if;
        if found and f.state in ('open', 'joined') then perform public.rb_flip_free(f, 'admin'); end if;
    end if;
    update public.rb_items set locked = null where id = item_id;
end $$;

-- ================================================================ leaving online mode: what would be cancelled, then cancel it
create or replace function public.rb_online_status() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return json_build_object(
        'flip_open', exists (select 1 from public.rb_flips where a = me and state = 'open'),
        'flip_host_joined', exists (select 1 from public.rb_flips where a = me and state = 'joined'),
        'flip_joined', exists (select 1 from public.rb_flips where b = me and state = 'joined'),
        'flip_locked', exists (select 1 from public.rb_flips where (a = me or b = me) and state = 'locked'),
        'golf_open', exists (select 1 from public.rb_golf where a = me and state in ('open', 'asked')),
        'golf_live', exists (select 1 from public.rb_golf where (a = me or b = me) and state = 'live'),
        'giveaways', coalesce((select json_agg(g.title) from public.rb_giveaways g join public.rb_giveaway_entries e
                                 on e.giveaway = g.id and e.owner = me where g.state = 'live' and g.ends_at > now()), '[]'::json));
end $$;

create or replace function public.rb_online_leave() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype; g record; n_flip integer := 0; n_golf integer := 0; n_give integer := 0;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for f in select * from public.rb_flips where a = me and state = 'open' for update loop
        perform public.rb_flip_free(f, 'left'); n_flip := n_flip + 1;
    end loop;
    for f in select * from public.rb_flips where b = me and state = 'joined' for update loop
        update public.rb_flips set state = 'open', b = null, joined_at = null where id = f.id; n_flip := n_flip + 1;
    end loop;
    for g in select id from public.rb_golf where a = me and state in ('open', 'asked') loop
        perform public.rb_golf_cancel(g.id); n_golf := n_golf + 1;
    end loop;
    for g in select id from public.rb_golf where (a = me or b = me) and state = 'live' loop
        perform public.rb_golf_end(g.id, me); n_golf := n_golf + 1;
    end loop;
    delete from public.rb_giveaway_entries e using public.rb_giveaways gw
     where e.owner = me and e.giveaway = gw.id and gw.state = 'live' and gw.ends_at > now();
    get diagnostics n_give = row_count;
    return json_build_object('flips', n_flip, 'golf', n_golf, 'giveaways', n_give);
end $$;

-- ================================================================ casino: Slots go, Roulette and Hi-Lo come
create or replace function public.rb_slots(bet integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
    raise exception 'rb_update_needed';
end $$;

-- Roulette: 25 pockets. 12 red, 12 black (x2) and 1 gold (x24). Returns 96% on every bet.
create or replace function public.rb_roulette(bet integer, pick text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; slot integer; colour text; pay integer := 0;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if pick not in ('red', 'black', 'gold') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'roulette');
    slot := floor(public.rb_rand() * 25)::int;                     -- 0 = gold, odd = red, even = black
    colour := case when slot = 0 then 'gold' when slot % 2 = 1 then 'red' else 'black' end;
    if colour = pick then pay := public.rb_win(p.id, bet * case when pick = 'gold' then 24 else 2 end, 'roulette'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'roulette', bet, jsonb_build_object('slot', slot, 'pick', pick), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('slot', slot, 'colour', colour, 'win', colour = pick,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

-- Hi-Lo: a card is shown; guess if the next one is higher (or the same) or lower (or the same). Every right guess
-- multiplies the prize by the odds (98.5% of fair). Cash out whenever you like after the first right guess.
create or replace function public.rb_hilo(action text, bet integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; cards jsonb; card integer; nxt integer;
        mult numeric; step numeric := coalesce(public.rb_cfg('hilo_step'), 0.985); pay integer := 0; right_ boolean;
        rank integer; hits integer; top numeric;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'hilo' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        perform public.rb_bet(p, bet, 'hilo');
        card := floor(public.rb_rand() * 52)::int;                  -- 0..51: rank = card % 13 + 1, suit = card / 13
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'hilo', bet, jsonb_build_object('cards', jsonb_build_array(card), 'mult', 1, 'hits', 0), true, 0)
            returning * into r;
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', jsonb_build_array(card), 'mult', 1,
                                                                'hits', 0, 'bet', r.bet, 'coins', p.coins - r.bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    cards := r.secret -> 'cards';
    mult := (r.secret ->> 'mult')::numeric;
    hits := (r.secret ->> 'hits')::int;
    card := (cards ->> (jsonb_array_length(cards) - 1))::int;
    rank := card % 13 + 1;
    if action = 'state' then
        return jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits, 'bet', r.bet);
    end if;
    if action in ('higher', 'lower') then
        nxt := floor(public.rb_rand() * 52)::int;
        right_ := case when action = 'higher' then nxt % 13 + 1 >= rank else nxt % 13 + 1 <= rank end;
        cards := cards || to_jsonb(nxt);
        if not right_ then
            update public.rb_rounds set open = false, paid = 0,
                   secret = jsonb_build_object('cards', cards, 'mult', 0, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', 0, 'hits', hits,
                                                                    'right', false, 'paid', 0, 'bet', r.bet, 'coins', p.coins));
        end if;
        mult := round(mult * step * 13.0 / (case when action = 'higher' then 14 - rank else rank end), 4);
        hits := hits + 1;
        top := public.rb_cfg('win_max') / r.bet;
        if mult >= top then action := 'cash'; mult := top; end if;          -- the biggest prize: paid at once
        if action <> 'cash' then
            update public.rb_rounds set secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                    'right', true, 'bet', r.bet, 'coins', p.coins));
        end if;
    end if;
    if action = 'cash' then
        if hits < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * mult, 'hilo');
        update public.rb_rounds set open = false, paid = pay,
               secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                'right', true, 'paid', pay, 'bet', r.bet, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $$;

-- quests count the new games (and no longer Slots)
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_quest_rows(uuid)'::regprocedure) into src;
    if position('roulette' in src) = 0 then
        execute replace(src, $q$casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('timing'))$q$,
                             $q$casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('timing'), ('roulette'), ('hilo'))$q$);
    end if;
end $$;

-- bots: keys like everyone (1 every 30 minutes, up to 12), and Roulette instead of Slots
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_bots_tick()'::regprocedure) into src;
    if position('key_every_min' in src) = 0 then
        src := replace(src, 'key_min = (key_min + mins) % 60, keys = least(48, keys + (key_min + mins) / 60)',
                       'key_min = (key_min + mins) % public.rb_cfg(''key_every_min'')::int, keys = least(greatest(keys, public.rb_cfg(''key_cap'')::int), keys + (key_min + mins) / public.rb_cfg(''key_every_min'')::int)');
        src := replace(src, $q$(array['slots', 'plinko', 'dice', 'mines', 'rocket'])$q$, $q$(array['roulette', 'plinko', 'dice', 'mines', 'rocket'])$q$);
        execute src;
    end if;
end $$;

-- the heartbeat also gives back any item left in a coinflip that is over
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure) into src;
    if position('rb_flip_cleanup' in src) = 0 then
        execute replace(src, 'perform public.rb_bots_tick();', 'perform public.rb_bots_tick(); perform public.rb_flip_cleanup(auth.uid());');
    end if;
end $$;

-- ================================================================ the advent calendar: 1 to 24 December, and a big door on the 25th
create table if not exists public.rb_advent (
    day integer primary key check (day between 1 and 25),
    coins integer not null default 0, keys integer not null default 0,
    items text[] not null default '{}', cases text[] not null default '{}',
    big boolean not null default false
);
create table if not exists public.rb_advent_claims (
    owner uuid not null references public.profiles (id) on delete cascade,
    day integer not null,
    at timestamptz not null default now(),
    primary key (owner, day)
);
alter table public.rb_advent enable row level security;
alter table public.rb_advent_claims enable row level security;

-- the day of December in Paris (0 outside December 2026)
create or replace function public.rb_advent_day() returns integer
language sql stable set search_path = '' as $$
    select case when to_char(now() at time zone 'Europe/Paris', 'YYYY-MM') = '2026-12'
                then extract(day from now() at time zone 'Europe/Paris')::int else 0 end $$;

create or replace function public.rb_advent_reward(d public.rb_advent) returns json
language sql stable set search_path = '' as $$
    select json_build_object('coins', d.coins, 'keys', d.keys, 'items', to_json(d.items), 'cases', to_json(d.cases), 'big', d.big) $$;

create or replace function public.rb_advent() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; today integer := public.rb_advent_day();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    return json_build_object('today', today, 'admin', p.admin, 'open', today > 0 or p.admin,
        'catchup', coalesce(public.rb_cfg('advent_catchup'), 0) > 0,
        'days', (select json_agg(json_build_object('day', a.day, 'big', a.big,
                    'claimed', exists (select 1 from public.rb_advent_claims c where c.owner = me and c.day = a.day),
                    -- what is behind a door: shown once it is opened, and to the admin (right click to peek)
                    'reward', case when p.admin or exists (select 1 from public.rb_advent_claims c where c.owner = me and c.day = a.day)
                                   then public.rb_advent_reward(a) end) order by a.day)
                 from public.rb_advent a));
end $$;

create or replace function public.rb_advent_claim(which integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; d public.rb_advent%rowtype; today integer := public.rb_advent_day(); it text; cs text;
        given jsonb := '[]'::jsonb; new_id uuid;
begin
    p := public.rb_lock_me();
    select * into d from public.rb_advent where day = which;
    if not found then raise exception 'rb_bad_choice'; end if;
    if today = 0 or which > today or (which < today and coalesce(public.rb_cfg('advent_catchup'), 0) = 0) then
        raise exception 'rb_too_soon';
    end if;
    insert into public.rb_advent_claims (owner, day) values (p.id, which) on conflict do nothing;
    if not found then raise exception 'rb_already_claimed'; end if;
    perform public.rb_pay(p.id, d.coins, d.keys, 'advent', which::text);
    foreach it in array d.items loop
        new_id := public.rb_give(p.id, it, 'advent');
        given := given || jsonb_build_object('id', new_id, 'item', it);
    end loop;
    foreach cs in array d.cases loop
        perform public.rb_stock_add(p.id, cs, 1);
    end loop;
    return json_build_object('reward', public.rb_advent_reward(d), 'given', given, 'coins', p.coins + d.coins, 'keys', p.keys + d.keys);
end $$;

-- ================================================================ new looks, limited Christmas looks and new cases
-- balls and song lines come in grey, 13 colours (x1.25) and black / white (one rarity up, x1.25)
do $$ declare row text[]; col text; tiers text[] := array['standard', 'rare', 'special', 'epic'];
               base_price integer[] := array[120, 360, 960, 2400]; t integer; up integer;
begin
    foreach row slice 1 in array array[['ball', 'petal', '1'], ['ball', 'gear', '2'], ['ball', 'planet', '3'], ['ball', 'nova', '4'],
                                       ['line', 'wave', '1'], ['line', 'stars', '2'], ['line', 'helix', '3'], ['line', 'lightning', '4']] loop
        t := row[3]::int; up := least(4, t + 1);
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values (row[1] || ':' || row[2] || ':grey', row[1], row[2], 'grey', tiers[t], base_price[t], base_price[t], true, 0)
            on conflict (id) do nothing;
        foreach col in array array['blue', 'green', 'red', 'yellow', 'orange', 'brown', 'teal', 'lava', 'purple', 'sky', 'lime', 'pink', 'beam'] loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values (row[1] || ':' || row[2] || ':' || col, row[1], row[2], col, tiers[t], base_price[t] * 5 / 4, base_price[t] * 5 / 4, true, 0)
                on conflict (id) do nothing;
        end loop;
        foreach col in array array['black', 'white'] loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values (row[1] || ':' || row[2] || ':' || col, row[1], row[2], col, tiers[up], base_price[up] * 25 / 16, base_price[up] * 25 / 16, true, 0)
                on conflict (id) do nothing;
        end loop;
    end loop;
end $$;

insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('banner:slate', 'banner', 'slate', '', 'standard', 400, 400, true, 0),
    ('banner:pastel', 'banner', 'pastel', '', 'standard', 400, 400, true, 0),
    ('banner:tides', 'banner', 'tides', '', 'rare', 1200, 1200, true, 0),
    ('banner:canyon', 'banner', 'canyon', '', 'rare', 1200, 1200, true, 0),
    ('banner:koi', 'banner', 'koi', '', 'special', 3500, 3500, true, 0),
    ('banner:synthwave', 'banner', 'synthwave', '', 'special', 3500, 3500, true, 0),
    ('banner:supernova', 'banner', 'supernova', '', 'epic', 9000, 9000, true, 0),
    ('banner:dragon', 'banner', 'dragon', '', 'epic', 9000, 9000, true, 0),
    ('frame:wood', 'frame', 'wood', '', 'standard', 300, 300, true, 0),
    ('frame:pulse', 'frame', 'pulse', '', 'rare', 1000, 1000, true, 0),
    ('frame:thorns', 'frame', 'thorns', '', 'special', 3000, 3000, true, 0),
    ('frame:gears', 'frame', 'gears', '', 'special', 3000, 3000, true, 0),
    ('frame:phoenix', 'frame', 'phoenix', '', 'epic', 8000, 8000, true, 0),
    ('theme:lagoon', 'theme', 'lagoon', '', 'rare', 540, 540, true, 0),
    ('theme:midnight', 'theme', 'midnight', '', 'special', 1440, 1440, true, 0),
    ('theme:inferno', 'theme', 'inferno', '', 'epic', 3600, 3600, true, 0),
    -- limited (Christmas): never sold, only from the advent calendar and the Winter Case
    ('banner:wreath', 'banner', 'wreath', '', 'rare', null, 1200, true, 0),
    ('banner:hearth', 'banner', 'hearth', '', 'special', null, 3500, true, 0),
    ('banner:northstar', 'banner', 'northstar', '', 'epic', null, 12000, true, 0),
    ('frame:holly', 'frame', 'holly', '', 'rare', null, 1000, true, 0),
    ('frame:snowflake', 'frame', 'snowflake', '', 'special', null, 3000, true, 0),
    ('frame:northstar', 'frame', 'northstar', '', 'epic', null, 10000, true, 0),
    ('ball:snowglobe:white', 'ball', 'snowglobe', 'white', 'special', null, 1500, true, 0),
    ('line:garland:red', 'line', 'garland', 'red', 'rare', null, 563, true, 0)
on conflict (id) do nothing;
update public.rb_catalog set limited = true, price = null
 where id in ('banner:snow', 'banner:aurora', 'frame:frost', 'banner:wreath', 'banner:hearth', 'banner:northstar', 'frame:holly',
              'frame:snowflake', 'frame:northstar', 'ball:snowglobe:white', 'line:garland:red');

insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode, limited) values
    ('lucky', 17, 250, '{8200,1400,330,60,10,0}', 70, 460, false, 9, 0, '{76104,23500,384,0,12}', '', false),
    ('frames', 18, 1000, '{3500,3800,2000,550,150,0}', 400, 2600, false, 9, 0, '{100000,0,0,0,0}', 'kinds:frame', false),
    ('cosmos', 19, 4500, '{3600,0,3200,2300,850,50}', 1300, 5000, false, 9, 0, '{70190,29150,600,42,18}', '', false),
    ('winter', 20, 1500, '{3500,0,4500,2000,0,0}', 800, 2500, false, 9, 0, '{100000,0,0,0,0}',
     'items:banner:snow,banner:wreath,frame:holly,frame:frost,line:garland:red,banner:aurora,banner:hearth,frame:snowflake,ball:snowglobe:white', true),
    ('giftbox', 21, 2000, '{8000,1200,600,160,40,0}', 1500, 4000, false, 9, 0, '{72170,27250,520,42,18}', '', true)
on conflict (id) do nothing;
update public.rb_cases set kind = case when id in ('pocket', 'starter', 'standard', 'premium', 'jackpot', 'titan', 'elite', 'royal', 'lucky') then 'coins'
                                       when id in ('gamble', 'painter', 'vault', 'shiny', 'mythic', 'cosmos') then 'hunt'
                                       when mode like 'kinds:%' then 'style'
                                       when limited then 'limited' else kind end;

-- the deals of the day never offer a limited look
create or replace function public.rb_deal_list() returns table (item text, pct integer)
language sql stable security definer set search_path = '' as $$
    select c.id, (20 + (abs(hashtext(c.id || public.rb_today()::text)) % 4) * 5)::int
      from public.rb_catalog c
     where c.price is not null and not c.limited and c.price <= 30000
       and c.kind in ('badge', 'ball', 'line', 'font', 'theme', 'banner', 'frame')
       and not (c.kind = 'badge' and (c.cls >= 3 or c.rarity = 'exotic'))
     order by md5(c.id || public.rb_today()::text) limit 4 $$;

-- the deals show the taxed shop price before and after the deal (what the buyer really pays)
create or replace function public.rb_deals() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('deals', coalesce((select json_agg(json_build_object('item', d.item, 'pct', d.pct,
                                 'price', ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)))::int,
                                 'now', public.rb_shop_price(d.item), 'worth', c.worth))
                                 from public.rb_deal_list() d join public.rb_catalog c on c.id = d.item), '[]'::json),
                             'ends_in', ceil(extract(epoch from ((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris' - now())))::int) $$;

insert into public.rb_advent (day, coins, keys, items, cases, big) values
    (1, 500, 0, '{}', '{}', false), (2, 0, 2, '{}', '{}', false), (3, 750, 0, '{}', '{}', false),
    (4, 0, 0, '{}', '{winter}', false), (5, 0, 0, '{frame:holly}', '{}', false), (6, 1000, 0, '{}', '{}', false),
    (7, 0, 0, '{line:garland:red}', '{}', false), (8, 0, 3, '{}', '{}', false), (9, 1250, 0, '{}', '{}', false),
    (10, 0, 0, '{banner:snow}', '{}', false), (11, 0, 0, '{}', '{giftbox,giftbox}', false), (12, 0, 0, '{banner:wreath}', '{}', false),
    (13, 1500, 0, '{}', '{}', false), (14, 0, 0, '{frame:frost}', '{}', false), (15, 0, 4, '{}', '{}', false),
    (16, 2000, 0, '{}', '{}', false), (17, 0, 0, '{ball:snowglobe:white}', '{}', false), (18, 0, 0, '{}', '{winter,winter}', false),
    (19, 0, 0, '{frame:snowflake}', '{}', false), (20, 2500, 0, '{}', '{}', false), (21, 0, 0, '{banner:hearth}', '{}', false),
    (22, 0, 5, '{}', '{}', false), (23, 0, 0, '{}', '{giftbox,giftbox,giftbox}', false), (24, 3000, 0, '{banner:aurora}', '{}', false),
    (25, 10000, 6, '{banner:northstar,frame:northstar}', '{winter,winter,winter}', true)
on conflict (day) do nothing;

-- every price and chance, now that every item is in
select public.rb_price_all();

-- ================================================================ who may call what
do $$ declare f text; begin
    foreach f in array array['rb_nice(double precision)', 'rb_detail(text, text)', 'rb_worth_base(public.rb_catalog)',
                             'rb_price_all()', 'rb_shop_price(text)', 'rb_pick_weighted(text[], integer, integer)',
                             'rb_case_keyless(public.rb_cases)', 'rb_golf_cap(bigint)', 'rb_golf_busy(uuid)',
                             'rb_flip_check(uuid, uuid[])', 'rb_flip_free(public.rb_flips, text)', 'rb_flip_settle(uuid)',
                             'rb_flip_tick(uuid)', 'rb_flip_cleanup(uuid)', 'rb_flip_busy(uuid)', 'rb_flip_json(public.rb_flips, uuid)',
                             'rb_advent_day()', 'rb_advent_reward(public.rb_advent)',
                             'rb_case_buy(text, integer, text)', 'rb_trade_offer(uuid, uuid[], integer, integer)',
                             'rb_golf_create(integer)', 'rb_golf_join(uuid)', 'rb_golf_cancel(uuid)', 'rb_golf_lobbies()',
                             'rb_flip_create(text, uuid[])', 'rb_flip_cancel(uuid)', 'rb_flip_join(uuid)', 'rb_flip_leave(uuid)',
                             'rb_flip_lock(uuid, uuid[])', 'rb_flip_state(uuid)', 'rb_flip_list()', 'rb_online_status()',
                             'rb_online_leave()', 'rb_roulette(integer, text, text)', 'rb_hilo(text, integer, text)',
                             'rb_advent()', 'rb_advent_claim(integer)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_case_buy(text, integer, text)', 'rb_trade_offer(uuid, uuid[], integer, integer)',
                             'rb_golf_create(integer)', 'rb_golf_join(uuid)', 'rb_golf_cancel(uuid)', 'rb_golf_lobbies()',
                             'rb_flip_create(text, uuid[])', 'rb_flip_cancel(uuid)', 'rb_flip_join(uuid)', 'rb_flip_leave(uuid)',
                             'rb_flip_lock(uuid, uuid[])', 'rb_flip_state(uuid)', 'rb_flip_list()', 'rb_online_status()',
                             'rb_online_leave()', 'rb_roulette(integer, text, text)', 'rb_hilo(text, integer, text)',
                             'rb_advent()', 'rb_advent_claim(integer)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

-- apps older than 3.2 must update before playing online
insert into public.rb_config (key, value) values ('min_build', 2026111720)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
