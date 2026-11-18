-- Undo 025 (4.2): the coinflip, Timing and advent door 1 of 4.1 come back. Items, coins and finished coinflips stay.
begin;
drop function if exists public.rb_flip_vs_bot(uuid);
create or replace function public.rb_flip_json(f public.rb_flips, me uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('id', f.id, 'state', f.state, 'mine', f.a = me, 'joiner', f.b = me,
        'a', public.rb_flip_name(f.a, case when f.bot_side = 'a' then f.bot_name end),
        'b', public.rb_flip_name(f.b, case when f.bot_side = 'b' then f.bot_name end),
        'a_bot', f.bot_side = 'a', 'b_bot', f.bot_side = 'b', 'admin_offer', f.admin_offer,
        'a_side', f.a_side, 'b_side', case when f.a_side = 'black' then 'white' else 'black' end,
        'a_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.a_what) w),
        'b_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.b_what) w),
        'a_value', f.a_value, 'b_value', f.b_value,
        'min', floor(f.a_value * (1 - coalesce(public.rb_cfg('flip_range'), 0.1))),
        'max', ceil(f.a_value * (1 + coalesce(public.rb_cfg('flip_range'), 0.1))),
        'chance_a', f.chance_a,
        'expires', case when f.state in ('open', 'setup') then greatest(0, ceil(extract(epoch from (f.at
                         + make_interval(mins => case when f.state = 'setup' then coalesce(public.rb_cfg('flip_setup_min'), 10)::int
                                                      else coalesce(f.expires_min, public.rb_cfg('lobby_min')::int, 5) end) - now()))))::int end,
        'pick_left', case when f.state = 'joined' then greatest(0, ceil(extract(epoch from (f.joined_at
                         + make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)) - now()))))::int end,
        'flip_in', case when f.state = 'locked' then greatest(0, extract(epoch from (f.flip_at - now())))::numeric(6, 2) end,
        'result', case when f.state = 'done' then f.result end,
        'winner', case when f.state = 'done' then (case f.winner_side when 'a' then public.rb_flip_name(f.a, f.bot_name)
                                                                     else public.rb_flip_name(f.b, f.bot_name) end) end,
        'won', case when f.state = 'done' then f.winner = me end,
        'at', f.at) $$;

create or replace function public.rb_flip_join(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; r record;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    for r in select id from public.rb_flips where (a = p.id or b = p.id) and state in ('setup', 'open', 'joined', 'locked') loop
        perform public.rb_flip_tick(r.id);
    end loop;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if f.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    update public.rb_flips set b = p.id, state = 'joined', joined_at = now() where id = f.id returning * into f;
    if f.a is not null then perform public.rb_notice(f.a, 'flip_join', jsonb_build_object('from', p.username, 'id', f.id)); end if;
    return public.rb_flip_json(f, p.id);
end $$;

-- the joiner locks in: decided now by the server, lands 15 seconds later, cannot be undone
create or replace function public.rb_flip_lock(fid uuid, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; chk record; rng double precision; ch double precision; a_wins boolean;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.b is distinct from p.id or f.state <> 'joined' then raise exception 'rb_duel_gone'; end if;
    chk := public.rb_flip_check(p.id, items);
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    if chk.total < floor(f.a_value * (1 - rng)) or chk.total > ceil(f.a_value * (1 + rng)) then raise exception 'rb_flip_range'; end if;
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + chk.total)));
    a_wins := public.rb_rand() < ch;
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    update public.rb_flips set b_items = items, b_what = chk.whats, b_value = chk.total, chance_a = round(ch::numeric, 4),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked', locked_at = now(),
           flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
     where id = f.id returning * into f;
    if f.a is not null then perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', p.username, 'id', f.id)); end if;
    return public.rb_flip_json(f, p.id);
end $$;

create or replace function public.rb_flip_bot_items(target bigint, n integer) returns text[]
language plpgsql security definer set search_path = '' as $$
declare res text[] := '{}'; left_ bigint := target; per bigint; pick text; i integer;
begin
    for i in 1..greatest(1, least(6, n)) loop
        per := left_ / (n - i + 1);
        exit when per < 50;
        select c.id into pick from public.rb_catalog c
         where c.tradeable and not c.limited and c.kind in ('badge', 'ball', 'line', 'font', 'banner', 'frame', 'theme')
           and coalesce(c.worth, 0) between greatest(5, per * 0.4) and per * 1.6
           and not (c.kind <> 'badge' and c.id = any (res))
         order by abs(ln(c.worth::double precision / per)) + random() * 0.35 limit 1;
        exit when pick is null;
        res := res || pick;
        left_ := left_ - public.rb_worth(pick);
    end loop;
    return res;
end $$;

create or replace function public.rb_flip_bot_name() returns text
language sql volatile set search_path = '' as $$
    select (array['Nova', 'Pixel', 'Echo', 'Atlas', 'Juno', 'Orion', 'Kira', 'Milo', 'Vega', 'Rook', 'Luma', 'Sable'])[1 + floor(random() * 12)::int] $$;

-- make one bot offer (value: rare big ones, some poor ones, mostly average)
create or replace function public.rb_flip_bot_offer(val bigint, admin_made boolean, bot text, side text, minutes integer, items text[]) returns uuid
language plpgsql security definer set search_path = '' as $$
declare r double precision := random(); whats text[]; total bigint; fid uuid;
begin
    if items is not null and array_length(items, 1) > 0 then
        whats := items;
    else
        if val is null then
            val := case when r < 0.03 then 150000 + floor(random() * 450000)
                        when r < 0.13 then 25000 + floor(random() * 125000)
                        when r < 0.33 then 300 + floor(random() * 1700)
                        else 2000 + floor(random() * 23000) end;
        end if;
        whats := public.rb_flip_bot_items(val, 1 + floor(random() * 4)::int);
    end if;
    if coalesce(array_length(whats, 1), 0) = 0 then return null; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    insert into public.rb_flips (a, a_side, state, a_what, a_value, bot_side, bot_name, admin_offer, expires_min)
        values (null, coalesce(side, case when random() < 0.5 then 'black' else 'white' end), 'open', whats, total, 'a',
                coalesce(bot, public.rb_flip_bot_name()), admin_made,
                coalesce(minutes, public.rb_cfg('bot_flip_min')::int, 60))
        returning id into fid;
    return fid;
end $$;

-- every minute (from the heartbeat): 0 to 3 bot offers depending on the hour, and now and then a bot joins a player's lobby
create or replace function public.rb_flip_bots_tick() returns void
language plpgsql security definer set search_path = '' as $$
declare tgt integer; cur integer; f public.rb_flips%rowtype; whats text[]; total bigint; tries integer;
        rng double precision := coalesce(public.rb_cfg('flip_range'), 0.1); ch double precision; a_wins boolean;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    tgt := least(coalesce(public.rb_cfg('bot_flips_max'), 3)::int,
                 abs(hashtext('flipbots' || floor(extract(epoch from now()) / 2400)::text)) % 4);
    select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state in ('open', 'joined', 'locked');
    if cur < tgt and random() < 0.35 then perform public.rb_flip_bot_offer(null, false, null, null, null, null); end if;
    -- a bot joins one waiting player lobby (after a minute and a half at least)
    for f in select * from public.rb_flips where state = 'open' and a is not null and bot_side is null
               and now() - at > interval '90 seconds' order by random() limit 1 for update skip locked loop
        if random() >= 0.12 then exit; end if;
        tries := 0;
        loop
            tries := tries + 1;
            whats := public.rb_flip_bot_items(f.a_value, 1 + floor(random() * 3)::int);
            select coalesce(sum(public.rb_worth(w)), 0) into total from unnest(whats) w;
            exit when (total between floor(f.a_value * (1 - rng)) and ceil(f.a_value * (1 + rng))) or tries >= 6;
        end loop;
        if total between floor(f.a_value * (1 - rng)) and ceil(f.a_value * (1 + rng)) then
            ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                           least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + total)));
            a_wins := public.rb_rand() < ch;
            update public.rb_flips set b = null, bot_side = 'b', bot_name = public.rb_flip_bot_name(), b_what = whats, b_value = total,
                   chance_a = round(ch::numeric, 4), joined_at = now(),
                   result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
                   winner_side = case when a_wins then 'a' else 'b' end, state = 'locked', locked_at = now(),
                   flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
             where id = f.id;
            perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', 'BOT', 'id', f.id, 'bot', true));
        end if;
    end loop;
end $$;

drop function if exists public.rb_flip_bot_fit(bigint, bigint, bigint);
drop function if exists public.rb_flip_bot_for(bigint);
drop function if exists public.rb_flip_bots();

create or replace function public.rb_timing(action text, bet integer, ms integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; rd public.rb_rounds%rowtype; seed jsonb; real_ms double precision;
        pos double precision; d double precision; mult numeric := 0; pay integer := 0; grade text;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into rd from public.rb_rounds where owner = p.id and game = 'timing' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false where id = rd.id;
        end if;
        if (select coalesce(sum(r.paid - r.bet), 0) from public.rb_rounds r where r.owner = p.id and r.game = 'timing'
              and r.at >= date_trunc('day', now())) >= 20000 then raise exception 'rb_slow_down'; end if;
        perform public.rb_bet(p, bet, 'timing');
        seed := jsonb_build_object('v', 2.0 + public.rb_rand() * 0.6, 'a', 0.35 + public.rb_rand() * 0.15,
                                   'o', public.rb_rand() * 2, 'c', round((0.2 + public.rb_rand() * 0.6)::numeric, 3));
        insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'timing', bet, seed, true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('seed', seed, 'coins', p.coins - bet));
    end if;
    if action <> 'stop' or not found then raise exception 'rb_bad_choice'; end if;
    real_ms := extract(epoch from clock_timestamp() - rd.at) * 1000;
    if ms is null or ms < 0 or abs(ms - real_ms) > 450 or real_ms > 9000 then ms := least(real_ms, 999999); end if;
    pos := public.rb_timing_pos(rd.secret, least(ms, 9000));
    d := abs(pos - (rd.secret ->> 'c')::float8);
    if real_ms > 9000 then grade := 'late';
    elsif d <= 0.008 then grade := 'perfect'; mult := 4;
    elsif d <= 0.025 then grade := 'good'; mult := 1.8;
    elsif d <= 0.05 then grade := 'close'; mult := 0.9;
    else grade := 'miss'; end if;
    if mult > 0 then pay := public.rb_win(p.id, rd.bet * mult, 'timing'); end if;
    update public.rb_rounds set open = false, paid = pay, secret = rd.secret || jsonb_build_object('pos', pos, 'grade', grade) where id = rd.id;
    return public.rb_remember(p.id, req, jsonb_build_object('pos', pos, 'grade', grade, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins + pay));
end $$;

update public.rb_advent set items = '{frame:yuletide}' where day = 1;
update public.rb_config set value = 2026111812 where key = 'min_build';
commit;
