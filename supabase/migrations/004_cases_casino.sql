-- Rubenium 004: cases, the daily case, the free spin and the casino. Every result is rolled here, on the server,
-- and saved before the app shows anything. Safe to run more than once. Needs 003 first.
-- Run it in Supabase: SQL Editor > New query > paste > Run.

insert into public.rb_config (key, value) values
    ('bet_min', 10), ('bet_max', 1000), ('win_max', 50000),
    ('spin_hours', 3), ('daily_hours', 24)
on conflict (key) do nothing;

alter table public.profiles add column if not exists spin_at timestamptz;
alter table public.profiles add column if not exists spin_prize jsonb;            -- rolled, waiting for "Collect"
alter table public.profiles add column if not exists daily_at timestamptz;

-- a random number 0 <= x < 1 from the database's secure generator
create or replace function public.rb_rand() returns double precision
language sql volatile set search_path = '' as $$
    select (('x' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8))::bit(32)::bigint)::double precision
           / 4294967296.0 $$;

-- ---------------------------------------------------------------- cases
-- odds are out of 10 000: coins, standard, rare, special, epic, exotic. pity = a drop of `pity_tier` or better
-- is certain after `pity_after` opens without one.
create table if not exists public.rb_cases (
    id text primary key, pos integer not null, price integer not null,
    odds integer[] not null, coin_min integer not null, coin_max integer not null,
    exotics boolean not null, pity_tier integer not null, pity_after integer not null);
insert into public.rb_cases values
    ('starter',  1,  100, array[7900, 1830,  245,   25,    0,   0],  15,   35, false, 2, 30),
    ('standard', 2,  300, array[6100, 2750,  900,  220,   30,   0],  60,  130, false, 3, 25),
    ('premium',  3,  800, array[3555, 2000, 3000, 1050,  370,  25], 200,  400, true,  3, 10),
    ('vault',    4, 2000, array[2000,    0, 3750, 2700, 1400, 150], 500,  900, true,  4, 10)
on conflict (id) do update set pos = excluded.pos, price = excluded.price, odds = excluded.odds,
    coin_min = excluded.coin_min, coin_max = excluded.coin_max, exotics = excluded.exotics,
    pity_tier = excluded.pity_tier, pity_after = excluded.pity_after;
create table if not exists public.rb_case_stats (
    owner uuid not null references public.profiles (id) on delete cascade, case_id text not null,
    opens integer not null default 0, dry integer not null default 0, primary key (owner, case_id));
-- casino rounds that take more than one step (blackjack, bombs, rocket). The hidden part never leaves the server.
create table if not exists public.rb_rounds (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    game text not null, bet integer not null, secret jsonb not null, open boolean not null default true,
    paid integer not null default 0, at timestamptz not null default clock_timestamp());
create unique index if not exists rb_rounds_one_open on public.rb_rounds (owner, game) where open;
create index if not exists rb_rounds_history on public.rb_rounds (owner, at desc) where not open;
do $$ declare t text; begin
    foreach t in array array['rb_cases', 'rb_case_stats', 'rb_rounds'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end $$;
grant select on public.rb_cases to anon, authenticated;
drop policy if exists "read cases" on public.rb_cases;
create policy "read cases" on public.rb_cases for select to anon, authenticated using (true);

-- pick one badge of a rarity (1 standard .. 5 exotic)
create or replace function public.rb_pick_badge(tier integer, with_exotics boolean) returns text
language sql volatile security definer set search_path = '' as $$
    select c.id from public.rb_catalog c
     where c.kind = 'badge'
       and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
       and (with_exotics or c.base not in ('galaxy', 'phoenix', 'glitch', 'crystal', 'dragon'))
     order by public.rb_rand() limit 1 $$;

-- roll a drop table: returns 0 for coins, 1..5 for a rarity
create or replace function public.rb_roll(odds integer[]) returns integer
language plpgsql volatile set search_path = '' as $$
declare r integer := floor(public.rb_rand() * 10000)::int; i integer;
begin
    for i in 1 .. array_length(odds, 1) loop
        if r < odds[i] then return i - 1; end if;
        r := r - odds[i];
    end loop;
    return 0;
end $$;

drop function if exists public.rb_open_case(text, text);
create or replace function public.rb_open_case(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; s public.rb_case_stats%rowtype;
        res jsonb; tier integer; what text; coins integer := 0; new_id uuid; pity boolean := false;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    perform public.rb_pay(p.id, -c.price, -1, 'case', c.id);
    insert into public.rb_case_stats as st (owner, case_id) values (p.id, c.id) on conflict do nothing;
    select * into s from public.rb_case_stats st where st.owner = p.id and st.case_id = c.id for update;
    tier := public.rb_roll(c.odds);
    if s.dry + 1 >= c.pity_after and tier < c.pity_tier then
        tier := c.pity_tier; pity := true;
    end if;
    if tier = 0 then
        coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
        perform public.rb_pay(p.id, coins, 0, 'case_coins', c.id);
    else
        what := public.rb_pick_badge(tier, c.exotics);
        new_id := public.rb_give(p.id, what, 'case:' || c.id);
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'case:' || c.id, c.price,
        jsonb_build_object('item', what, 'tier', tier), false,
        coins + coalesce((select value from public.rb_catalog where id = what), 0));
    update public.rb_case_stats set opens = opens + 1, dry = case when tier >= c.pity_tier then 0 else dry + 1 end
     where owner = p.id and rb_case_stats.case_id = c.id;
    return public.rb_remember(p.id, req, jsonb_build_object('tier', tier, 'item', what, 'id', new_id, 'won', coins,
        'pity', pity, 'coins', p.coins - c.price + coins, 'keys', p.keys - 1));
end $$;

-- the free daily case
create or replace function public.rb_daily_case() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r double precision; what text; coins integer := 0; keys integer := 0; new_id uuid;
        tier integer := 0;
begin
    p := public.rb_lock_me();
    if p.daily_at is not null and now() < p.daily_at + make_interval(hours => public.rb_cfg('daily_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := public.rb_rand();
    if r < 0.60 then coins := 30 + floor(public.rb_rand() * 91)::int;
    elsif r < 0.75 then keys := 1;
    elsif r < 0.95 then tier := 1;
    elsif r < 0.995 then tier := 2;
    else tier := 3; end if;
    if tier > 0 then
        what := public.rb_pick_badge(tier, false);
        new_id := public.rb_give(p.id, what, 'daily');
    end if;
    update public.profiles set daily_at = now() where id = p.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'daily', 0,
        jsonb_build_object('item', what, 'tier', tier, 'keys', keys), false,
        coins + coalesce((select value from public.rb_catalog where id = what), 0));
    perform public.rb_pay(p.id, coins, keys, 'daily_case', null);
    return jsonb_build_object('tier', tier, 'item', what, 'id', new_id, 'won', coins, 'won_keys', keys,
                              'coins', p.coins + coins, 'keys', p.keys + keys);
end $$;

-- the free spin: rolled and kept on the server, paid when "Collect" is pressed
create or replace function public.rb_spin() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r integer; prize jsonb;
        slots integer[] := array[20, 40, 60, 100, 150, 250, 500, -1];        -- -1 = one key
        odds  integer[] := array[3000, 2500, 1800, 1200, 600, 300, 100, 500];
begin
    p := public.rb_lock_me();
    if p.spin_prize is not null then return p.spin_prize || jsonb_build_object('waiting', true); end if;
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := public.rb_roll(odds);
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] < 0 then 1 else 0 end);
    update public.profiles set spin_at = now(), spin_prize = prize where id = p.id;
    return prize;
end $$;

create or replace function public.rb_spin_collect() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if p.spin_prize is null then raise exception 'rb_nothing_to_collect'; end if;
    update public.profiles set spin_prize = null where id = p.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'spin', 0,
        jsonb_build_object('keys', (p.spin_prize ->> 'won_keys')::int), false, (p.spin_prize ->> 'won')::int);
    perform public.rb_pay(p.id, (p.spin_prize ->> 'won')::int, (p.spin_prize ->> 'won_keys')::int, 'spin', null);
    return jsonb_build_object('coins', p.coins + (p.spin_prize ->> 'won')::int,
                              'keys', p.keys + (p.spin_prize ->> 'won_keys')::int);
end $$;

-- when the free things are ready again (seconds; 0 = now)
create or replace function public.rb_timers() returns jsonb
language sql stable security definer set search_path = '' as $$
    select jsonb_build_object(
        'spin', greatest(0, ceil(extract(epoch from (p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) - now()))))::int,
        'spin_waiting', p.spin_prize,
        'daily', greatest(0, ceil(extract(epoch from (p.daily_at + make_interval(hours => public.rb_cfg('daily_hours')::int) - now()))))::int)
      from public.profiles p where p.id = auth.uid() $$;

-- ---------------------------------------------------------------- casino
create or replace function public.rb_bet(p public.profiles, bet integer, game text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if bet is null or bet < public.rb_cfg('bet_min') or bet > public.rb_cfg('bet_max') then
        raise exception 'rb_bad_bet';
    end if;
    perform public.rb_pay(p.id, -bet, 0, 'bet', game);
end $$;

create or replace function public.rb_win(who uuid, amount numeric, game text) returns integer
language plpgsql security definer set search_path = '' as $$
declare pay integer := least(floor(amount), public.rb_cfg('win_max'))::int;
begin
    perform public.rb_pay(who, greatest(pay, 0), 0, 'win', game);
    return greatest(pay, 0);
end $$;

-- Slots: 3 reels, 6 symbols. Three the same pays x3 to x50, any two the same x1.5.
create or replace function public.rb_slots(bet integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r integer[] := '{}'; i integer; mult numeric := 0; pay integer;
        weights integer[] := array[2857, 2381, 1905, 1429, 952, 476];      -- 6:5:4:3:2:1
        triple numeric[] := array[3, 5, 8, 12, 25, 50];
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_bet(p, bet, 'slots');
    for i in 1 .. 3 loop r := r || public.rb_roll(weights); end loop;
    if r[1] = r[2] and r[2] = r[3] then mult := triple[r[1] + 1];
    elsif r[1] = r[2] or r[2] = r[3] or r[1] = r[3] then mult := 1.5; end if;
    pay := public.rb_win(p.id, bet * mult, 'slots');
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'slots', bet, '{}'::jsonb, false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('reels', to_jsonb(r), 'mult', mult, 'paid', pay,
                                                            'coins', p.coins - bet + pay));
end $$;

-- Plinko: 10 rows, the ball goes left or right at each pin. risk 0 low, 1 medium, 2 high.
create or replace function public.rb_plinko(bet integer, risk integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; path integer[] := '{}'; box integer := 0; i integer; d integer;
        mult numeric; pay integer;
        tables numeric[][] := array[[8.5, 3, 1.4, 1.1, 0.95, 0.5, 0.95, 1.1, 1.4, 3, 8.5],
                                    [21, 5, 2, 1.3, 0.6, 0.4, 0.6, 1.3, 2, 5, 21],
                                    [70, 9, 3, 0.9, 0.3, 0.2, 0.3, 0.9, 3, 9, 70]];
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if risk is null or risk < 0 or risk > 2 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'plinko');
    for i in 1 .. 10 loop
        d := case when public.rb_rand() < 0.5 then 0 else 1 end;
        path := path || d; box := box + d;
    end loop;
    mult := tables[risk + 1][box + 1];
    pay := public.rb_win(p.id, bet * mult, 'plinko');
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'plinko', bet, '{}'::jsonb, false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('path', to_jsonb(path), 'box', box, 'mult', mult,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

-- Dice: choose your chance to win (5 to 95 %). The lower the chance, the bigger the prize. 3 % for the house.
create or replace function public.rb_dice(bet integer, chance integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; roll integer; mult numeric; pay integer := 0;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if chance is null or chance < 5 or chance > 95 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'dice');
    roll := floor(public.rb_rand() * 100)::int;                    -- 0..99; you win below your chance
    mult := floor(9700.0 / chance) / 100;
    if roll < chance then pay := public.rb_win(p.id, bet * mult, 'dice'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'dice', bet, '{}'::jsonb, false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('roll', roll, 'mult', mult, 'win', roll < chance,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

-- Bombs: 25 cards hide gems and bombs. Each gem raises the prize; cash out any time. 3 % for the house.
drop function if exists public.rb_mines_mult(integer, integer);
create or replace function public.rb_mines_mult(gems integer, bombs integer) returns numeric
language plpgsql immutable set search_path = '' as $$
declare chance numeric := 1; i integer;
begin
    if gems <= 0 then return 1; end if;
    for i in 0 .. gems - 1 loop chance := chance * (25 - bombs - i)::numeric / (25 - i); end loop;
    return least(1000, floor(0.97 / chance * 100) / 100);
end $$;

create or replace function public.rb_mines(action text, arg integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; bombs integer[]; picked integer[]; n integer;
        pay integer := 0; hit boolean := false; done boolean := false;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'mines' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        n := (arg / 10000);                                   -- arg = bombs * 10000 + bet
        if n not in (1, 3, 5, 10, 20) then raise exception 'rb_bad_choice'; end if;
        perform public.rb_bet(p, arg % 10000, 'mines');
        select array_agg(t) into bombs from (select t from generate_series(0, 24) t order by public.rb_rand() limit n) x;
        insert into public.rb_rounds (owner, game, bet, secret)
            values (p.id, 'mines', arg % 10000, jsonb_build_object('bombs', to_jsonb(bombs), 'picked', '[]'::jsonb))
            returning * into r;
        return jsonb_build_object('open', true, 'bet', r.bet, 'bombs', n, 'picked', '[]'::jsonb, 'mult', 1,
                                  'coins', p.coins - r.bet);
    end if;
    if not found then return jsonb_build_object('open', false); end if;
    select array_agg(v::int) into bombs from jsonb_array_elements_text(r.secret -> 'bombs') v;
    select coalesce(array_agg(v::int), '{}') into picked from jsonb_array_elements_text(r.secret -> 'picked') v;
    n := array_length(bombs, 1);
    if action = 'pick' then
        if arg is null or arg < 0 or arg > 24 or arg = any (picked) then raise exception 'rb_bad_choice'; end if;
        if arg = any (bombs) then
            hit := true; done := true;
        else
            picked := picked || arg;
            if coalesce(array_length(picked, 1), 0) >= 25 - n then action := 'cash'; end if;      -- every gem found
        end if;
    end if;
    if action = 'cash' then
        if coalesce(array_length(picked, 1), 0) < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * public.rb_mines_mult(array_length(picked, 1), n), 'mines');
        done := true;
    end if;
    update public.rb_rounds set open = not done, paid = pay,
           secret = jsonb_build_object('bombs', to_jsonb(bombs), 'picked', to_jsonb(picked)) where id = r.id;
    return jsonb_build_object('open', not done, 'bet', r.bet, 'bombs', n, 'picked', to_jsonb(picked), 'hit', hit,
        'tile', arg, 'mult', public.rb_mines_mult(coalesce(array_length(picked, 1), 0), n), 'paid', pay,
        'board', case when done then to_jsonb(bombs) end, 'coins', p.coins + pay);
end $$;

-- Rocket: the multiplier climbs until the rocket blows up. Cash out before it does. 4 % for the house.
create or replace function public.rb_rocket(action text, bet integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; crash numeric; now_mult numeric; pay integer := 0;
        u double precision;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'rocket' and open for update;
    if found then
        crash := (r.secret ->> 'crash')::numeric;
        now_mult := floor(exp(0.08 * extract(epoch from (clock_timestamp() - r.at))) * 100) / 100;
        if now_mult >= crash then                               -- it already blew up
            update public.rb_rounds set open = false where id = r.id;
            if action <> 'start' then
                return jsonb_build_object('open', false, 'crashed', true, 'crash', crash, 'paid', 0, 'coins', p.coins);
            end if;
        elsif action = 'cash' then
            pay := public.rb_win(p.id, r.bet * now_mult, 'rocket');
            update public.rb_rounds set open = false, paid = pay where id = r.id;
            return jsonb_build_object('open', false, 'crashed', false, 'mult', now_mult, 'crash', crash, 'paid', pay,
                                      'coins', p.coins + pay);
        elsif action = 'look' then
            return jsonb_build_object('open', true, 'mult', now_mult, 'bet', r.bet,
                                      'age', extract(epoch from (clock_timestamp() - r.at)));
        else
            raise exception 'rb_round_open';
        end if;
    end if;
    if action <> 'start' then return jsonb_build_object('open', false); end if;
    perform public.rb_bet(p, bet, 'rocket');
    u := public.rb_rand();
    crash := greatest(1.00, least(100, floor(96 / (1 - u)) / 100));
    insert into public.rb_rounds (owner, game, bet, secret) values (p.id, 'rocket', bet, jsonb_build_object('crash', crash));
    return jsonb_build_object('open', true, 'mult', 1, 'bet', bet, 'age', 0, 'coins', p.coins - bet);
end $$;

-- Blackjack. Dealer stands on 17. Blackjack pays 3 to 2. Cards are 0..51 (rank = card % 13: 0 ace, 10-12 faces).
create or replace function public.rb_bj_total(cards integer[]) returns integer
language plpgsql immutable set search_path = '' as $$
declare t integer := 0; aces integer := 0; c integer; v integer;
begin
    foreach c in array cards loop
        v := c % 13;
        if v = 0 then aces := aces + 1; t := t + 11; elsif v >= 9 then t := t + 10; else t := t + v + 1; end if;
    end loop;
    while t > 21 and aces > 0 loop t := t - 10; aces := aces - 1; end loop;
    return t;
end $$;

create or replace function public.rb_blackjack(action text, bet integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; deck integer[]; me integer[]; dealer integer[];
        stake integer; done boolean := false; pay integer := 0; outcome text := ''; spent integer := 0;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'blackjack' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        perform public.rb_bet(p, bet, 'blackjack');
        spent := bet; stake := bet;
        select array_agg(c) into deck from (select c from generate_series(0, 51) c order by public.rb_rand()) x;
        me := array[deck[1], deck[3]]; dealer := array[deck[2], deck[4]]; deck := deck[5:52];
        insert into public.rb_rounds (owner, game, bet, secret) values (p.id, 'blackjack', bet, '{}'::jsonb) returning * into r;
        if public.rb_bj_total(me) = 21 or public.rb_bj_total(dealer) = 21 then action := 'natural'; done := true; end if;
    else
        if not found then return jsonb_build_object('open', false); end if;
        select array_agg(v::int) into deck from jsonb_array_elements_text(r.secret -> 'deck') v;
        select array_agg(v::int) into me from jsonb_array_elements_text(r.secret -> 'me') v;
        select array_agg(v::int) into dealer from jsonb_array_elements_text(r.secret -> 'dealer') v;
        stake := (r.secret ->> 'stake')::int;
        if action = 'double' then
            if array_length(me, 1) <> 2 then raise exception 'rb_bad_choice'; end if;
            perform public.rb_pay(p.id, -r.bet, 0, 'bet', 'blackjack');
            spent := r.bet; stake := stake + r.bet;
            me := me || deck[1]; deck := deck[2:];
            done := true;
        elsif action = 'hit' then
            me := me || deck[1]; deck := deck[2:];
            if public.rb_bj_total(me) >= 21 then done := true; end if;
        elsif action = 'stand' then
            done := true;
        else
            raise exception 'rb_bad_choice';
        end if;
    end if;
    if done then
        if action = 'natural' then
            if public.rb_bj_total(me) = 21 and public.rb_bj_total(dealer) = 21 then outcome := 'push'; pay := stake;
            elsif public.rb_bj_total(me) = 21 then outcome := 'blackjack'; pay := floor(stake * 2.5)::int;
            else outcome := 'lose'; end if;
        elsif public.rb_bj_total(me) > 21 then
            outcome := 'bust';
        else
            while public.rb_bj_total(dealer) < 17 loop dealer := dealer || deck[1]; deck := deck[2:]; end loop;
            if public.rb_bj_total(dealer) > 21 or public.rb_bj_total(me) > public.rb_bj_total(dealer) then
                outcome := 'win'; pay := stake * 2;
            elsif public.rb_bj_total(me) = public.rb_bj_total(dealer) then outcome := 'push'; pay := stake;
            else outcome := 'lose'; end if;
        end if;
        pay := public.rb_win(p.id, pay, 'blackjack');
    end if;
    update public.rb_rounds set open = not done, paid = pay, secret = jsonb_build_object('deck', to_jsonb(deck),
           'me', to_jsonb(me), 'dealer', to_jsonb(dealer), 'stake', stake) where id = r.id;
    return jsonb_build_object('open', not done, 'me', to_jsonb(me), 'total', public.rb_bj_total(me), 'stake', stake,
        'dealer', case when done then to_jsonb(dealer) else to_jsonb(dealer[1:1]) end,       -- the second card stays hidden
        'dealer_total', case when done then public.rb_bj_total(dealer) end,
        'outcome', outcome, 'paid', pay, 'coins', p.coins - spent + pay);
end $$;

-- ---------------------------------------------------------------- who may call what
do $$ declare f text; begin
    foreach f in array array['rb_rand()', 'rb_pick_badge(integer, boolean)', 'rb_roll(integer[])',
        'rb_open_case(text, text)', 'rb_daily_case()', 'rb_spin()', 'rb_spin_collect()', 'rb_timers()',
        'rb_bet(public.profiles, integer, text)', 'rb_win(uuid, numeric, text)', 'rb_slots(integer, text)',
        'rb_plinko(integer, integer, text)', 'rb_dice(integer, integer, text)', 'rb_mines_mult(integer, integer)',
        'rb_mines(text, integer)', 'rb_rocket(text, integer)', 'rb_bj_total(integer[])', 'rb_blackjack(text, integer)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_open_case(text, text)', 'rb_daily_case()', 'rb_spin()', 'rb_spin_collect()',
        'rb_timers()', 'rb_slots(integer, text)', 'rb_plinko(integer, integer, text)', 'rb_dice(integer, integer, text)',
        'rb_mines(text, integer)', 'rb_rocket(text, integer)', 'rb_blackjack(text, integer)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;
