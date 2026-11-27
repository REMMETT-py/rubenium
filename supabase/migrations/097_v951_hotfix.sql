-- Rubenium 9.5.1 hotfix. Safe to run twice. Undo: 097_down.sql.
--
-- The free spin wheel, the rocket and the roulette: since 9.0 an admin's "rig" check was written
-- coalesce(least(.., greatest(.., <rig or null>)), <the real roll>). Postgres' greatest() skips a null, so with no rig
-- it gave the lowest value instead of null, and the real roll was never used:
--   * the free spin always landed on slot 0 (100 coins),
--   * the rocket always crashed at 1.00x,
--   * the roulette always landed on 0 (gold).
-- Now the rig is only used when there is one.
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
        if position(fixes[i][3] in d) > 0 then continue; end if;             -- already fixed
        if position(fixes[i][2] in d) = 0 then raise exception 'rb_hotfix: % is not the expected version', fixes[i][1]; end if;
        execute replace(d, fixes[i][2], fixes[i][3]);
    end loop;
end $$;

commit;
