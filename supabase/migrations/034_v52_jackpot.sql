-- ================================================================ Rubenium 5.2: JACKPOT
-- One jackpot every 15 minutes (Paris clock, on :00 :15 :30 :45). For 120 s anyone can put in 1 to 3 items (6 players
-- at most, each with their own colour); your chance is your share of the total worth. When the time is up the lobby
-- locks and bots fill the empty seats one by one with similar items (only if a real player is in). The wheel spins
-- (10 s) and lands on the winner, chosen by the server when the lobby locked. The winner gets their own items back and
-- picks half (rounded up) of everybody else's items; the rest leaves the game. 2 minutes to pick, then the best ones are
-- picked for them. To join, your items must be worth at least 1% of what is already in (at least 100), so a tiny entry
-- can't take a huge pot for nothing. Everything happens here; the app only shows it. Safe to run again.
begin;

insert into public.rb_features (name, parent) values ('jackpot', 'online') on conflict (name) do nothing;
insert into public.rb_config (key, value) values ('jackpot_every_s', 900), ('jackpot_open_s', 120), ('jackpot_min_pct', 1),
    ('jackpot_min_worth', 100), ('jackpot_xp', 150) on conflict (key) do nothing;

create table if not exists public.rb_jackpots (
    id uuid primary key default gen_random_uuid(),
    slot timestamptz not null unique,                 -- when it opened
    state text not null default 'open' check (state in ('open', 'locked', 'picking', 'done', 'empty')),
    lock_at timestamptz not null,                     -- no more joining
    spin_at timestamptz not null,                     -- the wheel starts (bots have all joined)
    result_at timestamptz not null,                   -- the wheel has stopped: the winner is shown
    pick_until timestamptz not null,
    winner_entry uuid,
    roll double precision,                            -- where on the wheel (0..1) it lands
    total bigint not null default 0,
    picks_allowed integer not null default 0,
    picked jsonb,
    at timestamptz not null default now());
alter table public.rb_jackpots enable row level security;

create table if not exists public.rb_jackpot_entries (
    id uuid primary key default gen_random_uuid(),
    jackpot uuid not null references public.rb_jackpots(id) on delete cascade,
    owner uuid references public.profiles(id) on delete cascade,
    bot_name text,
    colour integer not null,
    item_ids uuid[] not null default '{}',
    whats text[] not null,
    value bigint not null,
    join_at timestamptz not null default now());
create index if not exists rb_jackpot_entries_j on public.rb_jackpot_entries (jackpot);
create unique index if not exists rb_jackpot_entries_one on public.rb_jackpot_entries (jackpot, owner) where owner is not null;
alter table public.rb_jackpot_entries enable row level security;

-- ---------------------------------------------------------------- the jackpot of a moment (made when first asked)
create or replace function public.rb_jackpot_slot(t timestamptz) returns timestamptz
language sql immutable set search_path to '' as $$
    select to_timestamp(floor(extract(epoch from t) / 900) * 900) $$;

create or replace function public.rb_jackpot_make(s timestamptz) returns public.rb_jackpots
language plpgsql security definer set search_path to '' as $$
declare j public.rb_jackpots%rowtype; o double precision := coalesce(public.rb_cfg('jackpot_open_s'), 120);
begin
    select * into j from public.rb_jackpots where slot = s;
    if found then return j; end if;
    insert into public.rb_jackpots (slot, lock_at, spin_at, result_at, pick_until)
        values (s, s + make_interval(secs => o), s + make_interval(secs => o + 12), s + make_interval(secs => o + 22),
                s + make_interval(secs => o + 142))
        on conflict (slot) do nothing;
    select * into j from public.rb_jackpots where slot = s;
    return j;
end $$;

-- ---------------------------------------------------------------- what is up for grabs (everything but the winner's)
create or replace function public.rb_jackpot_pool(j public.rb_jackpots) returns jsonb
language sql stable security definer set search_path to '' as $$
    select coalesce(jsonb_agg(x order by (x ->> 'worth')::bigint desc, x ->> 'key'), '[]'::jsonb) from (
        select jsonb_build_object('key', it.id::text, 'item', it.item, 'worth', public.rb_worth(it.item),
                                  'from', p.username, 'colour', e.colour) x
          from public.rb_jackpot_entries e join public.rb_items it on it.id = any (e.item_ids)
          join public.profiles p on p.id = e.owner
         where e.jackpot = j.id and e.id is distinct from j.winner_entry and e.owner is not null
        union all
        select jsonb_build_object('key', 'bot:' || e.id::text || ':' || k, 'item', e.whats[k], 'worth', public.rb_worth(e.whats[k]),
                                  'from', e.bot_name, 'colour', e.colour)
          from public.rb_jackpot_entries e, generate_subscripts(e.whats, 1) k
         where e.jackpot = j.id and e.id is distinct from j.winner_entry and e.owner is null) z $$;

-- ---------------------------------------------------------------- the end: items move, the rest leaves the game
create or replace function public.rb_jackpot_finish(jid uuid, keys text[]) returns void
language plpgsql security definer set search_path to '' as $$
declare j public.rb_jackpots%rowtype; w public.rb_jackpot_entries%rowtype; k text; e record; pool jsonb; lost jsonb;
begin
    select * into j from public.rb_jackpots where id = jid for update;
    if not found or j.state not in ('locked', 'picking') then return; end if;
    select * into w from public.rb_jackpot_entries where id = j.winner_entry;
    pool := public.rb_jackpot_pool(j);
    if w.owner is null then                                       -- a bot won: the players' items leave the game
        select coalesce(jsonb_agg(it.item), '[]'::jsonb) into lost from public.rb_items it where it.locked = 'jackpot:' || j.id;
        delete from public.rb_items where locked = 'jackpot:' || j.id;
        insert into public.rb_audit (admin, action, target, detail) values (null, 'jackpot_bot_win', j.id::text,
            jsonb_build_object('items', lost, 'bot', w.bot_name));
    else
        keys := coalesce(keys, '{}');
        foreach k in array keys loop
            if k like 'bot:%' then
                select x into e from jsonb_array_elements(pool) x where x ->> 'key' = k;
                if found then perform public.rb_give(w.owner, (select x ->> 'item' from jsonb_array_elements(pool) x
                                                                where x ->> 'key' = k), 'jackpot'); end if;
            else
                update public.rb_items set owner = w.owner, locked = null, origin = 'jackpot'
                 where id::text = k and locked = 'jackpot:' || j.id and owner <> w.owner;
            end if;
        end loop;
        update public.rb_items set locked = null where locked = 'jackpot:' || j.id and owner = w.owner;   -- yours back
        insert into public.rb_seen (owner, item)
            select w.owner, it.item from public.rb_items it where it.owner = w.owner and it.origin = 'jackpot'
            on conflict do nothing;
        delete from public.rb_items where locked = 'jackpot:' || j.id;                                 -- not picked
        perform public.rb_xp_add(w.owner, coalesce(public.rb_cfg('jackpot_xp'), 150)::int, 'jackpot', j.id::text, false);
    end if;
    for e in select distinct owner from public.rb_jackpot_entries where jackpot = j.id and owner is not null loop
        perform public.rb_fix_equip(e.owner);
        perform public.rb_notice(e.owner, 'jackpot_end', jsonb_build_object('id', j.id, 'won', coalesce(e.owner = w.owner, false),
                                 'winner', coalesce(w.bot_name, (select username from public.profiles where id = w.owner)),
                                 'total', j.total));
    end loop;
    update public.rb_jackpots set state = 'done', picked = to_jsonb(keys) where id = j.id;
end $$;

-- ---------------------------------------------------------------- moving on with time (called by anyone who looks)
create or replace function public.rb_jackpot_advance(jid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare j public.rb_jackpots%rowtype; n integer; avg_ bigint; k integer; tgt bigint; whats text[]; free_c integer[];
        r_ double precision; acc bigint := 0; e record; names text[]; nm text; auto text[];
begin
    select * into j from public.rb_jackpots where id = jid for update;
    if not found then return; end if;
    if j.state = 'open' and now() >= j.lock_at then
        select count(*), coalesce(avg(value), 0)::bigint into n, avg_ from public.rb_jackpot_entries where jackpot = j.id;
        if n = 0 then
            update public.rb_jackpots set state = 'empty' where id = j.id;
            return;
        end if;
        select array_agg(c order by random()) into free_c from generate_series(0, 5) c
         where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id);
        select array_agg(b.name order by random()) into names from public.rb_flip_bots() b;
        for k in 1 .. 6 - n loop                                   -- bots take the empty seats, one every 1.6 s
            tgt := greatest(100, (avg_ * (0.5 + random()))::bigint);
            whats := public.rb_flip_bot_items(tgt, 1 + floor(random() * 3)::int);
            continue when coalesce(array_length(whats, 1), 0) = 0;
            nm := names[k];
            insert into public.rb_jackpot_entries (jackpot, owner, bot_name, colour, whats, value, join_at)
                values (j.id, null, nm, free_c[k], whats, (select sum(public.rb_worth(x)) from unnest(whats) x),
                        j.lock_at + make_interval(secs => 1.6 * k));
        end loop;
        select sum(value) into j.total from public.rb_jackpot_entries where jackpot = j.id;
        r_ := public.rb_rand() * j.total;                        -- the winner: share of the worth, decided now
        for e in select id, value from public.rb_jackpot_entries where jackpot = j.id order by join_at, id loop
            acc := acc + e.value;
            if r_ < acc then j.winner_entry := e.id; exit; end if;
        end loop;
        update public.rb_jackpots set state = 'locked', total = j.total, winner_entry = j.winner_entry,
               roll = r_ / greatest(1, j.total) where id = j.id;
        return;
    end if;
    if j.state = 'locked' and now() >= j.result_at then
        if (select owner from public.rb_jackpot_entries where id = j.winner_entry) is null then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        n := jsonb_array_length(public.rb_jackpot_pool(j));
        if n = 0 then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        update public.rb_jackpots set state = 'picking', picks_allowed = (n + 1) / 2 where id = j.id;
        return;
    end if;
    if j.state = 'picking' and now() >= j.pick_until then         -- time is up: the best ones are picked for you
        select array_agg(x ->> 'key') into auto from (select x from jsonb_array_elements(public.rb_jackpot_pool(j)) x
                                                      limit j.picks_allowed) z;
        perform public.rb_jackpot_finish(j.id, auto);
    end if;
end $$;

-- ---------------------------------------------------------------- what the app shows
create or replace function public.rb_jackpot_json(j public.rb_jackpots, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object(
        'id', j.id, 'state', j.state, 'now', extract(epoch from now()),
        'opens_at', extract(epoch from j.slot), 'lock_at', extract(epoch from j.lock_at),
        'spin_at', extract(epoch from j.spin_at), 'result_at', extract(epoch from j.result_at),
        'pick_until', extract(epoch from j.pick_until),
        'next_at', extract(epoch from j.slot) + coalesce(public.rb_cfg('jackpot_every_s'), 900),
        'total', (select coalesce(sum(value), 0) from public.rb_jackpot_entries e where e.jackpot = j.id and e.join_at <= now()),
        'min_join', greatest(coalesce(public.rb_cfg('jackpot_min_worth'), 100)::bigint,
                             (select coalesce(sum(value), 0) from public.rb_jackpot_entries e where e.jackpot = j.id)
                             * coalesce(public.rb_cfg('jackpot_min_pct'), 1) / 100)::bigint,
        'entries', coalesce((select jsonb_agg(jsonb_build_object(
                         'id', e.id, 'name', coalesce(p.username, e.bot_name), 'bot', e.owner is null, 'me', e.owner = me,
                         'colour', e.colour, 'value', e.value, 'items', to_jsonb(e.whats), 'join_at', extract(epoch from e.join_at))
                         order by e.join_at, e.id)
                     from public.rb_jackpot_entries e left join public.profiles p on p.id = e.owner
                    where e.jackpot = j.id and e.join_at <= now()), '[]'::jsonb),
        'winner', case when now() >= j.spin_at then j.winner_entry end,
        'roll', case when now() >= j.spin_at then j.roll end,
        'mine', exists (select 1 from public.rb_jackpot_entries e where e.jackpot = j.id and e.owner = me),
        'i_won', now() >= j.result_at and exists (select 1 from public.rb_jackpot_entries e where e.id = j.winner_entry and e.owner = me),
        'picks_allowed', j.picks_allowed, 'picked', j.picked,
        'pool', case when j.state = 'picking' and exists (select 1 from public.rb_jackpot_entries e
                                                           where e.id = j.winner_entry and e.owner = me)
                     then public.rb_jackpot_pool(j) end) $$;

create or replace function public.rb_jackpot_state() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); cur public.rb_jackpots%rowtype; j public.rb_jackpots%rowtype; mine public.rb_jackpots%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for j in select * from public.rb_jackpots where state in ('open', 'locked', 'picking') order by slot loop
        perform public.rb_jackpot_advance(j.id);
    end loop;
    cur := public.rb_jackpot_make(public.rb_jackpot_slot(now()));
    perform public.rb_jackpot_advance(cur.id);
    -- the one you are in (still running, or just finished) comes first; then the current one
    select jj.* into mine from public.rb_jackpots jj join public.rb_jackpot_entries e on e.jackpot = jj.id and e.owner = me
     where jj.state in ('locked', 'picking') or (jj.state = 'done' and jj.result_at > now() - interval '20 seconds')
     order by jj.slot desc limit 1;
    if found then
        return public.rb_jackpot_json(mine, me) || jsonb_build_object('feature', public.rb_feature_on('jackpot'));
    end if;
    select * into cur from public.rb_jackpots where id = cur.id;
    if cur.state in ('empty', 'done') or (cur.state <> 'open' and now() > cur.result_at + interval '15 seconds') then
        return jsonb_build_object('state', 'closed', 'now', extract(epoch from now()),
                                  'next_at', extract(epoch from cur.slot) + coalesce(public.rb_cfg('jackpot_every_s'), 900),
                                  'feature', public.rb_feature_on('jackpot'),
                                  'last', public.rb_jackpot_json(cur, me));
    end if;
    return public.rb_jackpot_json(cur, me) || jsonb_build_object('feature', public.rb_feature_on('jackpot'));
end $$;
revoke all on function public.rb_jackpot_state() from public, anon;
grant execute on function public.rb_jackpot_state() to authenticated;

create or replace function public.rb_jackpot_join(items uuid[], req text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; res jsonb; j public.rb_jackpots%rowtype; n integer; val bigint; whats text[];
        minj bigint; col integer; it record;
begin
    perform public.rb_need_feature('jackpot');
    perform public.rb_rate(auth.uid(), 'jackpot', 10);
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    j := public.rb_jackpot_make(public.rb_jackpot_slot(now()));
    select * into j from public.rb_jackpots where id = j.id for update;
    if j.state <> 'open' or now() >= j.lock_at then raise exception 'rb_jackpot_closed'; end if;
    if exists (select 1 from public.rb_jackpot_entries where jackpot = j.id and owner = p.id) then
        raise exception 'rb_jackpot_in';
    end if;
    select count(*) into n from public.rb_jackpot_entries where jackpot = j.id;
    if n >= 6 then raise exception 'rb_jackpot_full'; end if;
    if coalesce(array_length(items, 1), 0) not between 1 and 3 or
       (select count(distinct x) from unnest(items) x) <> array_length(items, 1) then raise exception 'rb_bad_choice'; end if;
    for it in select i.* from public.rb_items i where i.id = any (items) for update loop
        if it.owner <> p.id or it.locked is not null or not coalesce((select c.tradeable from public.rb_catalog c
                                                                       where c.id = it.item), false) then
            raise exception 'rb_item_locked';
        end if;
    end loop;
    select array_agg(i.item order by i.id), sum(public.rb_worth(i.item)) into whats, val
      from public.rb_items i where i.id = any (items) and i.owner = p.id;
    if coalesce(array_length(whats, 1), 0) <> array_length(items, 1) or coalesce(val, 0) <= 0 then
        raise exception 'rb_item_locked';
    end if;
    minj := greatest(coalesce(public.rb_cfg('jackpot_min_worth'), 100)::bigint,
                     (select coalesce(sum(value), 0) from public.rb_jackpot_entries where jackpot = j.id)
                     * coalesce(public.rb_cfg('jackpot_min_pct'), 1) / 100);
    if val < minj then raise exception 'rb_jackpot_too_small'; end if;
    select c into col from generate_series(0, 5) c
     where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id) order by random() limit 1;
    update public.rb_items set locked = 'jackpot:' || j.id where id = any (items);
    insert into public.rb_jackpot_entries (jackpot, owner, colour, item_ids, whats, value)
        values (j.id, p.id, col, items, whats, val);
    return public.rb_remember(p.id, req, public.rb_jackpot_json(j, p.id));
end $$;
revoke all on function public.rb_jackpot_join(uuid[], text) from public, anon;
grant execute on function public.rb_jackpot_join(uuid[], text) to authenticated;

create or replace function public.rb_jackpot_pick(jid uuid, keys text[]) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; j public.rb_jackpots%rowtype; pool jsonb;
begin
    p := public.rb_lock_me();
    perform public.rb_jackpot_advance(jid);
    select * into j from public.rb_jackpots where id = jid for update;
    if not found or j.state <> 'picking' then raise exception 'rb_jackpot_closed'; end if;
    if (select owner from public.rb_jackpot_entries where id = j.winner_entry) is distinct from p.id then
        raise exception 'rb_bad_choice';
    end if;
    pool := public.rb_jackpot_pool(j);
    if coalesce(array_length(keys, 1), 0) <> j.picks_allowed
       or (select count(distinct k) from unnest(keys) k) <> array_length(keys, 1)
       or exists (select 1 from unnest(keys) k where not exists (select 1 from jsonb_array_elements(pool) x
                                                                  where x ->> 'key' = k)) then
        raise exception 'rb_bad_choice';
    end if;
    perform public.rb_jackpot_finish(j.id, keys);
    return jsonb_build_object('done', true);
end $$;
revoke all on function public.rb_jackpot_pick(uuid, text[]) from public, anon;
grant execute on function public.rb_jackpot_pick(uuid, text[]) to authenticated;

revoke all on function public.rb_jackpot_make(timestamptz), public.rb_jackpot_advance(uuid), public.rb_jackpot_finish(uuid, text[]),
    public.rb_jackpot_pool(public.rb_jackpots), public.rb_jackpot_json(public.rb_jackpots, uuid) from public, anon, authenticated;

commit;
