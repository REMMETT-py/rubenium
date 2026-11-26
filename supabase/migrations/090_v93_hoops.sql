-- Rubenium 9.3: Hoops, 2 v 2 basketball against bots. Safe to run twice.
--
-- The match runs on the player's PC (you and a bot team-mate against two bots: Club, Regional, National or
-- Professional). rb_hoops_start gives a match id; rb_hoops_finish sends the final score once. The server checks the
-- match is the player's, still open, and that at least the match's length has passed since the start, that the
-- score is possible for that length, and that the stats add up to the score. The prize: a win pays by the bots'
-- level, a loss a little (a 3 minute match; shorter pays less, longer more), times the wealth tier's multiplier,
-- with a generous daily limit that grows with the tier (Casino Legend: none).
begin;

insert into public.rb_features (name, parent) values ('hoops', 'online') on conflict do nothing;
insert into public.rb_config (key, value) values ('hoops_cap', 6000) on conflict do nothing;   -- a day, x the tier

create table if not exists public.rb_hoops_games (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    level text not null check (level in ('Club', 'Regional', 'National', 'Professional')),
    mins integer not null check (mins between 2 and 5),
    state text not null default 'open' check (state in ('open', 'done', 'left')),
    started_at timestamptz not null default now(),
    done_at timestamptz,
    score_me integer,
    score_opp integer,
    ot boolean,
    won boolean,
    paid integer not null default 0,
    xp integer not null default 0,
    stats jsonb
);
create index if not exists rb_hoops_games_owner on public.rb_hoops_games (owner, done_at);
alter table public.rb_hoops_games enable row level security;
revoke all on table public.rb_hoops_games from anon, authenticated;

create or replace function public.rb_hoops_paid_today(who uuid) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce(sum(paid), 0)::int from public.rb_hoops_games
     where owner = who and done_at >= ((public.rb_today())::timestamp at time zone 'Europe/Paris') $$;

-- the day's limit for this player: hoops_cap x their tier's multiplier; none at the top tier
create or replace function public.rb_hoops_cap(who uuid) returns integer
language sql stable security definer set search_path to '' as $$
    select case when coalesce((public.rb_tier(who) ->> 'tier')::int, 0) >= 4 then null
                else floor(coalesce(public.rb_cfg('hoops_cap'), 6000) * public.rb_tier_mult(who))::int end $$;

create or replace function public.rb_hoops_lobby() returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid(); rec jsonb;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select coalesce(jsonb_object_agg(level, jsonb_build_object('w', w, 'l', l, 'best', best)), '{}') into rec
      from (select level, count(*) filter (where won) w, count(*) filter (where not won) l,
                   max(score_me - score_opp) best
              from public.rb_hoops_games where owner = me and state = 'done' group by level) z;
    return jsonb_build_object('rec', rec, 'today', public.rb_hoops_paid_today(me), 'cap', public.rb_hoops_cap(me),
                              'mult', public.rb_tier_mult(me), 'tier', public.rb_tier(me) ->> 'name');
end $$;

create or replace function public.rb_hoops_start(level text, mins integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); gid uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('hoops');
    if level not in ('Club', 'Regional', 'National', 'Professional') or mins not between 2 and 5 then
        raise exception 'rb_bad_request';
    end if;
    -- a match left open (the app closed) counts as left
    update public.rb_hoops_games set state = 'left', done_at = now() where owner = me and state = 'open';
    insert into public.rb_hoops_games (owner, level, mins) values (me, level, mins) returning id into gid;
    return jsonb_build_object('id', gid);
end $$;

create or replace function public.rb_hoops_finish(gid uuid, me_pts integer, opp_pts integer, ot boolean, stats jsonb)
returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_hoops_games%rowtype; won_ boolean; base integer; pr integer; cap integer;
        today integer; xp_ integer; capped boolean := false; maxp integer; fg integer; fga integer; th integer; tha integer;
        pts integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_hoops_games where id = gid and owner = me for update;
    if not found then raise exception 'rb_bad_request'; end if;
    if g.state <> 'open' then raise exception 'rb_already_done'; end if;
    -- the match can't be over before its clock ran out, and must be sent within 2 hours
    if now() < g.started_at + make_interval(secs => g.mins * 60) or now() > g.started_at + interval '2 hours' then
        update public.rb_hoops_games set state = 'left', done_at = now() where id = gid;
        return jsonb_build_object('paid', 0, 'xp', 0, 'why', 'time');
    end if;
    -- a possible score: at most 15 points a minute for a team (+ overtime's one basket), never a tie
    maxp := g.mins * 15 + 3;
    if me_pts not between 0 and maxp or opp_pts not between 0 and maxp or me_pts = opp_pts then
        raise exception 'rb_bad_request';
    end if;
    -- your own points must add up: 2 a basket, 3 a three, and no more than your team scored
    fg := coalesce((stats ->> 'fg')::int, 0); fga := coalesce((stats ->> 'fga')::int, 0);
    th := coalesce((stats ->> 'three')::int, 0); tha := coalesce((stats ->> 'threea')::int, 0);
    pts := coalesce((stats ->> 'pts')::int, 0);
    if fg > fga or th > tha or th > fg or tha > fga or pts <> 2 * fg + th or pts > me_pts then
        raise exception 'rb_bad_request';
    end if;
    won_ := me_pts > opp_pts;
    base := case g.level when 'Club' then case when won_ then 120 else 25 end
                         when 'Regional' then case when won_ then 220 else 40 end
                         when 'National' then case when won_ then 380 else 60 end
                         else case when won_ then 650 else 90 end end;
    base := round(base * (0.55 + 0.15 * g.mins))::int;                    -- 2 min 85%, 3 min 100%, 5 min 130%
    pr := public.rb_scaled(base, public.rb_tier_mult(me));
    cap := public.rb_hoops_cap(me);
    if cap is not null then
        today := public.rb_hoops_paid_today(me);
        if pr > cap - today then
            capped := true;
            pr := greatest(0, cap - today);
        end if;
    end if;
    xp_ := 15 + case when won_ then 15 else 0 end + 5 * (array_position(array['Club', 'Regional', 'National', 'Professional'], g.level) - 1);
    if pr > 0 then perform public.rb_pay(me, pr, 0, 'hoops', gid::text); end if;
    perform public.rb_xp_add(me, xp_, 'hoops', gid::text);
    update public.rb_hoops_games set state = 'done', done_at = now(), score_me = me_pts, score_opp = opp_pts, ot = rb_hoops_finish.ot,
           won = won_, paid = pr, xp = xp_, stats = rb_hoops_finish.stats where id = gid;
    return jsonb_build_object('paid', pr, 'xp', xp_, 'won', won_, 'capped', capped, 'today', public.rb_hoops_paid_today(me),
                              'cap', cap);
end $$;

revoke all on function public.rb_hoops_paid_today(uuid), public.rb_hoops_cap(uuid) from public, anon, authenticated;
revoke all on function public.rb_hoops_lobby(), public.rb_hoops_start(text, integer),
              public.rb_hoops_finish(uuid, integer, integer, boolean, jsonb) from public, anon;
grant execute on function public.rb_hoops_lobby(), public.rb_hoops_start(text, integer),
              public.rb_hoops_finish(uuid, integer, integer, boolean, jsonb) to authenticated;
commit;
