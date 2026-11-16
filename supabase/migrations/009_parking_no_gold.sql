-- Rubenium 009: the Parking mini game (get the red car out), no gold look in the shop, quests count Parking.
-- Run it once after 008. Running it again does no harm.

-- ---------------------------------------------------------------- gold belongs to awards only
-- Balls, lines and fonts no longer come in gold. Nobody can buy one again; one already bought stays its owner's.
create or replace function public.rb_seed_catalog() returns void
language plpgsql security definer set search_path = '' as $$
declare
    tiers text[] := array['standard', 'rare', 'special', 'epic', 'exotic'];
    badges text[] := array['heart','drop','clover','paw','cat','fish','cherry','feather','note','dice','headset','gamepad',
        'mushroom','tree','wave','ghost','spade','club','diamond','eye','snowflake','mountain','moon','sun',
        'star','bolt','flame','anchor','key','pickaxe','rook','shield','sword','skull','trident','quill',
        'hourglass','target','comet','saturn','alien','rocket','shootingstar','planet','crown','trophy','goldenstar','sunburst'];
    mythics text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium'];
    painted text[] := array['red', 'blue', 'yellow', 'green', 'orange', 'purple', 'pink', 'brown'];
    shiny text[] := array['hotpink', 'lime', 'sky', 'royal', 'lava'];
    colours text[] := array['blue','green','red','yellow','orange','brown','teal','lava','purple','sky','lime','pink','beam'];
    prestige text[] := array['black', 'white'];               -- no gold: gold belongs to awards
    cosmetics text[][] := array[
        ['ball','orbit','0'],['ball','pixel','0'],['ball','split','0'],['ball','halo','1'],['ball','bubble','1'],
        ['ball','spiral','1'],['ball','bullseye','2'],['ball','hex','2'],['ball','ripple','3'],['ball','shard','3'],
        ['line','dash','0'],['line','beads','0'],['line','zigzag','0'],['line','twin','1'],['line','pulse','1'],
        ['line','chain','1'],['line','ribbon','2'],['line','steps','2'],['line','spark','3'],['line','laser','3'],
        ['font','rounded','0'],['font','mono','1'],['font','serif','1'],['font','display','2'],['font','script','3']];
    themes text[][] := array[['sunset','1'],['ocean','1'],['forest','2'],['candy','2'],['storm','3'],['retro','3']];
    prog text[][] := array[['theme:1','0'],['ball:0','0'],['ring:0','0'],['font:0','0'],
        ['theme:2','120'],['ball:1','300'],['ring:1','480'],['theme:3','720'],['theme:4','1200'],['ball:2','1800'],
        ['ring:2','2400'],['theme:5','3300'],['theme:6','4500'],['ball:3','6000'],['ring:3','7500'],
        ['theme:7','9000'],['theme:8','12000']];
    b text; v text; i int; t int; p int; row text[]; worth int[]; base int;
begin
    worth := array[public.rb_cfg('price_standard')::int, public.rb_cfg('price_rare')::int,
                   public.rb_cfg('price_special')::int, public.rb_cfg('price_epic')::int,
                   public.rb_cfg('value_exotic')::int];
    delete from public.rb_catalog c where not exists (select 1 from public.rb_items it where it.item = c.id);
    for i in 1 .. array_length(badges, 1) loop
        b := badges[i]; t := (i - 1) / 12; base := worth[t + 1];
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':grey', 'badge', b, 'grey', tiers[t + 1], base, base, true, 0)
            on conflict (id) do update set rarity = excluded.rarity, price = excluded.price, value = excluded.value, cls = 0;
        foreach v in array painted loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, (base * 1.6)::int, true, 1)
                on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 1;
        end loop;
        foreach v in array shiny loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, base * 8, true, 2)
                on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 2;
        end loop;
        if t >= 2 then                                   -- Titanium: Epic and Legendary badges only
            foreach v in array array['black', 'white'] loop
                insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                    values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, base * 40, true, 3)
                    on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 3;
            end loop;
        else
            delete from public.rb_catalog c where c.id in ('badge:' || b || ':black', 'badge:' || b || ':white')
               and not exists (select 1 from public.rb_items it where it.item = c.id);
        end if;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':gold', 'badge', b, 'gold', tiers[t + 1], null, base * 200, true, 4)
            on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 4;
    end loop;
    foreach b in array mythics loop                      -- Mythic: cases, trading and the market only
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':black', 'badge', b, 'black', 'exotic', null, worth[5] * (case b when 'rubenium' then 2 else 1 end), true, 3),
                   ('badge:' || b || ':white', 'badge', b, 'white', 'exotic', null, worth[5] * (case b when 'rubenium' then 2 else 1 end), true, 3),
                   ('badge:' || b || ':prime', 'badge', b, 'prime', 'exotic', null, worth[5] * (case b when 'rubenium' then 6 else 3 end), true, 5),
                   ('badge:' || b || ':gold', 'badge', b, 'gold', 'exotic', null, worth[5] * (case b when 'rubenium' then 50 else 16 end), true, 4)
            on conflict (id) do update set rarity = 'exotic', price = null, value = excluded.value, cls = excluded.cls;
    end loop;
    foreach row slice 1 in array cosmetics loop          -- balls, lines, fonts: every colour is sold
        t := row[3]::int;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values (row[1] || ':' || row[2] || ':grey', row[1], row[2], 'grey', tiers[t + 1],
                    (worth[t + 1] * 0.8)::int, (worth[t + 1] * 0.8)::int, true) on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        foreach v in array colours loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
                values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[t + 1], worth[t + 1], worth[t + 1], true)
                on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        end loop;
        foreach v in array prestige loop
            p := least(t + 1, 3);
            i := (worth[p + 1] * 1.25)::int;
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
                values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[p + 1], i, i, true)
                on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        end loop;
    end loop;
    foreach row slice 1 in array themes loop
        t := row[2]::int;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values ('theme:' || row[1], 'theme', row[1], '', tiers[t + 1], (worth[t + 1] * 1.2)::int,
                    (worth[t + 1] * 1.2)::int, true) on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
    end loop;
    foreach row slice 1 in array prog loop
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values ('prog:' || row[1], 'prog', split_part(row[1], ':', 1), '', 'standard', null, row[2]::int, false)
            on conflict (id) do update set value = excluded.value;
    end loop;
end $$;

update public.rb_catalog set price = null
 where kind in ('ball', 'line', 'font') and variant = 'gold';
delete from public.rb_catalog c
 where c.kind in ('ball', 'line', 'font') and c.variant = 'gold'
   and not exists (select 1 from public.rb_items it where it.item = c.id);
delete from public.rb_sales where what like '%:gold';

-- ---------------------------------------------------------------- Parking
-- A 6 x 6 car park. "A" is the red car on the third row; it must reach the exit on the right. Each level was
-- solved by a computer: "best" is the fewest moves possible (one move = one car slid any distance).
create table if not exists public.rb_park_levels (
    id integer primary key, layout text not null check (length(layout) = 36), best integer not null,
    tier integer not null check (tier between 1 and 3));
insert into public.rb_park_levels (id, layout, best, tier) values
    (1, '.IIIEEFFFJJJ.MAABC.MD.BCHGDL.CHGDLKK', 5, 1),
    (2, 'LJ.CCKLJ..BKMFAABIMFGGDIH...DIH...EE', 5, 1),
    (3, '..FFJB.EEEJBAA...B.DDDCCG...HHG..II.', 5, 1),
    (4, 'HHBBEEJJJGDD.AAGCI.FFFCILLK.C...K...', 5, 1),
    (5, '..IIIC....JCDGAAJBDGKKJBEE.FF....HH.', 5, 1),
    (6, '..JEBBKKJEG.AA..G....ICCHH.ID.FFF.D.', 6, 1),
    (7, '.KLLI..K..I.D.AAJ.DCCCJ.EFF.GGEHH.BB', 6, 1),
    (8, '....CC..JJJGBAAHFGBEEHFDB.IIFD.....D', 6, 1),
    (9, 'DCHHH.DC.LLKB.AAGKB...G.B.F.JEIIF.JE', 6, 1),
    (10, '.IDDD..IB...AAB..E.HH..EFFCCCGKKJJ.G', 7, 1),
    (11, 'HEEEJJH..CFFAA.C.D..BB.D..GG.I.....I', 10, 2),
    (12, 'FKJJGGFK.CCLFAA.HLDD..HIEE..BI..MMB.', 10, 2),
    (13, 'NJMMDDNJBBH.IAA.HKILL.CKFF..CE.GG.CE', 10, 2),
    (14, 'HBJJGGHBC.ILAACFIL.K.FDL.K..D..EEED.', 10, 2),
    (15, 'GNHHEEGN.CCCGAA.DJIIKKDJ.MMBBLFFF..L', 10, 2),
    (16, '.GGFCC...FKK.AAFHJ....HJ..BB.E.DDIIE', 10, 2),
    (17, 'IJJJ.LI.BBHLAADEHF..DEGF.KKCG....CG.', 10, 2),
    (18, 'G.CCC.GKKFHHAADFBJ..DLBJ.E.LB..EIII.', 10, 2),
    (19, '.FFLBBGG.LCM.AA.CMKK.EEHI.JJJHI..DD.', 11, 2),
    (20, '.DDDCCBBB.IL.AA.ILENNFFGEKKHHGMMM.JJ', 11, 2),
    (21, 'MDDDFFMHHHJJLAAGCNLEEGCNII.K.N...KBB', 11, 2),
    (22, '.HCCBB.HNNLL.AAKIDJ..KIDJGGG.EFFFMME', 12, 2),
    (23, '....BB..IILG..AALGFHCCCGFHJEKK..JEDD', 12, 2),
    (24, 'J..FF.J.GGGH.AA..HIIBB.H.EDDCC.EKKLL', 13, 2),
    (25, 'EH.GG.EHBC.IAABC.ILLBK.IJ..K..J.FFDD', 16, 3),
    (26, '.KK.E..CDDEI.CJAAI.BJL.I.B.LGG.FFFHH', 16, 3),
    (27, '.KKJJ.FFF.B.DAA.BEDILLBECIH..GCIHMMG', 16, 3),
    (28, 'IIDDDKGGG.JKAAH.J.E.HBB.ECCL...FFL..', 16, 3),
    (29, 'LJJIHHLBBI...MAAG..MEEG..MNCCFKKNDDF', 16, 3),
    (30, 'MMEEEGLLDK.GAADKCIFF.KCIH.BBBIH.JJ..', 16, 3),
    (31, '.H..D..HGGD.JHAAD.J.......CEEBFFCIIB', 16, 3),
    (32, '.GD.MMLGD.IELBAAIE.BJFFC..JK.CHHHK..', 16, 3),
    (33, 'JJKK.L.NNFFLAACI..BBCI..MHCGGGMHDDEE', 16, 3),
    (34, 'GGC...F.C...FAAIE.B.DIEJB.DI.J..DHHJ', 17, 3),
    (35, '..B.NN..BCGJEAACGJEKKLMDEHHLMDIIFFFD', 18, 3),
    (36, '.FFKHH...KGG.AAKJ.DDIIJL..EEEL..BBCC', 20, 3),
    (37, 'K.IIBBK.HJJEAAH..E.LLDDMGGGF.MCCCF..', 31, 3)
on conflict (id) do update set layout = excluded.layout, best = excluded.best, tier = excluded.tier;

create table if not exists public.rb_park (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    level integer not null references public.rb_park_levels (id),
    at timestamptz not null default clock_timestamp(),
    open boolean not null default true, moves integer, paid integer not null default 0);
create index if not exists rb_park_owner on public.rb_park (owner, at desc);
alter table public.rb_park_levels enable row level security;
alter table public.rb_park enable row level security;
revoke all on public.rb_park_levels, public.rb_park from anon, authenticated;
insert into public.rb_config (key, value) values ('park_day_cap', 300), ('park_full_rounds', 10)
on conflict (key) do nothing;

create or replace function public.rb_park_day(who uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('rounds', count(*) filter (where paid > 0), 'paid', coalesce(sum(paid), 0),
                             'cap', public.rb_cfg('park_day_cap'), 'full', public.rb_cfg('park_full_rounds'))
      from public.rb_park where owner = who and not open and at >= date_trunc('day', now()) $$;

-- tier: 1 easy, 2 medium, 3 hard. A level not played lately is picked at random.
create or replace function public.rb_park_start(tier integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; l public.rb_park_levels%rowtype; rid uuid;
begin
    p := public.rb_lock_me();
    if tier is null or tier not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    update public.rb_park set open = false where owner = p.id and open;
    select * into l from public.rb_park_levels pl
     where pl.tier = rb_park_start.tier
     order by (select count(*) from (select level from public.rb_park where owner = p.id order by at desc limit 12) r
                where r.level = pl.id), public.rb_rand()
     limit 1;
    insert into public.rb_park (owner, level) values (p.id, l.id) returning id into rid;
    return json_build_object('round', rid, 'layout', l.layout, 'best', l.best, 'tier', l.tier, 'day', public.rb_park_day(p.id));
end $$;

-- plays the moves on the board. Returns the number of moves, or -1 if one move is impossible.
create or replace function public.rb_park_play(layout text, moves jsonb) returns integer
language plpgsql immutable set search_path = '' as $$
declare g text[] := string_to_array(layout, null); m jsonb; car text; d integer; cells integer[]; horiz boolean;
        i integer; k integer; n integer := 0; step integer; c integer; target integer;
begin
    if jsonb_typeof(moves) <> 'array' or jsonb_array_length(moves) > 400 then return -1; end if;
    for m in select * from jsonb_array_elements(moves) loop
        car := m ->> 'c'; d := (m ->> 'd')::integer;
        if car is null or length(car) <> 1 or car = '.' or d is null or d = 0 or abs(d) > 5 then return -1; end if;
        cells := array(select i2 - 1 from generate_series(1, 36) i2 where g[i2] = car order by i2);
        if coalesce(array_length(cells, 1), 0) < 2 then return -1; end if;
        horiz := cells[2] - cells[1] = 1;
        step := case when horiz then 1 else 6 end;
        for k in 1 .. abs(d) loop                               -- slide one square at a time
            if d > 0 then
                target := cells[array_length(cells, 1)] + step * k;
            else
                target := cells[1] - step * k;
            end if;
            if target < 0 or target > 35 then return -1; end if;
            if horiz and target / 6 <> cells[1] / 6 then return -1; end if;
            if g[target + 1] <> '.' then return -1; end if;
        end loop;
        foreach c in array cells loop g[c + 1] := '.'; end loop;
        foreach c in array cells loop g[c + d * step + 1] := car; end loop;
        n := n + 1;
    end loop;
    if g[17] <> 'A' or g[18] <> 'A' then return -1; end if;      -- the red car must reach the exit
    return n;
end $$;

create or replace function public.rb_park_finish(round uuid, moves jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_park%rowtype; l public.rb_park_levels%rowtype; n integer;
        secs double precision; pay integer := 0; day json; base integer; top integer;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_park where id = round and owner = p.id for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    update public.rb_park set open = false where id = r.id;
    select * into l from public.rb_park_levels where id = r.level;
    n := public.rb_park_play(l.layout, moves);
    secs := extract(epoch from (clock_timestamp() - r.at));
    if n < 0 then
        return jsonb_build_object('paid', 0, 'why', 'moves', 'coins', p.coins);
    end if;
    if secs < 2 + 0.3 * n or secs > 3600 then                  -- faster than a hand can move the cars
        update public.rb_park set moves = n where id = r.id;
        return jsonb_build_object('paid', 0, 'why', 'time', 'moves', n, 'coins', p.coins);
    end if;
    day := public.rb_park_day(p.id);
    base := (array[10, 15, 25])[l.tier]; top := (array[20, 30, 40])[l.tier];
    pay := base + round((top - base) * least(1.0, l.best::numeric / greatest(n, 1)));
    if (day ->> 'rounds')::int >= public.rb_cfg('park_full_rounds') * 2 then pay := pay / 4;
    elsif (day ->> 'rounds')::int >= public.rb_cfg('park_full_rounds') then pay := pay / 2; end if;
    pay := greatest(0, least(pay, public.rb_cfg('park_day_cap')::int - (day ->> 'paid')::int));
    update public.rb_park set moves = n, paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'park', 0, jsonb_build_object('moves', n, 'best', l.best), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'park', l.id::text);
    return jsonb_build_object('paid', pay, 'moves', n, 'best', l.best, 'coins', p.coins + pay,
                              'day', public.rb_park_day(p.id));
end $$;

-- ---------------------------------------------------------------- quests: Beat Tap or Parking both count
create or replace function public.rb_quest_rows(who uuid)
returns table (quest text, kind text, goal integer, reward integer, progress integer, period timestamptz, left_s integer)
language sql stable security definer set search_path = '' as $$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack')),
         q (quest, kind, goal, reward, progress) as (
            select * from (values
                ('h_rounds', 'hour', 5, 40, (select count(*) from h where game in (select g from casino))::int),
                ('h_mini',   'hour', 2, 40, (select count(*) from h where game in ('mini', 'park'))::int),
                ('h_bet',    'hour', 150, 45, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int),
                ('h_win',    'hour', 200, 45, (select coalesce(sum(paid), 0) from h where game in (select g from casino))::int)
            ) hq (quest, kind, goal, reward, progress)
            where hq.quest = (array['h_rounds', 'h_mini', 'h_bet', 'h_win'])[extract(hour from now())::int % 4 + 1]
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  1, 120, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 120, (select count(*) from d where game in ('mini', 'park'))::int),
            ('w_rounds', 'week', 150, 800, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  10, 800, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 5000, 900, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $$;


-- ---------------------------------------------------------------- more details on profiles
create or replace function public.rb_stats(who uuid) returns json
language sql stable security definer set search_path = '' as $$
    with r as (select * from public.rb_rounds where owner = who and not open),
         g as (select * from r where game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack'))
    select json_build_object(
        'bet', (select coalesce(sum(bet), 0) from g), 'won', (select coalesce(sum(paid), 0) from g),
        'best', (select coalesce(max(paid), 0) from g), 'rounds', (select count(*) from g),
        'cases', (select count(*) from r where game like 'case:%' or game = 'daily'),
        'spins', (select count(*) from r where game = 'spin'),
        'mini', (select count(*) from r where game = 'mini'),
        'park', (select count(*) from r where game = 'park'),
        'worth', (select coalesce(sum(c.value), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item
                   where it.owner = who),
        'first_case', (select min(at) from r where game like 'case:%'),
        'gold', (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
                  where it.owner = who and c.kind = 'badge' and c.cls = 4),
        'trades', (select count(*) from public.rb_trades t where t.state = 'done' and (t.a = who or t.b = who)),
        'items', (select count(*) from public.rb_items it where it.owner = who),
        'badges', (select count(distinct it.item) from public.rb_items it where it.owner = who and it.item like 'badge:%'),
        'friends', (select count(*) from public.rb_friends f where f.ok and (f.a = who or f.b = who))) $$;

create or replace function public.rb_profile(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; friend boolean; mine public.profiles%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into mine from public.profiles where id = me;
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    friend := public.rb_is_friend(me, p.id);
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'since', p.created_at, 'equip', p.equip,
        'admin', p.admin, 'avatar_v', p.avatar_v,
        'seen', case when friend or p.id = me then p.last_beat end,
        'me', p.id = me, 'friend', friend,
        'can_trade', p.id <> me and public.rb_can_trade(p) and public.rb_can_trade(mine),
        'state', (select case when f.ok then 'friend' when f.a = me then 'asked' else 'asks' end
                    from public.rb_friends f where (f.a = me and f.b = p.id) or (f.a = p.id and f.b = me)),
        'online', (friend or p.id = me) and public.rb_online(p),
        'badges', coalesce((select json_agg(x.item order by x.value desc, x.item)
                              from (select distinct it.item, c.value from public.rb_items it
                                      join public.rb_catalog c on c.id = it.item
                                     where it.owner = p.id and c.kind = 'badge') x), '[]'::json),
        'stats', case when friend or p.id = me or mine.admin then public.rb_stats(p.id) end,
        'items', (select count(*) from public.rb_items it where it.owner = p.id));
end $$;

-- ---------------------------------------------------------------- who may call what
revoke all on function public.rb_park_day(uuid), public.rb_park_play(text, jsonb) from public, anon, authenticated;
revoke all on function public.rb_park_start(integer), public.rb_park_finish(uuid, jsonb) from public, anon;
grant execute on function public.rb_park_start(integer), public.rb_park_finish(uuid, jsonb) to authenticated;
revoke all on function public.rb_seed_catalog() from public, anon, authenticated;
revoke all on function public.rb_quest_rows(uuid) from public, anon, authenticated;
