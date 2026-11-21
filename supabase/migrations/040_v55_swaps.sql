-- ================================================================ Rubenium 5.5: SWAPS on the market
-- A swap: you put one of your items up and say which items (1 to 3 choices) you would take for it. Anyone who owns one
-- of them can take the swap: the two items change owners at once, no coins, no fee. At most 3 open swaps and 3 open
-- listings each. Safe to run again.
begin;
insert into public.rb_config (key, value) values ('swap_max', 3) on conflict (key) do nothing;
update public.rb_config set value = 3 where key = 'market_max_listings';

create table if not exists public.rb_item_swaps (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles(id) on delete cascade,
    item uuid not null,
    what text not null,
    wants text[] not null,
    state text not null default 'open' check (state in ('open', 'done', 'cancelled')),
    taker uuid references public.profiles(id) on delete set null,
    got text,
    at timestamptz not null default now(),
    done_at timestamptz);
create index if not exists rb_item_swaps_open on public.rb_item_swaps (state, at desc);
alter table public.rb_item_swaps enable row level security;
revoke all on public.rb_item_swaps from anon, authenticated;

create or replace function public.rb_swap_create(item_id uuid, wants text[]) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; it public.rb_items%rowtype; sid uuid; w text;
begin
    perform public.rb_rate(auth.uid(), 'swap', 20);
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    if not coalesce((select tradeable from public.rb_catalog where id = it.item), false) then raise exception 'rb_not_tradeable'; end if;
    wants := array(select distinct x from unnest(coalesce(wants, '{}')) x);
    if coalesce(array_length(wants, 1), 0) not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    foreach w in array wants loop
        if w = it.item or not coalesce((select tradeable from public.rb_catalog where id = w), false) then
            raise exception 'rb_bad_choice';
        end if;
    end loop;
    if (select count(*) from public.rb_item_swaps where owner = p.id and state = 'open') >= coalesce(public.rb_cfg('swap_max'), 3) then
        raise exception 'rb_too_many_swaps';
    end if;
    insert into public.rb_item_swaps (owner, item, what, wants) values (p.id, it.id, it.item, wants) returning id into sid;
    update public.rb_items set locked = 'swap:' || sid where id = it.id;
    return jsonb_build_object('swap', sid);
end $$;

create or replace function public.rb_swap_cancel(sid uuid) returns boolean
language plpgsql security definer set search_path to '' as $$
declare s public.rb_item_swaps%rowtype;
begin
    select * into s from public.rb_item_swaps where id = sid and owner = auth.uid() for update;
    if not found or s.state <> 'open' then return false; end if;
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where id = s.id;
    update public.rb_items set locked = null where id = s.item and locked = 'swap:' || s.id;
    return true;
end $$;

-- take a swap with one of your items that it asks for
create or replace function public.rb_swap_take(sid uuid, item_id uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me public.profiles%rowtype; s public.rb_item_swaps%rowtype; mine public.rb_items%rowtype; seller public.profiles%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'swap', 20);
    perform public.rb_need_feature('market');
    me := public.rb_lock_me();
    if not public.rb_can_trade(me) then raise exception 'rb_trade_locked'; end if;
    select * into s from public.rb_item_swaps where id = sid for update;
    if not found or s.state <> 'open' then raise exception 'rb_swap_gone'; end if;
    if s.owner = me.id then raise exception 'rb_own_listing'; end if;
    select * into seller from public.profiles where id = s.owner for update;
    if seller.banned then raise exception 'rb_swap_gone'; end if;
    select * into mine from public.rb_items where id = item_id and owner = me.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if mine.locked is not null then raise exception 'rb_item_locked'; end if;
    if not (mine.item = any (s.wants)) then raise exception 'rb_bad_choice'; end if;
    if not exists (select 1 from public.rb_items where id = s.item and owner = s.owner and locked = 'swap:' || s.id) then
        update public.rb_item_swaps set state = 'cancelled', done_at = now() where id = s.id;
        raise exception 'rb_swap_gone';
    end if;
    update public.rb_items set owner = me.id, locked = null, origin = 'swap' where id = s.item;
    update public.rb_items set owner = s.owner, locked = null, origin = 'swap' where id = mine.id;
    insert into public.rb_seen (owner, item) values (me.id, s.what), (s.owner, mine.item) on conflict do nothing;
    update public.rb_item_swaps set state = 'done', taker = me.id, got = mine.item, done_at = now() where id = s.id;
    -- the item given may have been in other open swaps of the taker: those end
    perform public.rb_fix_equip(me.id);
    perform public.rb_fix_equip(s.owner);
    perform public.rb_notice(s.owner, 'swapped', jsonb_build_object('gave', s.what, 'got', mine.item, 'with', me.username));
    return jsonb_build_object('got', s.what, 'id', s.item, 'gave', mine.item);
end $$;

-- every open swap (newest first), with which of my items could take each one
create or replace function public.rb_item_swaps_list() returns jsonb
language sql stable security definer set search_path to '' as $$
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', s.id, 'item', s.what, 'wants', to_jsonb(s.wants), 'from', p.username, 'mine', s.owner = auth.uid(),
               'at', extract(epoch from s.at), 'worth', public.rb_worth(s.what),
               'can', (select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'item', i.item)), '[]'::jsonb)
                         from public.rb_items i where i.owner = auth.uid() and i.locked is null and i.item = any (s.wants)))
             order by s.owner = auth.uid() desc, s.at desc), '[]'::jsonb)
      from (select * from public.rb_item_swaps where state = 'open' order by at desc limit 80) s
      join public.profiles p on p.id = s.owner and not p.banned $$;

revoke all on function public.rb_swap_create(uuid, text[]), public.rb_swap_cancel(uuid), public.rb_swap_take(uuid, uuid),
    public.rb_item_swaps_list() from public, anon;
grant execute on function public.rb_swap_create(uuid, text[]), public.rb_swap_cancel(uuid), public.rb_swap_take(uuid, uuid),
    public.rb_item_swaps_list() to authenticated;
-- ================================================================ titles for the best coinflip and golf players (wins)
create or replace function public.rb_title_kinds() returns text[]
language sql immutable set search_path to '' as $$
    select array['coins', 'worth', 'level', 'hours', 'badges', 'streak', 'blocks', 'wave', 'tap', 'park', 'memory',
                 'flip', 'golf'] $$;

create or replace function public.rb_title_values(kind text)
 returns table(id uuid, username text, val bigint)
 language sql stable security definer set search_path to '' as $$
    select w.id, w.username, (case kind
        when 'coins' then w.coins
        when 'level' then w.xp
        when 'hours' then w.minutes / 60
        when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
        when 'worth' then (select coalesce(sum(public.rb_worth(it.item)), 0) from public.rb_items it where it.owner = w.id)
        when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
        when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini')
        when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park')
        when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory')
        when 'blocks' then (select coalesce(max(g.score), 0) from public.rb_mg g where g.owner = w.id and g.game = 'blocks'
                              and not g.open and not g.void)
        when 'wave' then public.rb_wave_best(w.id)
        when 'flip' then (select count(*) from public.rb_flips f where f.winner = w.id and f.state = 'done')
        when 'golf' then (select count(*) from public.rb_golf g where g.winner = w.id and g.state = 'done' and g.b is not null)
        else 0 end)::bigint
      from public.profiles w where not w.banned and not w.bot $$;
revoke all on function public.rb_title_values(text) from public, anon, authenticated;
commit;
