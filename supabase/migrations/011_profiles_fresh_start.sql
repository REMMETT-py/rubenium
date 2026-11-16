-- Rubenium 011 (2.6): profile banners and frames, the OG tag, quick sell, and the 2.6 fresh start.
-- Run it ONCE in Supabase, after 010: SQL Editor > New query > paste everything > Run.
-- Running it a second time is safe: the fresh start (the reset of coins, items, spins and cases) only ever happens once.

-- ================================================================ settings
insert into public.rb_config (key, value) values
    ('quick_share', 0.25),                       -- quick sell pays 25% of what an item is worth
    ('quick_shop_share', 0.5),                   -- ...and never more than half of what you paid in the shop
    ('og_until', extract(epoch from timestamptz '2026-11-17 00:00:00 Europe/Paris'))
on conflict (key) do nothing;
insert into public.rb_config (key, value) values ('min_build', 2026111704)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);

-- ================================================================ the new things to own: banners, frames, the OG tag
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('banner:dusk', 'banner', 'dusk', '', 'standard', 400, 400, true, 0),
    ('banner:mint', 'banner', 'mint', '', 'standard', 400, 400, true, 0),
    ('banner:steel', 'banner', 'steel', '', 'standard', 400, 400, true, 0),
    ('banner:rose', 'banner', 'rose', '', 'standard', 400, 400, true, 0),
    ('banner:waves', 'banner', 'waves', '', 'rare', 1200, 1200, true, 0),
    ('banner:grid', 'banner', 'grid', '', 'rare', 1200, 1200, true, 0),
    ('banner:stripes', 'banner', 'stripes', '', 'rare', 1200, 1200, true, 0),
    ('banner:dots', 'banner', 'dots', '', 'rare', 1200, 1200, true, 0),
    ('banner:aurora', 'banner', 'aurora', '', 'special', 3500, 3500, true, 0),
    ('banner:circuit', 'banner', 'circuit', '', 'special', 3500, 3500, true, 0),
    ('banner:sunset', 'banner', 'sunset', '', 'special', 3500, 3500, true, 0),
    ('banner:peaks', 'banner', 'peaks', '', 'special', 3500, 3500, true, 0),
    ('banner:galaxy', 'banner', 'galaxy', '', 'epic', 9000, 9000, true, 0),
    ('banner:lava', 'banner', 'lava', '', 'epic', 9000, 9000, true, 0),
    ('banner:matrix', 'banner', 'matrix', '', 'epic', 9000, 9000, true, 0),
    ('banner:prism', 'banner', 'prism', '', 'epic', 9000, 9000, true, 0),
    ('frame:silver', 'frame', 'silver', '', 'standard', 300, 300, true, 0),
    ('frame:bronze', 'frame', 'bronze', '', 'standard', 300, 300, true, 0),
    ('frame:ink', 'frame', 'ink', '', 'standard', 300, 300, true, 0),
    ('frame:neon', 'frame', 'neon', '', 'rare', 1000, 1000, true, 0),
    ('frame:dashed', 'frame', 'dashed', '', 'rare', 1000, 1000, true, 0),
    ('frame:twin', 'frame', 'twin', '', 'rare', 1000, 1000, true, 0),
    ('frame:laurel', 'frame', 'laurel', '', 'special', 3000, 3000, true, 0),
    ('frame:crown', 'frame', 'crown', '', 'special', 3000, 3000, true, 0),
    ('frame:spikes', 'frame', 'spikes', '', 'special', 3000, 3000, true, 0),
    ('frame:flame', 'frame', 'flame', '', 'epic', 8000, 8000, true, 0),
    ('frame:orbit', 'frame', 'orbit', '', 'epic', 8000, 8000, true, 0),
    ('frame:rainbow', 'frame', 'rainbow', '', 'epic', 8000, 8000, true, 0),
    ('tag:og', 'tag', 'og', '', 'exotic', null, 0, false, 0)            -- free for the first users, never sold
on conflict (id) do update set kind = excluded.kind, base = excluded.base, rarity = excluded.rarity,
    price = excluded.price, value = excluded.value, tradeable = excluded.tradeable;

-- wearing them: a banner, a frame and a tag (the 3 badges on show stay the showcase)
create or replace function public.rb_equip(slot text, what text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; kind text; want text;
begin
    p := public.rb_lock_me();
    want := case slot when 'theme' then 'theme' when 'ball' then 'ball' when 'ring' then 'line' when 'font' then 'font'
                      when 'badge1' then 'badge' when 'badge2' then 'badge' when 'badge3' then 'badge'
                      when 'banner' then 'banner' when 'frame' then 'frame' when 'tag' then 'tag' end;
    if want is null then raise exception 'rb_bad_slot'; end if;
    if coalesce(what, '') = '' then
        p.equip := p.equip - slot;
    else
        select case when c.kind = 'prog' then (case c.base when 'ring' then 'line' else c.base end) else c.kind end
          into kind from public.rb_catalog c where c.id = what;
        if kind is distinct from want then raise exception 'rb_wrong_kind'; end if;
        if not public.rb_can_wear(p, what) then raise exception 'rb_not_yours'; end if;
        if want = 'badge' and exists (select 1 from jsonb_each_text(p.equip) e
                                       where e.key like 'badge%' and e.key <> slot and e.value = what) then
            raise exception 'rb_already_worn';
        end if;
        p.equip := p.equip || jsonb_build_object(slot, what);
    end if;
    update public.profiles set equip = p.equip where id = p.id;
    return p.equip;
end $$;

-- what everyone shows next to their name (tag, frame, banner): one small list for the whole app
create or replace function public.rb_looks() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(p.username, jsonb_strip_nulls(jsonb_build_object(
                         'tag', p.equip ->> 'tag', 'frame', p.equip ->> 'frame', 'banner', p.equip ->> 'banner')))
                       from public.profiles p
                      where not p.banned and p.equip ?| array['tag', 'frame', 'banner']), '{}'::json);
end $$;

-- ================================================================ the OG tag
create or replace function public.rb_og_give(who uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if not exists (select 1 from public.rb_items where owner = who and item = 'tag:og') then
        insert into public.rb_items (owner, item, origin) values (who, 'tag:og', 'og');
        insert into public.rb_seen (owner, item) values (who, 'tag:og') on conflict do nothing;
        update public.profiles set equip = coalesce(equip, '{}'::jsonb) || '{"tag": "tag:og"}'::jsonb
         where id = who and not (coalesce(equip, '{}'::jsonb) ? 'tag');
    end if;
end $$;

-- the hello at every login also hands out the OG tag until the end of 16 November (Paris time)
create or replace function public.rb_hello2(pc text, build bigint) returns json
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hello(pc);
    update public.profiles set build = coalesce(rb_hello2.build, 0) where id = auth.uid();
    if extract(epoch from now()) < coalesce(public.rb_cfg('og_until'), 0) then
        perform public.rb_og_give(auth.uid());
    end if;
    perform public.rb_fix_equip(auth.uid());
    return json_build_object('min_build', public.rb_cfg('min_build')::bigint,
                             'update', coalesce(build, 0) < public.rb_cfg('min_build'));
end $$;

-- ================================================================ quick sell: instant coins, a low but fair price
create or replace function public.rb_quick_value(who uuid, it public.rb_items) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare c public.rb_catalog%rowtype; pay integer; paid integer;
begin
    select * into c from public.rb_catalog where id = it.item;
    if not found or not c.tradeable or c.kind in ('prog', 'tag') or c.value <= 0 then return 0; end if;
    pay := floor(c.value * public.rb_cfg('quick_share'))::int;
    if it.origin = 'shop' then                         -- bought in the shop: never more than half of what was paid
        select -l.coins into paid from public.rb_ledger l
         where l.owner = who and l.reason = 'shop' and l.ref = it.item and l.at <= it.got_at + interval '1 minute'
         order by l.id desc limit 1;
        pay := least(pay, floor(coalesce(paid, c.value * 0.1) * public.rb_cfg('quick_shop_share'))::int);
    end if;
    return greatest(1, pay);
end $$;

create or replace function public.rb_quick_quote(ids uuid[]) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); total bigint := 0; n integer := 0; v integer; it public.rb_items%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for it in select * from public.rb_items where owner = me and id = any (ids) and locked is null loop
        v := public.rb_quick_value(me, it);
        if v > 0 then total := total + v; n := n + 1; end if;
    end loop;
    return json_build_object('total', total, 'n', n);
end $$;

create or replace function public.rb_quick_sell(ids uuid[], req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; it public.rb_items%rowtype; v integer; total bigint := 0; n integer := 0;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if coalesce(array_length(ids, 1), 0) = 0 or array_length(ids, 1) > 200 then raise exception 'rb_bad_choice'; end if;
    for it in select * from public.rb_items where owner = p.id and id = any (ids) and locked is null for update loop
        v := public.rb_quick_value(p.id, it);
        if v > 0 then
            delete from public.rb_items where id = it.id;
            total := total + v; n := n + 1;
        end if;
    end loop;
    if n = 0 then raise exception 'rb_not_tradeable'; end if;
    perform public.rb_fix_equip(p.id);
    perform public.rb_pay(p.id, total::int, 0, 'quick_sell', n::text);
    return public.rb_remember(p.id, req, jsonb_build_object('paid', total, 'n', n, 'coins', p.coins + total,
        'equip', (select equip from public.profiles where id = p.id)));
end $$;

-- ================================================================ daily deals can be banners and frames too
create or replace function public.rb_deal_list() returns table (item text, pct integer)
language sql stable security definer set search_path = '' as $$
    select c.id, (20 + (abs(hashtext(c.id || public.rb_today()::text)) % 4) * 5)::int
      from public.rb_catalog c
     where c.price is not null and c.price <= 30000 and c.kind in ('badge', 'ball', 'line', 'font', 'theme', 'banner', 'frame')
       and not (c.kind = 'badge' and (c.cls >= 3 or c.rarity = 'exotic'))
     order by md5(c.id || public.rb_today()::text) limit 4 $$;

-- an admin reset of one user never takes their OG tag
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_admin_reset(text, text)'::regprocedure) into src;
    if position('tag:%' in src) = 0 then
        src := replace(src, 'delete from public.rb_items where owner = p.id;',
                            'delete from public.rb_items where owner = p.id and item not like ''tag:%'';');
        src := replace(src, 'from public.rb_items it where it.owner = p.id), ''[]''::jsonb)',
                            'from public.rb_items it where it.owner = p.id and it.item not like ''tag:%''), ''[]''::jsonb)');
        src := replace(src, 'update public.profiles set equip = ''{}''::jsonb where id = p.id;',
                            'update public.profiles set equip = case when equip ? ''tag'' then jsonb_build_object(''tag'', equip -> ''tag'') else ''{}''::jsonb end where id = p.id;');
        execute src;
    end if;
exception when undefined_function then null;
end $$;

-- ================================================================ the 2.6 fresh start (happens once, ever)
-- Coins, keys, items, spins, cases and sets go back to the start for everyone. Kept: usernames, passwords,
-- friends, messages, pictures, time played (and its unlocks), the login streak. Everything taken is saved in
-- three backup tables (rb_bak26_profiles, rb_bak26_items, rb_bak26_stock), in case it is ever needed.
do $$ begin
    if coalesce(public.rb_cfg('reset_026'), 0) = 0 then
        create table if not exists public.rb_bak26_profiles as
            select id, username, coins, keys, equip, spin_at, spin_prize, scratch_at, daily_at, now() as saved_at
              from public.profiles;
        create table if not exists public.rb_bak26_items as select * from public.rb_items;
        create table if not exists public.rb_bak26_stock as select * from public.rb_case_stock;
        alter table public.rb_bak26_profiles enable row level security;
        alter table public.rb_bak26_items enable row level security;
        alter table public.rb_bak26_stock enable row level security;
        revoke all on public.rb_bak26_profiles, public.rb_bak26_items, public.rb_bak26_stock from anon, authenticated;

        -- everything in progress ends (nobody loses anything: every balance starts again anyway)
        update public.rb_offers set state = 'gone' where state = 'open';
        update public.rb_listings set state = 'cancelled' where state = 'open';
        update public.rb_trades set state = 'cancelled', why = 'reset' where state in ('asked', 'open');
        update public.rb_duels set state = 'cancelled', why = 'reset' where state in ('asked', 'on');
        update public.rb_rounds set open = false where open;
        update public.rb_mem set open = false where open;
        update public.rb_park set open = false where open;

        delete from public.rb_items;
        delete from public.rb_seen;
        delete from public.rb_case_stock;
        delete from public.rb_case_stats;
        delete from public.rb_set_claims;
        delete from public.rb_requests;

        insert into public.rb_ledger (owner, coins, keys, reason, ref)
            select id, greatest(-2000000000, least(2000000000, public.rb_cfg('start_coins')::bigint - coins))::int,
                   (public.rb_cfg('start_keys')::int - keys), 'reset', '2.6' from public.profiles;
        update public.profiles
           set coins = public.rb_cfg('start_coins')::bigint, keys = public.rb_cfg('start_keys')::int,
               spin_at = null, spin_prize = null, scratch_at = null, daily_at = null,
               equip = coalesce((select jsonb_object_agg(e.key, e.value) from jsonb_each(equip) e
                                  where e.value #>> '{}' like 'prog:%'), '{}'::jsonb);

        -- every account made before 17 November gets the OG tag
        perform public.rb_og_give(p.id) from public.profiles p
          where p.created_at < to_timestamp(public.rb_cfg('og_until'));

        insert into public.rb_config (key, value) values ('reset_026', 1)
            on conflict (key) do update set value = 1;
    end if;
end $$;

-- ================================================================ who may call what
do $$ declare f text; begin
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname like 'rb\_%' loop
        execute format('revoke all on function %s from public, anon, authenticated', f);
    end loop;
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = any (array[
                'rb_me', 'rb_delete_account', 'rb_state', 'rb_heartbeat', 'rb_hello', 'rb_hello2', 'rb_buy', 'rb_vendor_price',
                'rb_equip', 'rb_open_case', 'rb_daily_case', 'rb_case_gift', 'rb_spin', 'rb_spin_collect', 'rb_timers',
                'rb_slots', 'rb_plinko', 'rb_dice', 'rb_mines', 'rb_rocket', 'rb_blackjack',
                'rb_friend_add', 'rb_friend_remove', 'rb_friends_list', 'rb_profile', 'rb_history', 'rb_users',
                'rb_social', 'rb_avatar_set', 'rb_avatars_get', 'rb_rename',
                'rb_quests', 'rb_quest_claim', 'rb_mini_start', 'rb_mini_finish', 'rb_ledger_list',
                'rb_park_start', 'rb_park_finish', 'rb_tap_start', 'rb_tap_finish', 'rb_mem_start', 'rb_mem_flip',
                'rb_duel_ask', 'rb_duel_answer', 'rb_duel_play', 'rb_duels', 'rb_scratch', 'rb_login_state', 'rb_login_claim',
                'rb_sets', 'rb_set_claim', 'rb_leaders', 'rb_msg_send', 'rb_msg_threads', 'rb_msg_get', 'rb_msg_mute',
                'rb_trade_history', 'rb_backup_save', 'rb_backup_load',
                'rb_market_list', 'rb_market_cancel', 'rb_market_buy', 'rb_market_offer', 'rb_market_answer',
                'rb_market_offers', 'rb_market_unoffer', 'rb_admin_lock', 'rb_admin_revoke', 'rb_admin_catalog', 'rb_market_browse', 'rb_market_mine', 'rb_market_price',
                'rb_trade_request', 'rb_trade_accept', 'rb_trade_cancel', 'rb_trade_offer', 'rb_trade_ready',
                'rb_trade_confirm', 'rb_trade_get', 'rb_trades_list', 'rb_live', 'rb_giveaway_join',
                'rb_admin_stats', 'rb_admin_players', 'rb_admin_player', 'rb_admin_grant', 'rb_admin_give', 'rb_admin_take',
                'rb_admin_ban', 'rb_admin_avatar_clear', 'rb_admin_set', 'rb_admin_case', 'rb_admin_giveaway',
                'rb_admin_giveaway_end', 'rb_admin_sale', 'rb_admin_sale_end', 'rb_admin_audit',
                'rb_admin_undo', 'rb_admin_deals', 'rb_admin_undo_trade', 'rb_admin_undo_sale', 'rb_admin_resets',
                'rb_admin_reset_do', 'rb_admin_force_update', 'rb_admin_reset', 'rb_deals',
                'rb_looks', 'rb_quick_quote', 'rb_quick_sell']) loop
        execute format('grant execute on function %s to authenticated', f);
    end loop;
    grant execute on function public.rb_username_free(text) to anon, authenticated;
    grant execute on function public.rb_device_free(text) to anon, authenticated;
    grant execute on function public.rb_login_for(text) to anon, authenticated;
    grant execute on function public.rb_reset_ask(text, text, text) to anon, authenticated;
    grant execute on function public.rb_reset_status(uuid, text) to anon, authenticated;
end $$;
