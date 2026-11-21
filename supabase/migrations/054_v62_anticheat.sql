-- 6.2.1: Connect 4 payouts, the anti-cheat watch (flags + per-player game locks), and a tighter Cup Game.

-- Connect 4: Easy x1.2, Medium x2, Hard x5, Professional x250
create or replace function public.rb_c4_mult(level text) returns numeric language sql immutable set search_path = '' as $$
    select case level when 'easy' then 1.2 when 'medium' then 2.0 when 'hard' then 5.0 when 'pro' then 250.0 else 0 end $$;

-- ------------------------------------------------------------------------------------------------------------
-- Anti-cheat. rb_flags: what looked wrong (with the last rounds as a replay). rb_game_locks: a game switched off for one player.
create table if not exists public.rb_flags (
    id bigserial primary key, owner uuid not null references public.profiles (id) on delete cascade,
    game text not null, kind text not null, severity integer not null default 1, detail jsonb not null default '{}'::jsonb,
    replay jsonb, at timestamptz not null default now(), reviewed boolean not null default false, reviewed_at timestamptz);
create index if not exists rb_flags_open on public.rb_flags (reviewed, at desc);
create table if not exists public.rb_game_locks (
    owner uuid not null references public.profiles (id) on delete cascade, game text not null,
    until timestamptz not null, reason text, at timestamptz not null default now(), primary key (owner, game));
alter table public.rb_flags enable row level security;
alter table public.rb_game_locks enable row level security;

insert into public.rb_config (key, value) values ('flag_profit_day', 50000), ('cups_day_profit', 8000), ('cups_max_bet', 2000)
    on conflict (key) do nothing;

-- a locked game cannot take a bet (the lock is per player and per game; '*' = every game)
do $$
declare d text; e text;
begin
    select pg_get_functiondef('public.rb_bet(profiles,integer,text)'::regprocedure) into d;
    e := replace(d, E'begin\n    if bet is null', E'begin\n    if exists (select 1 from public.rb_game_locks l where l.owner = p.id and l.game in (game, ''*'') and l.until > now()) then\n        raise exception ''rb_game_locked'';\n    end if;\n    if bet is null');
    if e = d then raise exception 'rb_bet text did not match'; end if;
    execute e;
end $$;

create or replace function public.rb_flag(who uuid, g text, k text, sev integer, det jsonb, lock_h integer default 0) returns void
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- after a winning round closes: look for what a person cannot do
create or replace function public.rb_scan_round() returns trigger language plpgsql security definer set search_path = '' as $$
declare g text := new.game; who uuid := new.owner; prof bigint; nh integer; wh integer; ne integer; we integer;
        fcount integer; fast numeric; hi integer; n integer; lim numeric := coalesce(public.rb_cfg('flag_profit_day'), 50000);
begin
    begin
        if exists (select 1 from public.profiles where id = who and (admin or coalesce(bot, false))) then return new; end if;
        select coalesce(sum(paid - bet), 0) into prof from public.rb_rounds where owner = who and game = g and not open
           and at > now() - interval '24 hours';
        if prof >= lim * 4 then
            perform public.rb_flag(who, g, 'profit', 2, jsonb_build_object('profit_24h', prof, 'limit', lim), 24);
        elsif prof >= lim then
            perform public.rb_flag(who, g, 'profit', 1, jsonb_build_object('profit_24h', prof, 'limit', lim));
        end if;
        if new.paid - new.bet >= 150000 then
            perform public.rb_flag(who, g, 'big_win', 1, jsonb_build_object('won', new.paid - new.bet, 'bet', new.bet));
        end if;
        if g = 'c4' then
            if new.secret ->> 'level' = 'pro' then       -- the Professional plays perfectly and moves first: nobody beats it
                perform public.rb_flag(who, g, 'pro_win', 3, jsonb_build_object('moves', new.secret -> 'moves', 'bet', new.bet), 72);
            elsif new.secret ->> 'level' = 'hard' then
                select count(*) into n from public.rb_rounds where owner = who and game = 'c4' and not open and paid > bet
                   and secret ->> 'level' = 'hard' and at > now() - interval '24 hours';
                if n >= 6 then perform public.rb_flag(who, g, 'hard_wins', 1, jsonb_build_object('hard_wins_24h', n)); end if;
            end if;
        elsif g = 'cups' then
            select count(*) filter (where (secret ->> 'level')::int >= 1), count(*) filter (where (secret ->> 'level')::int >= 1 and paid > bet),
                   count(*) filter (where (secret ->> 'level')::int = 0), count(*) filter (where (secret ->> 'level')::int = 0 and paid > bet)
              into nh, wh, ne, we from public.rb_rounds
             where owner = who and game = 'cups' and not open and secret ->> 'level' is not null and at > now() - interval '24 hours';
            if nh >= 10 and wh::numeric / nh >= 0.7 then
                perform public.rb_flag(who, g, 'win_rate', 2, jsonb_build_object('rounds', nh, 'wins', wh, 'levels', '6+ cups'), 24);
            elsif ne >= 25 and we::numeric / ne >= 0.92 then
                perform public.rb_flag(who, g, 'win_rate', 2, jsonb_build_object('rounds', ne, 'wins', we, 'levels', '3 cups'), 24);
            end if;
            select count(*), avg(rt) into fcount, fast from (select (secret ->> 'rt')::numeric rt from public.rb_rounds
               where owner = who and game = 'cups' and not open and secret ->> 'rt' is not null order by at desc limit 10) t;
            if fcount >= 8 and fast < 0.8 and (select count(*) from (select paid > bet w from public.rb_rounds where owner = who
                 and game = 'cups' and not open order by at desc limit 10) q where w) >= 5 then
                perform public.rb_flag(who, g, 'fast_clicks', 2, jsonb_build_object('avg_reaction_s', round(fast, 2), 'rounds', fcount), 24);
            end if;
        elsif g in ('colour', 'sfx') then
            select count(*), count(*) filter (where (secret ->> 'acc')::numeric >= 97) into n, hi from (select secret from public.rb_rounds
               where owner = who and game = g and not open and secret ->> 'acc' is not null and (secret ->> 'level')::int = 2
               order by at desc limit 8) t;
            if n >= 8 and hi >= 6 then
                perform public.rb_flag(who, g, 'accuracy', 2, jsonb_build_object('hard_rounds', n, 'over_97', hi), 24);
            end if;
        end if;
    exception when others then
        null;                                            -- the watch never breaks a game
    end;
    return new;
end $$;
drop trigger if exists rb_rounds_scan on public.rb_rounds;
create trigger rb_rounds_scan after insert or update of open on public.rb_rounds
    for each row when (new.open = false and new.paid > new.bet) execute function public.rb_scan_round();

-- the admin side
create or replace function public.rb_admin_flag_count() returns integer language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return (select count(*) from public.rb_flags where not reviewed)::integer;
end $$;

create or replace function public.rb_admin_flags() returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return jsonb_build_object('open', (select count(*) from public.rb_flags where not reviewed),
        'list', coalesce((select jsonb_agg(to_jsonb(x)) from (
            select f.id, p.username as name, f.game, f.kind, f.severity, f.detail, f.replay, f.at, f.reviewed,
                   exists (select 1 from public.rb_game_locks l where l.owner = f.owner and (l.game = f.game or l.game = '*') and l.until > now()) as locked
              from public.rb_flags f join public.profiles p on p.id = f.owner
             order by f.reviewed, f.severity desc, f.at desc limit 80) x), '[]'::jsonb));
end $$;

create or replace function public.rb_admin_flag_do(fid bigint, action text) returns jsonb language plpgsql security definer set search_path = '' as $$
declare f public.rb_flags%rowtype; nm text;
begin
    perform public.rb_need_admin();
    select * into f from public.rb_flags where id = fid;
    if not found then raise exception 'rb_bad_choice'; end if;
    select username into nm from public.profiles where id = f.owner;
    if action = 'dismiss' then                              -- looked fine: reviewed, and the game opens again
        update public.rb_flags set reviewed = true, reviewed_at = now() where id = fid;
        delete from public.rb_game_locks where owner = f.owner and game = f.game;
    elsif action = 'unlock' then
        delete from public.rb_game_locks where owner = f.owner and game = f.game;
    elsif action = 'lock' then
        insert into public.rb_game_locks (owner, game, until, reason) values (f.owner, f.game, now() + interval '7 days', 'admin')
            on conflict (owner, game) do update set until = excluded.until, reason = 'admin';
        update public.rb_flags set reviewed = true, reviewed_at = now() where id = fid;
    elsif action = 'ban' then
        perform public.rb_admin_ban(nm, true);
        update public.rb_flags set reviewed = true, reviewed_at = now() where id = fid;
    else
        raise exception 'rb_bad_choice';
    end if;
    return jsonb_build_object('ok', true);
end $$;

revoke execute on function public.rb_admin_flag_count() from anon, public;
revoke execute on function public.rb_admin_flags() from anon, public;
revoke execute on function public.rb_admin_flag_do(bigint, text) from anon, public;
revoke execute on function public.rb_flag(uuid, text, text, integer, jsonb, integer) from anon, public, authenticated;
revoke execute on function public.rb_scan_round() from anon, public, authenticated;
grant execute on function public.rb_admin_flag_count() to authenticated;
grant execute on function public.rb_admin_flags() to authenticated;
grant execute on function public.rb_admin_flag_do(bigint, text) to authenticated;

-- ------------------------------------------------------------------------------------------------------------
-- Cup Game: a daily profit cap (a win pays the bet back once you are 8 000 up on the day), a top bet, and the reaction time
-- of every pick kept in the round (a script clicks the moment the cups stop).
do $$
declare d text; e text;
begin
    select pg_get_functiondef('public.rb_cups(text,integer,integer,integer,text)'::regprocedure) into d;
    e := replace(d, 'late boolean := false;' || E'\n', 'late boolean := false; profit bigint; capped boolean := false;' || E'\n');
    e := replace(e, E'        perform public.rb_bet(p, bet, ''cups'');',
        E'        if bet > coalesce(public.rb_cfg(''cups_max_bet''), 2000) then raise exception ''rb_bad_bet''; end if;\n        perform public.rb_bet(p, bet, ''cups'');');
    e := replace(e, E'        mult := (r.secret ->> ''mult'')::numeric;\n        if won then',
        E'        mult := (r.secret ->> ''mult'')::numeric;\n        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x\n         where x.owner = p.id and x.game = ''cups'' and x.at >= (public.rb_today()::timestamp at time zone ''Europe/Paris'');\n        if profit >= coalesce(public.rb_cfg(''cups_day_profit''), 8000) and mult > 1 then mult := 1; capped := true; end if;\n        if won then');
    e := replace(e, 'jsonb_build_object(''pick'', pick, ''late'', late)', 'jsonb_build_object(''pick'', pick, ''late'', late, ''rt'', round((t - ready)::numeric, 2))');
    e := replace(e, '''capped'', won and mult = 1', '''capped'', capped');
    if position('cups_day_profit' in e) = 0 or position('cups_max_bet' in e) = 0 or position('''rt''' in e) = 0
       or position('''capped'', capped' in e) = 0 or position('profit bigint' in e) = 0 then
        raise exception 'rb_cups text did not match';
    end if;
    execute e;
end $$;

-- (follow-up applied live) the lock check in rb_bet must name the parameter: l.game in (rb_bet.game, '*')
