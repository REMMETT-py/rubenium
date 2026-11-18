-- Rubenium 4.2: coinflip VS bot (5 bots with their own worth range), join only on lock-in, Timing (less speed-up,
-- slowdown apps caught), advent door 1 = First Frost 2026, apps older than 4.2 must update.
-- One transaction. Safe to run again. Nothing anyone owns is touched. Undo: 025_down.sql.
begin;
-- ================================================================ Coinflip 4.2
-- Joining reserves nothing: your items are checked and locked only when you lock in, in one step. If someone else
-- locked in first you get rb_flip_taken and nothing of yours was touched.
-- VS bot: the host of an open lobby can call a bot. The server picks the bot for that worth, its items and the result
-- now, and fixes the timeline: searching, found, choosing, joining, 3-2-1, then the usual 15 second count. The app only
-- shows it; the bot's name and items stay hidden until their moment, the result until the coin lands.
-- Five bots, each with its own worth range: Pixel and Milo (low), Nova and Vega (middle to high), Atlas (high to huge).
alter table public.rb_flips add column if not exists bot_found_at timestamptz;

create or replace function public.rb_flip_bots() returns table (name text, lo bigint, hi bigint)
language sql immutable set search_path = '' as $$
    values ('Pixel', 50::bigint, 3000::bigint), ('Milo', 500, 15000), ('Nova', 5000, 150000),
           ('Vega', 25000, 1000000), ('Atlas', 250000, 100000000) $$;

-- the bot for a worth: one of those whose range holds it (else the nearest)
create or replace function public.rb_flip_bot_for(val bigint) returns text
language sql volatile set search_path = '' as $$
    select coalesce(
        (select b.name from public.rb_flip_bots() b where val between b.lo and b.hi order by random() limit 1),
        (select b.name from public.rb_flip_bots() b order by least(abs(ln(greatest(val, 1)::double precision / b.lo)),
                                                                abs(ln(greatest(val, 1)::double precision / b.hi))) limit 1)) $$;

create or replace function public.rb_flip_bot_name() returns text
language sql volatile set search_path = '' as $$
    select name from public.rb_flip_bots() order by random() limit 1 $$;

-- items for a bot worth close to a target: real catalog items (never limited). The last one fills what is left.
create or replace function public.rb_flip_bot_items(target bigint, n integer) returns text[]
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- a set of bot items inside [lo, hi], or null
create or replace function public.rb_flip_bot_fit(target bigint, lo bigint, hi bigint) returns text[]
language plpgsql security definer set search_path = '' as $$
declare whats text[]; total bigint; tries integer := 0;
begin
    loop
        tries := tries + 1;
        whats := public.rb_flip_bot_items(target, 1 + (tries % 6));
        select coalesce(sum(public.rb_worth(w)), 0) into total from unnest(whats) w;
        if coalesce(array_length(whats, 1), 0) > 0 and total between lo and hi then return whats; end if;
        exit when tries >= 18;
    end loop;
    return null;
end $$;

create or replace function public.rb_flip_json(f public.rb_flips, me uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('id', f.id, 'state', f.state, 'mine', f.a = me, 'joiner', f.b = me,
        'a', public.rb_flip_name(f.a, case when f.bot_side = 'a' then f.bot_name end),
        'b', case when f.bot_side = 'b' and f.bot_found_at is not null and now() < f.bot_found_at then null
                  else public.rb_flip_name(f.b, case when f.bot_side = 'b' then f.bot_name end) end,
        'a_bot', f.bot_side = 'a', 'b_bot', f.bot_side = 'b', 'admin_offer', f.admin_offer,
        'vs_bot', f.bot_found_at is not null,
        'a_side', f.a_side, 'b_side', case when f.a_side = 'black' then 'white' else 'black' end,
        'a_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.a_what) w),
        'b_items', case when f.bot_found_at is not null and now() < f.locked_at then '[]'::json else
                   (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.b_what) w) end,
        'a_value', f.a_value,
        'b_value', case when f.bot_found_at is not null and now() < f.locked_at then null else f.b_value end,
        'min', floor(f.a_value * (1 - coalesce(public.rb_cfg('flip_range'), 0.1))),
        'max', ceil(f.a_value * (1 + coalesce(public.rb_cfg('flip_range'), 0.1))),
        'chance_a', case when f.bot_found_at is not null and now() < f.locked_at then null else f.chance_a end,
        'expires', case when f.state in ('open', 'setup') then greatest(0, ceil(extract(epoch from (f.at
                         + make_interval(mins => case when f.state = 'setup' then coalesce(public.rb_cfg('flip_setup_min'), 10)::int
                                                      else coalesce(f.expires_min, public.rb_cfg('lobby_min')::int, 5) end) - now()))))::int end,
        'pick_left', case when f.state = 'joined' then greatest(0, ceil(extract(epoch from (f.joined_at
                         + make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)) - now()))))::int end,
        'found_in', case when f.state = 'locked' and f.bot_found_at is not null
                         then greatest(0, extract(epoch from (f.bot_found_at - now())))::numeric(6, 2) end,
        'join_in', case when f.state = 'locked' and f.bot_found_at is not null
                        then greatest(0, extract(epoch from (f.locked_at - now())))::numeric(6, 2) end,
        'count_in', case when f.state = 'locked' and f.bot_found_at is not null
                         then greatest(0, extract(epoch from (f.locked_at + interval '3 seconds' - now())))::numeric(6, 2) end,
        'flip_in', case when f.state = 'locked' then greatest(0, extract(epoch from (f.flip_at - now())))::numeric(6, 2) end,
        'result', case when f.state = 'done' then f.result end,
        'winner', case when f.state = 'done' then (case f.winner_side when 'a' then public.rb_flip_name(f.a, f.bot_name)
                                                                     else public.rb_flip_name(f.b, f.bot_name) end) end,
        'won', case when f.state = 'done' then f.winner = me end,
        'at', f.at) $$;

-- looking before locking in: the lobby must be open and not yours. Nothing is reserved (4.2).
create or replace function public.rb_flip_join(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid;
    if not found or f.state <> 'open' then raise exception 'rb_flip_taken'; end if;
    if f.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    return public.rb_flip_json(f, p.id);
end $$;

-- locking in: you join and put your items in at the same moment. First to lock in wins the seat.
create or replace function public.rb_flip_lock(fid uuid, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; chk record; rng double precision; ch double precision; a_wins boolean;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if f.state = 'joined' and f.b = p.id then
        null;                                                        -- a seat taken before 4.2
    elsif f.state <> 'open' then
        raise exception 'rb_flip_taken';
    elsif f.a = p.id then
        raise exception 'rb_thats_you';
    elsif public.rb_flip_busy(p.id) then
        raise exception 'rb_one_lobby';
    end if;
    chk := public.rb_flip_check(p.id, items);
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    if chk.total < floor(f.a_value * (1 - rng)) or chk.total > ceil(f.a_value * (1 + rng)) then raise exception 'rb_flip_range'; end if;
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + chk.total)));
    a_wins := public.rb_rand() < ch;
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    update public.rb_flips set b = p.id, joined_at = now(), b_items = items, b_what = chk.whats, b_value = chk.total,
           chance_a = round(ch::numeric, 4),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked', locked_at = now(),
           flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
     where id = f.id returning * into f;
    if f.a is not null then perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', p.username, 'id', f.id)); end if;
    return public.rb_flip_json(f, p.id);
end $$;

-- VS bot: your open lobby gets a bot of the right worth
create or replace function public.rb_flip_vs_bot(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; rng double precision; whats text[]; total bigint;
        ch double precision; a_wins boolean; found_s double precision; choose_s double precision; bot text;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a is distinct from p.id then raise exception 'rb_duel_gone'; end if;
    if f.state <> 'open' then raise exception 'rb_flip_taken'; end if;
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    whats := public.rb_flip_bot_fit(f.a_value, floor(f.a_value * (1 - rng))::bigint, ceil(f.a_value * (1 + rng))::bigint);
    if whats is null then raise exception 'rb_no_bot'; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    bot := public.rb_flip_bot_for(f.a_value);
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + total)));
    a_wins := public.rb_rand() < ch;
    found_s := 3 + random() * 4;                                      -- searching…
    choose_s := 3 + random() * 3;                                     -- the bot picks its items…
    update public.rb_flips set b = null, bot_side = 'b', bot_name = bot, b_what = whats, b_value = total,
           chance_a = round(ch::numeric, 4), joined_at = now(),
           bot_found_at = now() + make_interval(secs => found_s),
           locked_at = now() + make_interval(secs => found_s + choose_s),
           flip_at = now() + make_interval(secs => found_s + choose_s + 3 + coalesce(public.rb_cfg('flip_wait_s'), 15)),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked'
     where id = f.id returning * into f;
    return public.rb_flip_json(f, p.id);
end $$;
revoke all on function public.rb_flip_vs_bot(uuid) from public, anon;
grant execute on function public.rb_flip_vs_bot(uuid) to authenticated;

-- a bot's own lobby: one of the five bots, a worth inside its range
create or replace function public.rb_flip_bot_offer(val bigint, admin_made boolean, bot text, side text, minutes integer, items text[]) returns uuid
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- every minute: bots open lobbies now and then (they no longer join players' lobbies by themselves: VS bot does that)
create or replace function public.rb_flip_bots_tick() returns void
language plpgsql security definer set search_path = '' as $$
declare tgt integer; cur integer;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    tgt := least(coalesce(public.rb_cfg('bot_flips_max'), 3)::int,
                 abs(hashtext('flipbots' || floor(extract(epoch from now()) / 2400)::text)) % 4);
    select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state in ('open', 'joined', 'locked');
    if cur < tgt and random() < 0.35 then perform public.rb_flip_bot_offer(null, false, null, null, null, null); end if;
end $$;
-- ================================================================ Timing 4.2
-- The needle speeds up far less (acceleration 0.08-0.14 instead of 0.35-0.50), and the stop time the app sends is
-- only believed when it fits the server's own clock: the app can never be ahead of the server, may be behind by at
-- most a normal network delay, and may not run more than 6% slow over the round (an app slowing Rubenium down).
-- Otherwise the server's own time is used, a little before the moment it got the stop (a normal delay).
create or replace function public.rb_timing(action text, bet integer, ms integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; rd public.rb_rounds%rowtype; seed jsonb; real_ms double precision;
        pos double precision; d double precision; mult numeric := 0; pay integer := 0; grade text; lag double precision;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into rd from public.rb_rounds where owner = p.id and game = 'timing' and open for update;
    if action = 'start' then
        if found then                                            -- an old round never stopped: lost
            update public.rb_rounds set open = false where id = rd.id;
        end if;
        if (select coalesce(sum(r.paid - r.bet), 0) from public.rb_rounds r where r.owner = p.id and r.game = 'timing'
              and r.at >= date_trunc('day', now())) >= 20000 then raise exception 'rb_slow_down'; end if;
        perform public.rb_bet(p, bet, 'timing');
        seed := jsonb_build_object('v', 2.0 + public.rb_rand() * 0.6, 'a', 0.08 + public.rb_rand() * 0.06,
                                   'o', public.rb_rand() * 2, 'c', round((0.2 + public.rb_rand() * 0.6)::numeric, 3));
        insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'timing', bet, seed, true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('seed', seed, 'coins', p.coins - bet));
    end if;
    if action <> 'stop' or not found then raise exception 'rb_bad_choice'; end if;
    real_ms := extract(epoch from clock_timestamp() - rd.at) * 1000;
    lag := real_ms - coalesce(ms, -1);
    if ms is null or ms < 0 or real_ms > 9000 or lag < -40 or lag > 400
       or (real_ms > 1000 and ms < real_ms * 0.94 - 150) then
        ms := greatest(0, least(real_ms - 80, 999999));              -- the server's clock decides
    end if;
    pos := public.rb_timing_pos(rd.secret, least(ms, 9000));
    d := abs(pos - (rd.secret ->> 'c')::float8);
    if real_ms > 9000 then grade := 'late';
    elsif d <= 0.008 then grade := 'perfect'; mult := 4;
    elsif d <= 0.025 then grade := 'good'; mult := 1.8;
    elsif d <= 0.05 then grade := 'close'; mult := 0.9;
    else grade := 'miss'; end if;
    if mult > 0 then pay := public.rb_win(p.id, rd.bet * mult, 'timing'); end if;
    update public.rb_rounds set open = false, paid = pay, secret = rd.secret || jsonb_build_object('pos', pos, 'grade', grade, 'ms', ms)
     where id = rd.id;
    return public.rb_remember(p.id, req, jsonb_build_object('pos', pos, 'grade', grade, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins + pay));
end $$;
-- ================================================================ advent 2026: door 1 is First Frost 2026
-- A Legendary frame made only for this door, for everyone who opens it in December 2026. Limited: it is never sold,
-- never in a case, and will not be made again. (It replaces the Yuletide frame nobody had received yet.)
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, limited)
    values ('frame:firstfrost', 'frame', 'firstfrost', '', 'epic', null, 20000, true, 0, true)
    on conflict (id) do update set rarity = 'epic', price = null, limited = true, tradeable = true;
update public.rb_catalog set worth = coalesce(worth, value), base_worth = coalesce(base_worth, value), weight = coalesce(weight, 1)
 where id = 'frame:firstfrost';
update public.rb_advent set items = '{frame:firstfrost}' where day = 1;

-- ================================================================ apps older than 4.2 must update
insert into public.rb_config (key, value) values ('min_build', 2026111816)
    on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);

commit;
