-- Undo of 094_v94_economy.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
drop function if exists public.rb_forge_from cascade;
CREATE OR REPLACE FUNCTION public.rb_forge_state(who uuid)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with t as (select (public.rb_tier(who) ->> 'tier')::int as tier),
         d as (select coalesce(public.rb_cfg('forge_day_' || t.tier), public.rb_cfg('forge_day'), 5)::int as cap from t)
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 250)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.005) / 10) * 10)::bigint),
        'cap', d.cap,
        'left', greatest(0, d.cap - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris'))))
    from d $function$;
drop function if exists public.rb_hourly_keys cascade;
CREATE OR REPLACE FUNCTION public.rb_login_rewards()
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select '[{"coins":150},{"coins":250},{"keys":1},{"coins":400},{"keys":2},{"coins":750},{"coins":1500,"keys":1,"case":"premium"}]'::jsonb $function$;
drop function if exists public.rb_reset_94 cascade;
CREATE OR REPLACE FUNCTION public.rb_spin_table(m numeric)
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select jsonb_build_object(
        'slots', jsonb_build_array(public.rb_scaled(100, m), public.rb_scaled(150, m), public.rb_scaled(250, m),
                                   public.rb_scaled(400, m), public.rb_scaled(600, m), public.rb_scaled(1000, m),
                                   public.rb_scaled(2000, m), -1, -2, -3),
        'odds', jsonb_build_array(1800, 1800, 1700, 1300, 900, 600, 300, 800, 400, 400)) $function$;
CREATE OR REPLACE FUNCTION public.rb_tier(who uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
                              'top', 4, 'cap_x', coalesce(public.rb_cfg('cap_x_' || t), 1));       -- 9.2.1
end $function$;
CREATE OR REPLACE FUNCTION public.rb_tier_keep(who uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare t integer := (public.rb_tier(who) ->> 'tier')::int;
begin
    update public.profiles set tier_floor = t where id = who and tier_floor < t;
    return t;
end $function$;
delete from public.rb_config where key = 'hourly_keys';
delete from public.rb_config where key = 'reset_094';
update public.rb_config set value = 25000 where key = 'tier_at_1';
update public.rb_config set value = 100000 where key = 'tier_at_2';
update public.rb_config set value = 250000 where key = 'tier_at_3';
update public.rb_config set value = 1000000 where key = 'tier_at_4';
commit;
