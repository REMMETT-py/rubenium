-- 6.8: Horse races last 3 times longer (the race proper is 60 s: lock + 74 s = done), five more maps (8 in all), and the admins can rig
-- the finishing order of a race: choose the 1st (and 2nd, 3rd) horse and how many races to let pass first.
alter table public.rb_arena add column if not exists race_rig integer[];
alter table public.rb_arena add column if not exists race_rig_in integer not null default 0;

do $m$
declare s text;
begin
    s := pg_get_functiondef('public.rb_race_make()'::regprocedure);
    if position('''beach''' in s) = 0 then
        s := replace(s, '(array[''desert'', ''forest'', ''snow''])[1 + floor(public.rb_rand() * 3)::int]',
                        '(array[''desert'', ''forest'', ''snow'', ''beach'', ''canyon'', ''night'', ''volcano'', ''moon''])[1 + floor(public.rb_rand() * 8)::int]');
        execute s;
    end if;
    s := pg_get_functiondef('public.rb_race_advance(uuid)'::regprocedure);
    if position('race_rig' in s) = 0 then
        s := replace(s, 'place_ integer; ret double precision; cut double precision;',
                        'place_ integer; ret double precision; cut double precision; rg integer[]; rin integer; pl2 integer[]; xx integer;');
        s := replace(s, 'r.winner := pl[1];',
                        'select race_rig, race_rig_in into rg, rin from public.rb_arena where id = 1 for update;
        if rg is not null and array_length(rg, 1) >= 1 then
            if coalesce(rin, 0) > 0 then
                update public.rb_arena set race_rig_in = rin - 1 where id = 1;
            else
                pl2 := rg;
                foreach xx in array pl loop
                    if not (xx = any (pl2)) then pl2 := pl2 || xx; end if;
                end loop;
                pl := pl2;
                update public.rb_arena set race_rig = null, race_rig_in = 0 where id = 1;
            end if;
        end if;
        r.winner := pl[1];');
        s := replace(s, 'interval ''34 seconds''', 'interval ''74 seconds''');
        execute s;
    end if;
end $m$;

-- admin: report / set / clear the rig. places = the horses (0 to 4) in the order they must finish (1 to 5 of them); skip = races to let
-- pass first (0 = the race that locks next: the open one if there is one, else the next one that opens). clear = true removes it.
create or replace function public.rb_admin_race_rig(places integer[] default null, skip integer default 0, clear boolean default false) returns jsonb
language plpgsql security definer set search_path = '' as $f$
declare a public.rb_arena%rowtype; r public.rb_races%rowtype; x integer;
begin
    perform public.rb_need_admin();
    if clear then
        update public.rb_arena set race_rig = null, race_rig_in = 0 where id = 1;
    elsif places is not null then
        if array_length(places, 1) is null or array_length(places, 1) > 5 then raise exception 'rb_bad_choice'; end if;
        foreach x in array places loop
            if x < 0 or x > 4 then raise exception 'rb_bad_choice'; end if;
        end loop;
        if (select count(distinct v) from unnest(places) v) <> array_length(places, 1) then raise exception 'rb_bad_choice'; end if;
        update public.rb_arena set race_rig = places, race_rig_in = greatest(0, least(coalesce(skip, 0), 20)) where id = 1;
    end if;
    select * into a from public.rb_arena where id = 1;
    select * into r from public.rb_races order by opened_at desc limit 1;
    return jsonb_build_object('rig', to_jsonb(a.race_rig), 'skip', a.race_rig_in, 'now', extract(epoch from now()),
                              'race_state', r.state, 'lock_at', extract(epoch from r.lock_at), 'done_at', extract(epoch from r.done_at),
                              'next_kind', a.next_kind, 'next_at', extract(epoch from a.next_at));
end $f$;
revoke all on function public.rb_admin_race_rig(integer[], integer, boolean) from public, anon;
grant execute on function public.rb_admin_race_rig(integer[], integer, boolean) to authenticated;
