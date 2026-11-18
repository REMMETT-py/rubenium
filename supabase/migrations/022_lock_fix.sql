-- Rubenium 022 (4.0 fix): the lock check of 021 was added after the line "begin" of each function. Functions that
-- were first saved from Windows keep CRLF line ends, so that line was not found and those functions were left
-- without the check (LOCKDOWN and the feature locks did not stop them). The same step again, line-end safe.
-- Safe to run again (a function that has the check is skipped).

-- ================================================================ every action checks its lock (added at the start of each function)
do $$ declare r record; src text; fn regprocedure; pos integer; begin
    for r in select * from (values
        ('rb_trade_request(text)', 'trading'), ('rb_trade_accept(uuid)', 'trading'),
        ('rb_trade_offer(uuid, uuid[], integer, integer)', 'trading'), ('rb_trade_ready(uuid, boolean, integer)', 'trading'),
        ('rb_trade_confirm(uuid, integer)', 'trading'),
        ('rb_market_list(uuid, integer)', 'market'), ('rb_market_buy(uuid, text)', 'market'), ('rb_market_offer(uuid, integer)', 'market'),
        ('rb_market_answer(uuid, boolean)', 'market'), ('rb_quick_sell(uuid[], text)', 'market'), ('rb_sell(uuid, text)', 'market'),
        ('rb_blackjack(text, integer)', 'casino'), ('rb_dice(integer, integer, text)', 'casino'), ('rb_plinko(integer, integer, text)', 'casino'),
        ('rb_mines(text, integer)', 'casino'), ('rb_rocket(text, integer, numeric)', 'casino'), ('rb_timing(text, integer, integer, text)', 'casino'),
        ('rb_hilo(text, integer, text)', 'casino'),
        ('rb_mini_start()', 'minigames'), ('rb_mini_finish(uuid, jsonb)', 'minigames'), ('rb_tap_start(text)', 'minigames'),
        ('rb_tap_finish(uuid, jsonb)', 'minigames'), ('rb_park_start(integer)', 'minigames'), ('rb_park_finish(uuid, jsonb)', 'minigames'),
        ('rb_mem_start(integer)', 'minigames'), ('rb_mem_flip(uuid, integer)', 'minigames'),
        ('rb_duel_ask(text, text, integer, integer)', 'minigames'), ('rb_duel_play(uuid)', 'minigames'),
        ('rb_golf_create(integer)', 'golf'), ('rb_golf_join(uuid)', 'golf'),
        ('rb_gold_wheel()', 'wheel'),
        ('rb_open_case_gold(text, text)', 'cases'), ('rb_daily_case()', 'cases'), ('rb_case_gift(text, text, text)', 'gifts'),
        ('rb_buy(text, text)', 'shop'),
        ('rb_msg_send(text, text)', 'chat'),
        ('rb_giveaway_join(uuid)', 'giveaways'),
        ('rb_quest_claim(text)', 'quests'), ('rb_set_claim(text)', 'quests'),
        ('rb_login_claim()', 'quests')) v(sig, feat) loop
        fn := to_regprocedure('public.' || r.sig);
        if fn is null then continue; end if;
        src := replace(pg_get_functiondef(fn), chr(13), '');      -- functions saved from Windows have CRLF line ends
        if position('rb_need_feature' in src) > 0 or position('LANGUAGE plpgsql' in src) = 0 then continue; end if;
        pos := position(E'\nbegin\n' in src);
        if pos = 0 then continue; end if;
        src := substr(src, 1, pos + 6) || '    perform public.rb_need_feature(''' || r.feat || ''');' || E'\n' || substr(src, pos + 7);
        execute src;
    end loop;
end $$;
