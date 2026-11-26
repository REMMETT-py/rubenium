-- Rubenium 9.2: privacy and public release. Safe to run twice.
--
-- 1. Deleting an account now removes everything that still named the player: the rows that keep their id without a
--    foreign key (password help, race bets, daily deals, rate counters, pawn visits, bot tickets), their rows in every
--    rb_bak* backup table (whichever exist: the 9.2 reset makes new ones after this runs), and their id or name in the
--    admin log. Only the PC id stays in rb_devices (no owner), because one PC can make one account, ever: the privacy
--    policy says so.
-- 2. rb_my_data(): a player downloads what the server holds about them (GDPR right of access / portability). Hidden game
--    state (round secrets, seeds, anti-cheat replays) is left out. At most 2 a minute.
-- 3. Terms: rb_consent records who accepted which version of the Terms of Use and Privacy Policy and said they are old
--    enough. New accounts record it at creation (the app sends it with the sign-up); existing players accept once with
--    rb_accept_terms. rb_terms_state() tells the app what to ask. terms_version and min_age live in rb_config.
-- 4. Password help: a temporary password is wiped a day after the admin gave it, and requests go after 90 days.
-- 5. rv_search (the Reversi bot's search) is no longer callable through the API (it was open to everyone, by default).
begin;

insert into public.rb_config (key, value) values ('terms_version', 20261126) on conflict do nothing;
insert into public.rb_config (key, value) values ('min_age', 18) on conflict do nothing;

-- ------------------------------------------------------------------ consent
create table if not exists public.rb_consent (
    owner uuid primary key references auth.users (id) on delete cascade,
    version numeric not null,
    adult boolean not null,
    at timestamptz not null default now()
);
alter table public.rb_consent enable row level security;
revoke all on public.rb_consent from public, anon, authenticated;

create or replace function public.rb_consent_signup()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v text := new.raw_user_meta_data ->> 'terms';
begin
    if v ~ '^[0-9]{8}$' and coalesce(new.raw_user_meta_data ->> 'adult', '') = 'true' then
        insert into public.rb_consent (owner, version, adult) values (new.id, v::numeric, true)
            on conflict (owner) do update set version = excluded.version, adult = true, at = now();
    end if;
    return new;
end $$;
revoke all on function public.rb_consent_signup() from public, anon, authenticated;
drop trigger if exists rb_consent_signup on auth.users;
create trigger rb_consent_signup after insert on auth.users for each row execute function public.rb_consent_signup();

create or replace function public.rb_terms_state()
returns json language sql stable security definer set search_path = '' as $$
    select json_build_object(
        'version', public.rb_cfg('terms_version'),
        'min_age', public.rb_cfg('min_age'),
        'accepted', exists (select 1 from public.rb_consent c where c.owner = auth.uid()
                            and c.version >= public.rb_cfg('terms_version') and c.adult));
$$;

create or replace function public.rb_accept_terms(version numeric, adult boolean)
returns boolean language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    if adult is not true then raise exception 'rb_too_young'; end if;
    if version is null or version < public.rb_cfg('terms_version') then raise exception 'rb_update_needed'; end if;
    insert into public.rb_consent (owner, version, adult) values (me, public.rb_cfg('terms_version'), true)
        on conflict (owner) do update set version = excluded.version, adult = true, at = now();
    return true;
end $$;

-- ------------------------------------------------------------------ delete everything
create or replace function public.rb_forget(me uuid, name text)
returns void language plpgsql security definer set search_path = '' as $$
#variable_conflict use_variable
declare t text; c text; nm text := name;
begin
    delete from public.rb_resets r where r.uid = me or (nm is not null and lower(r.name) = lower(nm));
    delete from public.rb_bot_tickets k where k.by = me;
    delete from public.rb_deal_buys d where d.owner = me;
    delete from public.rb_pawn_props p where p.owner = me;
    delete from public.rb_race_bets b where b.owner = me;
    delete from public.rb_rate_hits h where h.owner = me;
    update public.rb_audit a set target = '(deleted)' where a.target in (me::text, nm, lower(nm));
    for t, c in select x.table_name, x.column_name from information_schema.columns x
                 where x.table_schema = 'public' and x.table_name like 'rb\_bak%' and x.data_type = 'uuid'
                   and x.column_name in ('id', 'owner', 'seller', 'buyer', 'a', 'b', 'uid', 'who', 'host') loop
        execute format('delete from public.%I where %I = $1', t, c) using me;
    end loop;
end $$;
revoke all on function public.rb_forget(uuid, text) from public, anon, authenticated;

create or replace function public.rb_delete_account(confirm text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); name text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select username into name from public.profiles where id = me;
    if name is null or confirm is distinct from name then
        raise exception 'rb_confirm_mismatch';                 -- the username must be typed exactly
    end if;
    delete from auth.users where id = me;                      -- the profile and everything with a foreign key go with it
    perform public.rb_forget(me, name);                         -- 9.2: and the rest
    return true;
end $$;

-- ------------------------------------------------------------------ download my data
create or replace function public.rb_my_data()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); out jsonb;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_rate(me, 'my_data', 2);
    select jsonb_build_object(
        'about', 'Everything the Rubenium server holds about this account, made ' || now()::text,
        'account', (select to_jsonb(p) - 'backup' - 'bot_cfg' - 'rig_gold' from public.profiles p where p.id = me),
        'login', (select jsonb_build_object('created_at', u.created_at, 'last_sign_in_at', u.last_sign_in_at,
                                            'login', u.email) from auth.users u where u.id = me),
        'settings_backup', (select p.backup from public.profiles p where p.id = me),
        'consent', (select to_jsonb(c) - 'owner' from public.rb_consent c where c.owner = me),
        'pcs', (select coalesce(jsonb_agg(jsonb_build_object('pc', d.device, 'at', d.at)), '[]') from public.rb_devices d where d.owner = me),
        'items', (select coalesce(jsonb_agg(to_jsonb(i) - 'owner' order by i.got_at), '[]') from public.rb_items i where i.owner = me),
        'cases', (select coalesce(jsonb_agg(to_jsonb(s) - 'owner'), '[]') from public.rb_case_stock s where s.owner = me),
        'case_stats', (select coalesce(jsonb_agg(to_jsonb(s) - 'owner'), '[]') from public.rb_case_stats s where s.owner = me),
        'coins_and_keys', (select coalesce(jsonb_agg(to_jsonb(l) - 'owner' order by l.at), '[]') from public.rb_ledger l where l.owner = me),
        'xp', (select coalesce(jsonb_agg(to_jsonb(x) - 'owner' order by x.at), '[]') from public.rb_xp_log x where x.owner = me),
        'trophies', (select coalesce(jsonb_agg(to_jsonb(a) - 'owner'), '[]') from public.rb_ach a where a.owner = me),
        'quests', (select coalesce(jsonb_agg(to_jsonb(q) - 'owner'), '[]') from public.rb_quest_claims q where q.owner = me),
        'songs', (select coalesce(jsonb_agg(to_jsonb(s) - 'owner' order by s.at), '[]') from public.rb_songs s where s.owner = me),
        'wear', (select coalesce(jsonb_agg(to_jsonb(w) - 'owner'), '[]') from public.rb_wear w where w.owner = me),
        'avatar', (select a.data from public.rb_avatars a where a.id = me),
        'friends', (select coalesce(jsonb_agg(jsonb_build_object('with', p.username, 'accepted', f.ok, 'at', f.at)), '[]')
                    from public.rb_friends f join public.profiles p on p.id = case when f.a = me then f.b else f.a end
                    where me in (f.a, f.b)),
        'muted', (select coalesce(jsonb_agg(p.username), '[]') from public.rb_mutes m join public.profiles p on p.id = m.who where m.owner = me),
        'messages', (select coalesce(jsonb_agg(jsonb_build_object('from', pa.username, 'to', pb.username, 'text', m.body, 'at', m.at)
                                               order by m.at), '[]')
                     from public.rb_messages m join public.profiles pa on pa.id = m.a join public.profiles pb on pb.id = m.b
                     where me in (m.a, m.b)),
        'trades', (select coalesce(jsonb_agg(to_jsonb(t) order by t.at), '[]') from public.rb_trades t where me in (t.a, t.b)),
        'market', (select coalesce(jsonb_agg(to_jsonb(l) order by l.at), '[]') from public.rb_listings l where me in (l.seller, l.buyer)),
        'offers', (select coalesce(jsonb_agg(to_jsonb(o) - 'buyer'), '[]') from public.rb_offers o where o.buyer = me),
        'inbox', (select coalesce(jsonb_agg(to_jsonb(n) - 'owner' order by n.at), '[]') from public.rb_inbox n where n.owner = me),
        'race_bets', (select coalesce(jsonb_agg(jsonb_build_object('race', b.race, 'lane', b.lane, 'amount', b.amount,
                                                                    'paid', b.paid, 'at', b.at)), '[]') from public.rb_race_bets b where b.owner = me),
        'skill_games', (select coalesce(jsonb_agg(to_jsonb(s) - 'owner' order by s.at), '[]') from public.rb_skill_log s where s.owner = me),
        'game_locks', (select coalesce(jsonb_agg(to_jsonb(g) - 'owner'), '[]') from public.rb_game_locks g where g.owner = me),
        'anti_cheat', (select coalesce(jsonb_agg(jsonb_build_object('game', f.game, 'kind', f.kind, 'at', f.at,
                                                                     'reviewed', f.reviewed)), '[]') from public.rb_flags f where f.owner = me),
        'password_help', (select coalesce(jsonb_agg(jsonb_build_object('message', r.msg, 'state', r.state, 'at', r.at)), '[]')
                          from public.rb_resets r where r.uid = me)
    ) into out;
    return out;
end $$;

-- ------------------------------------------------------------------ password help clean-up
create or replace function public.rb_reset_ask(name text, pc text, msg text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare rid uuid; u uuid; nm text := left(btrim(coalesce(name, '')), 20);
begin
    if coalesce(pc, '') !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;
    update public.rb_resets r set temp = null where r.temp is not null and r.done_at < now() - interval '1 day';   -- 9.2
    delete from public.rb_resets r where r.at < now() - interval '90 days';                                       -- 9.2
    select id into u from public.profiles where lower(username) = lower(nm);
    if (select count(*) from public.rb_resets r where r.device = pc and r.at > now() - interval '1 day') >= 3
       or (select count(*) from public.rb_resets r where lower(r.name) = lower(nm) and r.at > now() - interval '1 day') >= 3
       or (u is null and (select count(*) from public.rb_resets r where r.uid is null and r.at > now() - interval '1 day') >= 300) then
        raise exception 'rb_slow_down';
    end if;
    insert into public.rb_resets (name, uid, device, msg) values (nm, u, pc, left(coalesce(msg, ''), 400)) returning id into rid;
    return rid;
end $$;

-- ------------------------------------------------------------------ grants
revoke all on function public.rb_terms_state(), public.rb_accept_terms(numeric, boolean), public.rb_my_data()
    from public, anon;
grant execute on function public.rb_terms_state(), public.rb_accept_terms(numeric, boolean), public.rb_my_data()
    to authenticated, service_role;
revoke execute on function public.rv_search(text, text, integer, integer, integer) from public, anon, authenticated;

commit;
