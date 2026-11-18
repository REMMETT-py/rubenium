-- ================================================================ Rubenium 4.4 (build 2026.11.18.22)
-- The admin's Rig: set a player's next free spin, scratch card, case, Slots, Dice or coinflip against a bot.
-- Transactional and safe to run again; 027_down.sql undoes it.
begin;
-- ================================================================ Rig (4.4): the admin sets a player's next result
-- One rig per player and game (per case for cases). It is used up by the next play and looks exactly like a normal
-- result: the server simply decides that roll, the app shows it the usual way. Free spin, scratch card, a case,
-- Slots, Dice and a coinflip against a bot.
create table if not exists public.rb_rigs (
    owner uuid not null references public.profiles (id) on delete cascade,
    kind text not null,
    key text not null default '',
    data jsonb not null,
    at timestamptz not null default now(),
    by_name text,
    primary key (owner, kind, key)
);
alter table public.rb_rigs enable row level security;
revoke all on public.rb_rigs from anon, authenticated;

create or replace function public.rb_rig_take(who uuid, k text, ky text) returns jsonb
language sql volatile security definer set search_path = '' as $$
    delete from public.rb_rigs where owner = who and kind = k and key = coalesce(ky, '') returning data $$;

-- a case drop, unless a rig says otherwise (same shape as rb_case_drop)
create or replace function public.rb_rig_case(who uuid, cid text, t integer, k integer, it text, co integer)
returns table (tier integer, klass integer, item text, coins integer)
language plpgsql volatile security definer set search_path = '' as $$
declare g jsonb; c public.rb_catalog%rowtype;
begin
    g := public.rb_rig_take(who, 'case', cid);
    tier := t; klass := k; item := it; coins := co;
    if g is not null then
        if g ? 'item' then
            select * into c from public.rb_catalog where id = g ->> 'item';
            if found then
                item := c.id; coins := 0; klass := coalesce(c.cls, 0);
                tier := coalesce(array_position(array['standard', 'rare', 'special', 'epic', 'exotic'], c.rarity), 1);
            end if;
        elsif g ? 'coins' then
            tier := 0; klass := 0; item := null; coins := greatest(0, (g ->> 'coins')::int);
        end if;
    end if;
    return next;
end $$;

create or replace function public.rb_admin_rig(name text, kind text, key text, data jsonb) returns boolean
language plpgsql volatile security definer set search_path = '' as $$
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
end $$;

create or replace function public.rb_admin_rigs() returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return coalesce((select jsonb_agg(jsonb_build_object('name', p.username, 'kind', r.kind, 'key', r.key, 'data', r.data,
                                                         'at', r.at, 'by', r.by_name) order by r.at desc)
                       from public.rb_rigs r join public.profiles p on p.id = r.owner), '[]'::jsonb)
           || coalesce((select jsonb_agg(jsonb_build_object('name', p.username, 'kind', 'gold', 'key', '', 'data', '{}'::jsonb))
                          from public.profiles p where p.rig_gold), '[]'::jsonb);
end $$;

revoke all on function public.rb_rig_take(uuid, text, text), public.rb_rig_case(uuid, text, integer, integer, text, integer)
    from public, anon, authenticated;
revoke all on function public.rb_admin_rig(text, text, text, jsonb), public.rb_admin_rigs() from public, anon;
grant execute on function public.rb_admin_rig(text, text, text, jsonb), public.rb_admin_rigs() to authenticated;

-- the hooks: each game asks for its rig at the moment it rolls
do $$
declare
    edits text[][] := array[
        array['public.rb_spin()',
              'r := case when p.rig_gold then 8 else public.rb_roll(odds) end;',
              'r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    r := coalesce(least(9, greatest(0, (public.rb_rig_take(p.id, ''wheel'', '''') ->> ''slot'')::int)), r);   -- 4.4 rig'],
        array['public.rb_scratch()',
              'roll := case when p.rig_gold then 0.999 else public.rb_rand() end;',
              'roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    roll := coalesce(case public.rb_rig_take(p.id, ''scratch'', '''') ->> ''tier'' when ''standard'' then 0.15 when ''rare'' then 0.45
                          when ''special'' then 0.65 when ''epic'' then 0.85 when ''exotic'' then 0.94 when ''golden'' then 0.99 end, roll);   -- 4.4 rig'],
        array['public.rb_open_case(text, text)',
              'd := public.rb_case_drop(c);',
              'd := public.rb_case_drop(c);
    select * into d from public.rb_rig_case(p.id, c.id, d.tier, d.klass, d.item, d.coins);   -- 4.4 rig'],
        array['public.rb_dice(integer, integer, text)',
              'roll := floor(public.rb_rand() * 100)::int;',
              'roll := floor(public.rb_rand() * 100)::int;
    roll := coalesce(case (public.rb_rig_take(p.id, ''dice'', '''') ->> ''win'')::boolean
                       when true then floor(public.rb_rand() * chance)::int
                       when false then chance + floor(public.rb_rand() * (100 - chance))::int end, roll);   -- 4.4 rig'],
        array['public.rb_flip_vs_bot(uuid)',
              'a_wins := public.rb_rand() < ch;',
              'a_wins := public.rb_rand() < ch;
    a_wins := coalesce((public.rb_rig_take(p.id, ''flip'', '''') ->> ''win'')::boolean, a_wins);   -- 4.4 rig'],
        array['public.rb_flip_lock(uuid, uuid[])',
              'a_wins := public.rb_rand() < ch;',
              'a_wins := public.rb_rand() < ch;
    if f.bot_side = ''a'' then a_wins := coalesce(not (public.rb_rig_take(p.id, ''flip'', '''') ->> ''win'')::boolean, a_wins); end if;   -- 4.4 rig'],
        array['public.rb_slots(integer, text)',
              '    if reels[1] = reels[2] and reels[2] = reels[3] then',
              '    reels := coalesce((select array[x ->> 0, x ->> 1, x ->> 2] from (select public.rb_rig_take(p.id, ''slots'', '''') -> ''reels'' x) z
                        where x is not null), reels);   -- 4.4 rig
    if reels[1] = reels[2] and reels[2] = reels[3] then']];
    i integer; src text; out_ text;
begin
    for i in 1..array_length(edits, 1) loop
        src := replace(pg_get_functiondef(edits[i][1]::regprocedure), chr(13), '');
        if position('4.4 rig' in src) > 0 then continue; end if;                 -- already done (safe to run again)
        if position(edits[i][2] in src) = 0 then raise exception 'rig hook: % changed', edits[i][1]; end if;
        out_ := replace(src, edits[i][2], edits[i][3]);
        execute out_;
    end loop;
end $$;

update public.rb_config set value = 2026111822 where key = 'min_build';
commit;
