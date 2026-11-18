-- ================================================================ Rubenium 4.3 (build 2026.11.18.20)
-- XP rework, coinflip bots sized to the players online, Slots, evened-out cases, Mini Golf solo, Wave Rush,
-- the pawn shop and quests that count every game. Transactional; 026_down.sql undoes it.
begin;

-- ================================================================ XP 4.3: earned, not farmed
-- Lost casino rounds give nothing; a win gives a little (1 to 5 by profit). Every other source gives much less, the
-- daily caps are lower, and XP coupons are worth far less. The level curve is unchanged: nobody loses a level.
create or replace function public.rb_xp_cap(src text) returns integer
language sql immutable set search_path = '' as $$
    select case src when 'casino' then 120 when 'minigames' then 300 when 'cases' then 40 when 'golf' then 150
                    when 'coinflip' then 60 when 'trading' then 48 when 'online' then 120 when 'wheel' then 20
                    when 'quests' then 200 when 'wave' then 150 else 100000 end $$;

create or replace function public.rb_rounds_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
declare amt integer := 0; src text;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;               -- counted once, when it ends
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo',
                    'slots') then
        if new.bet < 10 or coalesce(new.paid, 0) <= new.bet then return new; end if;     -- 4.3: a loss gives nothing
        src := 'casino'; amt := least(5, 1 + (new.paid - new.bet) / 300);
    elsif new.game in ('mini', 'park', 'memory', 'tap', 'g2048', 'sweeper', 'blocks', 'wave', 'golf_solo') then
        if coalesce(new.paid, 0) <= 0 then return new; end if;
        src := case when new.game = 'wave' then 'wave' else 'minigames' end;
        amt := least(12, 3 + new.paid / 30);
    elsif new.game like 'case:%' then
        src := 'cases'; amt := 2;
    elsif new.game in ('spin', 'scratch') then
        src := 'wheel'; amt := 4;
    else
        return new;
    end if;
    perform public.rb_xp_add(new.owner, amt, src, new.game, true);
    return new;
end $$;

create or replace function public.rb_golf_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.state = 'done' and old.state = 'live' and new.b is not null and (new.why <> 'forfeit' or new.hole > 1) then
        perform public.rb_xp_add(new.a, 12 + case when new.winner = new.a then 10 else 0 end, 'golf', new.id::text, true);
        perform public.rb_xp_add(new.b, 12 + case when new.winner = new.b then 10 else 0 end, 'golf', new.id::text, true);
    end if;
    return new;
end $$;

create or replace function public.rb_trade_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.state = 'done' and old.state <> 'done' then
        perform public.rb_xp_add(new.a, 8, 'trading', new.id::text, true);
        perform public.rb_xp_add(new.b, 8, 'trading', new.id::text, true);
    end if;
    return new;
end $$;

create or replace function public.rb_claim_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_xp_add(new.owner, case when tg_table_name = 'rb_set_claims' then 80 else 25 end, 'quests', tg_table_name, true);
    return new;
end $$;

-- coinflip: only the winner gets XP (10); online time: 5 every 10 minutes (was 10). Changed inside the functions.
do $$
declare fn regprocedure; src text; out_ text;
begin
    fn := 'public.rb_flip_settle(uuid)'::regprocedure;
    src := replace(pg_get_functiondef(fn), chr(13), '');
    out_ := replace(src, 'perform public.rb_xp_add(human_w, 25, ''coinflip''', 'perform public.rb_xp_add(human_w, 10, ''coinflip''');
    out_ := replace(out_, 'perform public.rb_xp_add(human_l, 25, ''coinflip''', 'perform public.rb_xp_add(human_l, 0, ''coinflip''');
    if out_ <> src then execute out_; end if;
    fn := 'public.rb_heartbeat(text)'::regprocedure;
    src := replace(pg_get_functiondef(fn), chr(13), '');
    out_ := replace(src, 'perform public.rb_xp_add(p.id, 10, ''online''', 'perform public.rb_xp_add(p.id, 5, ''online''');
    if out_ <> src then execute out_; end if;
    if position('rb_xp_add(human_w, 10, ''coinflip''' in pg_get_functiondef('public.rb_flip_settle(uuid)'::regprocedure)) = 0
       or position('rb_xp_add(p.id, 5, ''online''' in pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure)) = 0 then
        raise exception 'xp change did not apply';
    end if;
end $$;

update public.rb_catalog set value = case id when 'coupon:common' then 40 when 'coupon:uncommon' then 100
                                             when 'coupon:rare' then 250 when 'coupon:epic' then 600 end
 where id in ('coupon:common', 'coupon:uncommon', 'coupon:rare', 'coupon:epic');
insert into public.rb_config (key, value) values ('xp_day_cap', 1000)
    on conflict (key) do update set value = excluded.value;

-- ================================================================ Coinflip bots 4.3: sized to the people playing
-- Six bots in three tiers (two low, two middle, two high). What they put up follows the wealth (coins + items) of the
-- players online: with a few online, each offer is sized to one of them; with a crowd, to the server's average. There
-- are always 5 to 10 bot flips open, never a mythic, and never more than flip_bot_max coins.
insert into public.rb_config (key, value) values ('bot_flips_min', 5), ('flip_crowd', 4), ('flip_bot_max', 2000000)
on conflict (key) do update set value = excluded.value;
update public.rb_config set value = 10 where key = 'bot_flips_max';

-- one player's wealth: coins plus what their items are worth
create or replace function public.rb_wealth(who uuid) returns bigint
language sql stable security definer set search_path = '' as $$
    select coalesce((select p.coins from public.profiles p where p.id = who), 0)
         + coalesce((select sum(public.rb_worth(i.item)) from public.rb_items i where i.owner = who), 0)::bigint $$;

-- the wealth bot offers are sized to. A crowd online: their average (taken on a log scale, so one very rich player
-- doesn't drag every offer up). A few online: one of them at random. Nobody: the week's active players.
create or replace function public.rb_flip_wealth() returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare n integer; w double precision;
begin
    select count(*) into n from public.profiles where not bot and not banned and last_beat > now() - interval '5 minutes';
    if n >= coalesce(public.rb_cfg('flip_crowd'), 4)::int then
        select exp(avg(ln(greatest(public.rb_wealth(id), 500)))) into w
          from public.profiles where not bot and not banned and last_beat > now() - interval '5 minutes';
    elsif n > 0 then
        select public.rb_wealth(id) into w from public.profiles
         where not bot and not banned and last_beat > now() - interval '5 minutes' order by random() limit 1;
    else
        select exp(avg(ln(greatest(public.rb_wealth(id), 500)))) into w
          from public.profiles where not bot and not banned and last_beat > now() - interval '7 days';
    end if;
    return greatest(5000, least(coalesce(w, 20000), 50000000))::bigint;
end $$;

-- the bots, each with its share of that wealth (lo, hi as fractions)
drop function if exists public.rb_flip_bots();
create function public.rb_flip_bots() returns table (name text, tier text, lo double precision, hi double precision)
language sql immutable set search_path = '' as $$
    values ('Pixel', 'low', 0.003::double precision, 0.012::double precision), ('Milo', 'low', 0.006, 0.02),
           ('Nova', 'mid', 0.02, 0.05), ('Juno', 'mid', 0.03, 0.08),
           ('Vega', 'high', 0.08, 0.16), ('Atlas', 'high', 0.12, 0.25) $$;

-- the bot that fits a value best (used when you play a bot: it is the one who'd bet about what you bet)
create or replace function public.rb_flip_bot_for(val bigint) returns text
language sql volatile security definer set search_path = '' as $$
    with w as (select greatest(val, 1)::double precision / public.rb_flip_wealth() as f)
    select b.name from public.rb_flip_bots() b, w
     order by case when w.f between b.lo and b.hi then 0 else 1 end,
              least(abs(ln(w.f / b.lo)), abs(ln(w.f / b.hi))), random()
     limit 1 $$;

-- items for a bot: never a mythic unless it must match a mythic-sized stake
create or replace function public.rb_flip_bot_items(target bigint, n integer) returns text[]
language plpgsql volatile security definer set search_path = '' as $$
declare res text[] := '{}'; left_ bigint := target; per bigint; pick text; i integer;
begin
    n := greatest(1, least(6, n));
    for i in 1..n loop
        per := left_ / (n - i + 1);
        exit when per < 40;
        select c.id into pick from public.rb_catalog c
         where c.tradeable and not c.limited and c.kind in ('badge', 'ball', 'line', 'font', 'banner', 'frame', 'theme')
           and (c.rarity <> 'exotic' or target >= 8000000)
           and coalesce(c.worth, 0) between greatest(5, per * 0.4) and least(per * 1.6, left_ * 1.08)
           and not (c.kind <> 'badge' and c.id = any (res))
         order by case when i = n then abs(c.worth - left_)::double precision / greatest(left_, 1)
                       else abs(ln(c.worth::double precision / per)) + random() * 0.35 end
         limit 1;
        exit when pick is null;
        res := res || pick;
        left_ := left_ - public.rb_worth(pick);
    end loop;
    return res;
end $$;

-- a bot offer. No value given: a random bot, sized to the wealth above.
create or replace function public.rb_flip_bot_offer(val bigint, admin_made boolean, bot text, side text, minutes integer,
                                                    items text[]) returns uuid
language plpgsql volatile security definer set search_path = '' as $$
declare whats text[]; total bigint; fid uuid; b record; base bigint; top bigint;
begin
    top := coalesce(public.rb_cfg('flip_bot_max'), 2000000)::bigint;
    if items is not null and array_length(items, 1) > 0 then
        whats := items;
    else
        if val is null then
            select * into b from public.rb_flip_bots() x where x.name = bot;
            if not found then select * into b from public.rb_flip_bots() order by random() limit 1; end if;
            bot := b.name;
            base := public.rb_flip_wealth();
            val := floor(exp(ln(base * b.lo) + random() * (ln(base * b.hi) - ln(base * b.lo))));
            val := greatest(100, least(val, top));
        end if;
        whats := public.rb_flip_bot_fit(val, floor(val * 0.85)::bigint, ceil(val * 1.15)::bigint);
    end if;
    if coalesce(array_length(whats, 1), 0) = 0 then return null; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    insert into public.rb_flips (a, a_side, state, a_what, a_value, bot_side, bot_name, admin_offer, expires_min)
        values (null, coalesce(side, case when random() < 0.5 then 'black' else 'white' end), 'open', whats, total, 'a',
                coalesce(bot, public.rb_flip_bot_for(total)), admin_made,
                coalesce(minutes, 25 + floor(random() * 21)::int))
        returning id into fid;
    return fid;
end $$;

-- every minute: clear expired bot flips, keep 5 to 10 open (the target drifts every 20 minutes), one tier at a time
create or replace function public.rb_flip_bots_tick() returns void
language plpgsql volatile security definer set search_path = '' as $$
declare lo_ integer; hi_ integer; tgt integer; cur integer; fid uuid; tier_ text; tries integer := 0;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    for fid in select id from public.rb_flips where bot_side = 'a' and state in ('open', 'joined', 'locked') loop
        perform public.rb_flip_tick(fid);
    end loop;
    lo_ := coalesce(public.rb_cfg('bot_flips_min'), 5)::int;
    hi_ := greatest(lo_, coalesce(public.rb_cfg('bot_flips_max'), 10)::int);
    tgt := lo_ + abs(hashtext('flipbots' || floor(extract(epoch from now()) / 1200)::text)) % (hi_ - lo_ + 1);
    loop
        select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state = 'open';
        exit when cur >= tgt or tries >= 6;
        exit when cur >= lo_ and random() > 0.4;              -- above the minimum, top up slowly
        tries := tries + 1;
        -- the tier with the fewest open offers goes next, so low, middle and high are all there
        select t.tier into tier_ from (values ('low'), ('mid'), ('high')) t(tier)
         order by (select count(*) from public.rb_flips f join public.rb_flip_bots() b on b.name = f.bot_name
                    where f.bot_side = 'a' and not f.admin_offer and f.state = 'open' and b.tier = t.tier), random()
         limit 1;
        perform public.rb_flip_bot_offer(null, false,
                    (select b.name from public.rb_flip_bots() b where b.tier = tier_ order by random() limit 1), null, null, null);
    end loop;
end $$;

-- the old offers (some put up mythics) go now; the tick refills with the new ones
do $$
declare f public.rb_flips%rowtype;
begin
    for f in select * from public.rb_flips where bot_side = 'a' and not admin_offer and state = 'open' loop
        perform public.rb_flip_free(f, 'expired');
    end loop;
end $$;

revoke all on function public.rb_wealth(uuid), public.rb_flip_wealth(), public.rb_flip_bots() from public, anon, authenticated;

-- ================================================================ Slots (4.3): three reels, one table of prizes
-- Each reel: cherry 6, lemon 5, bell 4, seven 3, gem 2 (out of 20). Three of a kind pays the table; two bells, two
-- sevens or two gems pay a little. Returns 96.6% over time, a win about 1 spin in 4.
create or replace function public.rb_slots(bet integer, req text) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; reels text[] := '{}'; r double precision; s text; i integer;
        mult numeric := 0; pay integer := 0; pair text;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_bet(p, bet, 'slots');
    for i in 1..3 loop
        r := public.rb_rand() * 20;
        s := case when r < 6 then 'cherry' when r < 11 then 'lemon' when r < 15 then 'bell' when r < 18 then 'seven'
                  else 'gem' end;
        reels := reels || s;
    end loop;
    if reels[1] = reels[2] and reels[2] = reels[3] then
        mult := case reels[1] when 'cherry' then 5 when 'lemon' then 8 when 'bell' then 15 when 'seven' then 30 else 70 end;
    else
        pair := case when reels[1] in (reels[2], reels[3]) then reels[1] when reels[2] = reels[3] then reels[2] end;
        mult := case pair when 'bell' then 2 when 'seven' then 2 when 'gem' then 4 else 0 end;
    end if;
    if mult > 0 then pay := public.rb_win(p.id, bet * mult, 'slots'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'slots', bet, jsonb_build_object('reels', reels), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('reels', reels, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins - bet + pay));
end $$;
revoke all on function public.rb_slots(integer, text) from public, anon;
grant execute on function public.rb_slots(integer, text) to authenticated;

-- ================================================================ Cases 4.3: evened out
-- What a case gives back (coins, plus 35% of item worth, the quick-sell rate) now falls smoothly with the price:
-- coin cases 1.6x (Pocket) down to 0.97x (Royal), rare badge cases 1.2x (Gamble) down to 0.85x (Mythic Case).
-- Mythic chances are unchanged. Style cases are unchanged.
update public.rb_cases set odds = '{8894,904,176,23,3,0}', coin_min = 30, coin_max = 160 where id = 'pocket';
update public.rb_cases set odds = '{8379,1318,270,30,3,0}', coin_min = 70, coin_max = 340 where id = 'starter';
update public.rb_cases set odds = '{7474,1894,541,77,13,1}', coin_min = 175, coin_max = 960 where id = 'standard';
update public.rb_cases set odds = '{6839,2141,836,143,40,1}', coin_min = 485, coin_max = 2605 where id = 'premium';
update public.rb_cases set odds = '{6168,2172,1278,281,98,3}', coin_min = 1360, coin_max = 8965 where id = 'titan';
update public.rb_cases set odds = '{7788,0,1507,578,124,3}', coin_min = 45, coin_max = 435 where id = 'gamble';
update public.rb_cases set odds = '{4893,3405,1354,294,54,0}', coin_min = 245, coin_max = 2015 where id = 'painter';
update public.rb_cases set odds = '{2968,0,3730,2451,836,15}', coin_min = 1320, coin_max = 10540 where id = 'vault';
update public.rb_cases set odds = '{2316,0,0,5339,2285,60}', coin_min = 3970, coin_max = 31435 where id = 'mythic';
update public.rb_cases set odds = '{6383,1938,1163,388,124,4}', coin_min = 2570, coin_max = 15100 where id = 'elite';
update public.rb_cases set odds = '{6208,0,2014,1343,425,10}', coin_min = 11400, coin_max = 62700 where id = 'royal';
update public.rb_cases set odds = '{5405,0,2096,1703,766,30}', coin_min = 35, coin_max = 260 where id = 'shiny';
update public.rb_cases set odds = '{8353,1281,302,55,9,0}', coin_min = 70, coin_max = 445 where id = 'lucky';
update public.rb_cases set odds = '{1885,0,4064,2921,1080,50}', coin_min = 2955, coin_max = 11370 where id = 'cosmos';

-- ================================================================ Mini Golf solo (4.3): play alone, earn coins
-- 5 holes, no bet, no opponent, no turn clock. Each hole pays by strokes (1: 60, 2: 35, 3: 20, 4: 10, 5: 5, 6: 0),
-- paid at the end like every minigame: the same 2-hour window cap and the same tapering when it is played a lot
-- (rb_game_pay). A shot can't come sooner than 0.7 s after the last one, and a round shorter than 15 s pays nothing.
create table if not exists public.rb_golf_solo (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    holes integer[] not null,
    hole integer not null default 1,
    strokes integer[] not null,
    seq integer not null default 0,
    pos jsonb,
    state text not null default 'live',
    paid integer not null default 0,
    at timestamptz not null default now(),
    last_at timestamptz not null default now(),
    done_at timestamptz
);
create index if not exists rb_golf_solo_owner on public.rb_golf_solo (owner, state);
alter table public.rb_golf_solo enable row level security;
revoke all on public.rb_golf_solo from anon, authenticated;

create or replace function public.rb_golf_solo_pay(s integer) returns integer
language sql immutable set search_path = '' as $$
    select case s when 1 then 60 when 2 then 35 when 3 then 20 when 4 then 10 when 5 then 5 else 0 end $$;

create or replace function public.rb_golf_solo_json(g public.rb_golf_solo) returns jsonb
language sql stable security definer set search_path = '' as $$
    select jsonb_build_object('id', g.id, 'solo', true, 'state', g.state, 'me', 'a', 'a',
        (select username from public.profiles where id = g.owner), 'b', null, 'bet', 0, 'holes', g.holes, 'hole', g.hole,
        'seq', g.seq, 'n_holes', array_length(g.holes, 1), 'turn', 'a', 'left', 0, 'pa', g.pos, 'pb', null,
        'a_in', false, 'b_in', true, 'a_strokes', g.strokes, 'b_strokes', null, 'shots', '[]'::jsonb, 'paid', g.paid,
        'pays', jsonb_build_array(60, 35, 20, 10, 5, 0)) $$;

create or replace function public.rb_golf_solo_start() returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; g public.rb_golf_solo%rowtype; hs integer[];
begin
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    update public.rb_golf_solo set state = 'quit', done_at = now() where owner = p.id and state = 'live';
    hs := public.rb_golf_pick();
    insert into public.rb_golf_solo (owner, holes, strokes) values (p.id, hs, array_fill(0, array[array_length(hs, 1)]))
        returning * into g;
    return public.rb_golf_solo_json(g);
end $$;

create or replace function public.rb_golf_solo_shot(gid uuid, n integer, x double precision, y double precision,
                                                    holed boolean) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf_solo%rowtype; s integer; base integer := 0; pay integer := 0; i integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    select * into g from public.rb_golf_solo where id = gid and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if n < g.seq or g.state <> 'live' then return public.rb_golf_solo_json(g); end if;     -- already counted
    if n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if x is null or y is null or x not between 0 and 1 or y not between 0 and 0.62 then raise exception 'rb_bad_choice'; end if;
    if now() - g.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    s := g.strokes[g.hole] + 1;
    g.strokes[g.hole] := s;
    g.seq := g.seq + 1;
    g.last_at := now();
    if coalesce(holed, false) or s >= 6 then
        if g.hole >= array_length(g.holes, 1) then
            g.state := 'done';
            g.done_at := now();
            g.pos := null;
            if now() - g.at >= interval '15 seconds' then
                for i in 1..array_length(g.strokes, 1) loop
                    base := base + public.rb_golf_solo_pay(g.strokes[i]);
                end loop;
            end if;
            pay := public.rb_game_pay(me, 'golf_solo', base);
            if pay > 0 then perform public.rb_pay(me, pay, 0, 'minigame', 'golf_solo'); end if;
            g.paid := pay;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (me, 'golf_solo', 0, jsonb_build_object('strokes', g.strokes, 'solo', g.id), false, pay);
        else
            g.hole := g.hole + 1;
            g.pos := null;
        end if;
    else
        g.pos := jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4));
    end if;
    update public.rb_golf_solo set strokes = g.strokes, seq = g.seq, last_at = g.last_at, state = g.state, hole = g.hole,
           pos = g.pos, paid = g.paid, done_at = g.done_at where id = g.id;
    return public.rb_golf_solo_json(g);
end $$;

create or replace function public.rb_golf_solo_state(gid uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare g public.rb_golf_solo%rowtype;
begin
    select * into g from public.rb_golf_solo where id = gid and owner = auth.uid();
    if not found then raise exception 'rb_duel_gone'; end if;
    return public.rb_golf_solo_json(g);
end $$;

create or replace function public.rb_golf_solo_quit(gid uuid) returns void
language sql volatile security definer set search_path = '' as $$
    update public.rb_golf_solo set state = 'quit', done_at = now() where id = gid and owner = auth.uid() and state = 'live' $$;

revoke all on function public.rb_golf_solo_pay(integer), public.rb_golf_solo_json(public.rb_golf_solo) from public, anon, authenticated;
revoke all on function public.rb_golf_solo_start(), public.rb_golf_solo_shot(uuid, integer, double precision, double precision, boolean),
    public.rb_golf_solo_state(uuid), public.rb_golf_solo_quit(uuid) from public, anon;
grant execute on function public.rb_golf_solo_start(), public.rb_golf_solo_shot(uuid, integer, double precision, double precision, boolean),
    public.rb_golf_solo_state(uuid), public.rb_golf_solo_quit(uuid) to authenticated;

-- ================================================================ Wave Rush (4.3): the server's copy of the run
-- Exactly the client's maths (wave.py), in whole numbers: the course comes from the seed, the run from the ticks
-- where the player pressed or let go. The server replays every run and pays for the distance it finds, never for a
-- distance the client claims.
create or replace function public.rb_wave_sim(seed bigint, toggles integer[], max_ticks integer)
returns table (ticks integer, x integer)
language plpgsql immutable set search_path = '' as $$
declare
    k_vx constant integer := 12; k_r constant integer := 10; k_h constant integer := 1000; k_sw constant integer := 48;
    s bigint := seed & 2147483647;
    sx0 integer[] := array[0]; sln integer[] := array[900]; sc0 integer[] := array[500]; ssl integer[] := array[0];
    sgp integer[] := array[420]; sfrom integer[] := array[1]; sn integer[] := array[0];
    px integer[] := '{}'; pside integer[] := '{}';
    x_end integer := 900; c_end integer := 500;
    tg integer[]; k integer := 1; held boolean := true; t integer; px_ integer := 0; y integer := 500; i integer := 1;
    d integer; f integer; gap integer; r integer; p_zig integer; p_flat integer; ln_ integer; n integer; side integer;
    legs integer; leg integer; slope integer; room integer; lo integer; hi integer; j integer;
    c integer; half integer; top integer; bot integer; hh integer; dx integer; q integer;
begin
    select coalesce(array_agg(v order by v), '{}') into tg
      from (select distinct v from unnest(coalesce(toggles, '{}')) v where v > 0 and v < max_ticks) z;
    for t in 1..max_ticks loop
        while k <= coalesce(array_length(tg, 1), 0) and tg[k] <= t loop
            held := not held; k := k + 1;
        end loop;
        px_ := px_ + k_vx;
        y := y + case when held then -k_vx else k_vx end;
        -- grow the course ahead of the wave
        while x_end <= px_ + 4000 loop
            d := least(1000, x_end / 150);
            f := d * (d + 1000) / 2000;
            gap := 420 - 300 * f / 1000;
            gap := gap - gap % 2;
            lo := gap / 2 + 40; hi := k_h - gap / 2 - 40;
            if c_end < lo then                                   -- pull the centre back in first
                sx0 := sx0 || x_end; sln := sln || (lo - c_end); sc0 := sc0 || c_end; ssl := ssl || 1; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + (lo - c_end); c_end := lo;
            elsif c_end > hi then
                sx0 := sx0 || x_end; sln := sln || (c_end - hi); sc0 := sc0 || c_end; ssl := ssl || -1; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + (c_end - hi); c_end := hi;
            end if;
            s := (s * 1103515245 + 12345) & 2147483647; r := (s >> 8) % 1000;
            p_zig := 200 + 400 * d / 1000;
            p_flat := 450 - 200 * d / 1000;
            if r < p_flat then
                s := (s * 1103515245 + 12345) & 2147483647; ln_ := 300 + (s >> 8) % 500;
                if d >= 50 then
                    s := (s * 1103515245 + 12345) & 2147483647; n := (s >> 8) % (2 + 2 * d / 1000);
                else
                    n := 0;
                end if;
                s := (s * 1103515245 + 12345) & 2147483647; side := (s >> 8) % 2;
                sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || 0; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || n;
                for j in 0..n - 1 loop
                    px := px || (x_end + ln_ * (j + 1) / (n + 1)); pside := pside || side;
                    side := 1 - side;
                end loop;
                x_end := x_end + ln_;
            elsif r < p_flat + p_zig then
                s := (s * 1103515245 + 12345) & 2147483647; legs := 3 + (s >> 8) % (4 + 4 * d / 1000);
                s := (s * 1103515245 + 12345) & 2147483647; leg := greatest(100, 320 - 220 * d / 1000 + (s >> 8) % 60);
                slope := case when (hi - c_end) >= (c_end - lo) then 1 else -1 end;
                for j in 1..legs loop
                    room := case when slope > 0 then hi - c_end else c_end - lo end;
                    if room < 60 then
                        slope := -slope;
                        room := case when slope > 0 then hi - c_end else c_end - lo end;
                    end if;
                    ln_ := greatest(40, least(leg, room));
                    sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || slope; sgp := sgp || gap;
                    sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                    x_end := x_end + ln_; c_end := c_end + slope * ln_;
                    slope := -slope;
                end loop;
            else
                s := (s * 1103515245 + 12345) & 2147483647;
                slope := case when (s >> 8) % 2 = 1 then 1 else -1 end;
                room := case when slope > 0 then hi - c_end else c_end - lo end;
                if room < 120 then
                    slope := -slope;
                    room := case when slope > 0 then hi - c_end else c_end - lo end;
                end if;
                s := (s * 1103515245 + 12345) & 2147483647;
                ln_ := greatest(60, least(150 + (s >> 8) % 400, room));
                sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || slope; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + ln_; c_end := c_end + slope * ln_;
            end if;
        end loop;
        while px_ >= sx0[i] + sln[i] loop i := i + 1; end loop;
        c := sc0[i] + ssl[i] * (px_ - sx0[i]);
        half := sgp[i] / 2;
        top := c - half; bot := c + half;
        if sn[i] > 0 then
            hh := sgp[i] * 38 / 100;
            for j in sfrom[i]..sfrom[i] + sn[i] - 1 loop
                dx := abs(px_ - px[j]);
                if dx < k_sw then
                    q := hh * (k_sw - dx) / k_sw;
                    if pside[j] = 0 then top := greatest(top, c - half + q); else bot := least(bot, c + half - q); end if;
                end if;
            end loop;
        end if;
        if y - k_r < top or y + k_r > bot then
            ticks := t; x := px_; return next; return;
        end if;
    end loop;
    ticks := max_ticks; x := px_; return next;
end $$;
revoke all on function public.rb_wave_sim(bigint, integer[], integer) from public, anon, authenticated;

-- ================================================================ Wave Rush (4.3): solo runs and 1 v 1 duels
-- Solo: coins for the distance the server replays (from 30 m), paid like every mini game (the 2-hour cap and the
-- tapering), XP under its own daily cap. Duel: both players get the same course at the same time; the longer run
-- wins both bets (5% fee), or it is just for fun with no bet. A run can't end sooner than the time it takes to play.
insert into public.rb_config (key, value) values ('wave_duel_min', 8) on conflict (key) do nothing;
insert into public.rb_features (name, parent) values ('wave', 'online') on conflict (name) do nothing;

create table if not exists public.rb_wave_runs (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    seed bigint not null,
    duel uuid,
    state text not null default 'live',
    started_at timestamptz not null default now(),
    ticks integer not null default 0,
    dist integer not null default 0,
    live_x integer not null default 0,
    paid integer not null default 0,
    done_at timestamptz
);
create index if not exists rb_wave_runs_owner on public.rb_wave_runs (owner, state);
create index if not exists rb_wave_runs_duel on public.rb_wave_runs (duel);
alter table public.rb_wave_runs enable row level security;
revoke all on public.rb_wave_runs from anon, authenticated;

create table if not exists public.rb_wave_duels (
    id uuid primary key default gen_random_uuid(),
    a uuid not null references public.profiles (id) on delete cascade,
    b uuid references public.profiles (id) on delete cascade,
    bet integer not null default 0,
    seed bigint not null,
    state text not null default 'open',
    a_run uuid,
    b_run uuid,
    winner uuid,
    why text,
    at timestamptz not null default now(),
    live_at timestamptz,
    done_at timestamptz
);
create index if not exists rb_wave_duels_a on public.rb_wave_duels (a, state);
create index if not exists rb_wave_duels_b on public.rb_wave_duels (b, state);
create index if not exists rb_wave_duels_state on public.rb_wave_duels (state);
alter table public.rb_wave_duels enable row level security;
revoke all on public.rb_wave_duels from anon, authenticated;

-- coins for a solo distance (x in course units, 100 a metre)
create or replace function public.rb_wave_pay_for(x integer) returns integer
language sql immutable set search_path = '' as $$
    select case when x < 3000 then 0 else floor(power(x / 1000.0, 1.35))::int end $$;

create or replace function public.rb_wave_best(who uuid) returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce(max(dist), 0) from public.rb_wave_runs where owner = who and duel is null and state = 'done' $$;

create or replace function public.rb_wave_solo() returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; rid uuid; sd bigint;
begin
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    update public.rb_wave_runs set state = 'quit', done_at = now() where owner = p.id and duel is null and state = 'live';
    sd := floor(public.rb_rand() * 2147483647)::bigint;
    insert into public.rb_wave_runs (owner, seed) values (p.id, sd) returning id into rid;
    return jsonb_build_object('run', rid, 'seed', sd, 'best', public.rb_wave_best(p.id));
end $$;

-- the end of a duel: the longer run wins
create or replace function public.rb_wave_settle(did uuid, forfeit uuid) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare w public.rb_wave_duels%rowtype; da integer; db integer; win uuid; pot integer;
begin
    select * into w from public.rb_wave_duels where id = did for update;
    if not found or w.state <> 'live' then return; end if;
    select coalesce(case when state = 'done' then dist end, 0) into da from public.rb_wave_runs where id = w.a_run;
    select coalesce(case when state = 'done' then dist end, 0) into db from public.rb_wave_runs where id = w.b_run;
    win := case when forfeit is not null then (case when forfeit = w.a then w.b else w.a end)
                when da > db then w.a when db > da then w.b end;
    update public.rb_wave_runs set state = 'done', done_at = now() where id in (w.a_run, w.b_run) and state = 'live';
    update public.rb_wave_duels set state = 'done', winner = win, done_at = now(),
           why = case when forfeit is not null then 'forfeit' when win is null then 'draw' else 'distance' end where id = w.id;
    if w.bet > 0 then
        if win is null then
            perform public.rb_pay(w.a, w.bet, 0, 'wave_back', w.id::text);
            perform public.rb_pay(w.b, w.bet, 0, 'wave_back', w.id::text);
        else
            pot := floor(w.bet * 2 * (1 - coalesce(public.rb_cfg('golf_fee'), 0.05)))::int;
            perform public.rb_pay(win, pot, 0, 'wave_win', w.id::text);
        end if;
    end if;
    perform public.rb_notice(x, 'wave_end', jsonb_build_object('id', w.id, 'won', win = x, 'draw', win is null,
                             'other', (select username from public.profiles where id = case when x = w.a then w.b else w.a end)))
       from unnest(array[w.a, w.b]) x;
end $$;

-- lobbies close after lobby_min; a live duel ends after wave_duel_min (runs not finished by then count as 0 m)
create or replace function public.rb_wave_tick(did uuid) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare w public.rb_wave_duels%rowtype;
begin
    select * into w from public.rb_wave_duels where id = did for update;
    if not found then return; end if;
    if w.state = 'open' and now() - w.at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) then
        update public.rb_wave_duels set state = 'cancelled', why = 'expired', done_at = now() where id = w.id;
        if w.bet > 0 then perform public.rb_pay(w.a, w.bet, 0, 'wave_back', w.id::text); end if;
    elsif w.state = 'live' and now() - w.live_at > make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int) then
        perform public.rb_wave_settle(w.id, null);
    end if;
end $$;

create or replace function public.rb_wave_finish(run uuid, toggles integer[], ticks integer) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype; sim record; need double precision; base integer;
        pay integer := 0; best integer; w public.rb_wave_duels%rowtype; other public.rb_wave_runs%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('wave');
    select * into r from public.rb_wave_runs where id = run and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if r.state <> 'live' then
        return jsonb_build_object('dist', r.dist, 'paid', r.paid, 'best', public.rb_wave_best(me), 'again', true);
    end if;
    if ticks is null or ticks < 1 or coalesce(array_length(toggles, 1), 0) > 30000 then raise exception 'rb_bad_choice'; end if;
    select * into sim from public.rb_wave_sim(r.seed, toggles, least(54000, ticks + 2));
    need := sim.ticks / 60.0 * 0.9 - 1.5;                      -- the run takes real time to play
    if extract(epoch from now() - r.started_at) < need then raise exception 'rb_too_fast'; end if;
    best := public.rb_wave_best(me);
    if r.duel is null then
        base := public.rb_wave_pay_for(sim.x);
        pay := public.rb_game_pay(me, 'wave', base);
        if pay > 0 then perform public.rb_pay(me, pay, 0, 'minigame', 'wave'); end if;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (me, 'wave', 0, jsonb_build_object('x', sim.x, 'ticks', sim.ticks, 'run', r.id), false, pay);
    end if;
    update public.rb_wave_runs set state = 'done', ticks = sim.ticks, dist = sim.x, live_x = sim.x, paid = pay,
           done_at = now() where id = r.id;
    if r.duel is not null then
        select * into w from public.rb_wave_duels where id = r.duel for update;
        select * into other from public.rb_wave_runs where id = case when w.a_run = r.id then w.b_run else w.a_run end;
        if found and other.state = 'done' then perform public.rb_wave_settle(w.id, null); end if;
    end if;
    return jsonb_build_object('dist', sim.x, 'ticks', sim.ticks, 'paid', pay, 'best', greatest(best, sim.x),
                              'record', r.duel is null and sim.x > best and best > 0);
end $$;

-- a duel: what both runs are at (shown live), and how it ended
create or replace function public.rb_wave_duel_json(w public.rb_wave_duels, me uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
    select jsonb_build_object('id', w.id, 'state', w.state, 'bet', w.bet, 'seed', w.seed,
        'me', case when me = w.a then 'a' else 'b' end,
        'a', (select username from public.profiles where id = w.a), 'b', (select username from public.profiles where id = w.b),
        'run', case when me = w.a then w.a_run else w.b_run end,
        'a_x', ra.live_x, 'b_x', rb.live_x, 'a_done', ra.state = 'done', 'b_done', rb.state = 'done',
        'starts_in', case when w.live_at is not null then greatest(0, extract(epoch from (w.live_at + interval '4 seconds' - now())))::numeric(5, 1) end,
        'left', case when w.state = 'live' then greatest(0, ceil(extract(epoch from (w.live_at
                 + make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int) - now()))))::int end,
        'winner', case when w.winner = w.a then 'a' when w.winner = w.b then 'b' end, 'why', w.why)
      from (select 1) one
      left join public.rb_wave_runs ra on ra.id = w.a_run
      left join public.rb_wave_runs rb on rb.id = w.b_run $$;

create or replace function public.rb_wave_state(did uuid) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); w public.rb_wave_duels%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_wave_tick(did);
    select * into w from public.rb_wave_duels where id = did;
    if not found or (w.a <> me and w.b is distinct from me) then raise exception 'rb_duel_gone'; end if;
    return public.rb_wave_duel_json(w, me);
end $$;

-- every second while a duel run is on: how far you are (for the other player's screen only; never paid)
create or replace function public.rb_wave_ping(run uuid, x integer) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype;
begin
    select * into r from public.rb_wave_runs where id = run and owner = me;
    if not found or r.duel is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        update public.rb_wave_runs set live_x = greatest(live_x, least(coalesce(x, 0),
               floor(greatest(0, extract(epoch from now() - started_at)) * 60 * 12)::int + 2000)) where id = r.id;
    end if;
    return public.rb_wave_state(r.duel);
end $$;

create or replace function public.rb_wave_busy(who uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_wave_duels w where (w.a = who and w.state in ('open', 'live'))
                                                          or (w.b = who and w.state = 'live')) $$;

create or replace function public.rb_wave_create(bet integer) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; did uuid; old record;
begin
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    for old in select id from public.rb_wave_duels where (a = p.id or b = p.id) and state in ('open', 'live') loop
        perform public.rb_wave_tick(old.id);
    end loop;
    if public.rb_wave_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    perform public.rb_pay(p.id, -bet, 0, 'wave_bet', null);
    insert into public.rb_wave_duels (a, bet, seed) values (p.id, bet, floor(public.rb_rand() * 2147483647)::bigint)
        returning id into did;
    return jsonb_build_object('id', did, 'coins', p.coins - bet);
end $$;

create or replace function public.rb_wave_join(did uuid) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; w public.rb_wave_duels%rowtype; ra uuid; rb uuid;
begin
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    perform public.rb_wave_tick(did);
    select * into w from public.rb_wave_duels where id = did for update;
    if not found or w.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if w.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_wave_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if p.coins < w.bet then raise exception 'rb_not_enough'; end if;
    perform public.rb_pay(p.id, -w.bet, 0, 'wave_bet', w.id::text);
    insert into public.rb_wave_runs (owner, seed, duel, started_at) values (w.a, w.seed, w.id, now() + interval '4 seconds')
        returning id into ra;
    insert into public.rb_wave_runs (owner, seed, duel, started_at) values (p.id, w.seed, w.id, now() + interval '4 seconds')
        returning id into rb;
    update public.rb_wave_duels set b = p.id, state = 'live', live_at = now(), a_run = ra, b_run = rb where id = w.id
        returning * into w;
    perform public.rb_notice(w.a, 'wave_yes', jsonb_build_object('from', p.username, 'id', w.id));
    return public.rb_wave_duel_json(w, p.id) || jsonb_build_object('coins', p.coins - w.bet);
end $$;

create or replace function public.rb_wave_cancel(did uuid) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); w public.rb_wave_duels%rowtype;
begin
    select * into w from public.rb_wave_duels where id = did and a = me for update;
    if not found or w.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    update public.rb_wave_duels set state = 'cancelled', why = 'closed', done_at = now() where id = w.id;
    if w.bet > 0 then perform public.rb_pay(w.a, w.bet, 0, 'wave_back', w.id::text); end if;
end $$;

-- leaving a live duel: the other player wins
create or replace function public.rb_wave_leave(did uuid) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); w public.rb_wave_duels%rowtype;
begin
    select * into w from public.rb_wave_duels where id = did and (a = me or b = me);
    if not found then raise exception 'rb_duel_gone'; end if;
    if w.state = 'open' then perform public.rb_wave_cancel(did); return; end if;
    if w.state = 'live' then perform public.rb_wave_settle(did, me); end if;
end $$;

create or replace function public.rb_wave_lobbies() returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; o record; live uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    for o in select id from public.rb_wave_duels where state in ('open', 'live') and (state = 'open' or a = me or b = me) loop
        perform public.rb_wave_tick(o.id);
    end loop;
    select id into live from public.rb_wave_duels where state = 'live' and (a = me or b = me) order by live_at desc limit 1;
    return jsonb_build_object(
        'live', live, 'cap', public.rb_golf_cap(p.coins), 'best', public.rb_wave_best(me),
        'lobbies', coalesce((select jsonb_agg(jsonb_build_object('id', w.id, 'host', u.username, 'bet', w.bet, 'mine', w.a = me,
                     'left', greatest(0, ceil(extract(epoch from (w.at + make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int)
                     - now()))))::int) order by w.at)
                   from public.rb_wave_duels w join public.profiles u on u.id = w.a where w.state = 'open'), '[]'::jsonb),
        'history', coalesce((select jsonb_agg(h order by (h ->> 'at') desc) from (
                   select jsonb_build_object('id', w.id, 'at', w.at, 'bet', w.bet, 'state', w.state,
                          'other', (select username from public.profiles where id = case when w.a = me then w.b else w.a end),
                          'won', w.winner = me, 'draw', w.state = 'done' and w.winner is null,
                          'me_m', (select dist / 100 from public.rb_wave_runs where id = case when w.a = me then w.a_run else w.b_run end),
                          'other_m', (select dist / 100 from public.rb_wave_runs where id = case when w.a = me then w.b_run else w.a_run end)) h
                     from public.rb_wave_duels w where (w.a = me or w.b = me) and w.state in ('live', 'done')
                    order by w.at desc limit 6) z), '[]'::jsonb));
end $$;

revoke all on function public.rb_wave_pay_for(integer), public.rb_wave_best(uuid), public.rb_wave_settle(uuid, uuid),
    public.rb_wave_tick(uuid), public.rb_wave_duel_json(public.rb_wave_duels, uuid), public.rb_wave_busy(uuid)
    from public, anon, authenticated;
revoke all on function public.rb_wave_solo(), public.rb_wave_finish(uuid, integer[], integer), public.rb_wave_state(uuid),
    public.rb_wave_ping(uuid, integer), public.rb_wave_create(integer), public.rb_wave_join(uuid), public.rb_wave_cancel(uuid),
    public.rb_wave_leave(uuid), public.rb_wave_lobbies() from public, anon;
grant execute on function public.rb_wave_solo(), public.rb_wave_finish(uuid, integer[], integer), public.rb_wave_state(uuid),
    public.rb_wave_ping(uuid, integer), public.rb_wave_create(integer), public.rb_wave_join(uuid), public.rb_wave_cancel(uuid),
    public.rb_wave_leave(uuid), public.rb_wave_lobbies() to authenticated;

-- ================================================================ The pawn shop (4.3): quick sell, with haggling
-- The shopkeeper offers the quick-sell price. Take it, or ask for more (up to 1.5 times): the higher you ask, the
-- lower the chance he says yes (the same formula the app shows), and every no makes him angrier. His anger cools by
-- 10 a minute; at 100 he throws you out for 30 minutes. The roll is the server's (rb_rand); the price is always
-- worked out again from the items, never taken from the app.
create table if not exists public.rb_pawn (
    owner uuid primary key references public.profiles (id) on delete cascade,
    anger double precision not null default 0,
    anger_at timestamptz not null default now(),
    ban_until timestamptz
);
alter table public.rb_pawn enable row level security;
revoke all on public.rb_pawn from anon, authenticated;

create or replace function public.rb_pawn_chance(ratio double precision, anger double precision) returns double precision
language sql immutable set search_path = '' as $$
    select case when ratio <= 1 then 1.0
                else greatest(0.0, power(greatest(0.0, 1 - (ratio - 1) / 0.6), 1.6) * (1 - least(100, anger) / 250.0)) end $$;

create or replace function public.rb_pawn_rage(ratio double precision) returns double precision
language sql immutable set search_path = '' as $$
    select 20 + 60 * least(1.0, greatest(0.0, (ratio - 1) / 0.5)) $$;

-- your anger row, cooled down to now
create or replace function public.rb_pawn_me(who uuid) returns public.rb_pawn
language plpgsql volatile security definer set search_path = '' as $$
declare r public.rb_pawn%rowtype;
begin
    insert into public.rb_pawn (owner) values (who) on conflict (owner) do nothing;
    select * into r from public.rb_pawn where owner = who for update;
    r.anger := greatest(0, r.anger - 10 * extract(epoch from now() - r.anger_at) / 60);
    r.anger_at := now();
    if r.ban_until is not null and r.ban_until <= now() then r.ban_until := null; end if;
    update public.rb_pawn set anger = r.anger, anger_at = r.anger_at, ban_until = r.ban_until where owner = who;
    return r;
end $$;

create or replace function public.rb_pawn_quote(who uuid, ids uuid[]) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare total bigint := 0; n integer := 0; v integer; it public.rb_items%rowtype;
begin
    for it in select * from public.rb_items where owner = who and id = any (ids) and locked is null loop
        v := public.rb_quick_value(who, it);
        if v > 0 then total := total + v; n := n + 1; end if;
    end loop;
    return jsonb_build_object('base', total, 'n', n);
end $$;

-- coming in: his offer, his mood, or how long you are still banned for
create or replace function public.rb_pawn_enter(ids uuid[]) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); r public.rb_pawn%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('market');
    r := public.rb_pawn_me(me);
    return public.rb_pawn_quote(me, ids) || jsonb_build_object('anger', round(r.anger::numeric, 1),
        'ban_left', case when r.ban_until is not null then ceil(extract(epoch from r.ban_until - now()))::int else 0 end,
        'max_ratio', 1.5);
end $$;

-- sell to him: at his price (ask null), or at yours if he says yes
create or replace function public.rb_pawn_sell(ids uuid[], ask bigint, req text) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r public.rb_pawn%rowtype; q jsonb; base bigint; ratio double precision;
        ch double precision; yes boolean; price bigint; it public.rb_items%rowtype; n integer := 0; out_ jsonb;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if coalesce(array_length(ids, 1), 0) = 0 or array_length(ids, 1) > 200 then raise exception 'rb_bad_choice'; end if;
    r := public.rb_pawn_me(p.id);
    if r.ban_until is not null then
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'banned',
               'ban_left', ceil(extract(epoch from r.ban_until - now()))::int, 'anger', 0));
    end if;
    q := public.rb_pawn_quote(p.id, ids);
    base := (q ->> 'base')::bigint;
    if (q ->> 'n')::int = 0 or base <= 0 then raise exception 'rb_not_tradeable'; end if;
    if ask is null or ask <= base then
        ratio := 1; price := base; yes := true; ch := 1;
    else
        if ask > floor(base * 1.5) then raise exception 'rb_bad_choice'; end if;
        ratio := ask::double precision / base;
        ch := public.rb_pawn_chance(ratio, r.anger);
        yes := public.rb_rand() < ch;
        price := ask;
    end if;
    if not yes then
        r.anger := r.anger + public.rb_pawn_rage(ratio);
        if r.anger >= 100 then
            update public.rb_pawn set anger = 0, anger_at = now(), ban_until = now() + interval '30 minutes' where owner = p.id;
            return public.rb_remember(p.id, req, jsonb_build_object('result', 'kicked', 'anger', 100, 'ban_left', 1800,
                                                                    'chance', round(ch::numeric, 4)));
        end if;
        update public.rb_pawn set anger = r.anger, anger_at = now() where owner = p.id;
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'no', 'anger', round(r.anger::numeric, 1),
                                                                'chance', round(ch::numeric, 4), 'base', base));
    end if;
    for it in select * from public.rb_items where owner = p.id and id = any (ids) and locked is null for update loop
        if public.rb_quick_value(p.id, it) > 0 then
            delete from public.rb_items where id = it.id;
            n := n + 1;
        end if;
    end loop;
    if n = 0 then raise exception 'rb_not_tradeable'; end if;
    perform public.rb_fix_equip(p.id);
    perform public.rb_pay(p.id, price::int, 0, 'quick_sell', n::text);
    if ratio > 1 then                                          -- a deal cools him down a little
        update public.rb_pawn set anger = greatest(0, r.anger - 10), anger_at = now() where owner = p.id;
    end if;
    out_ := jsonb_build_object('result', 'yes', 'paid', price, 'n', n, 'coins', p.coins + price,
                               'anger', round(greatest(0, r.anger - case when ratio > 1 then 10 else 0 end)::numeric, 1),
                               'equip', (select equip from public.profiles where id = p.id));
    return public.rb_remember(p.id, req, out_);
end $$;

revoke all on function public.rb_pawn_me(uuid), public.rb_pawn_quote(uuid, uuid[]) from public, anon, authenticated;
revoke all on function public.rb_pawn_enter(uuid[]), public.rb_pawn_sell(uuid[], bigint, text) from public, anon;
grant execute on function public.rb_pawn_enter(uuid[]), public.rb_pawn_sell(uuid[], bigint, text) to authenticated;
grant execute on function public.rb_pawn_chance(double precision, double precision), public.rb_pawn_rage(double precision)
    to authenticated;

-- ================================================================ Quests count the newer games too (4.3)
-- Mini game quests now count Block Blast, Minesweeper, Mini Golf solo and Wave Rush; casino quests count Tower.
do $$
declare src text; n1 integer; n2 integer;
begin
    src := replace(pg_get_functiondef('public.rb_quest_rows(uuid)'::regprocedure), chr(13), '');
    if src like '%golf_solo%' then return; end if;                -- already done (safe to run again)
    n1 := (length(src) - length(replace(src, $q$game in ('mini', 'park', 'memory')$q$, ''))) / length($q$game in ('mini', 'park', 'memory')$q$);
    src := replace(src, $q$game in ('mini', 'park', 'memory')$q$, $q$game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'wave')$q$);
    n2 := (length(src) - length(replace(src, $q$('timing'), ('roulette'), ('hilo'))$q$, ''))) / length($q$('timing'), ('roulette'), ('hilo'))$q$);
    src := replace(src, $q$('timing'), ('roulette'), ('hilo'))$q$, $q$('timing'), ('roulette'), ('hilo'), ('tower'))$q$);
    if n1 <> 3 or n2 <> 1 then raise exception 'rb_quest_rows changed: % % (expected 3 1)', n1, n2; end if;
    execute src;
end $$;

update public.rb_config set value = 2026111820 where key = 'min_build';
commit;
