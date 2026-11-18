-- ================================================================ Rubenium 4.5 (build 2026.11.18.23)
-- Wave Rush duels you can watch and replay, a harder course, cases with a little more colour, new looks, XP
-- without a daily cap, bets that grow with your coins, trading between friends only. 028_down.sql undoes it.
begin;

CREATE OR REPLACE FUNCTION public.rb_wave_sim(seed bigint, toggles integer[], max_ticks integer)
 RETURNS TABLE(ticks integer, x integer)
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO ''
AS $function$
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
            d := least(1000, x_end / 110);
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
                if d >= 20 then
                    s := (s * 1103515245 + 12345) & 2147483647; n := (s >> 8) % (2 + 3 * d / 1000);
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
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1);
                if d >= 150 and ln_ >= 200 then                    -- 4.5: a spike on the longer ramps too
                    s := (s * 1103515245 + 12345) & 2147483647;
                    px := px || (x_end + ln_ / 2); pside := pside || ((s >> 8) % 2)::int; sn := sn || 1;
                else
                    sn := sn || 0;
                end if;
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
end $function$;

-- ================================================================ Wave Rush 4.5: see the other player, replays, spectators
-- Each run keeps the ticks where the player pressed or let go (live while it runs, final when it ends): the other
-- player and anyone watching rebuild the wave from them with the same maths as the server.
alter table public.rb_wave_runs add column if not exists live_tg integer[] not null default '{}';
alter table public.rb_wave_runs add column if not exists live_t integer not null default 0;

create or replace function public.rb_wave_ping(run uuid, x integer, toggles integer[], t integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype; most integer;
begin
    select * into r from public.rb_wave_runs where id = run and owner = me;
    if not found or r.duel is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        most := floor(greatest(0, extract(epoch from now() - r.started_at)) * 60)::int + 120;     -- no run from the future
        if coalesce(array_length(toggles, 1), 0) <= 30000 and coalesce(t, 0) between r.live_t and most then
            update public.rb_wave_runs set live_tg = coalesce((select array_agg(v order by v) from (select distinct v
                       from unnest(toggles) v where v > 0 and v <= t) z), '{}'), live_t = t where id = r.id;
        end if;
        update public.rb_wave_runs set live_x = greatest(live_x, least(coalesce(x, 0), most * 12 + 2000)) where id = r.id;
    end if;
    return public.rb_wave_state(r.duel);
end $$;

create or replace function public.rb_wave_ping(run uuid, x integer) returns jsonb
language sql security definer set search_path = '' as $$ select public.rb_wave_ping(run, x, null, null) $$;

-- the final ticks are kept when a run ends (rb_wave_finish): one line added after the sim
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_wave_finish(uuid, integer[], integer)'::regprocedure), chr(13), '');
    if position('4.5 replay' in src) = 0 then
        out_ := replace(src, '    update public.rb_wave_runs set state = ''done'', ticks = sim.ticks, dist = sim.x, live_x = sim.x, paid = pay,',
            '    update public.rb_wave_runs set live_tg = coalesce((select array_agg(v order by v) from (select distinct v   -- 4.5 replay
               from unnest(toggles) v where v > 0 and v <= sim.ticks) z), ''{}''), live_t = sim.ticks where id = r.id;
    update public.rb_wave_runs set state = ''done'', ticks = sim.ticks, dist = sim.x, live_x = sim.x, paid = pay,');
        if out_ = src then raise exception 'rb_wave_finish changed'; end if;
        execute out_;
    end if;
end $$;

create or replace function public.rb_wave_duel_json(w public.rb_wave_duels, me uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
    select jsonb_build_object('id', w.id, 'state', w.state, 'bet', w.bet, 'seed', w.seed,
        'me', case when me = w.a then 'a' when me = w.b then 'b' end,
        'a', (select username from public.profiles where id = w.a), 'b', (select username from public.profiles where id = w.b),
        'run', case when me = w.a then w.a_run when me = w.b then w.b_run end,
        'a_x', ra.live_x, 'b_x', rb.live_x, 'a_done', ra.state = 'done', 'b_done', rb.state = 'done',
        'a_tg', ra.live_tg, 'b_tg', rb.live_tg, 'a_t', ra.live_t, 'b_t', rb.live_t, 'a_ticks', ra.ticks, 'b_ticks', rb.ticks,
        'since', case when ra.started_at is not null then extract(epoch from now() - ra.started_at)::numeric(9, 2) end,
        'starts_in', case when w.live_at is not null then greatest(0, extract(epoch from (w.live_at + interval '4 seconds' - now())))::numeric(5, 1) end,
        'left', case when w.state = 'live' then greatest(0, ceil(extract(epoch from (w.live_at
                 + make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int) - now()))))::int end,
        'winner', case when w.winner = w.a then 'a' when w.winner = w.b then 'b' end, 'why', w.why)
      from (select 1) one
      left join public.rb_wave_runs ra on ra.id = w.a_run
      left join public.rb_wave_runs rb on rb.id = w.b_run $$;

-- anyone can watch a live duel (or see how one ended, for a minute)
create or replace function public.rb_wave_watch(did uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); w public.rb_wave_duels%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_wave_tick(did);
    select * into w from public.rb_wave_duels where id = did;
    if not found or w.state not in ('live', 'done') or (w.state = 'done' and w.done_at < now() - interval '2 minutes') then
        raise exception 'rb_duel_gone';
    end if;
    return public.rb_wave_duel_json(w, me);
end $$;
revoke all on function public.rb_wave_watch(uuid), public.rb_wave_ping(uuid, integer, integer[], integer) from public, anon;
grant execute on function public.rb_wave_watch(uuid), public.rb_wave_ping(uuid, integer, integer[], integer) to authenticated;

-- the lobby lists the duels being played, to watch
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_wave_lobbies()'::regprocedure), chr(13), '');
    if position('''watch''' in src) = 0 then
        out_ := replace(src, '        ''history'', coalesce(',
            '        ''watch'', coalesce((select jsonb_agg(jsonb_build_object(''id'', w.id, ''a'', ua.username, ''b'', ub.username, ''bet'', w.bet,
                     ''since'', extract(epoch from now() - w.live_at)::int) order by w.live_at desc)
                   from public.rb_wave_duels w join public.profiles ua on ua.id = w.a join public.profiles ub on ub.id = w.b
                  where w.state = ''live'' and w.a <> me and w.b <> me and w.live_at > now() - interval ''10 minutes''), ''[]''::jsonb),
        ''history'', coalesce(');
        if out_ = src then raise exception 'rb_wave_lobbies changed'; end if;
        execute out_;
    end if;
end $$;

-- ================================================================ Cases 4.5: a little more colour, still very rare at the top
-- More Painted (coloured) badges instead of plain grey, Shiny x2.5, Titanium x3, Gold x2.5, a touch more Epic and
-- Legendary in the small cases, and a Mythic is a little more often Prismatic or Gold. Nothing becomes easy.
do $$
begin
    if exists (select 1 from public.rb_config where key = 'cases_v45') then return; end if;      -- once only
    update public.rb_cases c set variants = array[
            greatest(0, 100000 - v.painted - v.shiny - v.tit - v.gold), v.painted, v.shiny, v.tit, v.gold]
      from (select id,
                   case when id in ('painter', 'shiny') then 100000 - variants[1] - (case when id = 'shiny' then variants[3]
                             else variants[3] * 5 / 2 end) - variants[4] * 3 - variants[5] * 5 / 2
                        when price >= 3500 then greatest(variants[2], 40000)
                        else greatest(variants[2], 32000) end as painted,
                   case when id = 'shiny' then variants[3] else least(variants[3] * 5 / 2, 40000) end as shiny,
                   variants[4] * 3 as tit, variants[5] * 5 / 2 as gold
              from public.rb_cases where kind in ('coins', 'hunt') and mode = '' or id = 'giftbox') v
     where c.id = v.id and c.variants[1] + c.variants[2] + c.variants[3] + c.variants[4] + c.variants[5] = 100000
       and c.variants <> array[100000, 0, 0, 0, 0];
    
    update public.rb_cases set odds = case id
            when 'pocket' then array[8870, 910, 180, 32, 8, 0]
            when 'starter' then array[8346, 1320, 285, 40, 9, 0]
            when 'lucky' then array[8330, 1285, 310, 62, 13, 0]
            when 'standard' then array[7438, 1900, 555, 88, 18, 1]
            when 'premium' then array[6795, 2150, 860, 150, 44, 1]
            else odds end
     where id in ('pocket', 'starter', 'lucky', 'standard', 'premium');
    insert into public.rb_config (key, value) values ('cases_v45', 1);
end $$;

-- a Mythic: Titanium, now and then Prismatic, very rarely Gold (was 96.5% / 3.3% / 0.185%)
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_case_drop(public.rb_cases)'::regprocedure), chr(13), '');
    out_ := replace(src, 'public.rb_roll(array[96515, 3300, 185])', 'public.rb_roll(array[94300, 5300, 400])');
    if out_ <> src then execute out_; end if;
    if position('array[94300, 5300, 400]' in pg_get_functiondef('public.rb_case_drop(public.rb_cases)'::regprocedure)) = 0 then
        raise exception 'mythic odds did not change';
    end if;
end $$;

-- ================================================================ New looks 4.5: 6 themes, 5 banners, 4 frames, a ball, a line
-- Sold in the Shop and found in the style cases like the others (nothing limited).
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, base_worth, weight) values
    ('theme:glacier', 'theme', 'glacier', '', 'rare', 540, 540, true, 0, 540, 540, 0.9),
    ('theme:jade', 'theme', 'jade', '', 'rare', 540, 540, true, 0, 540, 540, 0.9),
    ('theme:mirage', 'theme', 'mirage', '', 'special', 1440, 1440, true, 0, 1440, 1440, 0.9),
    ('theme:nebula', 'theme', 'nebula', '', 'special', 1440, 1440, true, 0, 1440, 1440, 0.9),
    ('theme:obsidian', 'theme', 'obsidian', '', 'epic', 3600, 3600, true, 0, 3600, 3600, 0.9),
    ('theme:prism', 'theme', 'prism', '', 'epic', 3600, 3600, true, 0, 3600, 3600, 0.9),
    ('banner:mosaic', 'banner', 'mosaic', '', 'standard', 400, 400, true, 0, 400, 400, 0.9),
    ('banner:reef', 'banner', 'reef', '', 'rare', 1200, 1200, true, 0, 1200, 1200, 0.9),
    ('banner:thunder', 'banner', 'thunder', '', 'rare', 1200, 1200, true, 0, 1200, 1200, 0.9),
    ('banner:blackhole', 'banner', 'blackhole', '', 'special', 3500, 3500, true, 0, 3500, 3500, 0.9),
    ('banner:crystal', 'banner', 'crystal', '', 'epic', 9000, 9000, true, 0, 9000, 9000, 0.9),
    ('frame:chrome', 'frame', 'chrome', '', 'standard', 300, 300, true, 0, 300, 300, 0.9),
    ('frame:ripple', 'frame', 'ripple', '', 'rare', 1000, 1000, true, 0, 1000, 1000, 0.9),
    ('frame:comet', 'frame', 'comet', '', 'special', 3000, 3000, true, 0, 3000, 3000, 0.9),
    ('frame:eclipse', 'frame', 'eclipse', '', 'epic', 8000, 8000, true, 0, 8000, 8000, 0.9)
on conflict (id) do nothing;

-- the Eclipse ball (Legendary) and the Comet line (Epic): grey, 13 colours (x1.25), black and white (a rarity up)
do $$ declare row text[]; col text; tiers text[] := array['standard', 'rare', 'special', 'epic'];
               base_price integer[] := array[120, 360, 960, 2400]; t integer; up integer; v integer;
begin
    foreach row slice 1 in array array[['ball', 'eclipse', '4'], ['line', 'comet', '3']] loop
        t := row[3]::int; up := least(4, t + 1);
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, base_worth, weight)
            values (row[1] || ':' || row[2] || ':grey', row[1], row[2], 'grey', tiers[t], base_price[t], base_price[t], true, 0,
                    base_price[t], base_price[t], 0.9)
            on conflict (id) do nothing;
        foreach col in array array['blue', 'green', 'red', 'yellow', 'orange', 'brown', 'teal', 'lava', 'purple', 'sky', 'lime', 'pink', 'beam'] loop
            v := base_price[t] * 5 / 4;
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, base_worth, weight)
                values (row[1] || ':' || row[2] || ':' || col, row[1], row[2], col, tiers[t], v, v, true, 0, v, v, 0.9)
                on conflict (id) do nothing;
        end loop;
        foreach col in array array['black', 'white'] loop
            v := base_price[up] * 25 / 16;
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, base_worth, weight)
                values (row[1] || ':' || row[2] || ':' || col, row[1], row[2], col, tiers[up], v, v, true, 0, v, v, 0.9)
                on conflict (id) do nothing;
        end loop;
    end loop;
end $$;

-- ================================================================ XP 4.5: no daily cap, steady per hour
-- There is no daily XP limit any more. Each way of earning has a small limit per hour instead, so playing longer
-- keeps paying a steady amount while scripts and quick farming can't spike it. Casino XP needs a real bet (50+).
alter table public.profiles add column if not exists xp_hr timestamptz;
alter table public.profiles add column if not exists xp_hr_src jsonb not null default '{}';

create or replace function public.rb_xp_cap(src text) returns integer
language sql immutable set search_path = '' as $$
    select case src when 'casino' then 30 when 'minigames' then 75 when 'cases' then 16 when 'golf' then 50
                    when 'coinflip' then 20 when 'trading' then 16 when 'online' then 30 when 'wheel' then 12
                    when 'quests' then 200 when 'wave' then 50 else 100000 end $$;

create or replace function public.rb_xp_add(who uuid, amount integer, src text, ref text, capped boolean default true)
returns integer language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; hr_src jsonb; used integer; give integer; lv integer; hr timestamptz := date_trunc('hour', now());
begin
    if amount is null or amount <= 0 then return 0; end if;
    select * into p from public.profiles where id = who for update;
    if not found or p.bot then return 0; end if;
    if p.xp_day is distinct from current_date then p.xp_day_gain := 0; p.xp_day_src := '{}'::jsonb; end if;
    if p.xp_hr is distinct from hr then p.xp_hr_src := '{}'::jsonb; end if;
    give := amount;
    hr_src := p.xp_hr_src;
    if capped then
        used := coalesce((p.xp_hr_src ->> src)::int, 0);
        give := least(give, public.rb_xp_cap(src) - used);
        if give <= 0 then return 0; end if;
        hr_src := p.xp_hr_src || jsonb_build_object(src, used + give);
    end if;
    lv := public.rb_level_of(p.xp + give);
    update public.profiles set xp = xp + give, level = lv, xp_day = current_date, xp_day_gain = p.xp_day_gain + give,
           xp_day_src = p.xp_day_src || jsonb_build_object(src, coalesce((p.xp_day_src ->> src)::int, 0) + give),
           xp_hr = hr, xp_hr_src = hr_src
     where id = who;
    insert into public.rb_xp_log (owner, amount, source, ref, level_after) values (who, give, src, left(ref, 80), lv);
    if lv > p.level then
        perform public.rb_notice(who, 'level_up', jsonb_build_object('level', lv, 'from', p.level));
    end if;
    return give;
end $$;

-- casino XP only for a real bet (50 coins or more), still only on a win
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_rounds_xp()'::regprocedure), chr(13), '');
    out_ := replace(src, 'if new.bet < 10 or coalesce(new.paid, 0) <= new.bet then return new; end if;',
                         'if new.bet < 50 or coalesce(new.paid, 0) <= new.bet then return new; end if;');
    if out_ <> src then execute out_; end if;
    if position('new.bet < 50' in pg_get_functiondef('public.rb_rounds_xp()'::regprocedure)) = 0 then
        raise exception 'casino xp change did not apply';
    end if;
end $$;

-- trading XP: once per pair of players every 6 hours (no XP for passing items back and forth)
create or replace function public.rb_trade_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.state = 'done' and old.state <> 'done' and not exists (
           select 1 from public.rb_trades t where t.id <> new.id and t.state = 'done' and t.updated > now() - interval '6 hours'
              and ((t.a = new.a and t.b = new.b) or (t.a = new.b and t.b = new.a))) then
        perform public.rb_xp_add(new.a, 8, 'trading', new.id::text, true);
        perform public.rb_xp_add(new.b, 8, 'trading', new.id::text, true);
    end if;
    return new;
end $$;

create or replace function public.rb_xp_json(p public.profiles) returns json
language sql stable set search_path = '' as $$
    select json_build_object('xp', p.xp, 'level', p.level,
        'into', p.xp - public.rb_xp_total(p.level),
        'need', case when p.level >= 100 then 0 else public.rb_xp_need(p.level) end,
        'badge', case when p.level_badge >= 0 and p.level_badge <= p.level then p.level_badge else (p.level / 5) * 5 end,
        'today', case when p.xp_day = current_date then p.xp_day_gain else 0 end,
        'cap', 0) $$;

do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_admin_xp_watch()'::regprocedure), chr(13), '');
    out_ := replace(src, 'where t.s >= coalesce(public.rb_cfg(''xp_day_cap''), 2500) group by', 'where t.s >= 1500 group by');
    out_ := replace(out_, '''caps'', json_build_object(''day'', public.rb_cfg(''xp_day_cap''),', '''caps'', json_build_object(''day'', 0,');
    if out_ <> src then execute out_; end if;
end $$;
update public.rb_config set value = 0 where key = 'xp_day_cap';

-- ================================================================ Casino 4.5: the biggest bet grows with your coins
-- 1 000 as before, or 5% of your coins, up to 5 000.
insert into public.rb_config (key, value) values ('bet_max_rich', 5000), ('bet_rich_pct', 5)
    on conflict (key) do update set value = excluded.value;

create or replace function public.rb_bet_cap(coins bigint) returns integer
language sql stable set search_path = '' as $$
    select greatest(public.rb_cfg('bet_max')::int,
                    least(coalesce(public.rb_cfg('bet_max_rich'), 5000)::int,
                          (floor(coins * coalesce(public.rb_cfg('bet_rich_pct'), 5) / 1000) * 10)::int)) $$;

create or replace function public.rb_bet(p public.profiles, bet integer, game text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if bet is null or bet < public.rb_cfg('bet_min') or bet > public.rb_bet_cap(p.coins) then
        raise exception 'rb_bad_bet';
    end if;
    perform public.rb_pay(p.id, -bet, 0, 'bet', game);
end $$;

-- ================================================================ Trading 4.5: friends only
do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_trade_request(text)'::regprocedure), chr(13), '');
    out_ := replace(src, '    if them.id = p.id then raise exception ''rb_thats_you''; end if;',
        '    if them.id = p.id then raise exception ''rb_thats_you''; end if;
    if not public.rb_is_friend(p.id, them.id) then raise exception ''rb_not_friends''; end if;');
    if out_ <> src then execute out_; end if;
    src := replace(pg_get_functiondef('public.rb_trade_accept(uuid)'::regprocedure), chr(13), '');
    out_ := replace(src, '    if not found or t.b <> me or t.state <> ''asked'' then raise exception ''rb_trade_gone''; end if;',
        '    if not found or t.b <> me or t.state <> ''asked'' then raise exception ''rb_trade_gone''; end if;
    if not public.rb_is_friend(t.a, t.b) then raise exception ''rb_not_friends''; end if;');
    if out_ <> src then execute out_; end if;
    if position('rb_not_friends' in pg_get_functiondef('public.rb_trade_request(text)'::regprocedure)) = 0
       or position('rb_not_friends' in pg_get_functiondef('public.rb_trade_accept(uuid)'::regprocedure)) = 0 then
        raise exception 'trade change did not apply';
    end if;
end $$;

update public.rb_config set value = 2026111823 where key = 'min_build';

commit;
