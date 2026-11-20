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

-- ================================================================ 5.1: profile looks cost more in the shop
-- Banners, frames and themes 5 times the price, balls and lines 2 times. Badges and fonts unchanged. Once only.
do $$ begin
    if exists (select 1 from public.rb_config where key = 'prices_051') then return; end if;
    create table if not exists public.rb_bak51_prices as select id, price from public.rb_catalog where price is not null;
    alter table public.rb_bak51_prices enable row level security;
    update public.rb_catalog set price = price * 5 where kind in ('banner', 'frame', 'theme') and price is not null;
    update public.rb_catalog set price = price * 2 where kind in ('ball', 'line') and price is not null;
    insert into public.rb_config (key, value) values ('prices_051', 1);
end $$;

-- ================================================================ 5.1: everyone sees the theme you wear on your profile
create or replace function public.rb_looks() returns json
language plpgsql stable security definer set search_path to '' as $function$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(p.username, jsonb_strip_nulls(jsonb_build_object(
                         'tag', p.equip ->> 'tag', 'frame', p.equip ->> 'frame', 'banner', p.equip ->> 'banner',
                         'theme', p.equip ->> 'theme',
                         'gold', nullif(least(coalesce((p.equip ->> 'banner_gold')::int, 3), public.rb_gold_level(p.equip ->> 'banner',
                                    (select w.minutes from public.rb_wear w where w.owner = p.id and w.item = p.equip ->> 'banner'))), 0))))
                       from public.profiles p
                      where not p.banned and p.equip ?| array['tag', 'frame', 'banner', 'theme']), '{}'::json);
end $function$;

-- ================================================================ 5.1: the trash can (an item gone for good, asked twice by the app)
create or replace function public.rb_trash(item_id uuid, confirm text) returns jsonb
language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; it public.rb_items%rowtype;
begin
    p := public.rb_lock_me();
    if confirm is distinct from 'DELETE' then raise exception 'rb_bad_choice'; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found or it.locked is not null then raise exception 'rb_item_locked'; end if;
    if it.item = 'tag:og' then raise exception 'rb_bad_choice'; end if;
    delete from public.rb_items where id = it.id;
    perform public.rb_fix_equip(p.id);
    insert into public.rb_ledger (owner, coins, keys, reason, ref) values (p.id, 0, 0, 'trash', it.item);
    return jsonb_build_object('gone', it.item, 'equip', (select equip from public.profiles where id = p.id));
end $function$;
revoke all on function public.rb_trash(uuid, text) from public, anon;
grant execute on function public.rb_trash(uuid, text) to authenticated;

-- ================================================================ 5.1: Ruben's cheats are back (Ruben's account only)
-- A right click instead of a left click in some games arms a one-time cheat for the next move, then plays it:
-- Bombs: the tile is never a bomb. Tower: never the bomb. Hi-Lo: the next card is the right one. Blackjack: Hit
-- draws the best card that does not bust. (Dice, Slots, the coinflip against a bot, the free spin and the scratch
-- card use the admin Rig on Ruben himself.) It works only for the account named Ruben, and only while he is admin.
create or replace function public.rb_admin_cheat(game text) returns boolean
language plpgsql volatile security definer set search_path = '' as $$
declare me uuid := auth.uid(); n text;
begin
    perform public.rb_need_admin();
    select username into n from public.profiles where id = me;
    if lower(coalesce(n, '')) <> 'ruben' then raise exception 'rb_not_admin'; end if;
    if game not in ('mines', 'tower', 'hilo', 'blackjack') then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_rigs (owner, kind, key, data, by_name) values (me, 'cheat', game, '{}', n)
        on conflict (owner, kind, key) do update set at = now();
    return true;
end $$;
revoke all on function public.rb_admin_cheat(text) from public, anon;
grant execute on function public.rb_admin_cheat(text) to authenticated;

do $$
declare src text; out_ text;
begin
    -- Bombs: the bomb under the tile moves somewhere else
    src := replace(pg_get_functiondef('public.rb_mines(text, integer)'::regprocedure), chr(13), '');
    if position('''cheat''' in src) = 0 then
        out_ := replace(src, '        if arg = any (bombs) then',
            '        if public.rb_rig_take(p.id, ''cheat'', ''mines'') is not null then        -- always used up by the move
            if arg = any (bombs) then
                bombs := array_replace(bombs, arg, coalesce((select t from generate_series(0, 24) t where t <> all (bombs)
                         and t <> all (picked) and t <> arg order by public.rb_rand() limit 1), arg));
            end if;
        end if;
        if arg = any (bombs) then');
        if out_ = src then raise exception 'rb_mines changed'; end if;
        execute out_;
    end if;
    -- Tower: the bombs of that row move to other columns
    src := replace(pg_get_functiondef('public.rb_tower(text, integer, integer, text)'::regprocedure), chr(13), '');
    if position('''cheat''' in src) = 0 then
        out_ := replace(src, '        if (s -> ''rows'' -> lvl) @> to_jsonb(arg) then',
            '        if public.rb_rig_take(p.id, ''cheat'', ''tower'') is not null then         -- always used up by the move
            if (s -> ''rows'' -> lvl) @> to_jsonb(arg) then
                s := jsonb_set(s, array[''rows'', lvl::text], (select coalesce(jsonb_agg(x), ''[]''::jsonb) from (select x
                       from generate_series(0, cols - 1) x where x <> arg order by ((s -> ''rows'' -> lvl) @> to_jsonb(x)) desc,
                       public.rb_rand() limit jsonb_array_length(s -> ''rows'' -> lvl)) t));
            end if;
        end if;
        if (s -> ''rows'' -> lvl) @> to_jsonb(arg) then');
        if out_ = src then raise exception 'rb_tower changed'; end if;
        execute out_;
    end if;
    -- Hi-Lo: the next card goes the way you said
    src := replace(pg_get_functiondef('public.rb_hilo(text, integer, text)'::regprocedure), chr(13), '');
    if position('''cheat''' in src) = 0 then
        out_ := replace(src, '        nxt := floor(public.rb_rand() * 52)::int;',
            '        nxt := floor(public.rb_rand() * 52)::int;
        if public.rb_rig_take(p.id, ''cheat'', ''hilo'') is not null then
            nxt := (case when action = ''higher'' then rank - 1 + floor(public.rb_rand() * (14 - rank))::int
                         else floor(public.rb_rand() * rank)::int end) + 13 * floor(public.rb_rand() * 4)::int;
        end if;');
        if out_ = src then raise exception 'rb_hilo changed'; end if;
        execute out_;
    end if;
    -- Blackjack: Hit draws the best card that does not bust
    src := replace(pg_get_functiondef('public.rb_blackjack(text, integer)'::regprocedure), chr(13), '');
    if position('''cheat''' in src) = 0 then
        out_ := replace(src, 'deck integer[]; me integer[]; dealer integer[];', 'deck integer[]; me integer[]; dealer integer[]; cheat_k integer;');
        out_ := replace(out_, '        elsif action = ''hit'' then
            me := me || deck[1]; deck := deck[2:];',
            '        elsif action = ''hit'' then
            if public.rb_rig_take(p.id, ''cheat'', ''blackjack'') is not null then
                select i into cheat_k from generate_subscripts(deck, 1) i where public.rb_bj_total(me || deck[i]) <= 21
                 order by public.rb_bj_total(me || deck[i]) desc, i limit 1;
                if cheat_k is not null and cheat_k > 1 then
                    deck := deck[cheat_k:cheat_k] || deck[1:cheat_k - 1] || deck[cheat_k + 1:];
                end if;
            end if;
            me := me || deck[1]; deck := deck[2:];');
        if position('cheat_k > 1' in out_) = 0 then raise exception 'rb_blackjack changed'; end if;
        execute out_;
    end if;
end $$;


update public.rb_config set value = greatest(value, 2026112100) where key = 'min_build';
commit;
