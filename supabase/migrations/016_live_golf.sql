-- Rubenium 016 (3.0.0 final): rarer top drops (the rarest item is 1 in 1 000 000), 1 key every 15 minutes (up to 5),
-- trading and the market open from the start, better mini game pay, the OG event (16/11/2026) with gold keys,
-- and live 1 v 1 mini golf between friends (it replaces duels).
-- Run it once in Supabase -> SQL Editor (after 015). Running it again changes nothing.

-- ================================================================ settings
insert into public.rb_config (key, value) values
    ('key_every_min', 15), ('key_cap', 5), ('trade_min_minutes', 0), ('game_window_cap', 200), ('game_pay_mult', 1.3),
    ('og_event_until', 1794870000),            -- 17/11/2026 00:00 Paris: the OG event is for the 16th
    ('golf_turn_s', 25), ('golf_fee', 0.05)
on conflict (key) do update set value = excluded.value
 where public.rb_config.key not in ('og_event_until');                 -- the admin may have moved the event: kept

-- ================================================================ rarer top drops (once)
do $$
begin
    if exists (select 1 from public.rb_config where key = 'odds_016') then return; end if;
    update public.rb_cases set odds[6] = case id when 'mythic' then 60 when 'vault' then 15 when 'titan' then 3
                                                when 'gamble' then 3 when 'premium' then 1 when 'standard' then 1 else odds[6] end,
                               odds[5] = case id when 'mythic' then 1840 when 'vault' then 785 when 'titan' then 77
                                                when 'gamble' then 247 when 'premium' then 39 else odds[5] end
     where (mode is null or mode not like 'kinds:%') and mode is distinct from 'jackpot';
    -- Shiny x0.8, Titanium and Gold x0.6; what is taken goes to Basic (Painted in the Painter's case)
    update public.rb_cases set variants = array[
            variants[1] + (variants[3] - round(variants[3] * 0.8)) + (variants[4] - round(variants[4] * 0.6)) + (variants[5] - round(variants[5] * 0.6)),
            variants[2], round(variants[3] * 0.8), round(variants[4] * 0.6), round(variants[5] * 0.6)]
     where (mode is null or mode not like 'kinds:%') and variants[5] > 0 and variants[1] > 0;
    update public.rb_cases set variants = array[
            variants[1],
            variants[2] + (variants[3] - round(variants[3] * 0.8)) + (variants[4] - round(variants[4] * 0.6)) + (variants[5] - round(variants[5] * 0.6)),
            round(variants[3] * 0.8), round(variants[4] * 0.6), round(variants[5] * 0.6)]
     where (mode is null or mode not like 'kinds:%') and variants[5] > 0 and variants[1] = 0;
    insert into public.rb_config (key, value) values ('odds_016', 1);
end $$;

-- Mythic finishes: Titanium 96.5%, Prismatic 3.3%, Gold 0.185% (Rubenium Gold: 1 in about 1 000 000 in the Mythic Hunt)
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_case_drop(public.rb_cases)'::regprocedure) into src;
    if position('array[90000, 9500, 500]' in src) > 0 then
        execute replace(src, 'array[90000, 9500, 500]', 'array[96515, 3300, 185]');
    end if;
end $$;

-- ================================================================ mini games pay a bit more
do $$ declare src text; begin
    select pg_get_functiondef(p.oid) into src from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'rb_game_pay';
    if src is not null and position('game_pay_mult' in src) = 0 then
        execute replace(src, E'begin\n    if n >= fr * 2',
                        E'begin\n    pay := round(pay * coalesce(public.rb_cfg(''game_pay_mult''), 1));\n    if n >= fr * 2');
    end if;
end $$;

-- ================================================================ gold keys (OG event): one use each, used before normal keys
alter table public.profiles add column if not exists gold_keys integer not null default 0 check (gold_keys >= 0);
alter table public.profiles add column if not exists og_event_at timestamptz;

create or replace function public.rb_gold_keys() returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce((select gold_keys from public.profiles where id = auth.uid()), 0) $$;

-- open a case with a gold key: the gold key becomes the key the case needs, then it is gone
create or replace function public.rb_open_case_gold(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if p.gold_keys < 1 then raise exception 'rb_no_key'; end if;
    if coalesce((select n from public.rb_case_stock where owner = p.id and case_id = which), 0) > 0 then
        raise exception 'rb_bad_choice';                         -- a gifted case opens free: no key is used
    end if;
    update public.profiles set gold_keys = gold_keys - 1, keys = keys + 1 where id = p.id;
    return public.rb_open_case(which, req);
end $$;

-- the OG event: once, for OG tag owners who log in before the end of 16/11/2026
create or replace function public.rb_og_event() returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; ids text[];
begin
    p := public.rb_lock_me();
    if p.og_event_at is not null or now() >= to_timestamp(coalesce(public.rb_cfg('og_event_until'), 0))
       or not exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og') then
        return json_build_object('given', false);
    end if;
    select array_agg(c.id order by c.pos, c.id) into ids from public.rb_cases c;
    update public.profiles set og_event_at = now(), gold_keys = gold_keys + 10 where id = p.id;
    perform public.rb_pay(p.id, 10000, 0, 'og_event', null);
    perform public.rb_stock_add(p.id, x, 1) from unnest(ids) x;
    return json_build_object('given', true, 'coins', 10000, 'gold_keys', 10, 'cases', to_json(ids));
end $$;

-- ================================================================ live 1 v 1 mini golf
create table if not exists public.rb_golf (
    id uuid primary key default gen_random_uuid(),
    a uuid not null references public.profiles (id) on delete cascade,        -- who asked (plays first on holes 1 and 3)
    b uuid not null references public.profiles (id) on delete cascade,
    bet integer not null default 0 check (bet >= 0),
    state text not null default 'asked' check (state in ('asked', 'live', 'done', 'cancelled')),
    holes integer[] not null, hole integer not null default 1,                -- hole = 1, 2 or 3
    turn uuid, turn_at timestamptz, seq integer not null default 0,
    pa jsonb, pb jsonb, a_in boolean not null default false, b_in boolean not null default false,
    a_strokes integer[] not null default '{0,0,0}', b_strokes integer[] not null default '{0,0,0}',
    a_miss integer not null default 0, b_miss integer not null default 0,
    shots jsonb not null default '[]', winner uuid, why text,
    at timestamptz not null default now(), done_at timestamptz);
create index if not exists rb_golf_a on public.rb_golf (a, state);
create index if not exists rb_golf_b on public.rb_golf (b, state);
alter table public.rb_golf enable row level security;
revoke all on public.rb_golf from anon, authenticated;

-- the end of a match: the lower total wins the pot (minus the fee); a draw gives both bets back
create or replace function public.rb_golf_end(gid uuid, forfeit uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_golf%rowtype; ta integer; tb integer; w uuid; pot integer;
begin
    select * into g from public.rb_golf where id = gid for update;
    if not found or g.state <> 'live' then return; end if;
    ta := (select sum(x) from unnest(g.a_strokes) x); tb := (select sum(x) from unnest(g.b_strokes) x);
    w := case when forfeit is not null then (case when forfeit = g.a then g.b else g.a end)
              when ta < tb then g.a when tb < ta then g.b end;
    update public.rb_golf set state = 'done', winner = w, done_at = now(),
           why = case when forfeit is not null then 'forfeit' when w is null then 'draw' else 'strokes' end where id = g.id;
    if g.bet > 0 then
        if w is null then
            perform public.rb_pay(g.a, g.bet, 0, 'golf_back', g.id::text);
            perform public.rb_pay(g.b, g.bet, 0, 'golf_back', g.id::text);
        else
            pot := floor(g.bet * 2 * (1 - coalesce(public.rb_cfg('golf_fee'), 0.05)))::int;
            perform public.rb_pay(w, pot, 0, 'golf_win', g.id::text);
        end if;
    end if;
    perform public.rb_notice(x, 'golf_end', jsonb_build_object('id', g.id, 'won', w = x, 'draw', w is null,
                             'other', (select username from public.profiles where id = case when x = g.a then g.b else g.a end)))
       from unnest(array[g.a, g.b]) x;
end $$;

-- whose turn is next (or the next hole, or the end)
create or replace function public.rb_golf_next(gid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_golf%rowtype; nxt uuid;
begin
    select * into g from public.rb_golf where id = gid for update;
    if g.a_in and g.b_in then
        if g.hole >= 3 then perform public.rb_golf_end(g.id, null); return; end if;
        update public.rb_golf set hole = g.hole + 1, pa = null, pb = null, a_in = false, b_in = false,
               turn = case when g.hole + 1 = 2 then g.b else g.a end, turn_at = now() where id = g.id;
        return;
    end if;
    nxt := case when g.turn = g.a then (case when not g.b_in then g.b else g.a end)
                else (case when not g.a_in then g.a else g.b end) end;
    update public.rb_golf set turn = nxt, turn_at = now() where id = g.id;
end $$;

-- time is up for a turn: a penalty stroke; three in a row and the match is lost. Old invitations are cancelled.
create or replace function public.rb_golf_tick(gid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_golf%rowtype; side text; n integer;
begin
    select * into g from public.rb_golf where id = gid for update;
    if not found then return; end if;
    if g.state = 'asked' and now() - g.at > interval '5 minutes' then
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

create or replace function public.rb_golf_invite(name text, bet integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.profiles%rowtype; gid uuid; hs integer[];
begin
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_duel_cap(p.coins, o.coins)) then raise exception 'rb_bad_bet'; end if;
    if (select count(*) from public.rb_golf g where g.a = p.id and g.state = 'asked') >= 3 then raise exception 'rb_too_many'; end if;
    if exists (select 1 from public.rb_golf g where g.state = 'asked' and g.a = p.id and g.b = o.id) then raise exception 'rb_too_many'; end if;
    select array_agg(h) into hs from (select h from generate_series(1, 8) h order by public.rb_rand() limit 3) x;
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf (a, b, bet, holes) values (p.id, o.id, bet, hs) returning id into gid;
    perform public.rb_notice(o.id, 'golf', jsonb_build_object('from', p.username, 'bet', bet, 'id', gid));
    return json_build_object('id', gid, 'coins', p.coins - bet);
end $$;

create or replace function public.rb_golf_answer(gid uuid, yes boolean) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; g public.rb_golf%rowtype;
begin
    p := public.rb_lock_me();
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or g.state <> 'asked' or (g.a <> p.id and g.b <> p.id) then raise exception 'rb_duel_gone'; end if;
    if not coalesce(yes, false) or g.a = p.id then
        update public.rb_golf set state = 'cancelled', why = case when g.a = p.id then 'taken back' else 'declined' end where id = g.id;
        if g.bet > 0 then perform public.rb_pay(g.a, g.bet, 0, 'golf_back', g.id::text); end if;
        if g.a <> p.id then perform public.rb_notice(g.a, 'golf_no', jsonb_build_object('from', p.username)); end if;
        return json_build_object('state', 'cancelled');
    end if;
    if exists (select 1 from public.rb_golf x where x.state = 'live' and p.id in (x.a, x.b)) then raise exception 'rb_too_many'; end if;
    perform public.rb_pay(p.id, -g.bet, 0, 'golf_bet', g.id::text);
    update public.rb_golf set state = 'live', turn = g.a, turn_at = now() where id = g.id;
    perform public.rb_notice(g.a, 'golf_yes', jsonb_build_object('from', p.username, 'id', g.id));
    return json_build_object('state', 'live', 'id', g.id);
end $$;

-- one shot: where it was hit from, the angle and power, and where the ball stopped (or that it went in)
create or replace function public.rb_golf_shot(gid uuid, n integer, x0 double precision, y0 double precision,
                                               ang double precision, pow double precision,
                                               x double precision, y double precision, holed boolean) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype; side text; done boolean; s integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    if n < g.seq then return public.rb_golf_state(gid); end if;           -- already counted (sent twice)
    if g.state <> 'live' or g.turn <> me or n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if pow is null or pow < 0 or pow > 1 or x is null or y is null or x not between 0 and 1 or y not between 0 and 0.62
       or x0 not between 0 and 1 or y0 not between 0 and 0.62 then raise exception 'rb_bad_choice'; end if;
    side := case when me = g.a then 'a' else 'b' end;
    s := (case when side = 'a' then g.a_strokes else g.b_strokes end)[g.hole] + 1;
    done := coalesce(holed, false) or s >= 6;
    if side = 'a' then
        update public.rb_golf set a_strokes[hole] = s, a_in = done, a_miss = 0, pa = jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4)),
               seq = seq + 1 where id = g.id;
    else
        update public.rb_golf set b_strokes[hole] = s, b_in = done, b_miss = 0, pb = jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4)),
               seq = seq + 1 where id = g.id;
    end if;
    update public.rb_golf set shots = (select coalesce(jsonb_agg(v), '[]'::jsonb) from (
               select v from jsonb_array_elements(shots) v order by (v ->> 'n')::int desc limit 11) t)
               || jsonb_build_array(jsonb_build_object('n', g.seq, 'by', side, 'hole', g.hole,
                    'x0', round(x0::numeric, 4), 'y0', round(y0::numeric, 4), 'ang', round(ang::numeric, 5),
                    'pow', round(pow::numeric, 4), 'x', round(x::numeric, 4), 'y', round(y::numeric, 4), 'in', coalesce(holed, false)))
     where id = g.id;
    perform public.rb_golf_next(g.id);
    return public.rb_golf_state(gid);
end $$;

create or replace function public.rb_golf_state(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    return json_build_object('id', g.id, 'state', g.state, 'me', case when me = g.a then 'a' else 'b' end,
        'a', (select username from public.profiles where id = g.a), 'b', (select username from public.profiles where id = g.b),
        'bet', g.bet, 'holes', g.holes, 'hole', g.hole, 'seq', g.seq,
        'turn', case when g.turn = g.a then 'a' when g.turn = g.b then 'b' end,
        'left', greatest(0, coalesce(public.rb_cfg('golf_turn_s'), 25) - extract(epoch from now() - g.turn_at))::numeric(6, 1),
        'pa', g.pa, 'pb', g.pb, 'a_in', g.a_in, 'b_in', g.b_in, 'a_strokes', g.a_strokes, 'b_strokes', g.b_strokes,
        'shots', g.shots, 'winner', case when g.winner = g.a then 'a' when g.winner = g.b then 'b' end, 'why', g.why);
end $$;

create or replace function public.rb_golf_list() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for r in select id from public.rb_golf where (a = me or b = me) and state in ('asked', 'live') loop
        perform public.rb_golf_tick(r.id);
    end loop;
    return coalesce((select json_agg(json_build_object(
        'id', x.id, 'state', x.state, 'bet', x.bet, 'asked_me', x.b = me and x.state = 'asked', 'mine', x.a = me,
        'other', (select username from public.profiles where id = case when x.a = me then x.b else x.a end),
        'me_total', (select sum(v) from unnest(case when x.a = me then x.a_strokes else x.b_strokes end) v),
        'other_total', (select sum(v) from unnest(case when x.a = me then x.b_strokes else x.a_strokes end) v),
        'won', x.winner = me, 'draw', x.state = 'done' and x.winner is null, 'why', x.why, 'at', x.at)
        order by x.state = 'live' desc, x.state = 'asked' desc, x.at desc)
        from (select * from public.rb_golf where a = me or b = me order by at desc limit 15) x), '[]'::json);
end $$;

create or replace function public.rb_golf_leave(gid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_golf where id = gid;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    if g.state = 'asked' then return public.rb_golf_answer(gid, false); end if;
    if g.state = 'live' then perform public.rb_golf_end(gid, me); end if;
    return json_build_object('state', 'done');
end $$;

-- ================================================================ who may call the new functions
do $$ declare f text; begin
    foreach f in array array['rb_gold_keys()', 'rb_open_case_gold(text, text)', 'rb_og_event()', 'rb_golf_end(uuid, uuid)',
                             'rb_golf_next(uuid)', 'rb_golf_tick(uuid)', 'rb_golf_invite(text, integer)',
                             'rb_golf_answer(uuid, boolean)',
                             'rb_golf_shot(uuid, integer, double precision, double precision, double precision, double precision, double precision, double precision, boolean)',
                             'rb_golf_state(uuid)', 'rb_golf_list()', 'rb_golf_leave(uuid)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_gold_keys()', 'rb_open_case_gold(text, text)', 'rb_og_event()', 'rb_golf_invite(text, integer)',
                             'rb_golf_answer(uuid, boolean)',
                             'rb_golf_shot(uuid, integer, double precision, double precision, double precision, double precision, double precision, double precision, boolean)',
                             'rb_golf_state(uuid)', 'rb_golf_list()', 'rb_golf_leave(uuid)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

-- ================================================================ every app older than this build must update
insert into public.rb_config (key, value) values ('min_build', 2026111709)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
