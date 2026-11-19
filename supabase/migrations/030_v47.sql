-- ================================================================ Rubenium 4.7 (build 2026.11.18.26)
-- Case odds from a table (every badge at least 1 in its finish's limit), a much better Golden Wheel, the pawn shop
-- asks before it sells, quicker case gifts, one of each deal a day, rate limits, no more cheats.
-- Needs 029 first. 030_down.sql undoes it (back to 029).
begin;

-- ================================================================ 4.7: rate limits
-- Each account can only do so many of these per minute (trades, market, coinflips, duels, messages, gifts).
-- Way above what a person clicks, low enough that a script can't flood the server or other players.
create table if not exists public.rb_rate_hits (owner uuid not null, bucket text not null,
    minute timestamptz not null, n integer not null default 0, primary key (owner, bucket));
alter table public.rb_rate_hits enable row level security;

create or replace function public.rb_rate(who uuid, bucket text, per_min integer) returns void
language plpgsql volatile security definer set search_path to '' as $function$
#variable_conflict use_column
declare m timestamptz := date_trunc('minute', now()); got integer;
begin
    if who is null or per_min is null or per_min <= 0 then return; end if;
    insert into public.rb_rate_hits as h (owner, bucket, minute, n) values (who, bucket, m, 1)
        on conflict (owner, bucket) do update
        set n = case when h.minute = excluded.minute then h.n + 1 else 1 end, minute = excluded.minute
    returning n into got;
    if got > per_min then raise exception 'rb_slow_down'; end if;
end $function$;
revoke all on function public.rb_rate(uuid, text, integer) from public, anon, authenticated;

do $$
declare f record; src text; out_ text;
begin
    for f in select * from (values
        ('rb_trade_request(text)', 'trade_ask', 10), ('rb_trade_offer(uuid,uuid[],integer)', 'trade', 90),
        ('rb_trade_offer(uuid,uuid[],integer,integer)', 'trade', 90), ('rb_trade_ready(uuid,boolean,integer)', 'trade', 90),
        ('rb_trade_confirm(uuid,integer)', 'trade', 90),
        ('rb_market_list(uuid,integer)', 'market_list', 20), ('rb_market_buy(uuid,text)', 'market_buy', 30),
        ('rb_market_offer(uuid,integer)', 'market_offer', 20), ('rb_market_cancel(uuid)', 'market_list', 20),
        ('rb_market_deal(uuid,uuid,integer)', 'market_offer', 20),
        ('rb_flip_create(text,uuid[])', 'flip', 15), ('rb_flip_join(uuid)', 'flip', 15), ('rb_flip_vs_bot(uuid)', 'flip', 15),
        ('rb_duel_ask(text,text,integer,integer)', 'duel', 10), ('rb_golf_create(integer)', 'duel', 10),
        ('rb_golf_join(uuid)', 'duel', 10), ('rb_wave_create(integer)', 'duel', 10), ('rb_wave_join(uuid)', 'duel', 10),
        ('rb_msg_send(text,text)', 'msg', 30), ('rb_friend_add(text)', 'friend', 10), ('rb_case_gift(text,text,text)', 'gift', 10)
    ) v(sig, bucket, per_min) loop
        if to_regprocedure('public.' || f.sig) is null then continue; end if;
        src := replace(pg_get_functiondef(('public.' || f.sig)::regprocedure), chr(13), '');
        if position('rb_rate(' in src) > 0 then continue; end if;
        out_ := regexp_replace(src, E'\nbegin\n', format(E'\nbegin\n    perform public.rb_rate(auth.uid(), %L, %s);\n', f.bucket, f.per_min));
        if out_ = src then raise notice 'no begin in %', f.sig; continue; end if;
        execute out_;
    end loop;
end $$;

-- ================================================================ Cases 4.7: every badge's chance from a table
-- Each case has a grid: the chance (in billionths) of each rarity (Common, Rare, Special, Epic) and finish (Basic,
-- Painted, Shiny, Titanium, Gold). Every badge a case can give is at least 1 in: Basic 250, Painted 1 000,
-- Shiny 10 000, Titanium 50 000, Gold 100 000, lower rarities a bit more common, cheap cases hold the lower rarities and
-- big cases everything. What a case pays on average stays the same. Mythic drops are not touched.
alter table public.rb_cases add column if not exists grid bigint[];

do $$
begin
    if exists (select 1 from public.rb_config where key = 'cases_v47') then return; end if;     -- once only
    create table if not exists public.rb_cases_v46 (id text primary key, odds integer[], variants integer[],
                                                    coin_min integer, coin_max integer);
    alter table public.rb_cases_v46 enable row level security;
    insert into public.rb_cases_v46 select id, odds, variants, coin_min, coin_max from public.rb_cases
        on conflict (id) do nothing;
    -- the old columns follow the table (totals per rarity out of 10 000, per finish out of 100 000) for anything
    -- that still reads them; the drop itself only reads the grid
    update public.rb_cases c set grid = v.grid, coin_min = v.cmin, coin_max = v.cmax, odds = v.odds, variants = v.vars
      from (values
        ('pocket', array[77462668, 160610047, 0, 0, 0, 69345322, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 39, 206, array[6926, 2381, 693, 0, 0, 0], array[47755, 52245, 0, 0, 0]),
        ('starter', array[70157057, 145462692, 8926453, 0, 0, 65083716, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 82, 400, array[7104, 2245, 651, 0, 0, 0], array[46694, 50224, 3082, 0, 0]),
        ('lucky', array[76419009, 158446139, 9723194, 0, 0, 68736521, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 79, 500, array[6867, 2446, 687, 0, 0, 0], array[46328, 50569, 3103, 0, 0]),
        ('standard', array[57981039, 120217101, 7377234, 0, 144953, 57981039, 0, 0, 0, 0, 57981039, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 143, 785, array[6982, 1857, 580, 580, 0, 1], array[57658, 39849, 2445, 0, 48]),
        ('gamble', array[0, 0, 0, 0, 0, 57981039, 0, 7377234, 0, 144953, 57981039, 0, 0, 581286, 144953, 0, 0, 0, 0, 0]::bigint[], 39, 379, array[8755, 0, 655, 587, 0, 3], array[93359, 0, 5939, 468, 234]),
        ('premium', array[67026081, 138970969, 8528082, 0, 167565, 63257313, 0, 8048562, 0, 158143, 60242299, 0, 0, 0, 0, 0, 0, 0, 0, 0]::bigint[], 285, 1529, array[6535, 2147, 715, 602, 0, 1], array[55002, 40119, 4785, 0, 94]),
        ('painter', array[0, 120217101, 7377234, 0, 144953, 0, 120217101, 7377234, 0, 144953, 0, 0, 0, 581286, 144953, 0, 0, 0, 581286, 0]::bigint[], 157, 1291, array[7432, 1278, 1277, 7, 6, 0], array[0, 93632, 5746, 453, 169]),
        ('giftbox', array[64590877, 133921851, 8218238, 0, 161477, 61836778, 0, 7867820, 0, 154592, 59633498, 0, 0, 597852, 0, 0, 0, 0, 0, 0]::bigint[], 584, 1557, array[6630, 2069, 699, 602, 0, 0], array[55214, 39741, 4774, 177, 94]),
        ('titan', array[61459901, 127430127, 7819868, 0, 153650, 60010375, 124424700, 7635437, 0, 150026, 58850754, 0, 0, 590005, 147127, 0, 0, 0, 581286, 144953]::bigint[], 631, 4157, array[5503, 1969, 1922, 596, 7, 3], array[40125, 56043, 3439, 261, 132]),
        ('vault', array[0, 0, 0, 0, 0, 71780526, 148828771, 9133015, 0, 179451, 63895104, 132479245, 8129711, 640577, 159738, 57981039, 0, 7377234, 581286, 144953]::bigint[], 789, 6301, array[4972, 0, 2299, 2053, 661, 15], array[38630, 56114, 4915, 244, 97]),
        ('cosmos', array[0, 0, 0, 0, 0, 90015562, 186637050, 11453155, 0, 225039, 76679923, 158987116, 9756391, 768750, 191700, 66678194, 0, 8483819, 668479, 166695]::bigint[], 1503, 5783, array[3843, 0, 2883, 2464, 760, 50], array[38213, 56594, 4862, 235, 96]),
        ('elite', array[70157057, 145462692, 8926453, 0, 175393, 65083716, 134943696, 8280945, 0, 162709, 61025043, 0, 7764538, 611803, 152563, 57981039, 0, 0, 581286, 144953]::bigint[], 1219, 7160, array[4381, 2247, 2085, 696, 587, 4], array[45284, 49943, 4448, 212, 113]),
        ('shiny', array[0, 0, 0, 0, 0, 0, 342438413, 21014050, 0, 412897, 0, 291706796, 17900857, 1410490, 351727, 0, 253658083, 15565963, 1226513, 305850]::bigint[], 70, 520, array[510, 0, 3639, 3114, 2707, 30], array[0, 93849, 5759, 279, 113]),
        ('mythic', array[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 86014871, 178342070, 10944126, 862337, 215037, 74795540, 155080061, 9516631, 749859, 186989]::bigint[], 1977, 15654, array[4773, 0, 0, 2764, 2403, 60], array[31122, 64528, 3960, 312, 78]),
        ('royal', array[0, 0, 0, 0, 0, 108801419, 225587390, 13843379, 0, 272004, 92682690, 192167036, 11792508, 929185, 231707, 80593644, 167101771, 10254355, 807987, 201484]::bigint[], 18912, 104013, array[937, 0, 3485, 2978, 2590, 10], array[31160, 64606, 3964, 192, 78])
      ) v(id, grid, cmin, cmax, odds, vars) where c.id = v.id;
    insert into public.rb_config (key, value) values ('cases_v47', 1);
end $$;

-- ================================================================ Cases 4.7: the drop reads the case's grid
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
 returns record language plpgsql security definer set search_path to '' as $function$
declare r double precision; roll bigint; myth bigint; i integer;
begin
    tier := 0; klass := 0; coins := 0;
    if c.grid is not null and c.mode = '' then                -- 4.7: one roll over the whole table
        roll := floor(public.rb_rand() * 1000000000)::bigint;
        myth := round(1000000000.0 * c.odds[6] / greatest(1, (select sum(x) from unnest(c.odds) x)))::bigint;
        if roll < myth then
            tier := 5;
            klass := (array[3, 5, 4])[public.rb_roll(array[94300, 5300, 400]) + 1];
            item := public.rb_pick_mythic(klass);
            return;
        end if;
        roll := roll - myth;
        for i in 1 .. 20 loop
            if roll < c.grid[i] then
                tier := (i - 1) / 5 + 1; klass := (i - 1) % 5;
                item := public.rb_pick_badge(tier, klass);
                if item is not null then return; end if;
                tier := 0; klass := 0; exit;
            end if;
            roll := roll - c.grid[i];
        end loop;
        coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
        if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
            coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
        end if;
        return;
    end if;
    tier := public.rb_roll(c.odds);
    if tier > 0 and c.mode like 'kinds:%' then
        item := public.rb_pick_weighted(string_to_array(substr(c.mode, 7), ','), tier, null);
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier > 0 and c.mode like 'items:%' then
        select k.id into item from public.rb_catalog k
         where k.id = any (string_to_array(substr(c.mode, 7), ','))
           and k.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
         order by -ln(greatest(public.rb_rand(), 1e-12)) / k.weight limit 1;
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier = 0 then
        if c.mode = 'jackpot' then
            r := public.rb_rand();
            coins := floor(c.price * case when r < 0.66 then 0.12 + public.rb_rand() * 0.33
                                          when r < 0.90 then 0.8 + public.rb_rand() * 0.8
                                          when r < 0.97 then 2.5 + public.rb_rand() * 1.5
                                          when r < 0.995 then 6.5 + public.rb_rand() * 3.5
                                          else 20 + public.rb_rand() * 12 end)::int;
        else
            coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
            if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
                coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
            end if;
        end if;
    elsif tier = 5 then
        klass := (array[3, 5, 4])[public.rb_roll(array[94300, 5300, 400]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$;

-- the free daily case: 25% a badge from the same kind of table (Basic Common/Rare, Painted Common, Shiny Common)
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_daily_case()'::regprocedure), chr(13), '');
    if position('daily_grid' in src) = 0 then
        out_ := replace(src, '        tier := public.rb_roll(array[0, 7800, 1900, 270, 30]);
        what := public.rb_pick_badge(tier, (array[0, 1, 2])[public.rb_roll(array[7600, 2350, 50]) + 1]);',
'        declare daily_grid bigint[] := array[60764128, 125987522, 7731341, 0, 0, 59604508, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; roll bigint; i integer; got_k integer;
        begin
            roll := floor(public.rb_rand() * (select sum(x) from unnest(daily_grid) x))::bigint;
            for i in 1 .. 20 loop
                if roll < daily_grid[i] then tier := (i - 1) / 5 + 1; got_k := (i - 1) % 5; exit; end if;
                roll := roll - daily_grid[i];
            end loop;
            what := public.rb_pick_badge(tier, got_k);
        end;');
        out_ := replace(out_, '    elsif r < 0.65 then keys := 1;', '    elsif r < 0.7459 then keys := 1;');
        out_ := replace(out_, '    if r < 0.50 then coins', '    if r < 0.5959 then coins');
        if position('daily_grid' in out_) = 0 or position('0.7459' in out_) = 0 or position('0.5959' in out_) = 0 then
            raise exception 'rb_daily_case changed';
        end if;
        execute out_;
    end if;
end $$;

-- ================================================================ 4.7: the admin can't break a case's odds table
create or replace function public.rb_admin_case(which text, new_price integer, new_odds integer[], new_variants integer[], new_min integer, new_max integer)
 returns boolean language plpgsql security definer set search_path to '' as $function$
declare g bigint[];
begin
    perform public.rb_need_admin();
    if new_price < 1 or array_length(new_odds, 1) <> 6 or array_length(new_variants, 1) <> 5
       or (select sum(x) from unnest(new_odds) x) <> 10000 or (select sum(x) from unnest(new_variants) x) <> 100000
       or (select min(x) from unnest(new_odds || new_variants) x) < 0 or new_min < 0 or new_max < new_min then
        raise exception 'rb_bad_choice';
    end if;
    select grid into g from public.rb_cases where id = which;
    update public.rb_cases set price = new_price, coin_min = new_min, coin_max = new_max,
           odds = case when g is null then new_odds else odds end,
           variants = case when g is null then new_variants else variants end
     where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    perform public.rb_log('case', which, jsonb_build_object('price', new_price, 'odds', new_odds, 'variants', new_variants));
    return true;
end $function$;

-- ================================================================ 4.7: the Golden Wheel pays about 3.7x more
-- 10 000 / 20 000 / 40 000 / 100 000 / 250 000 coins, or an Elite, Vault, Top Tier or Royal case with a key.
create or replace function public.rb_gold_wheel()
 returns jsonb language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; r integer;
        prizes text[] := array['10000', 'elite', '20000', 'vault', '40000', 'mythic', '100000', 'royal', '250000'];
        odds integer[] := array[26, 14, 20, 10, 12, 8, 4, 5, 1];
        what text; c integer := 0;
begin
    perform public.rb_need_feature('wheel');
    p := public.rb_lock_me();
    if p.gold_wheels < 1 then raise exception 'rb_nothing_to_collect'; end if;
    r := public.rb_roll(odds);
    what := prizes[r + 1];
    update public.profiles set gold_wheels = gold_wheels - 1 where id = p.id;
    if what ~ '^[0-9]+$' then
        c := what::int;
        perform public.rb_pay(p.id, c, 0, 'gold_wheel', what);
    else
        perform public.rb_stock_add(p.id, what, 1);
        perform public.rb_pay(p.id, 0, 1, 'gold_wheel', what);
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'gold_wheel', 0, jsonb_build_object('prize', what), false, c);
    return jsonb_build_object('slot', r, 'prize', what, 'coins_won', c, 'case', case when c = 0 then what end,
                              'coins', p.coins + c, 'keys', p.keys + case when c = 0 then 1 else 0 end, 'left', p.gold_wheels - 1);
end $function$;

-- ================================================================ 4.7: no more cheats
-- The four games go back to exactly what they were before 4.6, and the cheat function is gone.
CREATE OR REPLACE FUNCTION public.rb_mines(action text, arg integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; bombs integer[]; picked integer[]; n integer;
        pay integer := 0; hit boolean := false; done boolean := false;
begin
    perform public.rb_need_feature('casino');
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
end $function$;

CREATE OR REPLACE FUNCTION public.rb_tower(action text, bet integer, arg integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; s jsonb; mode integer; lvl integer; cols integer;
        bombs integer; rows_ jsonb := '[]'::jsonb; i integer; row_b jsonb; pay integer := 0; picks jsonb;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if action = 'start' then perform public.rb_need_feature('casino'); end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'tower' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        mode := coalesce(arg, 1);
        if mode not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
        cols := (array[4, 3, 2, 3])[mode + 1]; bombs := (array[1, 1, 1, 2])[mode + 1];
        perform public.rb_bet(p, bet, 'tower');
        for i in 1..8 loop
            select jsonb_agg(x) into row_b from (select x from generate_series(0, cols - 1) x order by public.rb_rand() limit bombs) t;
            rows_ := rows_ || jsonb_build_array(row_b);
        end loop;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'tower', bet, jsonb_build_object('mode', mode, 'rows', rows_, 'level', 0, 'picks', '[]'::jsonb), true, 0)
            returning * into r;
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'mode', mode, 'level', 0, 'cols', cols, 'bombs', bombs,
            'mult', 1, 'next', public.rb_tower_mult(mode, 1), 'bet', bet, 'coins', p.coins - bet, 'picks', '[]'::jsonb));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    s := r.secret; mode := (s ->> 'mode')::int; lvl := (s ->> 'level')::int; picks := s -> 'picks';
    cols := (array[4, 3, 2, 3])[mode + 1]; bombs := (array[1, 1, 1, 2])[mode + 1];
    if action = 'state' then
        return jsonb_build_object('open', true, 'mode', mode, 'level', lvl, 'cols', cols, 'bombs', bombs, 'picks', picks,
                                  'mult', public.rb_tower_mult(mode, lvl), 'next', public.rb_tower_mult(mode, lvl + 1), 'bet', r.bet);
    end if;
    if action = 'pick' then
        if arg is null or arg < 0 or arg >= cols then raise exception 'rb_bad_choice'; end if;
        picks := picks || to_jsonb(arg);
        if (s -> 'rows' -> lvl) @> to_jsonb(arg) then                              -- a bomb
            update public.rb_rounds set open = false, paid = 0, secret = s || jsonb_build_object('picks', picks, 'boom', true) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'boom', true, 'level', lvl, 'picks', picks,
                'rows', s -> 'rows', 'paid', 0, 'bet', r.bet, 'coins', p.coins, 'mode', mode, 'cols', cols));
        end if;
        lvl := lvl + 1;
        if lvl < 8 then
            update public.rb_rounds set secret = s || jsonb_build_object('level', lvl, 'picks', picks) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'level', lvl, 'picks', picks, 'mode', mode, 'cols', cols,
                'mult', public.rb_tower_mult(mode, lvl), 'next', public.rb_tower_mult(mode, lvl + 1), 'bet', r.bet, 'coins', p.coins));
        end if;
        action := 'cash';                                                        -- the top: paid at once
    end if;
    if action = 'cash' then
        if lvl < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * public.rb_tower_mult(mode, lvl), 'tower');
        update public.rb_rounds set open = false, paid = pay, secret = s || jsonb_build_object('level', lvl, 'picks', picks) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'boom', false, 'level', lvl, 'picks', picks,
            'rows', s -> 'rows', 'paid', pay, 'mult', public.rb_tower_mult(mode, lvl), 'bet', r.bet, 'coins', p.coins + pay,
            'mode', mode, 'cols', cols));
    end if;
    raise exception 'rb_bad_choice';
end $function$;

CREATE OR REPLACE FUNCTION public.rb_hilo(action text, bet integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; cards jsonb; card integer; nxt integer;
        mult numeric; step numeric := coalesce(public.rb_cfg('hilo_step'), 0.985); pay integer := 0; right_ boolean;
        rank integer; hits integer; top numeric;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'hilo' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        perform public.rb_bet(p, bet, 'hilo');
        card := floor(public.rb_rand() * 52)::int;                  -- 0..51: rank = card % 13 + 1, suit = card / 13
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'hilo', bet, jsonb_build_object('cards', jsonb_build_array(card), 'mult', 1, 'hits', 0), true, 0)
            returning * into r;
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', jsonb_build_array(card), 'mult', 1,
                                                                'hits', 0, 'bet', r.bet, 'coins', p.coins - r.bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    cards := r.secret -> 'cards';
    mult := (r.secret ->> 'mult')::numeric;
    hits := (r.secret ->> 'hits')::int;
    card := (cards ->> (jsonb_array_length(cards) - 1))::int;
    rank := card % 13 + 1;
    if action = 'state' then
        return jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits, 'bet', r.bet);
    end if;
    if action in ('higher', 'lower') then
        nxt := floor(public.rb_rand() * 52)::int;
        right_ := case when action = 'higher' then nxt % 13 + 1 >= rank else nxt % 13 + 1 <= rank end;
        cards := cards || to_jsonb(nxt);
        if not right_ then
            update public.rb_rounds set open = false, paid = 0,
                   secret = jsonb_build_object('cards', cards, 'mult', 0, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', 0, 'hits', hits,
                                                                    'right', false, 'paid', 0, 'bet', r.bet, 'coins', p.coins));
        end if;
        mult := round(mult * step * 13.0 / (case when action = 'higher' then 14 - rank else rank end), 4);
        hits := hits + 1;
        top := public.rb_cfg('win_max') / r.bet;
        if mult >= top then action := 'cash'; mult := top; end if;          -- the biggest prize: paid at once
        if action <> 'cash' then
            update public.rb_rounds set secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                    'right', true, 'bet', r.bet, 'coins', p.coins));
        end if;
    end if;
    if action = 'cash' then
        if hits < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * mult, 'hilo');
        update public.rb_rounds set open = false, paid = pay,
               secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                'right', true, 'paid', pay, 'bet', r.bet, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $function$;

CREATE OR REPLACE FUNCTION public.rb_blackjack(action text, bet integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; deck integer[]; me integer[]; dealer integer[];
        stake integer; done boolean := false; pay integer := 0; outcome text := ''; spent integer := 0;
begin
    perform public.rb_need_feature('casino');
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
end $function$;

drop function if exists public.rb_admin_cheat(text);
delete from public.rb_rigs where kind = 'cheat';

-- ================================================================ Pawn shop 4.7: asking is not selling
-- Asking for more only asks: if he says yes, the price is kept for 5 minutes for exactly those items, and the sale
-- happens when you press Sell (rb_pawn_sell with that price). His own price always sells at once.
alter table public.rb_pawn add column if not exists deal bigint;
alter table public.rb_pawn add column if not exists deal_key text;
alter table public.rb_pawn add column if not exists deal_at timestamptz;

create or replace function public.rb_pawn_key(ids uuid[]) returns text
language sql immutable set search_path to '' as $$
    select md5(coalesce(string_agg(x::text, ',' order by x), '')) from unnest(ids) x $$;

create or replace function public.rb_pawn_ask(ids uuid[], ask bigint, req text)
 returns jsonb language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_pawn%rowtype; q jsonb; base bigint; ratio double precision;
        ch double precision;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if coalesce(array_length(ids, 1), 0) = 0 or array_length(ids, 1) > 200 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_rate(p.id, 'pawn', 30);
    r := public.rb_pawn_me(p.id);
    if r.ban_until is not null then
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'banned',
               'ban_left', ceil(extract(epoch from r.ban_until - now()))::int, 'anger', 0));
    end if;
    q := public.rb_pawn_quote(p.id, ids);
    base := (q ->> 'base')::bigint;
    if (q ->> 'n')::int = 0 or base <= 0 then raise exception 'rb_not_tradeable'; end if;
    if ask is null or ask <= base then ask := base; end if;
    if ask > floor(base * 1.5) then raise exception 'rb_bad_choice'; end if;
    ratio := ask::double precision / base;
    ch := case when ratio <= 1 then 1 else public.rb_pawn_chance(ratio, r.anger) end;
    if ratio <= 1 or public.rb_rand() < ch then
        update public.rb_pawn set deal = ask, deal_key = public.rb_pawn_key(ids), deal_at = now(),
               anger = case when ratio > 1 then greatest(0, anger - 10) else anger end, anger_at = now()
         where owner = p.id;
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'yes', 'price', ask, 'base', base,
               'chance', round(ch::numeric, 4), 'anger', round(greatest(0, r.anger - case when ratio > 1 then 10 else 0 end)::numeric, 1)));
    end if;
    r.anger := r.anger + public.rb_pawn_rage(ratio);
    if r.anger >= 100 then
        update public.rb_pawn set anger = 0, anger_at = now(), ban_until = now() + interval '30 minutes', deal = null
         where owner = p.id;
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'kicked', 'anger', 100, 'ban_left', 1800,
                                                                'chance', round(ch::numeric, 4)));
    end if;
    update public.rb_pawn set anger = r.anger, anger_at = now() where owner = p.id;
    return public.rb_remember(p.id, req, jsonb_build_object('result', 'no', 'anger', round(r.anger::numeric, 1),
                                                            'chance', round(ch::numeric, 4), 'base', base));
end $function$;
revoke all on function public.rb_pawn_ask(uuid[], bigint, text) from public, anon;
grant execute on function public.rb_pawn_ask(uuid[], bigint, text) to authenticated;

create or replace function public.rb_pawn_sell(ids uuid[], ask bigint, req text)
 returns jsonb language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_pawn%rowtype; q jsonb; base bigint; price bigint;
        it public.rb_items%rowtype; n integer := 0; out_ jsonb;
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
        price := base;
    else                                                       -- 4.7: only a price he agreed to, for these items
        if r.deal is null or r.deal <> ask or r.deal_key is distinct from public.rb_pawn_key(ids)
           or r.deal_at < now() - interval '5 minutes' or ask > floor(base * 1.5) then
            raise exception 'rb_pawn_no_deal';
        end if;
        price := ask;
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
    update public.rb_pawn set deal = null, deal_key = null, deal_at = null where owner = p.id;
    out_ := jsonb_build_object('result', 'yes', 'paid', price, 'n', n, 'coins', p.coins + price,
                               'anger', round(r.anger::numeric, 1), 'equip', (select equip from public.profiles where id = p.id));
    return public.rb_remember(p.id, req, out_);
end $function$;

-- ================================================================ 4.7: gifting cases is quick
-- Pick a friend from the list and how many (1 to what's left today) in one go. rb_gift_left says how many are left.
create or replace function public.rb_gift_left() returns integer
language sql stable security definer set search_path to '' as $$
    select greatest(0, public.rb_cfg('gift_day')::int - (select count(*)::int from public.rb_ledger
           where owner = auth.uid() and reason = 'gift' and at >= date_trunc('day', now()))) $$;
revoke all on function public.rb_gift_left() from public, anon;
grant execute on function public.rb_gift_left() to authenticated;

create or replace function public.rb_case_gift_n(name text, which text, n integer, req text)
 returns jsonb language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; left_ integer; i integer;
begin
    perform public.rb_rate(auth.uid(), 'gift', 10);
    perform public.rb_need_feature('gifts');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if n is null or n < 1 or n > 10 then raise exception 'rb_bad_choice'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
    if not public.rb_is_friend(p.id, them.id) then raise exception 'rb_friends_only'; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    left_ := public.rb_cfg('gift_day')::int - (select count(*)::int from public.rb_ledger where owner = p.id and reason = 'gift'
             and at >= date_trunc('day', now()));
    if n > left_ then raise exception 'rb_gift_limit'; end if;
    if p.coins < c.price::bigint * n then raise exception 'rb_not_enough'; end if;
    for i in 1 .. n loop
        perform public.rb_pay(p.id, -c.price, 0, 'gift', c.id || ':' || them.username);
    end loop;
    perform public.rb_stock_add(them.id, c.id, n);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id, 'n', n));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - c.price::bigint * n, 'keys', p.keys,
                                                            'left', left_ - n));
end $function$;
revoke all on function public.rb_case_gift_n(text, text, integer, text) from public, anon;
grant execute on function public.rb_case_gift_n(text, text, integer, text) to authenticated;

-- ================================================================ 4.7: one of each deal per player per day
-- A deal's price is for one copy a day; after that the item costs its usual shop price again.
create table if not exists public.rb_deal_buys (owner uuid not null, day date not null, item text not null,
    primary key (owner, day, item));
alter table public.rb_deal_buys enable row level security;

create or replace function public.rb_buy(what text, req text)
 returns jsonb language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer; deal_pct integer;
        sale_pct integer;
begin
    perform public.rb_need_feature('shop');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind in ('prog', 'tag') or c.limited then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := public.rb_shop_price(what);
    select d.pct into deal_pct from public.rb_deal_list() d where d.item = what;
    if deal_pct is not null then
        if exists (select 1 from public.rb_deal_buys where owner = p.id and day = public.rb_today() and item = what) then
            sale_pct := coalesce((select max(s.pct) from public.rb_sales s
                                   where s.ends_at > now() and (rb_buy.what = s.what or rb_buy.what like s.what || ':%')), 0);
            cost := greatest(1, ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)) * (100 - sale_pct) / 100.0))::int;
        else
            insert into public.rb_deal_buys (owner, day, item) values (p.id, public.rb_today(), what);
        end if;
    end if;
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost, 'paid', cost));
end $function$;

create or replace function public.rb_deals()
 returns json language sql stable security definer set search_path to '' as $function$
    select json_build_object('deals', coalesce((select json_agg(json_build_object('item', d.item, 'pct', d.pct,
                                 'price', ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)))::int,
                                 'now', public.rb_shop_price(d.item), 'worth', c.worth,
                                 'bought', exists (select 1 from public.rb_deal_buys b where b.owner = auth.uid()
                                                   and b.day = public.rb_today() and b.item = d.item)))
                                 from public.rb_deal_list() d join public.rb_catalog c on c.id = d.item), '[]'::json),
                             'ends_in', ceil(extract(epoch from ((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris' - now())))::int) $function$;

update public.rb_config set value = 2026111826 where key = 'min_build';

commit;
