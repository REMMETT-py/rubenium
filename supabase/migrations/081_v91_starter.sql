-- Rubenium 9.1 starter pack and clearer tiers. Safe to run twice (the gift is given once).
--
-- 1. Wealth, exactly: your coins + the shop value of every item you got since the 9.1 fresh start
--    (26 Nov 2026, 05:28 UTC). Items kept from before 9.1 still belong to you but do not count, so everyone starts Poor.
-- 2. Lower tiers: Average 25 000, Investor 100 000, Businessman 250 000, Casino Legend 1 000 000.
--    Tiers reached before this change are cleared once (everyone starts at Poor).
-- 3. Starter pack for every player, once: 2 500 coins, 5 keys, 3 Starter Cases and 5 Standard Cases
--    (the Pocket Case was retired in 6.3; the Standard Case is the closest one in the shop).
-- 4. New accounts get the same pack.
begin;

insert into public.rb_config (key, value) values ('wealth_from', extract(epoch from timestamptz '2026-11-26 05:28:00+00'))
on conflict (key) do nothing;
update public.rb_config set value = v.value from (values
    ('tier_at_1', 25000), ('tier_at_2', 100000), ('tier_at_3', 250000), ('tier_at_4', 1000000),
    ('start_coins', 2500), ('start_keys', 5)
) as v(key, value) where rb_config.key = v.key;

create or replace function public.rb_wealth_items(who uuid) returns bigint
language sql stable security definer set search_path to '' as $$
    select coalesce(sum(public.rb_worth(i.item)), 0)::bigint from public.rb_items i
     where i.owner = who and i.got_at >= to_timestamp(coalesce(public.rb_cfg('wealth_from'), 0)) $$;

create or replace function public.rb_wealth(who uuid) returns bigint
language sql stable security definer set search_path to '' as $$
    select coalesce((select p.coins from public.profiles p where p.id = who), 0) + public.rb_wealth_items(who) $$;

create or replace function public.rb_tier(who uuid) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare c bigint := coalesce((select coins from public.profiles where id = who), 0);
        it bigint := public.rb_wealth_items(who); w bigint := c + it; t integer := 0; i integer; fl integer;
begin
    for i in 1 .. 4 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    fl := least(4, greatest(0, coalesce((select tier_floor from public.profiles where id = who), 0)));
    t := greatest(t, fl);
    return jsonb_build_object('tier', t, 'name', (array['Poor', 'Average', 'Investor', 'Businessman', 'Casino Legend'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'coins', c, 'items', it,
                              'at', case when t > 0 then public.rb_cfg('tier_at_' || t) else 0 end,
                              'next', case when t < 4 then public.rb_cfg('tier_at_' || (t + 1)) end,
                              'next_name', case when t < 4 then (array['Poor', 'Average', 'Investor', 'Businessman',
                                                                      'Casino Legend'])[t + 2] end,
                              'top', 4);
end $$;

create or replace function public.rb_starter_pack(who uuid) returns void
language sql security definer set search_path to '' as $$
    insert into public.rb_case_stock (owner, case_id, n) values (who, 'starter', 3), (who, 'standard', 5)
    on conflict (owner, case_id) do update set n = public.rb_case_stock.n + excluded.n $$;
revoke all on function public.rb_starter_pack(uuid) from public, anon, authenticated;
revoke all on function public.rb_wealth_items(uuid) from public, anon, authenticated;

create or replace function public.rb_new_user() returns trigger
language plpgsql security definer set search_path to '' as $$
declare
    name text := coalesce(new.raw_user_meta_data ->> 'username', '');
    pc text := left(coalesce(new.raw_user_meta_data ->> 'device', ''), 64);
begin
    if name !~ '^[A-Za-z0-9]{3,10}$' then raise exception 'rb_bad_username'; end if;
    if new.email is distinct from lower(name) || '@users.rubenium.app' then raise exception 'rb_bad_account'; end if;
    if exists (select 1 from public.profiles p where lower(p.username) = lower(name) or p.login = lower(name)) then
        raise exception 'rb_username_taken';
    end if;
    if pc like 'bot:%' then
        if not exists (select 1 from public.rb_bot_tickets t where t.token = substr(pc, 5)
                        and t.at > now() - interval '10 minutes') then raise exception 'rb_update_needed'; end if;
        delete from public.rb_bot_tickets where token = substr(pc, 5);
        insert into public.profiles (id, username, login, coins, keys, bot)
            values (new.id, name, lower(name), public.rb_cfg('start_coins'), public.rb_cfg('start_keys'), true);
        return new;
    end if;
    if pc !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;       -- an old version of the app
    if exists (select 1 from public.rb_devices d where d.device = pc) then             -- 9.1: one creation per PC, ever
        raise exception 'rb_device_used';
    end if;
    insert into public.profiles (id, username, login, coins, keys)
        values (new.id, name, lower(name), public.rb_cfg('start_coins'), public.rb_cfg('start_keys'));
    insert into public.rb_devices (device, owner) values (pc, new.id);
    perform public.rb_starter_pack(new.id);                                            -- 9.1: 3 Starter + 5 Standard
    return new;
end $$;

-- the gift, once: every player (not test bots) starts Poor with the pack
do $$
declare r record;
begin
    if coalesce((select value from public.rb_config where key = 'gift_91'), 0) = 1 then return; end if;
    update public.profiles set tier_floor = 0;
    for r in select id from public.profiles where not coalesce(bot, false) loop
        update public.profiles set coins = coins + 2500, keys = keys + 5 where id = r.id;
        insert into public.rb_ledger (owner, coins, keys, reason, ref) values (r.id, 2500, 5, 'gift', '9.1 starter pack');
        perform public.rb_starter_pack(r.id);
    end loop;
    insert into public.rb_config (key, value) values ('gift_91', 1) on conflict (key) do update set value = 1;
end $$;

commit;

