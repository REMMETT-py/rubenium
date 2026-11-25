-- Without a login (the public key only) nothing can be played, bought, claimed or changed. Every function anon may
-- execute is called with empty arguments: it must refuse, or be one of the public read-only ones below.
begin;
select t.player('Alice');
create temp table r (f text, err text);
grant all on r to anon;
create temp table before as select (select sum(coins) from public.profiles) c, (select count(*) from public.rb_items) i,
                                  (select count(*) from public.rb_ledger) l;
do $$
declare f record; args text;
begin
    perform t.act(null);
    for f in select p.oid::regprocedure::text sig, p.proname, p.pronargs from pg_proc p
              where p.pronamespace = 'public'::regnamespace and has_function_privilege('anon', p.oid, 'execute')
                and p.prorettype <> 'trigger'::regtype loop
        select string_agg('null', ', ') into args from generate_series(1, f.pronargs);
        insert into r values (f.sig, t.try(format('select public.%I(%s)', f.proname, coalesce(args, ''))));
    end loop;
end $$;
reset role;
do $$
declare bad text;
begin
    -- public on purpose: sign-up checks, password help, the shop's prices, admin swap list, pure maths helpers
    select string_agg(f, ', ') into bad from r where err = '' and split_part(f, '(', 1) not in (
        'rb_username_free', 'rb_device_free', 'rb_login_for', 'rb_reset_ask', 'rb_reset_status', 'rb_swaps_list',
        'rb_case_prices', 'rb_deal_list', 'rb_title_kinds', 'rb_case_week_start', 'rb_wave_level', 'rb_jackpot_slot',
        'rb_bet_cap', 'rb_case_cost', 'rb_flip_bot_fit', 'rb_flip_bot_for', 'rb_pawn_chance', 'rb_pawn_rage', 'rb_pawn_key',
        'rb_quest_prize', 'rb_ach_xp', 'rb_acc_mult', 'rb_c4_mult', 'rb_c4_json', 'rb_de2000', 'rb_hsb_lab', 'rb_num');
    assert bad is null, 'anon got an answer from: ' || bad;
    assert (select c from before) is not distinct from (select sum(coins) from public.profiles), 'coins changed';
    assert (select i from before) = (select count(*) from public.rb_items), 'items changed';
    assert (select l from before) = (select count(*) from public.rb_ledger), 'ledger changed';
end $$;
rollback;
