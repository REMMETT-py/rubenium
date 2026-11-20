-- ================================================================ Rubenium 5.0.1
-- The OG coupon (and its scratch card) only reaches a player once their app is 5.0 or newer: old apps were showing it
-- before updating. Applied on the live server on 20/11/2026. Safe to run again.
begin;
alter table public.profiles add column if not exists og_coupon_50 boolean not null default false;

update public.profiles p set og_coupon_50 = true
 where p.build >= 2026112001 and exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'coupon:og');
delete from public.rb_items i using public.profiles p
 where i.owner = p.id and i.item = 'coupon:og' and i.locked is null and not p.og_coupon_50;

create or replace function public.rb_hello2(pc text, build bigint) returns json
language plpgsql security definer set search_path to '' as $function$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hello(pc);
    update public.profiles set build = coalesce(rb_hello2.build, 0) where id = me;
    if extract(epoch from now()) < coalesce(public.rb_cfg('og_until'), 0) then
        perform public.rb_og_give(me);
    end if;
    -- 5.0: the OG coupon to level 5, given once, only to an app that is 5.0 or newer
    if coalesce(rb_hello2.build, 0) >= 2026112001
       and exists (select 1 from public.rb_items i where i.owner = me and i.item = 'tag:og')
       and not (select og_coupon_50 from public.profiles where id = me) then
        update public.profiles set og_coupon_50 = true where id = me;
        insert into public.rb_items (owner, item, origin) values (me, 'coupon:og', 'og');
        insert into public.rb_seen (owner, item) values (me, 'coupon:og') on conflict do nothing;
    end if;
    perform public.rb_fix_equip(me);
    return json_build_object('min_build', public.rb_cfg('min_build')::bigint,
                             'update', coalesce(build, 0) < public.rb_cfg('min_build'));
end $function$;
commit;
