-- ================================================================ Rubenium 5.1: Wave Rush
-- The first 150 ticks (2.5 s) slide along the walls instead of crashing, and two spikes on a flat piece are never
-- closer than 130 (they could close the whole gap on the hardest levels). The app (WAVE_SLIDE, WAVE_SPACE) does the
-- same maths. Apps older than 5.1 must update. Safe to run again.
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
    c integer; half integer; top integer; bot integer; hh integer; dx integer; q integer; gate boolean;
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
                    n := least(n, greatest(0, ln_ / 130 - 1));                -- 5.1: never stacked
                else
                    n := 0;
                end if;
                s := (s * 1103515245 + 12345) & 2147483647; side := (s >> 8) % 2;
                sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || 0; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1);
                gate := false;
                if n = 1 and d between 120 and 650 then                -- 4.6: a gate, a spike above and below at once
                    s := (s * 1103515245 + 12345) & 2147483647;
                    if (s >> 8) % 3 = 0 then
                        gate := true;
                        px := px || (x_end + ln_ / 2) || (x_end + ln_ / 2); pside := pside || 0 || 1; n := 0;
                    end if;
                end if;
                sn := sn || (case when gate then 2 else n end);
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
        if t <= 150 then                                             -- 5.1: the start slides on the walls
            y := greatest(top + k_r, least(bot - k_r, y));
        end if;
        if t > 150 and (y - k_r < top or y + k_r > bot) then
            ticks := t; x := px_; return next; return;
        end if;
    end loop;
    ticks := max_ticks; x := px_; return next;
end $function$;

-- ================================================================ 5.1: coinflip bots: 20 more names, 5 to 20 open, 30 min to 6 h
create or replace function public.rb_flip_bots()
 returns table(name text, tier text, lo double precision, hi double precision)
 language sql immutable set search_path to ''
as $function$
    values ('Pixel', 'low', 0.003::double precision, 0.012::double precision), ('Milo', 'low', 0.006, 0.02),
           ('Biscuit', 'low', 0.004, 0.014), ('Tango', 'low', 0.005, 0.016), ('Pebble', 'low', 0.003, 0.01),
           ('Nova', 'mid', 0.02, 0.05), ('Juno', 'mid', 0.03, 0.08),
           ('Orbit', 'mid', 0.025, 0.06), ('Kiwi', 'mid', 0.02, 0.055), ('Rocket', 'mid', 0.035, 0.08),
           ('Vega', 'high', 0.08, 0.16), ('Atlas', 'high', 0.12, 0.25),
           ('Titan', 'high', 0.1, 0.2), ('Onyx', 'high', 0.09, 0.18), ('Blaze', 'high', 0.12, 0.24),
           ('Noodle', 'low', 0.003, 0.011), ('Sprout', 'low', 0.004, 0.013), ('Waffle', 'low', 0.005, 0.015),
           ('Ziggy', 'low', 0.003, 0.012), ('Bloop', 'low', 0.004, 0.012), ('Pogo', 'low', 0.005, 0.018),
           ('Echo', 'mid', 0.02, 0.05), ('Comet', 'mid', 0.025, 0.065), ('Mango', 'mid', 0.02, 0.05),
           ('Raven', 'mid', 0.03, 0.07), ('Pulse', 'mid', 0.025, 0.06), ('Lynx', 'mid', 0.03, 0.075),
           ('Zephyr', 'mid', 0.02, 0.055), ('Glacier', 'high', 0.09, 0.17), ('Phantom', 'high', 0.1, 0.2),
           ('Cobalt', 'high', 0.08, 0.16), ('Talon', 'high', 0.11, 0.22), ('Quasar', 'high', 0.12, 0.25),
           ('Ember', 'high', 0.09, 0.18), ('Vortex', 'high', 0.1, 0.21) $function$;

update public.rb_config set value = 5 where key = 'bot_flips_min';
update public.rb_config set value = 20 where key = 'bot_flips_max';
insert into public.rb_config (key, value) values ('bot_flips_min', 5), ('bot_flips_max', 20) on conflict (key) do nothing;

do $$
declare src text; out_ text;
begin
    src := replace(pg_get_functiondef('public.rb_flip_bot_offer(bigint,boolean,text,text,integer,text[])'::regprocedure), chr(13), '');
    if position('25 + floor(random() * 21)' in src) > 0 then
        out_ := replace(src, '25 + floor(random() * 21)::int', '30 + floor(random() * 331)::int');   -- 30 min to 6 h
        execute out_;
    end if;
end $$;

update public.rb_config set value = greatest(value, 2026112100) where key = 'min_build';
commit;
