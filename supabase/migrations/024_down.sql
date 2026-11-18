-- Undo 024 (4.1): Keno, Limbo and 2048 can be played again (with an app older than 4.1). Block Blast scores stay.
begin;
grant execute on function public.rb_keno(integer, integer[], text) to authenticated;
grant execute on function public.rb_limbo(integer, numeric, text) to authenticated;
grant execute on function public.rb_2048_finish(uuid, text) to authenticated;
create or replace function public.rb_mg_start(game text, mode integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; sd bigint;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    if game not in ('g2048', 'sweeper', 'blocks') or mode not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
    update public.rb_mg set open = false, void = true where owner = p.id and open;
    sd := floor(public.rb_rand() * 2147483647)::bigint;
    insert into public.rb_mg (owner, game, mode, seed, state) values (p.id, game, mode,
        case when game in ('g2048', 'blocks') then sd else 0 end,
        case when game = 'sweeper' then jsonb_build_object('w', (array[9, 12, 16])[mode + 1], 'h', (array[9, 12, 14])[mode + 1],
                                                           'm', (array[10, 24, 40])[mode + 1], 'seed', sd) else '{}'::jsonb end)
        returning * into r;
    return json_build_object('id', r.id, 'game', game, 'mode', mode, 'seed', r.seed,
        'w', r.state -> 'w', 'h', r.state -> 'h', 'm', r.state -> 'm',
        'size', case when game = 'g2048' then (array[4, 5, 3])[mode + 1] when game = 'blocks' then (array[8, 10, 7])[mode + 1] end);
end $$;
update public.rb_config set value = 2026111800 where key = 'min_build';
commit;
