-- 6.4: Horse Racing pays the first three. The whole finishing order is drawn on the server (each horse's chance is its share of
-- the money, drawn without replacement) and stored in rb_races.places. First: 100% of their bet back + 70% of the pool,
-- second: 25% back + 20% of the pool, third: 5% back + 10% of the pool (pool = all the money minus those returned bets).
alter table public.rb_races add column if not exists places integer[];
create or replace function public.rb_race_advance(rid uuid) returns void language plpgsql security definer set search_path = '' as $f$
declare r public.rb_races%rowtype; n integer; avg_ bigint; names text[]; k integer; lane_ integer; tgt bigint; luck double precision;
        tot bigint; roll double precision; acc bigint := 0; b record; pay bigint; pl integer[]; left_ integer[]; i integer; r1 bigint; r2 bigint; r3 bigint; win_ bigint; pool bigint; place_ integer; ret double precision; cut double precision;
begin
    select * into r from public.rb_races where id = rid for update;
    if not found then return; end if;
    if r.state = 'open' and now() >= r.lock_at then
        select count(*), coalesce(avg(amount), 0)::bigint into n, avg_ from public.rb_race_bets where race = r.id;
        if n = 0 then avg_ := 1000 + floor(public.rb_rand() * 9000)::bigint; end if;   -- bots race on their own
        select array_agg(x.name order by random()) into names from public.rb_flip_bots() x;
        k := 0;
        for lane_ in 0 .. 4 loop
            continue when exists (select 1 from public.rb_race_bets where race = r.id and lane = lane_);
            k := k + 1;
            luck := public.rb_rand();
            tgt := case when luck < 0.10 then avg_ * (0.10 + 0.25 * public.rb_rand())
                        when luck < 0.20 then avg_ * (1.4 + 1.6 * public.rb_rand())
                        else avg_ * (0.45 + 0.75 * public.rb_rand()) end;
            tgt := greatest(100, round(tgt / 10.0) * 10);
            insert into public.rb_race_bets (race, lane, owner, bot_name, amount, at)
                values (r.id, lane_, null, coalesce(names[k], 'Bot ' || k), tgt, r.lock_at + make_interval(secs => 0.5 * k));
        end loop;
        select sum(amount) into tot from public.rb_race_bets where race = r.id;
        -- the whole finishing order, drawn horse by horse: each one's chance is its share of the money still in the draw
        pl := '{}'; left_ := array[0, 1, 2, 3, 4];
        for i in 1 .. 5 loop
            select sum(amount) into tot from public.rb_race_bets where race = r.id and lane = any (left_);
            roll := public.rb_rand() * tot; acc := 0; lane_ := null;
            for b in select lane, amount from public.rb_race_bets where race = r.id and lane = any (left_) order by lane loop
                acc := acc + b.amount;
                if roll < acc then lane_ := b.lane; exit; end if;
            end loop;
            if lane_ is null then lane_ := left_[array_length(left_, 1)]; end if;
            pl := pl || lane_; left_ := array_remove(left_, lane_);
        end loop;
        r.winner := pl[1];
        select sum(amount) into tot from public.rb_race_bets where race = r.id;
        update public.rb_races set state = 'live', total = tot, winner = r.winner, places = pl,
               start_at = r.lock_at + interval '7 seconds', done_at = r.lock_at + interval '34 seconds' where id = r.id;
        return;
    end if;
    if r.state = 'live' and now() >= r.done_at then
        -- 6.4: first place gets 100% of their own bet back, second 25%, third 5%. What is left of the money (the pool)
        -- goes 70% to first, 20% to second, 10% to third. Everything is paid out, nothing is kept.
        if r.places is null then      -- a race that was already running before this update
            r.places := array[r.winner] || array(select l from generate_series(0, 4) l where l <> r.winner order by l);
        end if;
        select bb.amount into r1 from public.rb_race_bets bb where bb.race = r.id and bb.lane = r.places[1];
        select bb.amount into r2 from public.rb_race_bets bb where bb.race = r.id and bb.lane = r.places[2];
        select bb.amount into r3 from public.rb_race_bets bb where bb.race = r.id and bb.lane = r.places[3];
        pool := r.total - r1 - floor(0.25 * r2)::bigint - floor(0.05 * r3)::bigint;
        for b in select * from public.rb_race_bets where race = r.id and owner is not null loop
            place_ := array_position(r.places, b.lane);
            ret := case place_ when 1 then 1.0 when 2 then 0.25 when 3 then 0.05 else 0 end;
            cut := case place_ when 1 then 0.70 when 2 then 0.20 when 3 then 0.10 else 0 end;
            pay := case when place_ <= 3 then floor(ret * b.amount)::bigint + floor(cut * pool)::bigint else 0 end;
            if pay > 0 then
                perform public.rb_pay(b.owner, least(pay, 2000000000)::int, 0, 'race_win', r.id::text);
                update public.rb_race_bets set paid = pay where id = b.id;
                perform public.rb_notice(b.owner, 'race_won', jsonb_build_object('race', r.id, 'won', pay, 'place', place_));
            end if;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (b.owner, 'horses', least(b.amount, 2000000000)::int,
                        jsonb_build_object('race', r.id, 'lane', b.lane, 'winner', r.winner, 'place', place_, 'total', r.total), false,
                        least(pay, 2000000000)::int);
        end loop;
        update public.rb_races set state = 'done' where id = r.id;
    end if;
end $f$;


do $m$
declare s text;
begin
    s := pg_get_functiondef('public.rb_race_json(public.rb_races, uuid)'::regprocedure);
    if position('''places''' in s) = 0 then
        s := replace(s, '''winner'', case when r.state <> ''open'' then r.winner end,',
                        '''winner'', case when r.state <> ''open'' then r.winner end, ''places'', case when r.state <> ''open'' then to_jsonb(r.places) end,');
        execute s;
    end if;
end $m$;
