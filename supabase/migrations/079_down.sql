-- Undo of 079_v91_skill.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
CREATE OR REPLACE FUNCTION public.rb_c4_finish(gid uuid, outcome text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare g public.rb_c4%rowtype; m numeric; pay integer := 0; profit bigint; capped boolean := false; c bigint;
begin
    select * into g from public.rb_c4 where id = gid and state = 'live' for update;
    if not found then raise exception 'rb_round_gone'; end if;
    if outcome = 'win' then
        m := public.rb_c4_mult(g.level);
        select coalesce(sum(paid - bet), 0) into profit from public.rb_rounds
         where owner = g.owner and game = 'c4' and at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('c4_day_profit'), 15000) then m := 1; capped := true; end if;
        pay := public.rb_win(g.owner, g.bet * m, 'c4');
    elsif outcome = 'draw' then
        pay := public.rb_win(g.owner, g.bet, 'c4');
    end if;
    update public.rb_c4 set state = 'done', outcome = rb_c4_finish.outcome, paid = pay, updated_at = now() where id = gid;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (g.owner, 'c4', g.bet, jsonb_build_object('level', g.level, 'moves', g.moves, 'outcome', outcome), false, pay);
    select coins into c from public.profiles where id = g.owner;
    return jsonb_build_object('paid', pay, 'capped', capped, 'coins', c);
end $function$;
CREATE OR REPLACE FUNCTION public.rb_c4_start(level text, bet integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; g public.rb_c4%rowtype; first_ boolean;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if level not in ('easy', 'medium', 'hard', 'pro') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_c4_close(p.id);
    perform public.rb_bet(p, bet, 'c4');
    first_ := level in ('hard', 'pro') or (level = 'medium' and public.rb_rand() < 0.5);
    insert into public.rb_c4 (owner, level, bet, bot_first, turn_by)
        values (p.id, level, bet, first_, case when first_ then null
                                               else now() + make_interval(secs => coalesce(public.rb_cfg('c4_turn_secs'), 30) + 5) end)
        returning * into g;
    return public.rb_remember(p.id, req, public.rb_c4_json(g) || jsonb_build_object('coins', p.coins - bet));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_colour(action text, level integer, bet integer, vals jsonb, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; t double precision := extract(epoch from now());
        view_s numeric; ans_s numeric; h double precision; s double precision; v double precision;
        ph double precision; ps double precision; pv double precision;
        de double precision; acc numeric; mult numeric; pay integer := 0; profit bigint; capped boolean := false;
        shown double precision; late boolean := false; lv integer;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    if action <> 'show' then
        res := public.rb_done(p.id, req);
        if res is not null then return res; end if;
    end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'colour' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
        end if;
        if level is null or level not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
        view_s := (array[6, 4, 2.5])[level + 1];
        ans_s := (array[30, 20, 10])[level + 1];
        h := floor(public.rb_rand() * 360);
        if level = 0 then s := 55 + floor(public.rb_rand() * 46); v := 60 + floor(public.rb_rand() * 41);
        elsif level = 1 then s := 30 + floor(public.rb_rand() * 56); v := 35 + floor(public.rb_rand() * 56);
        else s := 20 + floor(public.rb_rand() * 56); v := 30 + floor(public.rb_rand() * 56); end if;
        perform public.rb_bet(p, bet, 'colour');
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'colour', bet, jsonb_build_object('level', level, 'h', h, 's', s, 'v', v, 'view', view_s, 'ans', ans_s,
                                                            'started', t, 'shown', null), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'phase', 'ready', 'level', level, 'view', view_s,
                                                                'ans', ans_s, 'bet', bet, 'coins', p.coins - bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    lv := (r.secret ->> 'level')::int;
    view_s := (r.secret ->> 'view')::numeric; ans_s := (r.secret ->> 'ans')::numeric;
    shown := (r.secret ->> 'shown')::double precision;
    if action = 'show' then
        if shown is not null then raise exception 'rb_round_gone'; end if;
        if t > (r.secret ->> 'started')::double precision + 90 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            raise exception 'rb_round_gone';
        end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('shown', t) where id = r.id;
        return jsonb_build_object('open', true, 'phase', 'show', 'h', (r.secret ->> 'h')::double precision,
                                  's', (r.secret ->> 's')::double precision, 'v', (r.secret ->> 'v')::double precision,
                                  'view', view_s, 'ans', ans_s);
    end if;
    if action = 'state' then
        if shown is null then
            if t > (r.secret ->> 'started')::double precision + 90 then
                update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
                return jsonb_build_object('open', false);
            end if;
            return jsonb_build_object('open', true, 'phase', 'ready', 'level', lv, 'view', view_s, 'ans', ans_s, 'bet', r.bet);
        end if;
        if t > shown + view_s + ans_s + 5 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            return jsonb_build_object('open', false, 'expired', true);
        end if;
        return jsonb_build_object('open', true, 'phase', 'resume', 'level', lv, 'bet', r.bet,
                                  'wait', greatest(0, shown + view_s - t), 'left', greatest(0, shown + view_s + ans_s - t));
    end if;
    if action = 'submit' then
        if shown is null then raise exception 'rb_too_soon'; end if;
        ph := public.rb_num(vals, 'h', 0, 360); ps := public.rb_num(vals, 's', 0, 100); pv := public.rb_num(vals, 'v', 0, 100);
        if t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;
        late := t > shown + view_s + ans_s + 5;
        h := (r.secret ->> 'h')::double precision; s := (r.secret ->> 's')::double precision; v := (r.secret ->> 'v')::double precision;
        de := public.rb_de2000(public.rb_hsb_lab(h, s, v), public.rb_hsb_lab(ph, ps, pv));
        acc := case when late then 0 else round((100 * exp(-de / (array[28, 20, 14])[lv + 1]))::numeric, 1) end;
        mult := public.rb_acc_mult(lv, acc);
        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x
         where x.owner = p.id and x.game = 'colour' and x.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('colour_day_profit'), 12000) and mult > 1 then mult := 1; capped := true; end if;
        if mult > 0 then pay := public.rb_win(p.id, r.bet * mult, 'colour'); end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('acc', acc, 'de', round(de::numeric, 2), 'late', late, 'mult', mult,
                                                       'pick', jsonb_build_object('h', ph, 's', ps, 'v', pv)) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'acc', acc, 'de', round(de::numeric, 2), 'late', late,
            'mult', mult, 'paid', pay, 'capped', capped, 'h', h, 's', s, 'v', v, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $function$;
CREATE OR REPLACE FUNCTION public.rb_cups(action text, level integer, bet integer, pick integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; n integer; moves integer; secs numeric;
        mult numeric; sw jsonb := '[]'::jsonb; a integer; b integer; i integer; coin integer; start_ integer;
        pay integer := 0; won boolean; dur numeric; lim numeric := coalesce(public.rb_cfg('cups_pick_secs'), 30);
        t numeric := extract(epoch from now()); ready numeric; late boolean := false; profit bigint; capped boolean := false;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'cups' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false where id = r.id;
        end if;
        if level is null or level not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
        n := (array[3, 6, 9, 9])[level + 1];
        moves := (array[14, 24, 34, 46])[level + 1] + floor(public.rb_rand() * 5)::int;
        secs := (array[0.46, 0.32, 0.24, 0.16])[level + 1];
        mult := (array[1.2, 2.0, 3.0, 5.0])[level + 1];
        if bet > coalesce(public.rb_cfg('cups_max_bet'), 2000) then raise exception 'rb_bad_bet'; end if;
        perform public.rb_bet(p, bet, 'cups');
        start_ := floor(public.rb_rand() * n)::int;
        for i in 1 .. moves loop
            a := floor(public.rb_rand() * n)::int;
            b := (a + 1 + floor(public.rb_rand() * (n - 1))::int) % n;
            sw := sw || jsonb_build_array(jsonb_build_array(a, b));
        end loop;
        coin := start_;
        for i in 0 .. jsonb_array_length(sw) - 1 loop
            a := (sw -> i ->> 0)::int; b := (sw -> i ->> 1)::int;
            if coin = a then coin := b; elsif coin = b then coin := a; end if;
        end loop;
        dur := 2.0 + moves * secs;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'cups', bet, jsonb_build_object('level', level, 'n', n, 'start', start_, 'swaps', sw, 'coin', coin,
                                                          'mult', mult, 'ready', t + dur - 1), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'n', n, 'start', start_, 'swaps', sw,
            'secs', secs, 'mult', mult, 'bet', bet, 'pick_secs', lim, 'coins', p.coins - bet));
    end if;
    if action = 'pick' then
        if not found then raise exception 'rb_round_gone'; end if;
        n := (r.secret ->> 'n')::int;
        if pick is null or pick < -1 or pick >= n then raise exception 'rb_bad_choice'; end if;
        ready := (r.secret ->> 'ready')::numeric;
        if t < ready then raise exception 'rb_too_soon'; end if;
        if pick = -1 and t < ready + lim - 1 then raise exception 'rb_too_soon'; end if;
        late := pick = -1 or t > ready + lim + 4;
        coin := (r.secret ->> 'coin')::int;
        won := not late and pick = coin;
        mult := (r.secret ->> 'mult')::numeric;
        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x
         where x.owner = p.id and x.game = 'cups' and x.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('cups_day_profit'), 8000) and mult > 1 then mult := 1; capped := true; end if;
        if won then
            pay := public.rb_win(p.id, r.bet * mult, 'cups');
        end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('pick', pick, 'late', late, 'rt', round((t - ready)::numeric, 2)) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'won', won, 'coin', coin, 'paid', pay,
            'late', late, 'capped', capped, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $function$;
drop function if exists public.rb_my_stats cascade;
CREATE OR REPLACE FUNCTION public.rb_quest_rows(who uuid)
 RETURNS TABLE(quest text, kind text, goal integer, reward integer, progress integer, period timestamp with time zone, left_s integer)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('timing'), ('roulette'), ('hilo'), ('tower'), ('cups'), ('c4'), ('colour'), ('sfx')),
         pool (quest, goal, reward, progress) as (values
            ('h_rounds', 3, 25, (select count(*) from h where game in (select g from casino))::int),
            ('h_mini',   1, 25, (select count(*) from h where game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave', 'cups', 'c4'))::int),
            ('h_case',   1, 30, (select count(*) from h where game like 'case:%' or game = 'daily')::int),
            ('h_bet',  100, 25, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int)),
         q (quest, kind, goal, reward, progress) as (
            select pq.quest, 'hour', pq.goal, pq.reward, pq.progress from pool pq
             where pq.quest in ((array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[extract(hour from now())::int % 4 + 1],
                                (array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[(extract(hour from now())::int + 2) % 4 + 1])
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  2, 150, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 150, (select count(*) from d where game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave'))::int),
            ('d_spin',   'day',  1, 100, (select count(*) from d where game = 'spin')::int),
            ('w_rounds', 'week', 200, 1500, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  25, 2000, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 25000, 2000, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int),
            ('w_mini',   'week',  30, 1500, (select count(*) from r where game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave'))::int),
            ('w_golf',   'week',   3, 1500, ((select count(*) from public.rb_golf g where g.winner = who and g.state = 'done'
                                               and g.done_at >= date_trunc('week', now()))
                                             + (select count(*) from r where game in ('golf_party', 'golf_solo')))::int),
            ('w_scratch','week',   7, 1200, (select count(*) from r where game = 'scratch')::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $function$;
CREATE OR REPLACE FUNCTION public.rb_sfx(action text, level integer, bet integer, vals jsonb, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; t double precision := extract(epoch from now());
        view_s numeric; ans_s numeric; plays integer; prev_max integer; used integer;
        f double precision; d double precision; w integer; g double precision; wb double precision; sh integer;
        pf double precision; pd double precision; pw double precision; pg double precision; pwb double precision; psh double precision;
        shown double precision; late boolean := false; lv integer; tol double precision[]; parts jsonb := '{}'::jsonb;
        sp double precision; sdu double precision; sw double precision; sg double precision; ss double precision; sb double precision;
        wsum double precision; tot double precision; acc numeric; mult numeric; pay integer := 0; profit bigint; capped boolean := false;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    if action not in ('show') then
        res := public.rb_done(p.id, req);
        if res is not null then return res; end if;
    end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'sfx' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
        end if;
        if level is null or level not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
        view_s := (array[12, 9, 7])[level + 1];
        ans_s := (array[75, 60, 45])[level + 1];
        plays := (array[6, 5, 4])[level + 1];
        prev_max := (array[999, 999, 999])[level + 1];
        if level = 0 then
            f := 110 * power(2, (floor(public.rb_rand() * 10) * 5) / 12.0);
            d := (array[0.3, 0.6, 1.0, 1.5])[1 + floor(public.rb_rand() * 4)::int];
            w := (array[0, 3])[1 + floor(public.rb_rand() * 2)::int]; g := 0; wb := 0; sh := 1;
        elsif level = 1 then
            f := 110 * power(2, floor(public.rb_rand() * 45) / 12.0);
            d := round((0.2 + public.rb_rand() * 1.4)::numeric, 2);
            w := floor(public.rb_rand() * 4)::int; g := floor(public.rb_rand() * 15) - 7; wb := 0; sh := floor(public.rb_rand() * 3)::int;
        else
            f := round((110 * power(2, public.rb_rand() * 45 / 12.0))::numeric, 1);
            d := round((0.15 + public.rb_rand() * 1.75)::numeric, 2);
            w := floor(public.rb_rand() * 4)::int; g := round((public.rb_rand() * 24 - 12)::numeric * 2) / 2;
            wb := floor(public.rb_rand() * 101); sh := floor(public.rb_rand() * 3)::int;
        end if;
        perform public.rb_bet(p, bet, 'sfx');
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'sfx', bet, jsonb_build_object('level', level, 'f', f, 'd', d, 'w', w, 'g', g, 'wb', wb, 'sh', sh,
                'view', view_s, 'ans', ans_s, 'plays', plays, 'prev', prev_max, 'used', 0, 'started', t, 'shown', null), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'phase', 'ready', 'level', level, 'view', view_s,
            'ans', ans_s, 'plays', plays, 'previews', prev_max, 'bet', bet, 'coins', p.coins - bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    lv := (r.secret ->> 'level')::int;
    view_s := (r.secret ->> 'view')::numeric; ans_s := (r.secret ->> 'ans')::numeric;
    shown := (r.secret ->> 'shown')::double precision;
    prev_max := (r.secret ->> 'prev')::int; used := (r.secret ->> 'used')::int;
    if action = 'show' then
        if shown is not null then raise exception 'rb_round_gone'; end if;
        if t > (r.secret ->> 'started')::double precision + 90 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            raise exception 'rb_round_gone';
        end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('shown', t) where id = r.id;
        return jsonb_build_object('open', true, 'phase', 'show', 'view', view_s, 'ans', ans_s, 'plays', (r.secret ->> 'plays')::int,
            'previews', prev_max, 'f', (r.secret ->> 'f')::double precision, 'd', (r.secret ->> 'd')::double precision,
            'w', (r.secret ->> 'w')::int, 'g', (r.secret ->> 'g')::double precision, 'wb', (r.secret ->> 'wb')::double precision,
            'sh', (r.secret ->> 'sh')::int);
    end if;
    if action = 'state' then
        if shown is null then
            if t > (r.secret ->> 'started')::double precision + 90 then
                update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
                return jsonb_build_object('open', false);
            end if;
            return jsonb_build_object('open', true, 'phase', 'ready', 'level', lv, 'view', view_s, 'ans', ans_s,
                                      'plays', (r.secret ->> 'plays')::int, 'previews', prev_max, 'bet', r.bet);
        end if;
        if t > shown + view_s + ans_s + 5 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            return jsonb_build_object('open', false, 'expired', true);
        end if;
        return jsonb_build_object('open', true, 'phase', 'resume', 'level', lv, 'bet', r.bet, 'previews', prev_max - used,
                                  'wait', greatest(0, shown + view_s - t), 'left', greatest(0, shown + view_s + ans_s - t));
    end if;
    if action = 'preview' then
        if shown is null or t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;
        if t > shown + view_s + ans_s + 5 then raise exception 'rb_too_soon'; end if;
        if used >= prev_max then raise exception 'rb_too_soon'; end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('used', used + 1) where id = r.id;
        return jsonb_build_object('left', prev_max - used - 1);
    end if;
    if action = 'submit' then
        if shown is null then raise exception 'rb_too_soon'; end if;
        pf := public.rb_num(vals, 'f', 100, 2000); pd := public.rb_num(vals, 'd', 0.1, 2.5); pw := public.rb_num(vals, 'w', 0, 3);
        pg := public.rb_num(vals, 'g', -12, 12); pwb := public.rb_num(vals, 'wb', 0, 100); psh := public.rb_num(vals, 'sh', 0, 2);
        if t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;
        late := t > shown + view_s + ans_s + 5;
        f := (r.secret ->> 'f')::double precision; d := (r.secret ->> 'd')::double precision; w := (r.secret ->> 'w')::int;
        g := (r.secret ->> 'g')::double precision; wb := (r.secret ->> 'wb')::double precision; sh := (r.secret ->> 'sh')::int;
        tol := case lv when 0 then array[9.0, 0.8, 1.0, 1.5, 1.5, 1] when 1 then array[4.5, 0.5, 0.65, 5.0, 0.7, 1]
                       else array[3.2, 0.36, 0.5, 4.0, 0.55, 0.5] end;
        sp := exp(-abs(12 * ln(pf / f) / ln(2::double precision)) / tol[1]);
        sdu := exp(-abs(ln(pd / d)) / tol[2]);
        sw := exp(-(abs(pw - w) / 3.0) / tol[3]);
        wsum := 2 + 1 + 1.5; tot := 2 * sp + 1 * sdu + 1.5 * sw;
        parts := jsonb_build_object('pitch', round((sp * 100)::numeric), 'dur', round((sdu * 100)::numeric), 'wave', round((sw * 100)::numeric));
        if lv >= 1 then
            sg := exp(-abs(pg - g) / tol[4]); ss := exp(-(abs(psh - sh) / 2.0) / tol[5]);
            wsum := wsum + 2; tot := tot + sg + ss;
            parts := parts || jsonb_build_object('glide', round((sg * 100)::numeric), 'shape', round((ss * 100)::numeric));
        end if;
        if lv >= 2 then
            sb := exp(-(abs(pwb - wb) / 100.0) / tol[6]);
            wsum := wsum + 0.7; tot := tot + 0.7 * sb;
            parts := parts || jsonb_build_object('wobble', round((sb * 100)::numeric));
        end if;
        acc := case when late then 0 else round((100 * tot / wsum)::numeric, 1) end;
        mult := public.rb_acc_mult(lv, acc);
        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x
         where x.owner = p.id and x.game = 'sfx' and x.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('sfx_day_profit'), 12000) and mult > 1 then mult := 1; capped := true; end if;
        if mult > 0 then pay := public.rb_win(p.id, r.bet * mult, 'sfx'); end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('acc', acc, 'late', late, 'mult', mult,
                   'pick', jsonb_build_object('f', pf, 'd', pd, 'w', pw, 'g', pg, 'wb', pwb, 'sh', psh)) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'acc', acc, 'late', late, 'mult', mult, 'paid', pay,
            'capped', capped, 'parts', parts, 'level', lv, 'coins', p.coins + pay,
            'f', f, 'd', d, 'w', w, 'g', g, 'wb', wb, 'sh', sh));
    end if;
    raise exception 'rb_bad_choice';
end $function$;
drop function if exists public.rb_skill_base cascade;
drop function if exists public.rb_skill_pay cascade;
drop function if exists public.rb_skill_state cascade;
drop function if exists public.rb_skill_window cascade;
CREATE OR REPLACE FUNCTION public.rb_timing(action text, bet integer, ms integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; rd public.rb_rounds%rowtype; seed jsonb; real_ms double precision;
        pos double precision; d double precision; mult numeric := 0; pay integer := 0; grade text; lag double precision;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into rd from public.rb_rounds where owner = p.id and game = 'timing' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false where id = rd.id;
        end if;
        if (select coalesce(sum(r.paid - r.bet), 0) from public.rb_rounds r where r.owner = p.id and r.game = 'timing'
              and r.at >= date_trunc('day', now())) >= 20000 then raise exception 'rb_slow_down'; end if;
        perform public.rb_bet(p, bet, 'timing');
        seed := jsonb_build_object('v', 2.0 + public.rb_rand() * 0.6, 'a', 0.08 + public.rb_rand() * 0.06,
                                   'o', public.rb_rand() * 2, 'c', round((0.2 + public.rb_rand() * 0.6)::numeric, 3));
        insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'timing', bet, seed, true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('seed', seed, 'coins', p.coins - bet));
    end if;
    if action <> 'stop' or not found then raise exception 'rb_bad_choice'; end if;
    real_ms := extract(epoch from clock_timestamp() - rd.at) * 1000;
    lag := real_ms - coalesce(ms, -1);
    if ms is null or ms < 0 or real_ms > 9000 or lag < -40 or lag > 400
       or (real_ms > 1000 and ms < real_ms * 0.94 - 150) then
        ms := greatest(0, least(real_ms - 80, 999999));
    end if;
    pos := public.rb_timing_pos(rd.secret, least(ms, 9000));
    d := abs(pos - (rd.secret ->> 'c')::float8);
    if real_ms > 9000 then grade := 'late';
    elsif d <= 0.008 then grade := 'perfect'; mult := 4;
    elsif d <= 0.025 then grade := 'good'; mult := 1.8;
    elsif d <= 0.05 then grade := 'close'; mult := 0.9;
    else grade := 'miss'; end if;
    if mult > 0 then pay := public.rb_win(p.id, rd.bet * mult, 'timing'); end if;
    update public.rb_rounds set open = false, paid = pay, secret = rd.secret || jsonb_build_object('pos', pos, 'grade', grade, 'ms', ms)
     where id = rd.id;
    return public.rb_remember(p.id, req, jsonb_build_object('pos', pos, 'grade', grade, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins + pay));
end $function$;
delete from public.rb_config where key = 'skill_day_cap';
delete from public.rb_config where key = 'skill_full_rounds';
delete from public.rb_config where key = 'skill_pay_mult';
commit;
