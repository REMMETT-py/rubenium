-- Rubenium 9.2: Mini Golf bots with four levels. Made by overhaul/golf/make_087.py from overhaul/golf/bot_odds.json
-- (do not edit by hand: run overhaul/golf/bots.py, then make_087.py). Safe to run twice.
--
-- Whoever opens a Mini Golf room picks the level of the bots in the empty seats: Easy, Medium, Hard or Professional
-- (rb_golf_parties.bot_level 0-3; a bot seat's skill is its level). The strokes a bot takes on a hole come from
-- rb_golf_bot_odds: every hole was played many times with the real ball physics by a bot of each level that searches
-- its shots (Hard and Professional look one shot ahead and go for the shots that still drop when hit a little off)
-- and then hits them with the error of its level. Holes 101-160 are the same holes mirrored, so they share the odds.
-- Bots never take the pot, as before.
begin;

create table if not exists public.rb_golf_bot_odds (hole integer not null, level text not null, p smallint[] not null,
                                                     primary key (hole, level));
alter table public.rb_golf_bot_odds enable row level security;
revoke all on public.rb_golf_bot_odds from public, anon, authenticated;
truncate public.rb_golf_bot_odds;
insert into public.rb_golf_bot_odds (hole, level, p) values
(1, 'easy', '{8,56,30,2,5,0}'),
(1, 'medium', '{19,62,16,3,0,0}'),
(1, 'hard', '{72,28,0,0,0,0}'),
(1, 'pro', '{98,2,0,0,0,0}'),
(2, 'easy', '{25,39,23,8,3,2}'),
(2, 'medium', '{39,45,12,3,0,0}'),
(2, 'hard', '{94,6,0,0,0,0}'),
(2, 'pro', '{100,0,0,0,0,0}'),
(3, 'easy', '{0,47,42,6,3,2}'),
(3, 'medium', '{0,78,20,2,0,0}'),
(3, 'hard', '{0,95,5,0,0,0}'),
(3, 'pro', '{0,100,0,0,0,0}'),
(4, 'easy', '{0,39,28,16,11,6}'),
(4, 'medium', '{5,64,17,11,2,2}'),
(4, 'hard', '{19,70,11,0,0,0}'),
(4, 'pro', '{56,44,0,0,0,0}'),
(5, 'easy', '{0,0,5,22,38,36}'),
(5, 'medium', '{0,3,78,17,2,0}'),
(5, 'hard', '{0,47,53,0,0,0}'),
(5, 'pro', '{0,81,19,0,0,0}'),
(6, 'easy', '{0,12,23,30,14,20}'),
(6, 'medium', '{0,33,55,11,0,2}'),
(6, 'hard', '{0,84,16,0,0,0}'),
(6, 'pro', '{0,100,0,0,0,0}'),
(7, 'easy', '{0,12,41,22,16,9}'),
(7, 'medium', '{0,44,39,16,2,0}'),
(7, 'hard', '{0,61,38,2,0,0}'),
(7, 'pro', '{0,95,5,0,0,0}'),
(8, 'easy', '{8,56,17,11,2,6}'),
(8, 'medium', '{28,44,20,6,2,0}'),
(8, 'hard', '{64,36,0,0,0,0}'),
(8, 'pro', '{95,5,0,0,0,0}'),
(9, 'easy', '{3,55,33,6,0,3}'),
(9, 'medium', '{6,78,11,2,3,0}'),
(9, 'hard', '{56,44,0,0,0,0}'),
(9, 'pro', '{98,2,0,0,0,0}'),
(10, 'easy', '{2,39,27,25,5,3}'),
(10, 'medium', '{2,70,20,5,3,0}'),
(10, 'hard', '{12,80,5,3,0,0}'),
(10, 'pro', '{34,64,2,0,0,0}'),
(11, 'easy', '{33,36,19,6,3,3}'),
(11, 'medium', '{42,31,22,2,2,2}'),
(11, 'hard', '{88,11,2,0,0,0}'),
(11, 'pro', '{100,0,0,0,0,0}'),
(12, 'easy', '{34,47,14,3,2,0}'),
(12, 'medium', '{56,38,6,0,0,0}'),
(12, 'hard', '{95,5,0,0,0,0}'),
(12, 'pro', '{98,2,0,0,0,0}'),
(13, 'easy', '{20,36,28,9,2,5}'),
(13, 'medium', '{34,48,14,2,2,0}'),
(13, 'hard', '{94,6,0,0,0,0}'),
(13, 'pro', '{100,0,0,0,0,0}'),
(14, 'easy', '{0,0,6,28,20,45}'),
(14, 'medium', '{0,42,45,11,2,0}'),
(14, 'hard', '{0,59,41,0,0,0}'),
(14, 'pro', '{0,91,9,0,0,0}'),
(15, 'easy', '{0,47,31,19,2,2}'),
(15, 'medium', '{6,41,41,9,3,0}'),
(15, 'hard', '{9,86,5,0,0,0}'),
(15, 'pro', '{19,81,0,0,0,0}'),
(16, 'easy', '{23,45,23,3,2,3}'),
(16, 'medium', '{30,50,14,6,0,0}'),
(16, 'hard', '{94,6,0,0,0,0}'),
(16, 'pro', '{100,0,0,0,0,0}'),
(17, 'easy', '{0,0,11,38,19,33}'),
(17, 'medium', '{0,0,42,42,14,2}'),
(17, 'hard', '{0,6,88,6,0,0}'),
(17, 'pro', '{0,52,48,0,0,0}'),
(18, 'easy', '{0,17,27,22,19,16}'),
(18, 'medium', '{0,47,27,16,5,6}'),
(18, 'hard', '{0,64,25,8,0,3}'),
(18, 'pro', '{0,80,16,3,0,2}'),
(19, 'easy', '{2,20,36,23,16,3}'),
(19, 'medium', '{5,38,38,12,6,2}'),
(19, 'hard', '{22,61,17,0,0,0}'),
(19, 'pro', '{42,47,11,0,0,0}'),
(20, 'easy', '{27,31,17,14,2,9}'),
(20, 'medium', '{44,45,9,2,0,0}'),
(20, 'hard', '{89,11,0,0,0,0}'),
(20, 'pro', '{100,0,0,0,0,0}'),
(21, 'easy', '{0,25,28,25,12,9}'),
(21, 'medium', '{0,41,38,9,6,6}'),
(21, 'hard', '{2,94,5,0,0,0}'),
(21, 'pro', '{25,72,3,0,0,0}'),
(22, 'easy', '{0,0,0,0,3,97}'),
(22, 'medium', '{0,0,0,14,48,38}'),
(22, 'hard', '{0,0,0,64,33,3}'),
(22, 'pro', '{0,0,0,95,5,0}'),
(23, 'easy', '{0,28,50,12,5,5}'),
(23, 'medium', '{8,41,36,11,5,0}'),
(23, 'hard', '{42,48,9,0,0,0}'),
(23, 'pro', '{70,30,0,0,0,0}'),
(24, 'easy', '{0,33,27,30,5,6}'),
(24, 'medium', '{0,44,34,16,6,0}'),
(24, 'hard', '{0,72,28,0,0,0}'),
(24, 'pro', '{0,98,2,0,0,0}'),
(25, 'easy', '{0,0,2,6,27,66}'),
(25, 'medium', '{0,0,3,61,23,12}'),
(25, 'hard', '{0,0,9,89,2,0}'),
(25, 'pro', '{0,0,12,83,5,0}'),
(26, 'easy', '{39,34,9,8,3,6}'),
(26, 'medium', '{38,28,16,9,6,3}'),
(26, 'hard', '{97,3,0,0,0,0}'),
(26, 'pro', '{100,0,0,0,0,0}'),
(27, 'easy', '{30,42,16,8,2,3}'),
(27, 'medium', '{59,30,11,0,0,0}'),
(27, 'hard', '{83,17,0,0,0,0}'),
(27, 'pro', '{98,2,0,0,0,0}'),
(28, 'easy', '{0,16,47,28,3,6}'),
(28, 'medium', '{0,55,41,3,2,0}'),
(28, 'hard', '{0,95,5,0,0,0}'),
(28, 'pro', '{0,100,0,0,0,0}'),
(29, 'easy', '{0,42,34,11,9,3}'),
(29, 'medium', '{0,52,39,6,3,0}'),
(29, 'hard', '{0,72,27,2,0,0}'),
(29, 'pro', '{0,97,2,2,0,0}'),
(30, 'easy', '{28,28,17,9,8,9}'),
(30, 'medium', '{45,36,12,6,0,0}'),
(30, 'hard', '{88,12,0,0,0,0}'),
(30, 'pro', '{100,0,0,0,0,0}'),
(31, 'easy', '{0,2,22,31,20,25}'),
(31, 'medium', '{0,28,33,25,8,6}'),
(31, 'hard', '{0,69,25,6,0,0}'),
(31, 'pro', '{0,97,3,0,0,0}'),
(32, 'easy', '{27,52,19,2,2,0}'),
(32, 'medium', '{17,69,9,3,2,0}'),
(32, 'hard', '{25,75,0,0,0,0}'),
(32, 'pro', '{41,59,0,0,0,0}'),
(33, 'easy', '{6,33,33,12,9,6}'),
(33, 'medium', '{70,27,3,0,0,0}'),
(33, 'hard', '{86,14,0,0,0,0}'),
(33, 'pro', '{100,0,0,0,0,0}'),
(34, 'easy', '{0,3,30,28,25,14}'),
(34, 'medium', '{0,20,34,30,11,5}'),
(34, 'hard', '{0,53,39,6,2,0}'),
(34, 'pro', '{2,83,16,0,0,0}'),
(35, 'easy', '{41,33,14,8,2,3}'),
(35, 'medium', '{48,38,5,5,2,3}'),
(35, 'hard', '{78,22,0,0,0,0}'),
(35, 'pro', '{100,0,0,0,0,0}'),
(36, 'easy', '{0,0,0,0,9,91}'),
(36, 'medium', '{0,0,0,0,27,73}'),
(36, 'hard', '{0,0,0,0,92,8}'),
(36, 'pro', '{0,0,0,0,98,2}'),
(37, 'easy', '{38,39,14,5,2,3}'),
(37, 'medium', '{36,44,16,5,0,0}'),
(37, 'hard', '{94,6,0,0,0,0}'),
(37, 'pro', '{100,0,0,0,0,0}'),
(38, 'easy', '{0,53,42,5,0,0}'),
(38, 'medium', '{0,86,11,3,0,0}'),
(38, 'hard', '{0,100,0,0,0,0}'),
(38, 'pro', '{0,100,0,0,0,0}'),
(39, 'easy', '{0,6,56,20,12,5}'),
(39, 'medium', '{0,55,41,3,2,0}'),
(39, 'hard', '{0,78,22,0,0,0}'),
(39, 'pro', '{0,100,0,0,0,0}'),
(40, 'easy', '{0,19,45,23,8,5}'),
(40, 'medium', '{9,41,25,12,6,6}'),
(40, 'hard', '{61,20,11,6,0,2}'),
(40, 'pro', '{97,3,0,0,0,0}'),
(41, 'easy', '{31,33,27,5,2,3}'),
(41, 'medium', '{50,33,14,3,0,0}'),
(41, 'hard', '{80,20,0,0,0,0}'),
(41, 'pro', '{100,0,0,0,0,0}'),
(42, 'easy', '{5,44,30,11,5,6}'),
(42, 'medium', '{28,52,12,3,5,0}'),
(42, 'hard', '{58,41,2,0,0,0}'),
(42, 'pro', '{86,14,0,0,0,0}'),
(43, 'easy', '{48,23,19,6,3,0}'),
(43, 'medium', '{53,38,6,3,0,0}'),
(43, 'hard', '{94,6,0,0,0,0}'),
(43, 'pro', '{100,0,0,0,0,0}'),
(44, 'easy', '{0,42,33,16,5,5}'),
(44, 'medium', '{6,53,28,8,2,3}'),
(44, 'hard', '{17,64,16,3,0,0}'),
(44, 'pro', '{42,56,2,0,0,0}'),
(45, 'easy', '{0,2,14,31,31,22}'),
(45, 'medium', '{0,2,36,50,9,3}'),
(45, 'hard', '{0,31,56,12,0,0}'),
(45, 'pro', '{0,95,5,0,0,0}'),
(46, 'easy', '{3,34,42,14,6,0}'),
(46, 'medium', '{5,73,22,0,0,0}'),
(46, 'hard', '{27,73,0,0,0,0}'),
(46, 'pro', '{70,30,0,0,0,0}'),
(47, 'easy', '{38,16,17,9,12,8}'),
(47, 'medium', '{52,27,14,5,3,0}'),
(47, 'hard', '{97,3,0,0,0,0}'),
(47, 'pro', '{100,0,0,0,0,0}'),
(48, 'easy', '{3,36,16,14,11,20}'),
(48, 'medium', '{11,9,47,17,8,8}'),
(48, 'hard', '{22,33,19,8,9,9}'),
(48, 'pro', '{62,34,3,0,0,0}'),
(49, 'easy', '{0,17,28,22,12,20}'),
(49, 'medium', '{0,36,44,11,9,0}'),
(49, 'hard', '{0,59,36,3,2,0}'),
(49, 'pro', '{0,92,8,0,0,0}'),
(50, 'easy', '{12,48,25,11,3,0}'),
(50, 'medium', '{38,53,9,0,0,0}'),
(50, 'hard', '{88,12,0,0,0,0}'),
(50, 'pro', '{100,0,0,0,0,0}'),
(51, 'easy', '{33,42,14,9,2,0}'),
(51, 'medium', '{17,47,22,8,5,2}'),
(51, 'hard', '{91,9,0,0,0,0}'),
(51, 'pro', '{100,0,0,0,0,0}'),
(52, 'easy', '{5,36,38,19,2,2}'),
(52, 'medium', '{25,52,22,2,0,0}'),
(52, 'hard', '{58,42,0,0,0,0}'),
(52, 'pro', '{92,8,0,0,0,0}'),
(53, 'easy', '{0,30,41,19,5,6}'),
(53, 'medium', '{0,67,25,8,0,0}'),
(53, 'hard', '{3,88,9,0,0,0}'),
(53, 'pro', '{34,66,0,0,0,0}'),
(54, 'easy', '{9,52,22,14,3,0}'),
(54, 'medium', '{50,34,14,0,2,0}'),
(54, 'hard', '{95,5,0,0,0,0}'),
(54, 'pro', '{100,0,0,0,0,0}'),
(55, 'easy', '{2,42,38,9,6,3}'),
(55, 'medium', '{8,53,25,3,9,2}'),
(55, 'hard', '{2,80,17,2,0,0}'),
(55, 'pro', '{27,72,2,0,0,0}'),
(56, 'easy', '{36,19,20,14,6,5}'),
(56, 'medium', '{50,38,8,3,2,0}'),
(56, 'hard', '{100,0,0,0,0,0}'),
(56, 'pro', '{100,0,0,0,0,0}'),
(57, 'easy', '{0,41,41,17,0,2}'),
(57, 'medium', '{8,66,23,3,0,0}'),
(57, 'hard', '{56,41,3,0,0,0}'),
(57, 'pro', '{89,11,0,0,0,0}'),
(58, 'easy', '{36,41,20,2,2,0}'),
(58, 'medium', '{56,19,17,6,0,2}'),
(58, 'hard', '{94,6,0,0,0,0}'),
(58, 'pro', '{100,0,0,0,0,0}'),
(59, 'easy', '{2,48,23,17,6,3}'),
(59, 'medium', '{16,62,19,3,0,0}'),
(59, 'hard', '{67,30,3,0,0,0}'),
(59, 'pro', '{81,19,0,0,0,0}'),
(60, 'easy', '{16,39,22,9,9,5}'),
(60, 'medium', '{48,17,19,6,3,6}'),
(60, 'hard', '{84,16,0,0,0,0}'),
(60, 'pro', '{100,0,0,0,0,0}');

alter table public.rb_golf_parties add column if not exists bot_level smallint not null default 1;

-- a bot's plan for a hole: how many strokes (drawn from the hole's odds for its level) and how fast it plays
create or replace function public.rb_party_bot_plan2(hid integer, skill double precision) returns jsonb
language plpgsql volatile security definer set search_path to '' as $$
declare lv integer := greatest(0, least(3, round(coalesce(skill, 1))::int)); odds smallint[]; r float8; acc float8 := 0;
        tot float8; n integer := 6;
begin
    select p into odds from public.rb_golf_bot_odds
     where hole = coalesce(hid, 0) % 100 and level = (array['easy', 'medium', 'hard', 'pro'])[lv + 1];
    if odds is null then return public.rb_party_bot_plan(skill); end if;
    tot := (select sum(x) from unnest(odds) x);
    r := public.rb_rand() * greatest(tot, 1);
    for k in 1 .. 6 loop
        acc := acc + odds[k];
        if r < acc then n := k; exit; end if;
    end loop;
    return jsonb_build_object('n', n, 'every', (array[4.5, 4.0, 3.5, 3.0])[lv + 1] + public.rb_rand() * (array[4.5, 3.5, 2.5, 1.5])[lv + 1],
                              'level', lv);
end $$;

-- the live party functions: bot seats get the room's level and plans from the odds
do $patch$
declare src text; out_ text;
begin
    select pg_get_functiondef('public.rb_party_start(uuid)'::regprocedure) into src;
    out_ := replace(src, 'names[k + 1], public.rb_rand(), array_fill', 'names[k + 1], g.bot_level::float8, array_fill');
    out_ := replace(out_, 'set plan = public.rb_party_bot_plan(skill) where', 'set plan = public.rb_party_bot_plan2(g.holes[1], skill) where');
    if out_ <> src then execute out_; end if;
    select pg_get_functiondef('public.rb_party_tick(uuid)'::regprocedure) into src;
    out_ := replace(src, 'then public.rb_party_bot_plan(skill) end', 'then public.rb_party_bot_plan2(g.holes[g.hole + 1], skill) end');
    if out_ <> src then execute out_; end if;
    select pg_get_functiondef('public.rb_party_json(uuid, uuid)'::regprocedure) into src;
    if position('''bot_level''' in src) = 0 then
        execute replace(src, '''holes'', to_jsonb(g.holes),', '''holes'', to_jsonb(g.holes), ''bot_level'', g.bot_level,');
    end if;
    select pg_get_functiondef('public.rb_party_list()'::regprocedure) into src;
    if position('''bot_level''' in src) = 0 then
        execute replace(src, '''size'', g.size, ''bet'', g.bet,', '''size'', g.size, ''bet'', g.bet, ''bot_level'', g.bot_level,');
    end if;
end $patch$;

-- open a room with a bot level (the old three-argument call keeps Medium)
create or replace function public.rb_party_create(size integer, bet integer, holes integer, bot_level integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare r jsonb;
begin
    if bot_level is null or bot_level not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
    r := public.rb_party_create(size, bet, holes);
    update public.rb_golf_parties set bot_level = rb_party_create.bot_level where id = (r ->> 'id')::uuid;
    return public.rb_party_json((r ->> 'id')::uuid, auth.uid());
end $$;

revoke all on function public.rb_party_bot_plan2(integer, double precision) from public, anon, authenticated;
revoke all on function public.rb_party_create(integer, integer, integer, integer) from public, anon;
grant execute on function public.rb_party_create(integer, integer, integer, integer) to authenticated;

commit;
