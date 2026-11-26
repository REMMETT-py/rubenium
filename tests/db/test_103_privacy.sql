-- 9.2 (088): privacy. Deleting an account leaves nothing that names the player (backups included), a player can
-- download their data (without hidden game state), terms are accepted once, and rv_search is not in the API.
begin;
do $$
declare a uuid := t.player('Gone'); b uuid := t.player('Stays'); n bigint; d jsonb; err text; st json; c uuid; v numeric := public.rb_cfg('terms_version');
begin
    -- some rows that name A without a foreign key, plus a backup table like the resets make
    insert into public.rb_resets (name, uid, device, msg) values ('Gone', a, md5('x'), 'it is me');
    insert into public.rb_resets (name, uid, device, msg) values ('gone', null, md5('y'), 'still me');
    insert into public.rb_deal_buys (owner, day, item) values (a, current_date, 'x');
    if exists (select 1 from public.rb_races) then
        insert into public.rb_race_bets (race, lane, owner, amount) values ((select id from public.rb_races limit 1), 1, a, 10);
    end if;
    insert into public.rb_rate_hits (owner, bucket, minute, n) values (a, 'test', now(), 1);
    insert into public.rb_bot_tickets (token, by) values ('tok-gone', a);
    insert into public.rb_audit (admin, action, target) values (b, 'give', a::text);
    insert into public.rb_items (owner, item, origin) values (a, (select id from public.rb_catalog limit 1), 'shop'),
                                                            (b, (select id from public.rb_catalog limit 1), 'shop');
    insert into public.rb_messages (a, b, body) values (a, b, 'hello from Gone');
    create table public.rb_bak99_profiles as select * from public.profiles;
    create table public.rb_bak99_items as select * from public.rb_items;

    -- download my data
    perform t.act(null);
    err := t.try('select public.rb_my_data()');
    assert err <> '', 'anon cannot download data';
    perform t.act(a);
    d := public.rb_my_data();
    assert d -> 'account' ->> 'username' = 'Gone', 'account: ' || left(d::text, 200);
    assert jsonb_array_length(d -> 'items') = 1, 'own items only';
    assert jsonb_array_length(d -> 'messages') = 1 and d -> 'messages' -> 0 ->> 'to' = 'Stays', 'messages';
    assert jsonb_array_length(d -> 'password_help') = 1, 'password help';
    assert d::text not like '%"secret"%' and d::text not like '%"seed"%' and d::text not like '%"temp"%', 'no hidden state';
    assert not (d -> 'account' ? 'rig_gold'), 'no admin rig flag';

    -- terms
    st := public.rb_terms_state();
    assert (st ->> 'accepted')::boolean = false, 'not accepted yet';
    err := t.try(format('select public.rb_accept_terms(%s, false)', v));
    assert err like '%rb_too_young%', 'must say old enough: ' || err;
    err := t.try('select public.rb_accept_terms(20000101, true)');
    assert err like '%rb_update_needed%', 'old terms version: ' || coalesce(err, 'ok');
    assert public.rb_accept_terms(v, true), 'accept';
    assert (public.rb_terms_state() ->> 'accepted')::boolean, 'accepted';
    perform t.act(null);
    err := t.try('select public.rb_terms_state()');
    assert err <> '', 'anon cannot read terms state';
    perform set_config('role', 'none', true);

    -- a new account that ticked the box at sign-up has it recorded
    c := gen_random_uuid();
    insert into auth.users (id, email, raw_user_meta_data) values (c, 'newbie@users.rubenium.app',
        jsonb_build_object('username', 'Newbie', 'device', md5('newbie'), 'terms', v::text, 'adult', true));
    assert exists (select 1 from public.rb_consent where owner = c and adult), 'consent from sign-up';

    -- delete A
    perform t.act(a);
    err := t.try('select public.rb_delete_account(''gone'')');
    assert err like '%rb_confirm_mismatch%', 'name typed exactly: ' || coalesce(err, 'ok');
    assert public.rb_delete_account('Gone'), 'deleted';
    perform set_config('role', 'none', true);
    assert not exists (select 1 from public.profiles where id = a), 'profile gone';
    assert not exists (select 1 from public.rb_resets where uid = a or lower(name) = 'gone'), 'password help gone';
    assert not exists (select 1 from public.rb_deal_buys where owner = a), 'deals gone';
    assert not exists (select 1 from public.rb_race_bets where owner = a), 'bets gone';
    assert not exists (select 1 from public.rb_rate_hits where owner = a), 'rate counters gone';
    assert not exists (select 1 from public.rb_bot_tickets where by = a), 'tickets gone';
    assert not exists (select 1 from public.rb_consent where owner = a), 'consent gone';
    assert not exists (select 1 from public.rb_audit where target = a::text), 'admin log no longer names A';
    assert not exists (select 1 from public.rb_bak99_profiles where id = a), 'backup profile gone';
    assert not exists (select 1 from public.rb_bak99_items where owner = a), 'backup items gone';
    assert exists (select 1 from public.rb_bak99_items where owner = b), 'other players keep their backup';
    assert exists (select 1 from public.profiles where id = b), 'B is fine';

    -- rv_search is not in the API
    assert not has_function_privilege('anon', 'public.rv_search(text, text, integer, integer, integer)', 'execute'), 'anon rv_search';
    assert not has_function_privilege('authenticated', 'public.rv_search(text, text, integer, integer, integer)', 'execute'), 'auth rv_search';
    assert not has_function_privilege('anon', 'public.rb_forget(uuid, text)', 'execute'), 'rb_forget private';
    assert not has_function_privilege('authenticated', 'public.rb_forget(uuid, text)', 'execute'), 'rb_forget private (auth)';

    -- password help: a temporary password is wiped after a day
    insert into public.rb_resets (name, uid, device, msg, state, temp, done_at, at)
        values ('Stays', b, md5('z'), 'm', 'done', 'Temp1234', now() - interval '2 days', now() - interval '2 days');
    perform public.rb_reset_ask('Stays', md5('w'), 'again');
    assert not exists (select 1 from public.rb_resets where temp = 'Temp1234'), 'old temp password wiped';
end $$;
rollback;
