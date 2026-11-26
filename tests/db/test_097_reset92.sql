-- 9.2 (083): the reset. OG players lose everything but the OG tag (level kept or not), others keep items; everyone
-- gets 2 500 coins and 5 keys once, streaks and quests go, bots' stats go, the arena keeps bots' entries.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('OgOne', 90000, 30); pb uuid := t.player('Plain', 70000, 20); pbot uuid;
        r jsonb; err text; itm text;
begin
    itm := (select id from public.rb_catalog where id like 'badge:%' limit 1);
    insert into public.rb_items (owner, item, origin) values (pa, 'tag:og', 'shop'), (pa, itm, 'shop'), (pb, itm, 'shop');
    insert into public.rb_case_stock (owner, case_id, n) values (pa, 'standard', 4), (pb, 'standard', 4) on conflict (owner, case_id) do update set n = 4;
    update public.profiles set xp = 5000, level = 7, streak = 9, streak_day = current_date,
                               equip = equip || '{"trophy1": "x"}'::jsonb where id in (pa, pb);
    insert into public.rb_quest_claims (owner, quest, period) values (pb, 'q', now());
    pbot := t.player('BotOne', 100, 0);
    update public.profiles set bot = true, bot_cfg = '{"stats": {"wave": 5}}', streak = 4 where id = pbot;

    r := public.rb_reset_92(true);
    assert (r ->> 'og_players')::int >= 1, r::text;
    -- OG: only the tag left, the starter cases, coins and keys, level kept
    assert (select array_agg(i.item) from public.rb_items i where i.owner = pa) = array['tag:og'], 'og items';
    assert (select n from public.rb_case_stock where owner = pa and case_id = 'standard') = 5, 'og cases: the pack only';
    assert (select n from public.rb_case_stock where owner = pa and case_id = 'starter') = 3, 'og starter cases';
    assert (select coins from public.profiles where id = pa) = 2500 and (select keys from public.profiles where id = pa) = 5, 'og coins';
    assert (select level from public.profiles where id = pa) = 7, 'og level kept';
    assert not ((select equip from public.profiles where id = pa) ? 'trophy1'), 'og trophies off the profile';
    -- others: items and cases kept, coins and keys reset to the pack (once)
    assert exists (select 1 from public.rb_items where owner = pb and rb_items.item = itm), 'plain keeps items';
    assert (select n from public.rb_case_stock where owner = pb and case_id = 'standard') = 4, 'plain keeps cases, no double pack';
    assert (select coins from public.profiles where id = pb) = 2500 and (select keys from public.profiles where id = pb) = 5, 'plain coins';
    -- everyone
    assert (select count(*) from public.profiles where streak <> 0) = 0, 'streaks 0, bots too';
    assert not ((select bot_cfg from public.profiles where id = pbot) ? 'stats'), 'bot stats gone';
    assert (select coins from public.profiles where id = pbot) is not distinct from (select coins from public.rb_bak92_profiles where id = pbot), 'bots coins untouched';
    assert (select count(*) from public.rb_quest_claims) = 0, 'quests reset';
    assert public.rb_cfg('board_from') > 0, 'boards reset';
    assert (select count(*) from public.rb_bak92_profiles) > 0, 'backup kept';
    err := t.try('select public.rb_reset_92(true)');
    assert err like '%rb_already_done%', 'once: ' || err;
end $$;
rollback;
