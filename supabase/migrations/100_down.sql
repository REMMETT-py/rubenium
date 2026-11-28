-- Rubenium 10.0.1 undo: rb_hello2 as in 10.0 (the note no longer moves by itself).
begin;
create or replace function public.rb_hello2(pc text, build bigint)
 returns json
 language plpgsql
 security definer
 set search_path to ''
as $function$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hello(pc);
    update public.profiles set build = coalesce(rb_hello2.build, 0) where id = me;
    if extract(epoch from now()) < coalesce(public.rb_cfg('og_until'), 0) then
        perform public.rb_og_give(me);
    end if;
    if coalesce(rb_hello2.build, 0) >= 2026112101
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
