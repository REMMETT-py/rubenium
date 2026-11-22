-- 6.4: admin button to start the Jackpot or a Horse Race right now. Only when nothing is running (the arena has one event at a
-- time); the next event is then always the other kind, 15 minutes after this one ends, like normal. With kind = null it only
-- reports the arena (what runs, what is next and when).
create or replace function public.rb_admin_arena(kind text default null) returns jsonb
language plpgsql security definer set search_path = '' as $f$
declare a public.rb_arena%rowtype;
begin
    perform public.rb_need_admin();
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1 for update;
    if kind is not null then
        if kind not in ('jackpot', 'race') then raise exception 'rb_bad_choice'; end if;
        if a.cur_id is not null then
            if a.cur_kind = kind then raise exception 'rb_arena_same'; end if;
            raise exception 'rb_arena_busy';
        end if;
        update public.rb_arena set next_kind = kind, next_at = now(), at = now() where id = 1;
        perform public.rb_arena_tick();                       -- opens it now and sets the other kind as next
        select * into a from public.rb_arena where id = 1;
    end if;
    return jsonb_build_object('cur_kind', a.cur_kind, 'next_kind', a.next_kind,
                              'next_at', extract(epoch from a.next_at), 'now', extract(epoch from now()),
                              'gap', coalesce(public.rb_cfg('arena_gap_s'), 900));
end $f$;
revoke all on function public.rb_admin_arena(text) from public, anon;
grant execute on function public.rb_admin_arena(text) to authenticated;
