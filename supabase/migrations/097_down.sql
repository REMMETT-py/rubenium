-- Undo 097_v951_hotfix.sql (puts the broken rig check back: only for testing the undo).
begin;
do $$
declare
    fixes text[][] := array[
        array['public.rb_spin()',
              $a$coalesce(least(9, greatest(0, (public.rb_rig_take(p.id, 'wheel', '') ->> 'slot')::int)), r)$a$,
              $b$coalesce((select least(9, greatest(0, v)) from (select (public.rb_rig_take(p.id, 'wheel', '') ->> 'slot')::int v) s where v is not null), r)$b$],
        array['public.rb_rocket(text,integer,numeric)',
              $a$coalesce(least(100, greatest(1, (public.rb_rig_take(p.id, 'rocket', '') ->> 'crash')::numeric)), crash)$a$,
              $b$coalesce((select least(100, greatest(1, v)) from (select (public.rb_rig_take(p.id, 'rocket', '') ->> 'crash')::numeric v) s where v is not null), crash)$b$],
        array['public.rb_roulette_multi(integer,text[],text)',
              $a$coalesce(least(24, greatest(0, (public.rb_rig_take(p.id, 'roulette', '') ->> 'slot')::int)), slot)$a$,
              $b$coalesce((select least(24, greatest(0, v)) from (select (public.rb_rig_take(p.id, 'roulette', '') ->> 'slot')::int v) s where v is not null), slot)$b$]];
    i integer;
    d text;
begin
    for i in 1 .. array_length(fixes, 1) loop
        if to_regprocedure(fixes[i][1]) is null then continue; end if;
        d := pg_get_functiondef(fixes[i][1]::regprocedure);
        if position(fixes[i][3] in d) > 0 then execute replace(d, fixes[i][3], fixes[i][2]); end if;
    end loop;
end $$;
commit;
