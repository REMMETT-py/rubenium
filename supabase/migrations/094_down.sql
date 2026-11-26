-- Undo of 094_v94_economy.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
CREATE OR REPLACE FUNCTION public.mz_bot(b jsonb, s integer, level text)
 RETURNS integer
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare h text := b ->> 'h'; v text := b ->> 'v'; p1 integer := (b -> 'p' ->> 0)::int; p2 integer := (b -> 'p' ->> 1)::int;
        w1 integer := (b -> 'w' ->> 0)::int; w2 integer := (b -> 'w' ->> 1)::int;
        me integer := case when s = 1 then p1 else p2 end; op integer := case when s = 1 then p2 else p1 end;
        goal integer := case when s = 1 then 0 else 8 end; depth integer; slip numeric; deadline timestamptz;
        m integer; sc integer; nh text; nv text; n1 integer; n2 integer; nw1 integer; nw2 integer; a integer;
        scored integer[] := '{}'; moves integer[] := '{}'; best integer; i integer; k integer; path integer[];
        cands integer[]; d integer; alpha integer; best_m integer; pick integer;
begin
    path := public.mz_path(h, v, me, goal);
    if level = 'easy' then                                         -- wanders: mostly along its path, walls at random
        if (case when s = 1 then w1 else w2 end) > 0 and public.rb_rand() < 0.22 then
            for i in 1..12 loop
                m := case when public.rb_rand() < 0.5 then 100 else 200 end + floor(public.rb_rand() * 64)::int;
                if public.mz_play(b, s, m) is not null then return m; end if;
            end loop;
        end if;
        cands := public.mz_steps(h, v, me, op);
        if public.rb_rand() < 0.3 or cardinality(path) = 0 then
            return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
        end if;
        if path[1] = any(cands) then return path[1]; end if;
        return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
    end if;
    depth := case level when 'medium' then 1 when 'hard' then 2 else 4 end;
    slip := case level when 'medium' then 0.14 when 'hard' then 0.05 else 0 end;
    deadline := clock_timestamp() + make_interval(secs => case level when 'insane' then 2.6 else 1.5 end);
    -- a sure race: just run
    if (case when s = 1 then w2 else w1 end) = 0 and cardinality(path) > 0
       and public.mz_dist(h, v, me, goal) <= public.mz_dist(h, v, op, 8 - goal) then
        if path[1] = any(public.mz_steps(h, v, me, op)) then return path[1]; end if;
    end if;
    cands := public.mz_candidates(h, v, p1, p2, w1, w2, s, case when level = 'medium' then 3 else 7 end);
    -- Professional deepens until its time is up and keeps the last search it finished; the others look depth ahead
    for d in (case when level = 'insane' then 1 else depth end)..depth loop
        scored := '{}'; moves := '{}'; alpha := -100000;
        foreach m in array cands loop
            nh := h; nv := v; n1 := p1; n2 := p2; nw1 := w1; nw2 := w2;
            if m < 100 then
                if s = 1 then n1 := m; else n2 := m; end if;
            else
                a := m % 100;
                if m < 200 then nh := overlay(h placing s::text from a + 1 for 1); else nv := overlay(v placing s::text from a + 1 for 1); end if;
                if public.mz_dist(nh, nv, p1, 0) >= 999 or public.mz_dist(nh, nv, p2, 8) >= 999 then continue; end if;
                if s = 1 then nw1 := w1 - 1; else nw2 := w2 - 1; end if;
            end if;
            if (s = 1 and n1 / 9 = 0) or (s = 2 and n2 / 9 = 8) then return m; end if;       -- home: win now
            sc := -public.mz_search(nh, nv, n1, n2, nw1, nw2, 3 - s, d - 1, -100000,
                                    case when slip > 0 then 100000 else -alpha + 1 end, deadline);
            if sc > alpha then alpha := sc; end if;
            scored := scored || sc; moves := moves || m;
        end loop;
        exit when cardinality(moves) = 0;
        exit when d > 1 and clock_timestamp() > deadline;          -- cut short: keep the last full search
        best := -100001; best_m := null;
        for i in 1..cardinality(moves) loop                         -- ties: a step beats a wall, so it never stalls
            if scored[i] > best or (scored[i] = best and moves[i] < 100 and coalesce(best_m, 999) >= 100) then
                best := scored[i]; best_m := moves[i];
            end if;
        end loop;
        pick := best_m;
        k := array_position(cands, best_m);                         -- the next depth looks at the best move first
        if k is not null and k > 1 then cands := best_m || (cands[1:k - 1] || cands[k + 1:]); end if;
        exit when clock_timestamp() > deadline or abs(best) >= 5000;
    end loop;
    m := coalesce(pick, path[1]);
    -- Medium and Hard slip now and then: the second best move (never one that loses on the spot)
    if slip > 0 and public.rb_rand() < slip and cardinality(moves) > 1 then
        k := null; sc := -100001;
        for i in 1..cardinality(moves) loop
            if moves[i] <> m and scored[i] > sc and scored[i] > -5000 then sc := scored[i]; k := moves[i]; end if;
        end loop;
        if k is not null then m := k; end if;
    end if;
    return m;
end $function$;
drop function if exists public.rb_forge_from cascade;
CREATE OR REPLACE FUNCTION public.rb_forge_state(who uuid)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with t as (select (public.rb_tier(who) ->> 'tier')::int as tier),
         d as (select coalesce(public.rb_cfg('forge_day_' || t.tier), public.rb_cfg('forge_day'), 5)::int as cap from t)
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 250)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.005) / 10) * 10)::bigint),
        'cap', d.cap,
        'left', greatest(0, d.cap - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris'))))
    from d $function$;
drop function if exists public.rb_hourly_keys cascade;
CREATE OR REPLACE FUNCTION public.rb_login_rewards()
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select '[{"coins":150},{"coins":250},{"keys":1},{"coins":400},{"keys":2},{"coins":750},{"coins":1500,"keys":1,"case":"premium"}]'::jsonb $function$;
drop function if exists public.rb_reset_94 cascade;
CREATE OR REPLACE FUNCTION public.rb_spin_table(m numeric)
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select jsonb_build_object(
        'slots', jsonb_build_array(public.rb_scaled(100, m), public.rb_scaled(150, m), public.rb_scaled(250, m),
                                   public.rb_scaled(400, m), public.rb_scaled(600, m), public.rb_scaled(1000, m),
                                   public.rb_scaled(2000, m), -1, -2, -3),
        'odds', jsonb_build_array(1800, 1800, 1700, 1300, 900, 600, 300, 800, 400, 400)) $function$;
CREATE OR REPLACE FUNCTION public.rb_tier(who uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare c bigint := coalesce((select coins from public.profiles where id = who), 0);
        it bigint := public.rb_wealth_items(who); w bigint := c + it; t integer := 0; i integer; fl integer;
begin
    for i in 1 .. 4 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    fl := least(4, greatest(0, coalesce((select tier_floor from public.profiles where id = who), 0)));
    t := greatest(t, fl);
    return jsonb_build_object('tier', t, 'name', (array['Poor', 'Average', 'Investor', 'Businessman', 'Casino Legend'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'coins', c, 'items', it,
                              'at', case when t > 0 then public.rb_cfg('tier_at_' || t) else 0 end,
                              'next', case when t < 4 then public.rb_cfg('tier_at_' || (t + 1)) end,
                              'next_name', case when t < 4 then (array['Poor', 'Average', 'Investor', 'Businessman',
                                                                      'Casino Legend'])[t + 2] end,
                              'top', 4, 'cap_x', coalesce(public.rb_cfg('cap_x_' || t), 1));       -- 9.2.1
end $function$;
CREATE OR REPLACE FUNCTION public.rb_tier_keep(who uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare t integer := (public.rb_tier(who) ->> 'tier')::int;
begin
    update public.profiles set tier_floor = t where id = who and tier_floor < t;
    return t;
end $function$;
CREATE OR REPLACE FUNCTION public.rv_bot(b text, p text, level text)
 RETURNS integer
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare o text := case p when '1' then '2' else '1' end; mv integer[] := public.rv_moves(b, p); m integer; r integer;
        b1 text; b2 text; replies integer[]; v integer; worst integer; best integer := null; pick integer;
begin
    if cardinality(mv) = 0 then return null; end if;
    if level = 'easy' then return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    if level = 'medium' and public.rb_rand() < 0.35 then return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    foreach m in array mv loop
        b1 := public.rv_play(b, m, p);
        if level = 'medium' then
            v := cardinality(public.rv_flips(b, m, p)) * 10;
        elsif level = 'hard' then
            v := public.rv_eval(b1, p) - 6 * cardinality(public.rv_moves(b1, o));
        elsif level = 'insane' then                             -- insane: three moves ahead, deeper at the end
            v := -public.rv_search(b1, o, case when public.rv_count(b, '.') <= 7 then 6 else 2 end, -1000000, 1000000);
        else                                                    -- (not used) one answer deep
            replies := public.rv_moves(b1, o);
            if cardinality(replies) = 0 then
                v := public.rv_eval(b1, p) + 60;                 -- they must pass: great
            else
                worst := null;
                foreach r in array replies loop
                    b2 := public.rv_play(b1, r, o);
                    v := public.rv_eval(b2, p);
                    if worst is null or v < worst then worst := v; end if;
                end loop;
                v := worst - 5 * cardinality(replies);
            end if;
        end if;
        v := v * 4 + floor(public.rb_rand() * 4)::int;           -- equal moves: not always the same one
        if best is null or v > best then best := v; pick := m; end if;
    end loop;
    return pick;
end $function$;
CREATE OR REPLACE FUNCTION public.tri_bot(b jsonb, s integer, level text)
 RETURNS integer
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me integer[] := public.tri_q(b, s); op integer[] := public.tri_q(b, 3 - s); nm integer[]; cv integer;
        sc integer; best integer; pick integer; nbest integer := 0; wins integer[] := '{}'; safe integer[] := '{}';
        allm integer[] := '{}'; scores integer[] := array_fill(0, array[9]); r float8 := public.rb_rand();
begin
    for m in 0..8 loop
        continue when m = any(me) or m = any(op);
        allm := allm || m;
        nm := public.tri_add(me, m);
        if public.tri_win(nm) then
            wins := wins || m; sc := 2000;
        else
            cv := public.tri_val(op, nm);                             -- the other side to move after it
            sc := case when cv < 0 then 1000 + cv when cv > 0 then -1000 + cv else 0 end;
            if cv <> 1 then safe := safe || m; end if;                -- it does not hand them a win at once
        end if;
        scores[m + 1] := sc;
        if best is null or sc > best then best := sc; pick := m; nbest := 1;
        elsif sc = best then nbest := nbest + 1; if public.rb_rand() * nbest < 1 then pick := m; end if; end if;
    end loop;
    if cardinality(allm) = 0 then return null; end if;
    if level = 'insane' then return pick; end if;
    if level = 'hard' then
        if cardinality(wins) > 0 or r >= 0.14 then return pick; end if;
        if cardinality(safe) > 0 then return safe[1 + floor(public.rb_rand() * cardinality(safe))::int]; end if;
        return pick;
    end if;
    if level = 'medium' then
        if cardinality(wins) > 0 then return wins[1]; end if;
        if r < 0.3 then return pick; end if;
        if cardinality(safe) > 0 and public.rb_rand() < 0.85 then
            return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
        end if;
        return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
    end if;
    if cardinality(wins) > 0 and r < 0.55 then return wins[1]; end if;   -- easy
    if cardinality(safe) > 0 and public.rb_rand() < 0.4 then
        return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
    end if;
    return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
end $function$;
delete from public.rb_config where key = 'hourly_keys';
delete from public.rb_config where key = 'reset_094';
update public.rb_config set value = 25000 where key = 'tier_at_1';
update public.rb_config set value = 100000 where key = 'tier_at_2';
update public.rb_config set value = 250000 where key = 'tier_at_3';
update public.rb_config set value = 1000000 where key = 'tier_at_4';
commit;
