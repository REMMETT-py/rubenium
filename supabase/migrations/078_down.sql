-- Undo of 078_v91.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
CREATE OR REPLACE FUNCTION public.rb_buy(what text, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer; d record; sale_pct integer;
begin
    perform public.rb_need_feature('shop');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind in ('prog', 'tag') or c.limited then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'anim' and position('-' in c.base) > 0 then raise exception 'rb_not_for_sale'; end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := public.rb_shop_price(what);
    select * into d from public.rb_deal_list() x where x.item = what limit 1;
    if found then                                          -- a deal: once per deal period (week, day or hour)
        if exists (select 1 from public.rb_deal_buys where owner = p.id and day = d.period and item = what) then
            sale_pct := coalesce((select max(s.pct) from public.rb_sales s
                                   where s.ends_at > now() and (rb_buy.what = s.what or rb_buy.what like s.what || ':%')), 0);
            cost := greatest(1, ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)) * (100 - sale_pct) / 100.0))::int;
        else
            insert into public.rb_deal_buys (owner, day, item) values (p.id, d.period, what) on conflict do nothing;
        end if;
    end if;
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost, 'paid', cost));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_device_free(pc text)
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select json_build_object('free', not exists (select 1 from public.rb_devices d where d.device = pc and d.owner is not null),
        'name', (select p.username from public.rb_devices d join public.profiles p on p.id = d.owner where d.device = pc)) $function$;
CREATE OR REPLACE FUNCTION public.rb_forge_state(who uuid)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 500)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.01) / 10) * 10)::bigint),
        'left', greatest(0, coalesce(public.rb_cfg('forge_day'), 5)::int - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris')))) $function$;
CREATE OR REPLACE FUNCTION public.rb_my_tier()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return public.rb_tier(auth.uid()) || jsonb_build_object('forge', public.rb_forge_state(auth.uid()));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    name text := coalesce(new.raw_user_meta_data ->> 'username', '');
    pc text := left(coalesce(new.raw_user_meta_data ->> 'device', ''), 64);
    used boolean := false;
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
    if exists (select 1 from public.rb_devices d where d.device = pc and d.owner is not null) then
        raise exception 'rb_device_used';
    end if;
    used := exists (select 1 from public.rb_devices d where d.device = pc);              -- a deleted account was here
    insert into public.profiles (id, username, login, coins, keys)
        values (new.id, name, lower(name), case when used then 0 else public.rb_cfg('start_coins') end,
                case when used then 0 else public.rb_cfg('start_keys') end);
    insert into public.rb_devices (device, owner) values (pc, new.id)
        on conflict (device) do update set owner = excluded.owner, at = now();
    return new;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_pick_weighted(k text[], tier integer, klass integer)
 RETURNS text
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select c.id from public.rb_catalog c
     where c.kind = any (k) and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
       and (klass is null or c.cls = klass) and not c.limited
       and (c.kind = 'badge' or c.price is not null)
     order by -ln(greatest(public.rb_rand(), 1e-12)) / c.weight limit 1 $function$;
drop function if exists public.rb_reset_economy_91 cascade;
CREATE OR REPLACE FUNCTION public.rb_tier(who uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare w bigint := public.rb_wealth(who); t integer := 0; i integer; nxt numeric;
begin
    for i in 1 .. 5 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    nxt := case when t < 5 then public.rb_cfg('tier_at_' || (t + 1)) end;
    return jsonb_build_object('tier', t, 'name', (array['Rookie', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'next', nxt);
end $function$;
drop function if exists public.rb_tier_keep cascade;
delete from public.rb_config where key = 'forge_day_0';
delete from public.rb_config where key = 'forge_day_1';
delete from public.rb_config where key = 'forge_day_2';
delete from public.rb_config where key = 'forge_day_3';
delete from public.rb_config where key = 'forge_day_4';
update public.rb_config set value = 500 where key = 'forge_min';
update public.rb_config set value = 0.01 where key = 'forge_pct';
delete from public.rb_config where key = 'remaster_91';
delete from public.rb_config where key = 'remaster_91_set';
delete from public.rb_config where key = 'reset_091';
update public.rb_config set value = 5000 where key = 'tier_at_1';
update public.rb_config set value = 25000 where key = 'tier_at_2';
update public.rb_config set value = 100000 where key = 'tier_at_3';
update public.rb_config set value = 500000 where key = 'tier_at_4';
update public.rb_config set value = 1.0 where key = 'tier_x_0';
update public.rb_config set value = 1.25 where key = 'tier_x_1';
update public.rb_config set value = 1.6 where key = 'tier_x_2';
update public.rb_config set value = 2.2 where key = 'tier_x_3';
update public.rb_config set value = 3.0 where key = 'tier_x_4';
insert into public.rb_config (key, value) values ('tier_at_5', 2000000), ('tier_x_5', 4.0) on conflict (key) do update set value = excluded.value;
-- Rows are not put back: profiles.tier_floor stays (unused), the 9.1 cases and animation prices stay.
commit;
