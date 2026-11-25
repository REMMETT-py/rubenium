-- Undo of 076_v90_remaster.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
drop function if exists public.rb_admin_grant_all cascade;
CREATE OR REPLACE FUNCTION public.rb_admin_rig(name text, kind text, key text, data jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; me text;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if kind not in ('wheel', 'scratch', 'case', 'slots', 'dice', 'flip') then raise exception 'rb_bad_choice'; end if;
    key := case when kind = 'case' then coalesce(key, '') else '' end;
    if kind = 'case' and not exists (select 1 from public.rb_cases where id = key) then raise exception 'rb_no_case'; end if;
    if data is not null then
        if kind = 'wheel' and coalesce((data ->> 'slot')::int, -1) not between 0 and 9 then raise exception 'rb_bad_choice'; end if;
        if kind = 'scratch' and coalesce(data ->> 'tier', '') not in ('standard', 'rare', 'special', 'epic', 'exotic', 'golden') then
            raise exception 'rb_bad_choice';
        end if;
        if kind = 'case' and not ((data ? 'item' and exists (select 1 from public.rb_catalog where id = data ->> 'item'))
                                  or (data ? 'coins' and (data ->> 'coins')::int between 0 and 10000000)) then
            raise exception 'rb_bad_choice';
        end if;
        if kind = 'slots' and (jsonb_array_length(coalesce(data -> 'reels', '[]'::jsonb)) <> 3 or exists (
               select 1 from jsonb_array_elements_text(data -> 'reels') r where r not in ('cherry', 'lemon', 'bell', 'seven', 'gem'))) then
            raise exception 'rb_bad_choice';
        end if;
        if kind in ('dice', 'flip') and jsonb_typeof(data -> 'win') <> 'boolean' then raise exception 'rb_bad_choice'; end if;
    end if;
    select username into me from public.profiles where id = auth.uid();
    delete from public.rb_rigs r where r.owner = p.id and r.kind = rb_admin_rig.kind and r.key = rb_admin_rig.key;
    if data is not null then
        insert into public.rb_rigs (owner, kind, key, data, by_name) values (p.id, rb_admin_rig.kind, rb_admin_rig.key, data, me);
    end if;
    perform public.rb_log(case when data is null then 'rig_clear' else 'rig' end, p.username,
                          jsonb_build_object('kind', kind, 'key', key, 'data', data));
    return true;
end $function$;
drop function if exists public.rb_admin_set_balance cascade;
CREATE OR REPLACE FUNCTION public.rb_flag(who uuid, g text, k text, sev integer, det jsonb, lock_h integer DEFAULT 0)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare rep jsonb; fid bigint;
begin
    select coalesce(jsonb_agg(jsonb_build_object('at', r.at, 'bet', r.bet, 'paid', r.paid, 'info', r.secret) order by r.at desc), '[]'::jsonb)
      into rep from (select * from public.rb_rounds where owner = who and game = g and not open order by at desc limit 12) r;
    select id into fid from public.rb_flags where owner = who and game = g and kind = k and not reviewed
       and at > now() - interval '12 hours' order by id desc limit 1;
    if fid is null then
        insert into public.rb_flags (owner, game, kind, severity, detail, replay) values (who, g, k, sev, det, rep);
    else
        update public.rb_flags set detail = det, replay = rep, severity = greatest(severity, sev), at = now() where id = fid;
    end if;
    if lock_h > 0 then
        insert into public.rb_game_locks (owner, game, until, reason) values (who, g, now() + lock_h * interval '1 hour', k)
            on conflict (owner, game) do update set until = greatest(public.rb_game_locks.until, excluded.until), reason = excluded.reason;
    end if;
end $function$;
drop function if exists public.rb_forge_state cascade;
CREATE OR REPLACE FUNCTION public.rb_game_pay(who uuid, g text, pay integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        m numeric := public.rb_level_mult(who); got integer;
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1) * m);
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    got := greatest(0, least(pay, floor((w ->> 'cap')::int * m)::int - (w ->> 'paid')::int));
    if got > 0 then perform public.rb_key_find(who, g); end if;
    return got;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_gold_wheel()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r integer;
        prizes text[] := array['10000', 'shiny', '20000', 'premium', '40000', 'mythic', '100000', 'royal', '250000'];
        odds integer[] := array[26, 14, 20, 10, 12, 8, 4, 5, 1];
        what text; c integer := 0;
begin
    perform public.rb_need_feature('wheel');
    p := public.rb_lock_me();
    if p.gold_wheels < 1 then raise exception 'rb_nothing_to_collect'; end if;
    r := public.rb_roll(odds);
    what := prizes[r + 1];
    update public.profiles set gold_wheels = gold_wheels - 1 where id = p.id;
    if what ~ '^[0-9]+$' then
        c := what::int;
        perform public.rb_pay(p.id, c, 0, 'gold_wheel', what);
    else
        perform public.rb_stock_add(p.id, what, 1);
        perform public.rb_pay(p.id, 0, 1, 'gold_wheel', what);
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'gold_wheel', 0, jsonb_build_object('prize', what), false, c);
    return jsonb_build_object('slot', r, 'prize', what, 'coins_won', c, 'case', case when c = 0 then what end,
                              'coins', p.coins + c, 'keys', p.keys + case when c = 0 then 1 else 0 end, 'left', p.gold_wheels - 1);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_heartbeat(device text)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    p public.profiles%rowtype;
    credited boolean := false; elsewhere boolean := false;
    got_coins integer := 0; got_keys integer := 0;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_bots_tick(); perform public.rb_flip_cleanup(auth.uid());
    update public.profiles set bot_real_at = now() where id = auth.uid() and bot;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    device := left(coalesce(device, ''), 64);
    if p.last_beat is not null and p.beat_device is distinct from device
       and now() - p.last_beat < interval '150 seconds' then
        elsewhere := true;                                   -- another PC is earning right now
    elsif p.last_beat is null or now() - p.last_beat >= interval '55 seconds' then
        credited := p.last_beat is not null and now() - p.last_beat < interval '150 seconds';
        if credited then
            p.minutes := p.minutes + 1; if p.minutes % 10 = 0 then perform public.rb_xp_add(p.id, 5, 'online', null, true); end if; perform public.rb_wear_add(p.id, p.equip ->> 'banner'); p.coin_min := p.coin_min + 1; p.key_min := p.key_min + 1;
            if p.day <> current_date then p.day := current_date; p.day_coins := 0; end if;
            if p.coin_min >= public.rb_cfg('coin_every_min') then
                p.coin_min := 0;
                if p.day_coins < public.rb_cfg('coin_day_cap') + public.rb_streak_bonus(p) * 72 then
                    got_coins := public.rb_cfg('coin_amount')::int + public.rb_streak_bonus(p); p.day_coins := p.day_coins + got_coins;
                end if;
            end if;
            if p.key_min >= public.rb_cfg('key_every_min') then
                p.key_min := 0;
                if p.keys < public.rb_cfg('key_cap') then got_keys := 1; end if;
            end if;
        end if;
        update public.profiles set minutes = p.minutes, coin_min = p.coin_min, key_min = p.key_min, day = p.day,
               day_coins = p.day_coins, last_beat = now(), beat_device = device where id = p.id;
        perform public.rb_pay(p.id, got_coins, got_keys, 'time', null);
    end if;
    return json_build_object('username', p.username, 'minutes', p.minutes, 'credited', credited,
                             'elsewhere', elsewhere, 'coins', p.coins + got_coins, 'keys', p.keys + got_keys,
                             'got_coins', got_coins, 'got_keys', got_keys, 'coin_min', p.coin_min, 'key_min', p.key_min,
                             'day_coins', p.day_coins);
end $function$;
drop function if exists public.rb_key_forge cascade;
CREATE OR REPLACE FUNCTION public.rb_login_claim()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; s integer; r jsonb; c integer; k integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    if p.streak_day = public.rb_today() then raise exception 'rb_wait'; end if;
    s := case when p.streak_day = public.rb_today() - 1 then p.streak + 1 else 1 end;
    r := public.rb_login_rewards() -> ((s - 1) % 7);
    c := coalesce((r ->> 'coins')::int, 0); k := coalesce((r ->> 'keys')::int, 0);
    update public.profiles set streak = s, streak_day = public.rb_today() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'login', s::text);
    if r ? 'case' then perform public.rb_stock_add(p.id, r ->> 'case', 1); end if;
    return jsonb_build_object('streak', s, 'reward', r, 'coins', p.coins + c, 'keys', p.keys + k);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_login_rewards()
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select '[{"coins":100},{"coins":150},{"keys":1},{"coins":250},{"keys":2},{"coins":500},{"coins":1000,"keys":1,"case":"premium"}]'::jsonb $function$;
drop function if exists public.rb_login_rewards_for cascade;
CREATE OR REPLACE FUNCTION public.rb_login_state()
 RETURNS json
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; s integer;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    s := case when p.streak_day = public.rb_today() then p.streak
              when p.streak_day = public.rb_today() - 1 then p.streak else 0 end;   -- missed a day: back to day 1
    return json_build_object('streak', s, 'claimed', p.streak_day = public.rb_today(),
                             'day', case when p.streak_day = public.rb_today() then (s - 1) % 7 else s % 7 end,
                             'rewards', public.rb_login_rewards());
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_answer(offer uuid, accept boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; o public.rb_offers%rowtype; l public.rb_listings%rowtype; res jsonb;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    select * into o from public.rb_offers where id = offer for update;
    if not found or o.state <> 'open' then raise exception 'rb_offer_gone'; end if;
    select * into l from public.rb_listings where id = o.listing;
    if l.seller <> p.id then raise exception 'rb_offer_gone'; end if;
    if not coalesce(accept, false) then
        update public.rb_offers set state = 'refused' where id = o.id;
        perform public.rb_notice(o.buyer, 'refused', jsonb_build_object('item', l.what, 'price', o.price));
        return jsonb_build_object('refused', true);
    end if;
    begin
        res := public.rb_market_deal(l.id, o.buyer, o.price);
    exception when others then
        update public.rb_offers set state = 'gone' where id = o.id;
        if sqlerrm like 'rb_not_enough%' then raise exception 'rb_buyer_poor'; end if;
        raise;
    end;
    update public.rb_offers set state = 'taken' where id = o.id;
    perform public.rb_notice(o.buyer, 'bought', jsonb_build_object('item', l.what, 'price', o.price));
    return jsonb_build_object('sold', true, 'coins', (select coins from public.profiles where id = p.id));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_browse(kind text, sort text, page integer)
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(json_agg(x), '[]'::json) from (
        select l.id as listing, l.what as item, l.price, p.username as seller, l.seller = auth.uid() as mine,
               public.rb_estimate(l.what) as estimate, c.rarity
          from public.rb_listings l
          join public.profiles p on p.id = l.seller
          join public.rb_catalog c on c.id = l.what
         where l.state = 'open' and (coalesce(kind, '') = '' or c.kind = kind)
         order by case when sort = 'cheap' then l.price end asc nulls last, l.at desc
         limit 40 offset greatest(0, coalesce(page, 0)) * 40) x $function$;
CREATE OR REPLACE FUNCTION public.rb_market_buy(listing uuid, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb;
begin
    perform public.rb_rate(auth.uid(), 'market_buy', 30);
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    res := public.rb_market_deal(listing, p.id, (select price from public.rb_listings where id = listing));
    return public.rb_remember(p.id, req, res);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_cancel(listing uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; l public.rb_listings%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'market_list', 20);
    p := public.rb_lock_me();
    select * into l from public.rb_listings where id = listing and seller = p.id for update;
    if not found or l.state <> 'open' then raise exception 'rb_not_listed'; end if;
    update public.rb_listings set state = 'cancelled' where id = l.id;
    update public.rb_items set locked = null where id = l.item and locked = 'market:' || l.id;
    return true;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_list(item_id uuid, price integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype; est integer;
        lid uuid;
begin
    perform public.rb_rate(auth.uid(), 'market_list', 20);
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    select * into c from public.rb_catalog where id = it.item;
    if not c.tradeable then raise exception 'rb_not_tradeable'; end if;
    est := public.rb_estimate(it.item);
    if price is null or price < ceil(est * public.rb_cfg('market_min_mult'))
       or price > greatest(floor(est * public.rb_cfg('market_max_mult')), coalesce(c.price, 0)) then
        raise exception 'rb_bad_price';
    end if;
    if (select count(*) from public.rb_listings where seller = p.id and state = 'open') >= public.rb_cfg('market_max_listings') then
        raise exception 'rb_too_many_listings';
    end if;
    insert into public.rb_listings (seller, item, what, price) values (p.id, it.id, it.item, price) returning id into lid;
    update public.rb_items set locked = 'market:' || lid where id = it.id;
    return jsonb_build_object('listing', lid, 'price', price);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_mine()
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(json_agg(json_build_object('listing', l.id, 'item', l.what, 'price', l.price, 'state', l.state,
                                               'at', l.sold_at, 'buyer', (select username from public.profiles where id = l.buyer))
                             order by l.at desc), '[]'::json)
      from (select * from public.rb_listings where seller = auth.uid()
             and (state = 'open' or (state = 'sold' and sold_at > now() - interval '7 days'))
             order by at desc limit 40) l $function$;
CREATE OR REPLACE FUNCTION public.rb_market_offer(listing uuid, price integer)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; l public.rb_listings%rowtype; oid uuid;
begin
    perform public.rb_rate(auth.uid(), 'market_offer', 20);
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into l from public.rb_listings where id = listing;
    if not found or l.state <> 'open' then raise exception 'rb_not_listed'; end if;
    if l.seller = p.id then raise exception 'rb_own_listing'; end if;
    if price is null or price >= l.price or price < ceil(l.price * public.rb_cfg('offer_min_share')) then
        raise exception 'rb_bad_price';
    end if;
    if price > p.coins then raise exception 'rb_not_enough'; end if;
    if (select count(*) from public.rb_offers where buyer = p.id and state = 'open') >= public.rb_cfg('offers_max') then
        raise exception 'rb_too_many_offers';
    end if;
    update public.rb_offers set state = 'gone' where rb_offers.listing = l.id and buyer = p.id and state = 'open';
    insert into public.rb_offers (listing, buyer, price) values (l.id, p.id, price) returning id into oid;
    perform public.rb_notice(l.seller, 'offer', jsonb_build_object('item', l.what, 'price', price, 'from', p.username));
    return oid;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_market_offers()
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select json_build_object(
        'to_me', coalesce((select json_agg(json_build_object('offer', o.id, 'item', l.what, 'price', o.price,
                        'asking', l.price, 'from', b.username, 'at', o.at) order by o.at desc)
              from public.rb_offers o join public.rb_listings l on l.id = o.listing
              join public.profiles b on b.id = o.buyer
             where l.seller = auth.uid() and o.state = 'open' and l.state = 'open'), '[]'::json),
        'mine', coalesce((select json_agg(json_build_object('offer', o.id, 'item', l.what, 'price', o.price,
                        'asking', l.price, 'state', o.state, 'at', o.at) order by o.at desc)
              from (select * from public.rb_offers where buyer = auth.uid() order by at desc limit 20) o
              join public.rb_listings l on l.id = o.listing), '[]'::json)) $function$;
CREATE OR REPLACE FUNCTION public.rb_market_price(what text)
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select json_build_object('estimate', public.rb_estimate(what), 'worth', public.rb_worth(what),
        'min', ceil(public.rb_estimate(what) * public.rb_cfg('market_min_mult')),
        'max', greatest(floor(public.rb_estimate(what) * public.rb_cfg('market_max_mult')), coalesce(public.rb_shop_price(what), 0)),
        'sales', coalesce((select json_agg(s.price) from (select price from public.rb_listings
                            where rb_listings.what = rb_market_price.what and state = 'sold'
                            order by sold_at desc limit 10) s), '[]'::json)) $function$;
CREATE OR REPLACE FUNCTION public.rb_market_search(ids text[], kind text, rarity text, cls integer, sort text, page integer)
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(json_agg(x), '[]'::json) from (
        select l.id as listing, l.what as item, l.price, p.username as seller, l.seller = auth.uid() as mine,
               public.rb_estimate(l.what) as estimate, c.rarity, c.worth
          from public.rb_listings l
          join public.profiles p on p.id = l.seller
          join public.rb_catalog c on c.id = l.what
         where l.state = 'open'
           and (rb_market_search.ids is null or l.what = any (rb_market_search.ids))
           and (coalesce(rb_market_search.kind, '') = '' or c.kind = rb_market_search.kind)
           and (coalesce(rb_market_search.rarity, '') = '' or c.rarity = rb_market_search.rarity)
           and (rb_market_search.cls is null or (c.kind = 'badge' and c.cls = rb_market_search.cls))
         order by case when rb_market_search.sort = 'cheap' then l.price end asc nulls last,
                  case when rb_market_search.sort = 'dear' then l.price end desc nulls last,
                  case when rb_market_search.sort = 'deal' then l.price::numeric / greatest(1, c.worth) end asc nulls last,
                  l.at desc
         limit 40 offset greatest(0, coalesce(rb_market_search.page, 0)) * 40) x $function$;
CREATE OR REPLACE FUNCTION public.rb_market_unoffer(offer uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    update public.rb_offers set state = 'gone' where id = offer and buyer = auth.uid() and state = 'open';
    return found;
end $function$;
drop function if exists public.rb_my_tier cascade;
CREATE OR REPLACE FUNCTION public.rb_plinko(bet integer, risk integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; path integer[] := '{}'; box integer := 0; i integer; d integer;
        mult numeric; pay integer;
        tables numeric[][] := array[[8.5, 3, 1.4, 1.1, 0.95, 0.5, 0.95, 1.1, 1.4, 3, 8.5],
                                    [21, 5, 2, 1.3, 0.6, 0.4, 0.6, 1.3, 2, 5, 21],
                                    [70, 9, 3, 0.9, 0.3, 0.2, 0.3, 0.9, 3, 9, 70]];
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if risk is null or risk < 0 or risk > 2 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'plinko');
    for i in 1 .. 10 loop
        d := case when public.rb_rand() < 0.5 then 0 else 1 end;
        path := path || d; box := box + d;
    end loop;
    mult := tables[risk + 1][box + 1];
    pay := public.rb_win(p.id, bet * mult, 'plinko');
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'plinko', bet, '{}'::jsonb, false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('path', to_jsonb(path), 'box', box, 'mult', mult,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_quest_claim(which text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; q record; prize jsonb; k integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    select * into q from public.rb_quest_rows(p.id) x where x.quest = which;
    if not found then raise exception 'rb_no_quest'; end if;
    if q.progress < q.goal then raise exception 'rb_not_done'; end if;
    begin
        insert into public.rb_quest_claims (owner, quest, period) values (p.id, q.quest, q.period);
    exception when unique_violation then
        raise exception 'rb_already_claimed';
    end;
    prize := public.rb_quest_prize(q.reward);
    k := (prize ->> 'keys')::int;
    perform public.rb_pay(p.id, 0, k, 'quest', q.quest);
    if prize ->> 'case' is not null then
        perform public.rb_stock_add(p.id, prize ->> 'case', 1);
    end if;
    return jsonb_build_object('paid', 0, 'coins', p.coins, 'won_keys', k, 'keys', p.keys + k, 'key_found', true,
                              'case', prize ->> 'case');
end $function$;
CREATE OR REPLACE FUNCTION public.rb_rocket(action text, bet integer, target numeric)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; crash numeric; now_mult numeric; pay integer := 0;
        u double precision; aim numeric; past jsonb; ended jsonb;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'rocket' and open for update;
    if found then
        crash := (r.secret ->> 'crash')::numeric;
        aim := (r.secret ->> 'target')::numeric;
        now_mult := floor(exp(0.10 * extract(epoch from (clock_timestamp() - r.at))) * 100) / 100;
        if aim is not null and crash >= aim and now_mult >= aim then            -- the automatic cash-out was reached
            pay := public.rb_win(p.id, r.bet * aim, 'rocket');
            update public.rb_rounds set open = false, paid = pay where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', false, 'auto', true, 'mult', aim, 'crash', crash,
                                        'paid', pay, 'coins', p.coins + pay);
        elsif now_mult >= crash then
            update public.rb_rounds set open = false where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', true, 'crash', crash, 'paid', 0, 'coins', p.coins);
        elsif action = 'cash' then
            if now_mult < public.rb_cfg('rocket_min') then raise exception 'rb_too_early'; end if;
            pay := public.rb_win(p.id, r.bet * now_mult, 'rocket');
            update public.rb_rounds set open = false, paid = pay where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', false, 'mult', now_mult, 'crash', crash, 'paid', pay,
                                        'coins', p.coins + pay);
        elsif action = 'look' then
            return jsonb_build_object('open', true, 'mult', now_mult, 'bet', r.bet, 'target', aim,
                                      'age', extract(epoch from (clock_timestamp() - r.at)));
        else
            raise exception 'rb_round_open';
        end if;
    end if;
    select coalesce(jsonb_agg(x.c), '[]'::jsonb) into past from (
        select (secret ->> 'crash')::numeric as c from public.rb_rounds
         where owner = p.id and game = 'rocket' and not open order by at desc limit 10) x;
    if ended is not null and action <> 'start' then return ended || jsonb_build_object('history', past); end if;
    if action <> 'start' then return jsonb_build_object('open', false, 'history', past); end if;
    if target is not null and (target < public.rb_cfg('rocket_min') or target > 100) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'rocket');
    u := public.rb_rand();
    crash := greatest(1.00, least(100, floor(96 / (1 - u)) / 100));
    insert into public.rb_rounds (owner, game, bet, secret)
        values (p.id, 'rocket', bet, jsonb_build_object('crash', crash, 'target', target));
    return jsonb_build_object('open', true, 'mult', 1, 'bet', bet, 'age', 0, 'target', target, 'history', past,
                              'coins', p.coins + pay - bet);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_roulette_multi(bet integer, picks text[], req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; slot integer; colour text; pay bigint := 0; x text; num integer;
        n integer; wins jsonb := '[]'::jsonb; m integer; total integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('roulette');
    n := coalesce(array_length(picks, 1), 0);
    if n < 1 or n > 6 or (select count(distinct v) from unnest(picks) v) <> n then raise exception 'rb_bad_choice'; end if;
    -- 5.15: no opposite bets (red with black, low with high): you can't cover the whole table
    if ('red' = any (picks) and 'black' = any (picks)) or ('low' = any (picks) and 'high' = any (picks)) then
        raise exception 'rb_roulette_opposite';
    end if;
    foreach x in array picks loop
        if x ~ '^n:[0-9]{1,2}$' then
            if substr(x, 3)::int not between 1 and 24 then raise exception 'rb_bad_choice'; end if;
        elsif x not in ('red', 'black', 'gold', 'low', 'high') then
            raise exception 'rb_bad_choice';
        end if;
    end loop;
    if bet is null or bet < public.rb_cfg('bet_min') then raise exception 'rb_bad_bet'; end if;
    total := bet * n;
    perform public.rb_bet(p, total, 'roulette');
    slot := floor(public.rb_rand() * 25)::int;
    colour := case when slot = 0 then 'gold' when slot % 2 = 1 then 'red' else 'black' end;
    foreach x in array picks loop
        num := case when x like 'n:%' then substr(x, 3)::int end;
        m := case when num is not null and slot = num then 24
                  when x = 'gold' and slot = 0 then 25
                  when x = 'low' and slot between 1 and 12 then 2
                  when x = 'high' and slot between 13 and 24 then 2
                  when x in ('red', 'black') and colour = x then 2
                  else 0 end;
        if m > 0 then
            pay := pay + bet::bigint * m;
            wins := wins || to_jsonb(x);
        end if;
    end loop;
    if pay > 0 then pay := public.rb_win(p.id, pay, 'roulette'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'roulette', total, jsonb_build_object('slot', slot, 'picks', to_jsonb(picks)), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('slot', slot, 'colour', colour, 'win', pay > 0, 'wins', wins,
                                                            'paid', pay, 'coins', p.coins - total + pay));
end $function$;
drop function if exists public.rb_scaled cascade;
CREATE OR REPLACE FUNCTION public.rb_scratch()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; roll double precision; tier text; c integer := 0; k integer := 0; g integer := 0; cp text;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('scratch');
    if p.scratch_at is not null and now() < p.scratch_at + make_interval(hours => public.rb_cfg('scratch_hours')::int) then
        raise exception 'rb_wait';
    end if;
    roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    roll := coalesce(case public.rb_rig_take(p.id, 'scratch', '') ->> 'tier' when 'standard' then 0.15 when 'rare' then 0.45
                          when 'special' then 0.65 when 'epic' then 0.85 when 'exotic' then 0.94 when 'golden' then 0.99 end, roll);   -- 4.4 rig
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    if roll < 0.30 then tier := 'standard'; c := 80 + floor(public.rb_rand() * 81)::int;
    elsif roll < 0.57 then tier := 'rare'; c := 220 + floor(public.rb_rand() * 201)::int;
    elsif roll < 0.77 then tier := 'special'; k := 1; cp := 'coupon:common';
    elsif roll < 0.91 then tier := 'epic'; k := 2; cp := 'coupon:uncommon';
    elsif roll < 0.97 then tier := 'exotic'; c := 2500; cp := 'coupon:rare';
    else tier := 'golden'; g := 1; cp := 'coupon:epic'; end if;
    update public.profiles set scratch_at = now(), gold_wheels = gold_wheels + g where id = p.id;
    perform public.rb_pay(p.id, c, k, 'scratch', tier);
    if cp is not null then perform public.rb_give(p.id, cp, 'scratch'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'scratch', 0, jsonb_build_object('tier', tier, 'keys', k, 'coupon', cp), false, c);
    return jsonb_build_object('rarity', tier, 'coins_won', c, 'keys_won', k, 'coins', p.coins + c, 'keys', p.keys + k,
                              'gold_wheel', g = 1, 'coupon', cp, 'next', public.rb_cfg('scratch_hours')::int * 3600);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_scratch_odds()
 RETURNS json
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select json_build_array(
        json_build_object('tier', 'standard', 'pct', 30, 'prize', '80-160 coins'),
        json_build_object('tier', 'rare', 'pct', 27, 'prize', '220-420 coins'),
        json_build_object('tier', 'special', 'pct', 20, 'prize', '1 key + Common XP coupon'),
        json_build_object('tier', 'epic', 'pct', 14, 'prize', '2 keys + Uncommon XP coupon'),
        json_build_object('tier', 'exotic', 'pct', 6, 'prize', '2 500 coins + Rare XP coupon'),
        json_build_object('tier', 'golden', 'pct', 3, 'prize', 'Golden Wheel + Epic XP coupon')) $function$;
CREATE OR REPLACE FUNCTION public.rb_spin()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r integer; prize jsonb; q public.profiles%rowtype;
        slots integer[] := array[120, 200, 300, 450, 700, 1200, 2500, -1, -2, -3];   -- -1 = a key, -2 = the Golden Wheel, -3 = an XP coupon
        odds  integer[] := array[1730, 1700, 1700, 1300, 900, 600, 300, 770, 500, 500];
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('wheel');
    if p.spin_prize is not null then perform public.rb_spin_pay(p, p.spin_prize); end if;     -- a prize from an old app: paid now
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    r := coalesce(least(9, greatest(0, (public.rb_rig_take(p.id, 'wheel', '') ->> 'slot')::int)), r);   -- 4.4 rig
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] = -1 then 1 else 0 end,
                                'gold', slots[r + 1] = -2,
                                'coupon', case when slots[r + 1] = -3 then public.rb_coupon_pick(array[6500, 2700, 700, 100]) end);
    update public.profiles set spin_at = now() where id = p.id;
    perform public.rb_spin_pay(p, prize);
    select * into q from public.profiles where id = p.id;
    return prize || jsonb_build_object('collected', true, 'coins', q.coins, 'keys', q.keys, 'gold_wheels', q.gold_wheels);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_spin_odds()
 RETURNS json
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select json_build_object('slots', json_build_array(120, 200, 300, 450, 700, 1200, 2500, -1, -2, -3),
                             'odds', json_build_array(1730, 1700, 1700, 1300, 900, 600, 300, 770, 500, 500)) $function$;
drop function if exists public.rb_spin_table cascade;
drop function if exists public.rb_tier cascade;
drop function if exists public.rb_tier_mult cascade;
drop trigger if exists rb_rounds_scan on public.rb_rounds;
CREATE TRIGGER rb_rounds_scan AFTER INSERT OR UPDATE OF open ON public.rb_rounds FOR EACH ROW WHEN (((new.open = false) AND (new.paid > new.bet))) EXECUTE FUNCTION rb_scan_round();
update public.rb_config set value = 1000000000 where key = 'c4_day_profit';
update public.rb_config set value = 25 where key = 'coin_amount';
update public.rb_config set value = 1800 where key = 'coin_day_cap';
update public.rb_config set value = 10 where key = 'coin_every_min';
update public.rb_config set value = 1000000000 where key = 'cups_day_profit';
delete from public.rb_config where key = 'flags_on';
delete from public.rb_config where key = 'forge_day';
delete from public.rb_config where key = 'forge_min';
delete from public.rb_config where key = 'forge_pct';
update public.rb_config set value = 1000000000 where key = 'game_day_cap';
update public.rb_config set value = 5 where key = 'gold_wheel_pct';
update public.rb_config set value = 12 where key = 'key_cap';
update public.rb_config set value = 30 where key = 'key_every_min';
delete from public.rb_config where key = 'market_on';
delete from public.rb_config where key = 'remaster_90';
delete from public.rb_config where key = 'remaster_90_set';
update public.rb_config set value = 12 where key = 'scratch_hours';
update public.rb_config set value = 0.33 where key = 'shop_tax';
update public.rb_config set value = 2 where key = 'spin_hours';
update public.rb_config set value = 500 where key = 'start_coins';
update public.rb_config set value = 3 where key = 'start_keys';
delete from public.rb_config where key = 'tier_at_1';
delete from public.rb_config where key = 'tier_at_2';
delete from public.rb_config where key = 'tier_at_3';
delete from public.rb_config where key = 'tier_at_4';
delete from public.rb_config where key = 'tier_at_5';
delete from public.rb_config where key = 'tier_x_0';
delete from public.rb_config where key = 'tier_x_1';
delete from public.rb_config where key = 'tier_x_2';
delete from public.rb_config where key = 'tier_x_3';
delete from public.rb_config where key = 'tier_x_4';
delete from public.rb_config where key = 'tier_x_5';
commit;
