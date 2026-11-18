-- Rubenium 4.3 (migration 026) undone: back to the 025 server. Run in one transaction.
-- Player data stays: items sold in the pawn shop stay sold, coins paid stay paid. The new tables (solo golf, Wave Rush,
-- the pawn shop) are dropped with their rows; open Wave Rush duel bets are refunded first.
begin;
do $$
declare w record;
begin
    for w in select * from public.rb_wave_duels where state in ('open', 'live') and bet > 0 loop
        perform public.rb_pay(w.a, w.bet, 0, 'wave_back', w.id::text);
        if w.state = 'live' and w.b is not null then perform public.rb_pay(w.b, w.bet, 0, 'wave_back', w.id::text); end if;
    end loop;
end $$;
drop function if exists public.rb_wave_lobbies(), public.rb_wave_leave(uuid), public.rb_wave_cancel(uuid), public.rb_wave_join(uuid),
    public.rb_wave_create(integer), public.rb_wave_busy(uuid), public.rb_wave_ping(uuid, integer), public.rb_wave_state(uuid),
    public.rb_wave_duel_json(public.rb_wave_duels, uuid), public.rb_wave_finish(uuid, integer[], integer), public.rb_wave_tick(uuid),
    public.rb_wave_settle(uuid, uuid), public.rb_wave_solo(), public.rb_wave_best(uuid), public.rb_wave_pay_for(integer),
    public.rb_wave_sim(bigint, integer[], integer);
drop table if exists public.rb_wave_runs, public.rb_wave_duels;
delete from public.rb_features where name = 'wave';
delete from public.rb_config where key = 'wave_duel_min';
drop function if exists public.rb_golf_solo_quit(uuid), public.rb_golf_solo_state(uuid),
    public.rb_golf_solo_shot(uuid, integer, double precision, double precision, boolean), public.rb_golf_solo_start(),
    public.rb_golf_solo_json(public.rb_golf_solo), public.rb_golf_solo_pay(integer);
drop table if exists public.rb_golf_solo;
drop function if exists public.rb_pawn_sell(uuid[], bigint, text), public.rb_pawn_enter(uuid[]), public.rb_pawn_quote(uuid, uuid[]),
    public.rb_pawn_me(uuid), public.rb_pawn_rage(double precision), public.rb_pawn_chance(double precision, double precision);
drop table if exists public.rb_pawn;
drop function if exists public.rb_flip_wealth(), public.rb_wealth(uuid);
drop function if exists public.rb_flip_bots();
delete from public.rb_config where key in ('bot_flips_min', 'flip_crowd', 'flip_bot_max');
update public.rb_config set value = 3 where key = 'bot_flips_max';
update public.rb_config set value = 2500 where key = 'xp_day_cap';
update public.rb_catalog set value = case id when 'coupon:common' then 150 when 'coupon:uncommon' then 400
                                             when 'coupon:rare' then 1000 when 'coupon:epic' then 2500 end
 where id in ('coupon:common', 'coupon:uncommon', 'coupon:rare', 'coupon:epic');
-- the cases' odds and coin ranges as they were
update public.rb_cases set odds = '{7800,1800,350,45,5,0}', coin_min = 35, coin_max = 175 where id = 'pocket';
update public.rb_cases set odds = '{7600,1950,400,45,5,0}', coin_min = 80, coin_max = 400 where id = 'starter';
update public.rb_cases set odds = '{7200,2100,600,85,14,1}', coin_min = 200, coin_max = 1100 where id = 'standard';
update public.rb_cases set odds = '{6900,2100,820,140,39,1}', coin_min = 500, coin_max = 2700 where id = 'premium';
update public.rb_cases set odds = '{10000,0,0,0,0,0}', coin_min = 240, coin_max = 64000 where id = 'jackpot';
update public.rb_cases set odds = '{7000,1700,1000,220,77,3}', coin_min = 1200, coin_max = 7900 where id = 'titan';
update public.rb_cases set odds = '{5600,0,3000,1150,247,3}', coin_min = 60, coin_max = 600 where id = 'gamble';
update public.rb_cases set odds = '{3400,4400,1750,380,70,0}', coin_min = 350, coin_max = 2900 where id = 'painter';
update public.rb_cases set odds = '{3400,0,3500,2300,785,15}', coin_min = 1150, coin_max = 9200 where id = 'vault';
update public.rb_cases set odds = '{3800,0,0,4300,1840,60}', coin_min = 2400, coin_max = 19000 where id = 'mythic';
update public.rb_cases set odds = '{7200,1500,900,300,96,4}', coin_min = 2300, coin_max = 13500 where id = 'elite';
update public.rb_cases set odds = '{8300,0,900,600,190,10}', coin_min = 8000, coin_max = 44000 where id = 'royal';
update public.rb_cases set odds = '{3000,0,3200,2600,1170,30}', coin_min = 100, coin_max = 700 where id = 'shiny';
update public.rb_cases set odds = '{8200,1400,330,60,10,0}', coin_min = 70, coin_max = 460 where id = 'lucky';
update public.rb_cases set odds = '{3600,0,3200,2300,850,50}', coin_min = 1300, coin_max = 5000 where id = 'cosmos';
-- the functions as they were (025)
CREATE OR REPLACE FUNCTION public.rb_flip_bots()
 RETURNS TABLE(name text, lo bigint, hi bigint)
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    values ('Pixel', 50::bigint, 3000::bigint), ('Milo', 500, 15000), ('Nova', 5000, 150000),
           ('Vega', 25000, 1000000), ('Atlas', 250000, 100000000) $function$
;
CREATE OR REPLACE FUNCTION public.rb_claim_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform public.rb_xp_add(new.owner, case when tg_table_name = 'rb_set_claims' then 150 else 60 end, 'quests', tg_table_name, true);
    return new;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_flip_bot_for(val bigint)
 RETURNS text
 LANGUAGE sql
 SET search_path TO ''
AS $function$
    select coalesce(
        (select b.name from public.rb_flip_bots() b where val between b.lo and b.hi order by random() limit 1),
        (select b.name from public.rb_flip_bots() b order by least(abs(ln(greatest(val, 1)::double precision / b.lo)),
                                                                abs(ln(greatest(val, 1)::double precision / b.hi))) limit 1)) $function$
;
CREATE OR REPLACE FUNCTION public.rb_flip_bot_items(target bigint, n integer)
 RETURNS text[]
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare res text[] := '{}'; left_ bigint := target; per bigint; pick text; i integer;
begin
    n := greatest(1, least(6, n));
    for i in 1..n loop
        per := left_ / (n - i + 1);
        exit when per < 40;
        select c.id into pick from public.rb_catalog c
         where c.tradeable and not c.limited and c.kind in ('badge', 'ball', 'line', 'font', 'banner', 'frame', 'theme')
           and coalesce(c.worth, 0) between greatest(5, per * 0.4) and least(per * 1.6, left_ * 1.08)
           and not (c.kind <> 'badge' and c.id = any (res))
         order by case when i = n then abs(c.worth - left_)::double precision / greatest(left_, 1)
                       else abs(ln(c.worth::double precision / per)) + random() * 0.35 end
         limit 1;
        exit when pick is null;
        res := res || pick;
        left_ := left_ - public.rb_worth(pick);
    end loop;
    return res;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_flip_bot_offer(val bigint, admin_made boolean, bot text, side text, minutes integer, items text[])
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare whats text[]; total bigint; fid uuid; b record;
begin
    if items is not null and array_length(items, 1) > 0 then
        whats := items;
    else
        if val is null then
            select * into b from public.rb_flip_bots() order by random() limit 1;
            bot := coalesce(bot, b.name);
            val := floor(exp(ln(b.lo) + random() * (ln(b.hi) - ln(b.lo))));
        end if;
        whats := public.rb_flip_bot_fit(val, floor(val * 0.85)::bigint, ceil(val * 1.15)::bigint);
    end if;
    if coalesce(array_length(whats, 1), 0) = 0 then return null; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    insert into public.rb_flips (a, a_side, state, a_what, a_value, bot_side, bot_name, admin_offer, expires_min)
        values (null, coalesce(side, case when random() < 0.5 then 'black' else 'white' end), 'open', whats, total, 'a',
                coalesce(bot, public.rb_flip_bot_for(total)), admin_made,
                coalesce(minutes, public.rb_cfg('bot_flip_min')::int, 60))
        returning id into fid;
    return fid;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_flip_bots_tick()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare tgt integer; cur integer;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    tgt := least(coalesce(public.rb_cfg('bot_flips_max'), 3)::int,
                 abs(hashtext('flipbots' || floor(extract(epoch from now()) / 2400)::text)) % 4);
    select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state in ('open', 'joined', 'locked');
    if cur < tgt and random() < 0.35 then perform public.rb_flip_bot_offer(null, false, null, null, null, null); end if;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_flip_settle(fid uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare f public.rb_flips%rowtype; human_w uuid; human_l uuid; w text; lost jsonb;
begin
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'locked' or now() < f.flip_at then return; end if;
    human_w := case f.winner_side when 'a' then f.a else f.b end;
    human_l := case f.winner_side when 'a' then f.b else f.a end;
    perform 1 from public.rb_items where locked = 'flip:' || f.id order by id for update;
    if human_w is not null and human_l is not null then                        -- player against player
        update public.rb_items set owner = human_w, locked = null, origin = 'flip' where locked = 'flip:' || f.id and owner = human_l;
        update public.rb_items set locked = null where locked = 'flip:' || f.id;
        insert into public.rb_seen (owner, item) select human_w, x from unnest(f.a_what || f.b_what) x on conflict do nothing;
        perform public.rb_fix_equip(human_l);
    elsif human_w is not null then                                             -- a player beat a bot: the bot's items are made for them
        update public.rb_items set locked = null where locked = 'flip:' || f.id;
        foreach w in array (case when f.bot_side = 'a' then f.a_what else f.b_what end) loop
            perform public.rb_give(human_w, w, 'flip');
        end loop;
    else                                                                       -- a bot won: the player's items leave the game
        select coalesce(jsonb_agg(it.item), '[]'::jsonb) into lost from public.rb_items it where it.locked = 'flip:' || f.id;
        delete from public.rb_items where locked = 'flip:' || f.id;
        insert into public.rb_audit (admin, action, target, detail) values (null, 'flip_bot_win', f.id::text,
            jsonb_build_object('player', human_l, 'items', lost, 'bot', f.bot_name));
        perform public.rb_fix_equip(human_l);
    end if;
    update public.rb_flips set state = 'done', done_at = now(), winner = human_w where id = f.id;
    if human_w is not null then
        perform public.rb_notice(human_w, 'flip_end', jsonb_build_object('id', f.id, 'won', true, 'value', f.a_value + f.b_value));
        perform public.rb_xp_add(human_w, 25, 'coinflip', f.id::text, true);
    end if;
    if human_l is not null then
        perform public.rb_notice(human_l, 'flip_end', jsonb_build_object('id', f.id, 'won', false, 'value', f.a_value + f.b_value));
        perform public.rb_xp_add(human_l, 25, 'coinflip', f.id::text, true);
    end if;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_golf_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if new.state = 'done' and old.state = 'live' and new.b is not null and (new.why <> 'forfeit' or new.hole > 1) then
        perform public.rb_xp_add(new.a, 40 + case when new.winner = new.a then 30 else 0 end, 'golf', new.id::text, true);
        perform public.rb_xp_add(new.b, 40 + case when new.winner = new.b then 30 else 0 end, 'golf', new.id::text, true);
    end if;
    return new;
end $function$
;
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
            p.minutes := p.minutes + 1; if p.minutes % 10 = 0 then perform public.rb_xp_add(p.id, 10, 'online', null, true); end if; perform public.rb_wear_add(p.id, p.equip ->> 'banner'); p.coin_min := p.coin_min + 1; p.key_min := p.key_min + 1;
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
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_quest_rows(who uuid)
 RETURNS TABLE(quest text, kind text, goal integer, reward integer, progress integer, period timestamp with time zone, left_s integer)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('timing'), ('roulette'), ('hilo')),
         pool (quest, goal, reward, progress) as (values
            ('h_rounds', 3, 25, (select count(*) from h where game in (select g from casino))::int),
            ('h_mini',   1, 25, (select count(*) from h where game in ('mini', 'park', 'memory'))::int),
            ('h_case',   1, 30, (select count(*) from h where game like 'case:%' or game = 'daily')::int),
            ('h_bet',  100, 25, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int)),
         q (quest, kind, goal, reward, progress) as (
            select pq.quest, 'hour', pq.goal, pq.reward, pq.progress from pool pq
             where pq.quest in ((array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[extract(hour from now())::int % 4 + 1],
                                (array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[(extract(hour from now())::int + 2) % 4 + 1])
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  2, 150, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 150, (select count(*) from d where game in ('mini', 'park', 'memory'))::int),
            ('d_spin',   'day',  1, 100, (select count(*) from d where game = 'spin')::int),
            ('w_rounds', 'week', 200, 1500, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  25, 2000, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 25000, 2000, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int),
            ('w_mini',   'week',  30, 1500, (select count(*) from r where game in ('mini', 'park', 'memory'))::int),
            ('w_golf',   'week',   3, 1500, (select count(*) from public.rb_golf g where g.winner = who and g.state = 'done'
                                               and g.done_at >= date_trunc('week', now()))::int),
            ('w_scratch','week',   7, 1200, (select count(*) from r where game = 'scratch')::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $function$
;
CREATE OR REPLACE FUNCTION public.rb_rounds_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare amt integer := 0; src text;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;               -- counted once, when it ends
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo') then
        if new.bet < 10 then return new; end if;
        src := 'casino'; amt := least(25, 3 + new.bet / 40);
    elsif new.game in ('mini', 'park', 'memory', 'tap', 'g2048', 'sweeper', 'blocks') then
        if coalesce(new.paid, 0) <= 0 then return new; end if;              -- a game thrown away gives nothing
        src := 'minigames'; amt := least(45, 10 + new.paid / 6);
    elsif new.game like 'case:%' then
        src := 'cases'; amt := 8;
    elsif new.game in ('spin', 'scratch') then
        src := 'wheel'; amt := 15;
    else
        return new;
    end if;
    perform public.rb_xp_add(new.owner, amt, src, new.game, true);
    return new;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_trade_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if new.state = 'done' and old.state <> 'done' then
        perform public.rb_xp_add(new.a, 15, 'trading', new.id::text, true);
        perform public.rb_xp_add(new.b, 15, 'trading', new.id::text, true);
    end if;
    return new;
end $function$
;
CREATE OR REPLACE FUNCTION public.rb_xp_cap(src text)
 RETURNS integer
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select case src when 'casino' then 600 when 'minigames' then 900 when 'cases' then 200 when 'golf' then 600
                    when 'coinflip' then 300 when 'trading' then 150 when 'online' then 300 when 'wheel' then 60
                    when 'quests' then 600 else 100000 end $function$
;
CREATE OR REPLACE FUNCTION public.rb_slots(bet integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    raise exception 'rb_update_needed';
end $function$
;
update public.rb_config set value = 2026111816 where key = 'min_build';
commit;
