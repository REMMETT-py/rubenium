-- ================================================================ Rubenium 5.3: Mini Golf 3, 5, 10 or 15 holes; 60 holes
-- The 5.3 app asks for a number of holes when it starts a round or opens a match (3, 5, 10 or 15). Twelve new holes
-- (49-60): golf_hole_total goes to 60 once the 5.3 app is out (older apps don't have the new holes). Safe to run again.
begin;

create or replace function public.rb_golf_pick(n integer) returns integer[]
language sql security definer set search_path = '' as $$
    select array_agg(h) from (
        select h + case when public.rb_rand() < 0.5 then 100 else 0 end as h
          from generate_series(1, coalesce(public.rb_cfg('golf_hole_total'), 24)::int) h order by public.rb_rand()
         limit greatest(1, least(15, n))) x $$;

create or replace function public.rb_golf_holes_ok(n integer) returns integer
language plpgsql immutable set search_path = '' as $$
begin
    if n is null then return 5; end if;
    if n not in (3, 5, 10, 15) then raise exception 'rb_bad_choice'; end if;
    return n;
end $$;

create or replace function public.rb_golf_create(bet integer, holes integer) returns json
language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; gid uuid; hs integer[]; n integer; old record;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    for old in select id from public.rb_golf where (a = p.id or b = p.id) and state in ('open', 'asked', 'live') loop
        perform public.rb_golf_tick(old.id);
    end loop;
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    hs := public.rb_golf_pick(public.rb_golf_holes_ok(holes));
    n := array_length(hs, 1);
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf (a, b, bet, holes, state, a_strokes, b_strokes)
        values (p.id, null, bet, hs, 'open', array_fill(0, array[n]), array_fill(0, array[n])) returning id into gid;
    return json_build_object('id', gid, 'coins', p.coins - bet);
end $function$;

create or replace function public.rb_golf_solo_start(holes integer) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare p public.profiles%rowtype; g public.rb_golf_solo%rowtype; hs integer[];
begin
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    update public.rb_golf_solo set state = 'quit', done_at = now() where owner = p.id and state = 'live';
    hs := public.rb_golf_pick(public.rb_golf_holes_ok(holes));
    insert into public.rb_golf_solo (owner, holes, strokes) values (p.id, hs, array_fill(0, array[array_length(hs, 1)]))
        returning * into g;
    return public.rb_golf_solo_json(g);
end $$;

revoke all on function public.rb_golf_pick(integer), public.rb_golf_holes_ok(integer) from public, anon, authenticated;
revoke all on function public.rb_golf_create(integer, integer), public.rb_golf_solo_start(integer) from public, anon;
grant execute on function public.rb_golf_create(integer, integer), public.rb_golf_solo_start(integer) to authenticated;
commit;
-- at release: update public.rb_config set value = 60 where key = 'golf_hole_total';
