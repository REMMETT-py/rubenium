-- Rubenium 4.4 (migration 027) undone: the games roll on their own again, the rigs are gone.
begin;
do $$
declare
    edits text[][] := array[
        array['public.rb_spin()',
              'r := case when p.rig_gold then 8 else public.rb_roll(odds) end;',
              'r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    r := coalesce(least(9, greatest(0, (public.rb_rig_take(p.id, ''wheel'', '''') ->> ''slot'')::int)), r);   -- 4.4 rig'],
        array['public.rb_scratch()',
              'roll := case when p.rig_gold then 0.999 else public.rb_rand() end;',
              'roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    roll := coalesce(case public.rb_rig_take(p.id, ''scratch'', '''') ->> ''tier'' when ''standard'' then 0.15 when ''rare'' then 0.45
                          when ''special'' then 0.65 when ''epic'' then 0.85 when ''exotic'' then 0.94 when ''golden'' then 0.99 end, roll);   -- 4.4 rig'],
        array['public.rb_open_case(text, text)',
              'd := public.rb_case_drop(c);',
              'd := public.rb_case_drop(c);
    select * into d from public.rb_rig_case(p.id, c.id, d.tier, d.klass, d.item, d.coins);   -- 4.4 rig'],
        array['public.rb_dice(integer, integer, text)',
              'roll := floor(public.rb_rand() * 100)::int;',
              'roll := floor(public.rb_rand() * 100)::int;
    roll := coalesce(case (public.rb_rig_take(p.id, ''dice'', '''') ->> ''win'')::boolean
                       when true then floor(public.rb_rand() * chance)::int
                       when false then chance + floor(public.rb_rand() * (100 - chance))::int end, roll);   -- 4.4 rig'],
        array['public.rb_flip_vs_bot(uuid)',
              'a_wins := public.rb_rand() < ch;',
              'a_wins := public.rb_rand() < ch;
    a_wins := coalesce((public.rb_rig_take(p.id, ''flip'', '''') ->> ''win'')::boolean, a_wins);   -- 4.4 rig'],
        array['public.rb_flip_lock(uuid, uuid[])',
              'a_wins := public.rb_rand() < ch;',
              'a_wins := public.rb_rand() < ch;
    if f.bot_side = ''a'' then a_wins := coalesce(not (public.rb_rig_take(p.id, ''flip'', '''') ->> ''win'')::boolean, a_wins); end if;   -- 4.4 rig'],
        array['public.rb_slots(integer, text)',
              '    if reels[1] = reels[2] and reels[2] = reels[3] then',
              '    reels := coalesce((select array[x ->> 0, x ->> 1, x ->> 2] from (select public.rb_rig_take(p.id, ''slots'', '''') -> ''reels'' x) z
                        where x is not null), reels);   -- 4.4 rig
    if reels[1] = reels[2] and reels[2] = reels[3] then']];
    i integer; src text; out_ text;
begin
    for i in 1..array_length(edits, 1) loop
        src := replace(pg_get_functiondef(edits[i][1]::regprocedure), chr(13), '');
        if position(edits[i][3] in src) = 0 then continue; end if;                 -- not hooked
        out_ := replace(src, edits[i][3], edits[i][2]);
        execute out_;
    end loop;
end $$;

drop function if exists public.rb_admin_rigs(), public.rb_admin_rig(text, text, text, jsonb),
    public.rb_rig_case(uuid, text, integer, integer, text, integer), public.rb_rig_take(uuid, text, text);
drop table if exists public.rb_rigs;
update public.rb_config set value = 2026111820 where key = 'min_build';
commit;
