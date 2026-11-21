-- 6.2.3: the Jackpot stays open until a player joins; the countdown starts with the first player.
-- An empty round has lock_at = slot + 100 years ("waiting"); the first join sets the real times. rb_jackpot_make reuses
-- a waiting round from an earlier slot instead of opening another. The JSON shows lock_at = now + open time while waiting
-- (so older apps still show an open jackpot you can join) and "waiting": true for the new app.
create or replace function public.rb_jackpot_make(s timestamp with time zone) returns public.rb_jackpots
language plpgsql security definer set search_path = '' as $f$
declare j public.rb_jackpots; far interval := interval '100 years';
begin
    select * into j from public.rb_jackpots where state = 'open' and lock_at > slot + interval '1 day' order by slot limit 1;
    if found then return j; end if;
    select * into j from public.rb_jackpots where slot = s;
    if found then return j; end if;
    insert into public.rb_jackpots (slot, lock_at, spin_at, result_at, pick_until)
        values (s, s + far, s + far, s + far, s + far) on conflict (slot) do nothing;
    select * into j from public.rb_jackpots where slot = s;
    return j;
end $f$;

do $m$
declare src text; o text;
begin
    -- json: rename the old one, wrap it
    if not exists (select 1 from pg_proc where proname = 'rb_jackpot_json_raw') then
        alter function public.rb_jackpot_json(public.rb_jackpots, uuid) rename to rb_jackpot_json_raw;
    end if;
end $m$;
create or replace function public.rb_jackpot_json(j public.rb_jackpots, me uuid) returns jsonb
language sql stable security definer set search_path = '' as $f$
    select case when j.state = 'open' and j.lock_at > j.slot + interval '1 day' then
        public.rb_jackpot_json_raw(j, me) || jsonb_build_object('waiting', true,
            'lock_at', extract(epoch from now()) + coalesce(public.rb_cfg('jackpot_open_s'), 120))
        else public.rb_jackpot_json_raw(j, me) || jsonb_build_object('waiting', false) end
$f$;
revoke all on function public.rb_jackpot_json_raw(public.rb_jackpots, uuid) from public, anon, authenticated;
revoke all on function public.rb_jackpot_json(public.rb_jackpots, uuid) from public, anon, authenticated;
revoke all on function public.rb_jackpot_make(timestamp with time zone) from public, anon, authenticated;

-- join: the first player starts the clock
create or replace function public.rb_jackpot_join(items uuid[], req text) returns jsonb
language plpgsql security definer set search_path = '' as $f$
declare p public.profiles%rowtype; res jsonb; j public.rb_jackpots%rowtype; n integer; val bigint; whats text[];
        minj bigint; col integer; it record; o double precision := coalesce(public.rb_cfg('jackpot_open_s'), 120);
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
    if n >= 5 then raise exception 'rb_jackpot_full'; end if;
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
    if val > coalesce(public.rb_cfg('jackpot_max_worth'), 250000) then raise exception 'rb_jackpot_too_big'; end if;
    select c into col from generate_series(0, 5) c
     where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id) order by random() limit 1;
    update public.rb_items set locked = 'jackpot:' || j.id where id = any (items);
    insert into public.rb_jackpot_entries (jackpot, owner, colour, item_ids, whats, value)
        values (j.id, p.id, col, items, whats, val);
    if n = 0 then        -- 6.2.3: the first player starts the countdown
        update public.rb_jackpots set lock_at = now() + make_interval(secs => o),
               spin_at = now() + make_interval(secs => o + 12), result_at = now() + make_interval(secs => o + 22),
               pick_until = now() + make_interval(secs => o + 142) where id = j.id;
        select * into j from public.rb_jackpots where id = j.id;
    end if;
    return public.rb_remember(p.id, req, public.rb_jackpot_json(j, p.id));
end $f$;
