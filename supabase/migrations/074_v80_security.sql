-- Rubenium 8.0, server part 1: security. Made by overhaul/db/make_074.py (do not edit the .sql by hand: edit
-- overhaul/db/074_template.sql or overhaul/golf/sim.sql and run the script again).
-- One transaction, safe to run twice. Undo: 074_down.sql. Nothing players own is changed; no coins, items, hours,
-- streaks or levels are touched. Old apps keep working (every rb_* function keeps its name, arguments and answer),
-- except solo Mini Golf on apps older than 8.0, which asks for the update (see DECISIONS.md, 8.0).
begin;

-- ===================================================================================== golf: the server rolls the ball
-- The hole layouts (1-60, and 101-160 = the same hole mirrored), exactly as in the app.
-- The golf shot, rolled on the server: the same maths as simulate() in Rubenium.py, step for step (1/240 s steps,
-- at most 14 s), so the server decides where the ball stops and whether it went in.
-- Included in 074_v80_security.sql; kept here too so overhaul/golf/test_sim.py can compare it with the app.
create table if not exists public.rb_golf_hole_defs (
    id integer primary key,
    name text not null,
    tee float8[] not null, cup float8[] not null,
    rects float8[] not null default '{}', circles float8[] not null default '{}', sand float8[] not null default '{}',
    ice float8[] not null default '{}', water float8[] not null default '{}', boost float8[] not null default '{}');
alter table public.rb_golf_hole_defs enable row level security;
revoke all on public.rb_golf_hole_defs from anon, authenticated, public;

create or replace function public.rb_golf_sim(hid integer, x float8, y float8, ang float8, pw float8,
                                              out ex float8, out ey float8, out holed boolean)
language plpgsql stable security definer set search_path = '' as $$
declare
    h public.rb_golf_hole_defs%rowtype;
    vmax constant float8 := 1.5297058540778357;          -- sqrt(2 * GOLF_DEC * GOLF_DMAX)
    dt constant float8 := 0.004166666666666667;          -- 1 / 240
    r constant float8 := 0.013;                          -- BALL_R
    cupr constant float8 := 0.022;                       -- CUP_R
    fh constant float8 := 0.62;                          -- FIELD_H
    bounce constant float8 := 0.78;
    dec0 constant float8 := 0.9;                         -- GOLF_DEC
    x0 float8 := x; y0 float8 := y;
    v float8; vx float8; vy float8; cx float8; cy float8;
    qx float8; qy float8; dx float8; dy float8; d float8; nx float8; ny float8; vn float8;
    bd float8; bnx float8; bny float8; sd float8; snx float8; sny float8; k integer; j integer;
    speed float8; dc float8; pull float8; dec float8; f float8;
    nr integer; nc integer; nw integer; nb integer; ns integer; ni integer; hit boolean;
begin
    select * into h from public.rb_golf_hole_defs where id = hid;
    if not found then raise exception 'rb_bad_choice'; end if;
    v := sqrt(greatest(0::float8, least(1::float8, pw))) * vmax;
    vx := cos(ang) * v; vy := sin(ang) * v;
    cx := h.cup[1]; cy := h.cup[2];
    nr := coalesce(array_length(h.rects, 1), 0) / 4; nc := coalesce(array_length(h.circles, 1), 0) / 3;
    nw := coalesce(array_length(h.water, 1), 0) / 4; nb := coalesce(array_length(h.boost, 1), 0) / 6;
    ns := coalesce(array_length(h.sand, 1), 0) / 4; ni := coalesce(array_length(h.ice, 1), 0) / 4;
    for step in 0 .. 240 * 14 - 1 loop
        x := x + vx * dt;
        y := y + vy * dt;
        if x < r then x := r; vx := abs(vx) * bounce;
        elsif x > 1 - r then x := 1 - r; vx := -abs(vx) * bounce; end if;
        if y < r then y := r; vy := abs(vy) * bounce;
        elsif y > fh - r then y := fh - r; vy := -abs(vy) * bounce; end if;
        for k in 0 .. nr - 1 loop                         -- walls
            j := k * 4;
            qx := greatest(h.rects[j + 1], least(h.rects[j + 3], x));
            qy := greatest(h.rects[j + 2], least(h.rects[j + 4], y));
            dx := x - qx; dy := y - qy;
            d := sqrt(dx * dx + dy * dy);
            if d < r then
                if d < 1e-9::float8 then                  -- inside the wall: out the nearest side (Python's min of tuples)
                    bd := x - h.rects[j + 1]; bnx := -1; bny := 0;
                    sd := h.rects[j + 3] - x; snx := 1; sny := 0;
                    if sd < bd or (sd = bd and (snx < bnx or (snx = bnx and sny < bny))) then bd := sd; bnx := snx; bny := sny; end if;
                    sd := y - h.rects[j + 2]; snx := 0; sny := -1;
                    if sd < bd or (sd = bd and (snx < bnx or (snx = bnx and sny < bny))) then bd := sd; bnx := snx; bny := sny; end if;
                    sd := h.rects[j + 4] - y; snx := 0; sny := 1;
                    if sd < bd or (sd = bd and (snx < bnx or (snx = bnx and sny < bny))) then bd := sd; bnx := snx; bny := sny; end if;
                    nx := bnx; ny := bny;
                    if nx <> 0 then x := case when nx < 0 then h.rects[j + 1] - r else h.rects[j + 3] + r end; end if;
                    if ny <> 0 then y := case when ny < 0 then h.rects[j + 2] - r else h.rects[j + 4] + r end; end if;
                else
                    nx := dx / d; ny := dy / d;
                    x := qx + nx * r; y := qy + ny * r;
                end if;
                vn := vx * nx + vy * ny;
                if vn < 0 then
                    vx := vx - (1 + bounce) * vn * nx;
                    vy := vy - (1 + bounce) * vn * ny;
                end if;
            end if;
        end loop;
        for k in 0 .. nc - 1 loop                         -- bumpers
            j := k * 3;
            dx := x - h.circles[j + 1]; dy := y - h.circles[j + 2];
            d := sqrt(dx * dx + dy * dy);
            if d < h.circles[j + 3] + r and d > 1e-9::float8 then
                nx := dx / d; ny := dy / d;
                x := h.circles[j + 1] + nx * (h.circles[j + 3] + r); y := h.circles[j + 2] + ny * (h.circles[j + 3] + r);
                vn := vx * nx + vy * ny;
                if vn < 0 then
                    vx := vx - (1 + 0.95::float8) * vn * nx;
                    vy := vy - (1 + 0.95::float8) * vn * ny;
                end if;
            end if;
        end loop;
        for k in 0 .. nw - 1 loop                         -- water: back to where it was hit from
            j := k * 4;
            if h.water[j + 1] <= x and x <= h.water[j + 3] and h.water[j + 2] <= y and y <= h.water[j + 4] then
                ex := x0; ey := y0; holed := false;
                return;
            end if;
        end loop;
        for k in 0 .. nb - 1 loop                         -- boost pads
            j := k * 6;
            if h.boost[j + 1] <= x and x <= h.boost[j + 3] and h.boost[j + 2] <= y and y <= h.boost[j + 4] then
                vx := vx + h.boost[j + 5] * dt * 4;
                vy := vy + h.boost[j + 6] * dt * 4;
            end if;
        end loop;
        speed := sqrt(vx * vx + vy * vy);
        dc := sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
        if dc < cupr * 2.2::float8 and speed < 0.7::float8 then   -- the cup pulls a slow ball in a little
            pull := 1.6::float8 * dt;
            vx := vx + (cx - x) / greatest(dc, 1e-6::float8) * pull;
            vy := vy + (cy - y) / greatest(dc, 1e-6::float8) * pull;
        end if;
        if dc < cupr and speed < 1.05::float8 then
            ex := cx; ey := cy; holed := true;
            return;
        end if;
        dec := (dec0 + speed * 0.04::float8) * dt;
        hit := false;
        for k in 0 .. ns - 1 loop
            j := k * 4;
            if h.sand[j + 1] <= x and x <= h.sand[j + 3] and h.sand[j + 2] <= y and y <= h.sand[j + 4] then hit := true; exit; end if;
        end loop;
        if hit then
            dec := dec * 4.0::float8;
        else
            for k in 0 .. ni - 1 loop
                j := k * 4;
                if h.ice[j + 1] <= x and x <= h.ice[j + 3] and h.ice[j + 2] <= y and y <= h.ice[j + 4] then hit := true; exit; end if;
            end loop;
            if hit then dec := dec * 0.25::float8; end if;
        end if;
        if speed <= dec or speed < 0.004::float8 then exit; end if;
        f := (speed - dec) / speed;
        vx := vx * f; vy := vy * f;
    end loop;
    ex := x; ey := y; holed := false;
end $$;
revoke all on function public.rb_golf_sim(integer, float8, float8, float8, float8) from public, anon, authenticated;

insert into public.rb_golf_hole_defs (id, name, tee, cup, rects, circles, sand, ice, water, boost) values
(1, 'Warm-up', '{0.1,0.31}', '{0.88,0.31}', '{}', '{0.5,0.31,0.05}', '{}', '{}', '{}', '{}'),
(2, 'The Gate', '{0.1,0.31}', '{0.88,0.31}', '{0.48,0.0,0.52,0.24,0.48,0.38,0.52,0.62}', '{}', '{}', '{}', '{}', '{}'),
(3, 'Dogleg', '{0.1,0.5}', '{0.86,0.12}', '{0.0,0.0,0.62,0.36}', '{}', '{}', '{}', '{}', '{}'),
(4, 'Pinball', '{0.1,0.31}', '{0.9,0.31}', '{}', '{0.35,0.2,0.045,0.35,0.42,0.045,0.6,0.31,0.045,0.75,0.15,0.045,0.75,0.47,0.045}', '{}', '{}', '{}', '{}'),
(5, 'Zigzag', '{0.1,0.1}', '{0.9,0.52}', '{0.3,0.0,0.36,0.44,0.62,0.18,0.68,0.62}', '{}', '{}', '{}', '{}', '{}'),
(6, 'The Island', '{0.1,0.31}', '{0.5,0.31}', '{0.38,0.17,0.62,0.21,0.38,0.41,0.62,0.45,0.38,0.21,0.42,0.41}', '{}', '{}', '{}', '{}', '{}'),
(7, 'Tunnel', '{0.08,0.08}', '{0.92,0.54}', '{0.25,0.0,0.75,0.26,0.25,0.36,0.75,0.62}', '{}', '{}', '{}', '{}', '{}'),
(8, 'Diamond', '{0.08,0.31}', '{0.92,0.31}', '{0.45,0.2,0.55,0.42}', '{0.3,0.31,0.04,0.7,0.31,0.04}', '{}', '{}', '{}', '{}'),
(9, 'Bunker', '{0.1,0.31}', '{0.88,0.31}', '{}', '{}', '{0.4,0.12,0.62,0.5}', '{}', '{}', '{}'),
(10, 'Lake', '{0.1,0.5}', '{0.88,0.14}', '{}', '{}', '{}', '{}', '{0.3,0.0,0.55,0.4}', '{}'),
(11, 'Ice Rink', '{0.1,0.31}', '{0.86,0.31}', '{0.5,0.0,0.54,0.2,0.5,0.42,0.54,0.62}', '{}', '{}', '{0.2,0.0,0.8,0.62}', '{}', '{}'),
(12, 'Launch Pad', '{0.08,0.52}', '{0.9,0.1}', '{0.0,0.0,0.4,0.36}', '{}', '{}', '{}', '{}', '{0.42,0.4,0.56,0.62,0.0,-1.6}'),
(13, 'Moat', '{0.1,0.31}', '{0.7,0.31}', '{}', '{}', '{}', '{}', '{0.55,0.12,0.85,0.18,0.55,0.44,0.85,0.5,0.85,0.12,0.91,0.5}', '{}'),
(14, 'Sand Trap Alley', '{0.08,0.1}', '{0.92,0.52}', '{0.3,0.0,0.34,0.4,0.64,0.22,0.68,0.62}', '{}', '{0.36,0.4,0.62,0.62}', '{}', '{}', '{0.7,0.02,0.95,0.16,0.0,1.4}'),
(15, 'Bumper Lake', '{0.08,0.31}', '{0.92,0.31}', '{}', '{0.4,0.31,0.05,0.62,0.15,0.04,0.62,0.47,0.04}', '{}', '{}', '{0.45,0.24,0.58,0.38}', '{}'),
(16, 'Express', '{0.08,0.31}', '{0.92,0.31}', '{0.3,0.0,0.7,0.22,0.3,0.4,0.7,0.62}', '{}', '{0.78,0.18,0.86,0.44}', '{0.44,0.22,0.7,0.4}', '{}', '{0.32,0.24,0.42,0.38,1.8,0.0}'),
(17, 'Horseshoe', '{0.1,0.12}', '{0.12,0.5}', '{0.0,0.28,0.72,0.34}', '{0.86,0.31,0.04}', '{0.4,0.4,0.56,0.62}', '{}', '{}', '{}'),
(18, 'Twin Lakes', '{0.08,0.31}', '{0.92,0.31}', '{}', '{0.5,0.31,0.035}', '{}', '{}', '{0.25,0.0,0.75,0.2,0.25,0.42,0.75,0.62}', '{}'),
(19, 'Pinball Alley', '{0.08,0.31}', '{0.92,0.31}', '{0.2,0.0,0.8,0.1,0.2,0.52,0.8,0.62}', '{0.32,0.22,0.03,0.32,0.4,0.03,0.47,0.31,0.03,0.62,0.2,0.03,0.62,0.42,0.03,0.76,0.31,0.03}', '{}', '{}', '{}', '{}'),
(20, 'Ice Bridge', '{0.08,0.31}', '{0.92,0.31}', '{}', '{}', '{}', '{0.22,0.24,0.78,0.38}', '{0.22,0.0,0.78,0.24,0.22,0.38,0.78,0.62}', '{}'),
(21, 'Fortress', '{0.1,0.31}', '{0.7,0.31}', '{0.55,0.16,0.85,0.2,0.55,0.42,0.85,0.46,0.81,0.2,0.85,0.42,0.55,0.2,0.59,0.27,0.55,0.35,0.59,0.42}', '{0.35,0.31,0.04}', '{}', '{}', '{}', '{}'),
(22, 'Slalom', '{0.08,0.1}', '{0.92,0.52}', '{0.22,0.0,0.26,0.42,0.42,0.2,0.46,0.62,0.62,0.0,0.66,0.42,0.8,0.2,0.84,0.62}', '{}', '{}', '{}', '{}', '{}'),
(23, 'Booster Loop', '{0.1,0.5}', '{0.1,0.12}', '{0.0,0.28,0.7,0.34}', '{}', '{}', '{0.2,0.0,0.4,0.28}', '{}', '{0.74,0.36,0.96,0.6,0.0,-1.7,0.4,0.04,0.7,0.24,-1.6,0.0}'),
(24, 'Dunes', '{0.08,0.31}', '{0.92,0.31}', '{0.48,0.24,0.52,0.38}', '{}', '{0.18,0.0,0.88,0.22,0.18,0.4,0.88,0.62}', '{}', '{}', '{0.2,0.26,0.34,0.36,1.2,0.0}'),
(25, 'Switchback', '{0.08,0.1}', '{0.92,0.52}', '{0.0,0.2,0.8,0.24,0.2,0.38,1.0,0.42}', '{}', '{}', '{}', '{}', '{}'),
(26, 'Bullseye', '{0.08,0.31}', '{0.52,0.31}', '{}', '{0.52,0.17,0.035,0.52,0.45,0.035,0.65,0.31,0.035,0.42,0.2,0.03,0.42,0.42,0.03}', '{}', '{}', '{}', '{}'),
(27, 'Frozen Pond', '{0.08,0.31}', '{0.92,0.31}', '{}', '{}', '{}', '{0.15,0.06,0.85,0.56}', '{0.4,0.24,0.6,0.38}', '{}'),
(28, 'Sandbox', '{0.08,0.52}', '{0.9,0.12}', '{}', '{0.62,0.4,0.04}', '{0.25,0.0,0.75,0.62}', '{}', '{}', '{0.28,0.44,0.4,0.58,1.5,-0.9}'),
(29, 'Keyhole', '{0.08,0.5}', '{0.9,0.31}', '{0.5,0.0,0.54,0.26,0.5,0.36,0.54,0.62}', '{}', '{0.58,0.14,0.7,0.48}', '{}', '{}', '{}'),
(30, 'Snail', '{0.1,0.1}', '{0.5,0.34}', '{0.25,0.18,0.75,0.21,0.72,0.21,0.75,0.5,0.25,0.47,0.72,0.5,0.25,0.29,0.28,0.47}', '{}', '{}', '{}', '{}', '{}'),
(31, 'Waterfalls', '{0.08,0.31}', '{0.92,0.31}', '{}', '{}', '{}', '{}', '{0.3,0.0,0.36,0.44,0.64,0.18,0.7,0.62}', '{}'),
(32, 'Sand Rocket', '{0.08,0.31}', '{0.92,0.31}', '{}', '{}', '{0.28,0.0,0.72,0.62}', '{}', '{}', '{0.28,0.26,0.72,0.36,2.2,0.0}'),
(33, 'Ping Pong', '{0.08,0.31}', '{0.5,0.31}', '{0.35,0.12,0.38,0.5,0.62,0.12,0.65,0.5}', '{}', '{}', '{}', '{}', '{}'),
(34, 'Crossroads', '{0.08,0.12}', '{0.92,0.5}', '{0.4,0.0,0.44,0.22,0.4,0.4,0.44,0.62,0.56,0.0,0.6,0.22,0.56,0.4,0.6,0.62}', '{0.5,0.31,0.03}', '{}', '{}', '{}', '{}'),
(35, 'Frozen Moat', '{0.08,0.31}', '{0.8,0.31}', '{}', '{}', '{}', '{0.2,0.12,0.66,0.5}', '{0.66,0.12,0.92,0.18,0.66,0.44,0.92,0.5,0.92,0.12,0.97,0.5}', '{}'),
(36, 'Labyrinth', '{0.08,0.08}', '{0.12,0.57}', '{0.0,0.16,0.7,0.2,0.3,0.32,1.0,0.36,0.0,0.48,0.7,0.52}', '{}', '{}', '{}', '{}', '{}'),
(37, 'Comet Trail', '{0.08,0.31}', '{0.92,0.31}', '{}', '{0.32,0.15,0.04,0.47,0.47,0.04,0.62,0.15,0.04,0.77,0.47,0.04}', '{}', '{}', '{}', '{0.15,0.25,0.25,0.37,1.4,0.0}'),
(38, 'Oasis', '{0.08,0.31}', '{0.6,0.31}', '{}', '{}', '{0.15,0.0,0.85,0.62}', '{}', '{0.7,0.2,0.76,0.42}', '{}'),
(39, 'Double Dogleg', '{0.1,0.52}', '{0.9,0.1}', '{0.0,0.0,0.45,0.4,0.55,0.22,1.0,0.62}', '{}', '{}', '{}', '{}', '{}'),
(40, 'Grand Finale', '{0.08,0.52}', '{0.92,0.12}', '{0.3,0.0,0.34,0.38}', '{0.8,0.45,0.04}', '{}', '{0.62,0.0,0.85,0.3}', '{0.5,0.32,0.62,0.62}', '{0.36,0.04,0.48,0.16,1.6,0.0}'),
(41, 'Hourglass', '{0.08,0.31}', '{0.92,0.31}', '{0.4,0.0,0.6,0.22,0.4,0.4,0.6,0.62}', '{}', '{0.7,0.05,0.85,0.2}', '{}', '{}', '{}'),
(42, 'Ice Rink', '{0.1,0.52}', '{0.88,0.1}', '{0.48,0.24,0.52,0.62}', '{0.7,0.4,0.04}', '{}', '{0.05,0.05,0.95,0.57}', '{}', '{}'),
(43, 'Moat', '{0.08,0.31}', '{0.5,0.31}', '{}', '{}', '{}', '{}', '{0.35,0.12,0.65,0.18,0.35,0.44,0.65,0.5,0.35,0.18,0.4,0.26,0.35,0.36,0.4,0.44,0.6,0.18,0.65,0.44}', '{0.2,0.04,0.3,0.1,1.4,0.0}'),
(44, 'Pinball', '{0.5,0.55}', '{0.5,0.08}', '{}', '{0.3,0.2,0.04,0.5,0.3,0.045,0.7,0.2,0.04,0.4,0.42,0.035,0.6,0.42,0.035}', '{}', '{}', '{}', '{}'),
(45, 'Staircase', '{0.06,0.55}', '{0.94,0.07}', '{0.2,0.38,0.24,0.62,0.4,0.24,0.44,0.5,0.6,0.1,0.64,0.36,0.8,0.0,0.84,0.22}', '{}', '{}', '{}', '{}', '{}'),
(46, 'Desert Run', '{0.08,0.1}', '{0.92,0.52}', '{}', '{0.5,0.31,0.05}', '{0.25,0.0,0.4,0.45,0.6,0.17,0.75,0.62}', '{}', '{}', '{0.42,0.45,0.58,0.57,1.3,0.0}'),
(47, 'Crossroads', '{0.08,0.31}', '{0.92,0.31}', '{0.3,0.0,0.34,0.25,0.3,0.37,0.34,0.62,0.66,0.0,0.7,0.25,0.66,0.37,0.7,0.62}', '{}', '{}', '{0.34,0.25,0.66,0.37}', '{}', '{}'),
(48, 'Volcano', '{0.08,0.52}', '{0.5,0.31}', '{}', '{0.5,0.12,0.035,0.5,0.5,0.035}', '{0.2,0.0,0.32,0.62}', '{}', '{0.4,0.2,0.44,0.42,0.56,0.2,0.6,0.42}', '{0.65,0.04,0.8,0.14,-1.3,0.0}'),
(49, 'Spiral', '{0.08,0.08}', '{0.5,0.31}', '{0.2,0.16,0.8,0.2,0.76,0.2,0.8,0.5,0.3,0.46,0.76,0.5,0.3,0.26,0.34,0.46}', '{}', '{}', '{}', '{}', '{}'),
(50, 'River Crossing', '{0.08,0.31}', '{0.92,0.31}', '{}', '{}', '{0.7,0.1,0.8,0.52}', '{}', '{0.42,0.0,0.56,0.24,0.42,0.38,0.56,0.62}', '{}'),
(51, 'Ice Slalom', '{0.06,0.31}', '{0.94,0.31}', '{}', '{0.3,0.2,0.035,0.45,0.42,0.035,0.6,0.2,0.035,0.75,0.42,0.035}', '{}', '{0.2,0.0,0.85,0.62}', '{}', '{}'),
(52, 'Rocket Ramp', '{0.08,0.52}', '{0.92,0.52}', '{0.3,0.22,0.34,0.62,0.66,0.22,0.7,0.62}', '{}', '{}', '{}', '{}', '{0.36,0.04,0.64,0.16,1.6,0.0}'),
(53, 'Sand Castle', '{0.08,0.31}', '{0.75,0.31}', '{0.62,0.14,0.88,0.18,0.62,0.44,0.88,0.48,0.84,0.18,0.88,0.44}', '{0.55,0.31,0.035}', '{0.3,0.0,0.45,0.62}', '{}', '{}', '{}'),
(54, 'Lighthouse', '{0.08,0.52}', '{0.85,0.12}', '{}', '{0.5,0.31,0.06}', '{}', '{}', '{0.0,0.0,0.3,0.25,0.65,0.4,1.0,0.62}', '{}'),
(55, 'Bounce House', '{0.1,0.31}', '{0.9,0.31}', '{}', '{0.3,0.12,0.04,0.3,0.5,0.04,0.45,0.31,0.04,0.6,0.12,0.04,0.6,0.5,0.04,0.75,0.31,0.04}', '{}', '{}', '{}', '{}'),
(56, 'The Funnel', '{0.08,0.31}', '{0.92,0.31}', '{0.4,0.0,0.7,0.12,0.4,0.5,0.7,0.62,0.7,0.0,0.74,0.25,0.7,0.37,0.74,0.62}', '{}', '{}', '{0.74,0.25,0.95,0.37}', '{}', '{}'),
(57, 'Glacier Bay', '{0.1,0.1}', '{0.9,0.52}', '{0.45,0.0,0.49,0.4}', '{}', '{}', '{0.0,0.0,0.45,0.62}', '{0.6,0.0,0.7,0.35}', '{}'),
(58, 'Conveyor', '{0.08,0.1}', '{0.92,0.1}', '{0.2,0.18,0.8,0.22}', '{}', '{}', '{}', '{}', '{0.2,0.3,0.8,0.42,1.5,0.0,0.85,0.24,0.97,0.56,0.0,-1.5}'),
(59, 'Desert Oasis', '{0.08,0.52}', '{0.5,0.12}', '{}', '{0.5,0.4,0.04}', '{0.2,0.2,0.38,0.62,0.62,0.2,0.8,0.62}', '{}', '{0.44,0.0,0.46,0.06}', '{}'),
(60, 'Rubenium Cup', '{0.06,0.31}', '{0.94,0.31}', '{0.25,0.0,0.29,0.22,0.25,0.4,0.29,0.62}', '{0.5,0.2,0.04,0.5,0.42,0.04}', '{}', '{0.55,0.0,0.75,0.62}', '{0.78,0.0,0.84,0.2,0.78,0.42,0.84,0.62}', '{0.32,0.25,0.44,0.37,1.2,0.0}'),
(101, 'Warm-up', '{0.9,0.31}', '{0.12,0.31}', '{}', '{0.5,0.31,0.05}', '{}', '{}', '{}', '{}'),
(102, 'The Gate', '{0.9,0.31}', '{0.12,0.31}', '{0.48,0.0,0.52,0.24,0.48,0.38,0.52,0.62}', '{}', '{}', '{}', '{}', '{}'),
(103, 'Dogleg', '{0.9,0.5}', '{0.14,0.12}', '{0.38,0.0,1.0,0.36}', '{}', '{}', '{}', '{}', '{}'),
(104, 'Pinball', '{0.9,0.31}', '{0.09999999999999998,0.31}', '{}', '{0.65,0.2,0.045,0.65,0.42,0.045,0.4,0.31,0.045,0.25,0.15,0.045,0.25,0.47,0.045}', '{}', '{}', '{}', '{}'),
(105, 'Zigzag', '{0.9,0.1}', '{0.09999999999999998,0.52}', '{0.64,0.0,0.7,0.44,0.31999999999999995,0.18,0.38,0.62}', '{}', '{}', '{}', '{}', '{}'),
(106, 'The Island', '{0.9,0.31}', '{0.5,0.31}', '{0.38,0.17,0.62,0.21,0.38,0.41,0.62,0.45,0.5800000000000001,0.21,0.62,0.41}', '{}', '{}', '{}', '{}', '{}'),
(107, 'Tunnel', '{0.92,0.08}', '{0.07999999999999996,0.54}', '{0.25,0.0,0.75,0.26,0.25,0.36,0.75,0.62}', '{}', '{}', '{}', '{}', '{}'),
(108, 'Diamond', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.44999999999999996,0.2,0.55,0.42}', '{0.7,0.31,0.04,0.30000000000000004,0.31,0.04}', '{}', '{}', '{}', '{}'),
(109, 'Bunker', '{0.9,0.31}', '{0.12,0.31}', '{}', '{}', '{0.38,0.12,0.6,0.5}', '{}', '{}', '{}'),
(110, 'Lake', '{0.9,0.5}', '{0.12,0.14}', '{}', '{}', '{}', '{}', '{0.44999999999999996,0.0,0.7,0.4}', '{}'),
(111, 'Ice Rink', '{0.9,0.31}', '{0.14,0.31}', '{0.45999999999999996,0.0,0.5,0.2,0.45999999999999996,0.42,0.5,0.62}', '{}', '{}', '{0.19999999999999996,0.0,0.8,0.62}', '{}', '{}'),
(112, 'Launch Pad', '{0.92,0.52}', '{0.09999999999999998,0.1}', '{0.6,0.0,1.0,0.36}', '{}', '{}', '{}', '{}', '{0.43999999999999995,0.4,0.5800000000000001,0.62,-0.0,-1.6}'),
(113, 'Moat', '{0.9,0.31}', '{0.30000000000000004,0.31}', '{}', '{}', '{}', '{}', '{0.15000000000000002,0.12,0.44999999999999996,0.18,0.15000000000000002,0.44,0.44999999999999996,0.5,0.08999999999999997,0.12,0.15000000000000002,0.5}', '{}'),
(114, 'Sand Trap Alley', '{0.92,0.1}', '{0.07999999999999996,0.52}', '{0.6599999999999999,0.0,0.7,0.4,0.31999999999999995,0.22,0.36,0.62}', '{}', '{0.38,0.4,0.64,0.62}', '{}', '{}', '{0.050000000000000044,0.02,0.30000000000000004,0.16,-0.0,1.4}'),
(115, 'Bumper Lake', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{0.6,0.31,0.05,0.38,0.15,0.04,0.38,0.47,0.04}', '{}', '{}', '{0.42000000000000004,0.24,0.55,0.38}', '{}'),
(116, 'Express', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.30000000000000004,0.0,0.7,0.22,0.30000000000000004,0.4,0.7,0.62}', '{}', '{0.14,0.18,0.21999999999999997,0.44}', '{0.30000000000000004,0.22,0.56,0.4}', '{}', '{0.5800000000000001,0.24,0.6799999999999999,0.38,-1.8,0.0}'),
(117, 'Horseshoe', '{0.9,0.12}', '{0.88,0.5}', '{0.28,0.28,1.0,0.34}', '{0.14,0.31,0.04}', '{0.43999999999999995,0.4,0.6,0.62}', '{}', '{}', '{}'),
(118, 'Twin Lakes', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{0.5,0.31,0.035}', '{}', '{}', '{0.25,0.0,0.75,0.2,0.25,0.42,0.75,0.62}', '{}'),
(119, 'Pinball Alley', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.19999999999999996,0.0,0.8,0.1,0.19999999999999996,0.52,0.8,0.62}', '{0.6799999999999999,0.22,0.03,0.6799999999999999,0.4,0.03,0.53,0.31,0.03,0.38,0.2,0.03,0.38,0.42,0.03,0.24,0.31,0.03}', '{}', '{}', '{}', '{}'),
(120, 'Ice Bridge', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{}', '{}', '{0.21999999999999997,0.24,0.78,0.38}', '{0.21999999999999997,0.0,0.78,0.24,0.21999999999999997,0.38,0.78,0.62}', '{}'),
(121, 'Fortress', '{0.9,0.31}', '{0.30000000000000004,0.31}', '{0.15000000000000002,0.16,0.44999999999999996,0.2,0.15000000000000002,0.42,0.44999999999999996,0.46,0.15000000000000002,0.2,0.18999999999999995,0.42,0.41000000000000003,0.2,0.44999999999999996,0.27,0.41000000000000003,0.35,0.44999999999999996,0.42}', '{0.65,0.31,0.04}', '{}', '{}', '{}', '{}'),
(122, 'Slalom', '{0.92,0.1}', '{0.07999999999999996,0.52}', '{0.74,0.0,0.78,0.42,0.54,0.2,0.5800000000000001,0.62,0.33999999999999997,0.0,0.38,0.42,0.16000000000000003,0.2,0.19999999999999996,0.62}', '{}', '{}', '{}', '{}', '{}'),
(123, 'Booster Loop', '{0.9,0.5}', '{0.9,0.12}', '{0.30000000000000004,0.28,1.0,0.34}', '{}', '{}', '{0.6,0.0,0.8,0.28}', '{}', '{0.040000000000000036,0.36,0.26,0.6,-0.0,-1.7,0.30000000000000004,0.04,0.6,0.24,1.6,0.0}'),
(124, 'Dunes', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.48,0.24,0.52,0.38}', '{}', '{0.12,0.0,0.8200000000000001,0.22,0.12,0.4,0.8200000000000001,0.62}', '{}', '{}', '{0.6599999999999999,0.26,0.8,0.36,-1.2,0.0}'),
(125, 'Switchback', '{0.92,0.1}', '{0.07999999999999996,0.52}', '{0.19999999999999996,0.2,1.0,0.24,0.0,0.38,0.8,0.42}', '{}', '{}', '{}', '{}', '{}'),
(126, 'Bullseye', '{0.92,0.31}', '{0.48,0.31}', '{}', '{0.48,0.17,0.035,0.48,0.45,0.035,0.35,0.31,0.035,0.5800000000000001,0.2,0.03,0.5800000000000001,0.42,0.03}', '{}', '{}', '{}', '{}'),
(127, 'Frozen Pond', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{}', '{}', '{0.15000000000000002,0.06,0.85,0.56}', '{0.4,0.24,0.6,0.38}', '{}'),
(128, 'Sandbox', '{0.92,0.52}', '{0.09999999999999998,0.12}', '{}', '{0.38,0.4,0.04}', '{0.25,0.0,0.75,0.62}', '{}', '{}', '{0.6,0.44,0.72,0.58,-1.5,-0.9}'),
(129, 'Keyhole', '{0.92,0.5}', '{0.09999999999999998,0.31}', '{0.45999999999999996,0.0,0.5,0.26,0.45999999999999996,0.36,0.5,0.62}', '{}', '{0.30000000000000004,0.14,0.42000000000000004,0.48}', '{}', '{}', '{}'),
(130, 'Snail', '{0.9,0.1}', '{0.5,0.34}', '{0.25,0.18,0.75,0.21,0.25,0.21,0.28,0.5,0.28,0.47,0.75,0.5,0.72,0.29,0.75,0.47}', '{}', '{}', '{}', '{}', '{}'),
(131, 'Waterfalls', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{}', '{}', '{}', '{0.64,0.0,0.7,0.44,0.30000000000000004,0.18,0.36,0.62}', '{}'),
(132, 'Sand Rocket', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{}', '{0.28,0.0,0.72,0.62}', '{}', '{}', '{0.28,0.26,0.72,0.36,-2.2,0.0}'),
(133, 'Ping Pong', '{0.92,0.31}', '{0.5,0.31}', '{0.62,0.12,0.65,0.5,0.35,0.12,0.38,0.5}', '{}', '{}', '{}', '{}', '{}'),
(134, 'Crossroads', '{0.92,0.12}', '{0.07999999999999996,0.5}', '{0.56,0.0,0.6,0.22,0.56,0.4,0.6,0.62,0.4,0.0,0.43999999999999995,0.22,0.4,0.4,0.43999999999999995,0.62}', '{0.5,0.31,0.03}', '{}', '{}', '{}', '{}'),
(135, 'Frozen Moat', '{0.92,0.31}', '{0.19999999999999996,0.31}', '{}', '{}', '{}', '{0.33999999999999997,0.12,0.8,0.5}', '{0.07999999999999996,0.12,0.33999999999999997,0.18,0.07999999999999996,0.44,0.33999999999999997,0.5,0.030000000000000027,0.12,0.07999999999999996,0.5}', '{}'),
(136, 'Labyrinth', '{0.92,0.08}', '{0.88,0.57}', '{0.30000000000000004,0.16,1.0,0.2,0.0,0.32,0.7,0.36,0.30000000000000004,0.48,1.0,0.52}', '{}', '{}', '{}', '{}', '{}'),
(137, 'Comet Trail', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{0.6799999999999999,0.15,0.04,0.53,0.47,0.04,0.38,0.15,0.04,0.22999999999999998,0.47,0.04}', '{}', '{}', '{}', '{0.75,0.25,0.85,0.37,-1.4,0.0}'),
(138, 'Oasis', '{0.92,0.31}', '{0.4,0.31}', '{}', '{}', '{0.15000000000000002,0.0,0.85,0.62}', '{}', '{0.24,0.2,0.30000000000000004,0.42}', '{}'),
(139, 'Double Dogleg', '{0.9,0.52}', '{0.09999999999999998,0.1}', '{0.55,0.0,1.0,0.4,0.0,0.22,0.44999999999999996,0.62}', '{}', '{}', '{}', '{}', '{}'),
(140, 'Grand Finale', '{0.92,0.52}', '{0.07999999999999996,0.12}', '{0.6599999999999999,0.0,0.7,0.38}', '{0.19999999999999996,0.45,0.04}', '{}', '{0.15000000000000002,0.0,0.38,0.3}', '{0.38,0.32,0.5,0.62}', '{0.52,0.04,0.64,0.16,-1.6,0.0}'),
(141, 'Hourglass', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.4,0.0,0.6,0.22,0.4,0.4,0.6,0.62}', '{}', '{0.15000000000000002,0.05,0.30000000000000004,0.2}', '{}', '{}', '{}'),
(142, 'Ice Rink', '{0.9,0.52}', '{0.12,0.1}', '{0.48,0.24,0.52,0.62}', '{0.30000000000000004,0.4,0.04}', '{}', '{0.050000000000000044,0.05,0.95,0.57}', '{}', '{}'),
(143, 'Moat', '{0.92,0.31}', '{0.5,0.31}', '{}', '{}', '{}', '{}', '{0.35,0.12,0.65,0.18,0.35,0.44,0.65,0.5,0.6,0.18,0.65,0.26,0.6,0.36,0.65,0.44,0.35,0.18,0.4,0.44}', '{0.7,0.04,0.8,0.1,-1.4,0.0}'),
(144, 'Pinball', '{0.5,0.55}', '{0.5,0.08}', '{}', '{0.7,0.2,0.04,0.5,0.3,0.045,0.30000000000000004,0.2,0.04,0.6,0.42,0.035,0.4,0.42,0.035}', '{}', '{}', '{}', '{}'),
(145, 'Staircase', '{0.94,0.55}', '{0.06000000000000005,0.07}', '{0.76,0.38,0.8,0.62,0.56,0.24,0.6,0.5,0.36,0.1,0.4,0.36,0.16000000000000003,0.0,0.19999999999999996,0.22}', '{}', '{}', '{}', '{}', '{}'),
(146, 'Desert Run', '{0.92,0.1}', '{0.07999999999999996,0.52}', '{}', '{0.5,0.31,0.05}', '{0.6,0.0,0.75,0.45,0.25,0.17,0.4,0.62}', '{}', '{}', '{0.42000000000000004,0.45,0.5800000000000001,0.57,-1.3,0.0}'),
(147, 'Crossroads', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.6599999999999999,0.0,0.7,0.25,0.6599999999999999,0.37,0.7,0.62,0.30000000000000004,0.0,0.33999999999999997,0.25,0.30000000000000004,0.37,0.33999999999999997,0.62}', '{}', '{}', '{0.33999999999999997,0.25,0.6599999999999999,0.37}', '{}', '{}'),
(148, 'Volcano', '{0.92,0.52}', '{0.5,0.31}', '{}', '{0.5,0.12,0.035,0.5,0.5,0.035}', '{0.6799999999999999,0.0,0.8,0.62}', '{}', '{0.56,0.2,0.6,0.42,0.4,0.2,0.43999999999999995,0.42}', '{0.19999999999999996,0.04,0.35,0.14,1.3,0.0}'),
(149, 'Spiral', '{0.92,0.08}', '{0.5,0.31}', '{0.19999999999999996,0.16,0.8,0.2,0.19999999999999996,0.2,0.24,0.5,0.24,0.46,0.7,0.5,0.6599999999999999,0.26,0.7,0.46}', '{}', '{}', '{}', '{}', '{}'),
(150, 'River Crossing', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{}', '{}', '{0.19999999999999996,0.1,0.30000000000000004,0.52}', '{}', '{0.43999999999999995,0.0,0.5800000000000001,0.24,0.43999999999999995,0.38,0.5800000000000001,0.62}', '{}'),
(151, 'Ice Slalom', '{0.94,0.31}', '{0.06000000000000005,0.31}', '{}', '{0.7,0.2,0.035,0.55,0.42,0.035,0.4,0.2,0.035,0.25,0.42,0.035}', '{}', '{0.15000000000000002,0.0,0.8,0.62}', '{}', '{}'),
(152, 'Rocket Ramp', '{0.92,0.52}', '{0.07999999999999996,0.52}', '{0.6599999999999999,0.22,0.7,0.62,0.30000000000000004,0.22,0.33999999999999997,0.62}', '{}', '{}', '{}', '{}', '{0.36,0.04,0.64,0.16,-1.6,0.0}'),
(153, 'Sand Castle', '{0.92,0.31}', '{0.25,0.31}', '{0.12,0.14,0.38,0.18,0.12,0.44,0.38,0.48,0.12,0.18,0.16000000000000003,0.44}', '{0.44999999999999996,0.31,0.035}', '{0.55,0.0,0.7,0.62}', '{}', '{}', '{}'),
(154, 'Lighthouse', '{0.92,0.52}', '{0.15000000000000002,0.12}', '{}', '{0.5,0.31,0.06}', '{}', '{}', '{0.7,0.0,1.0,0.25,0.0,0.4,0.35,0.62}', '{}'),
(155, 'Bounce House', '{0.9,0.31}', '{0.09999999999999998,0.31}', '{}', '{0.7,0.12,0.04,0.7,0.5,0.04,0.55,0.31,0.04,0.4,0.12,0.04,0.4,0.5,0.04,0.25,0.31,0.04}', '{}', '{}', '{}', '{}'),
(156, 'The Funnel', '{0.92,0.31}', '{0.07999999999999996,0.31}', '{0.30000000000000004,0.0,0.6,0.12,0.30000000000000004,0.5,0.6,0.62,0.26,0.0,0.30000000000000004,0.25,0.26,0.37,0.30000000000000004,0.62}', '{}', '{}', '{0.050000000000000044,0.25,0.26,0.37}', '{}', '{}'),
(157, 'Glacier Bay', '{0.9,0.1}', '{0.09999999999999998,0.52}', '{0.51,0.0,0.55,0.4}', '{}', '{}', '{0.55,0.0,1.0,0.62}', '{0.30000000000000004,0.0,0.4,0.35}', '{}'),
(158, 'Conveyor', '{0.92,0.1}', '{0.07999999999999996,0.1}', '{0.19999999999999996,0.18,0.8,0.22}', '{}', '{}', '{}', '{}', '{0.19999999999999996,0.3,0.8,0.42,-1.5,0.0,0.030000000000000027,0.24,0.15000000000000002,0.56,-0.0,-1.5}'),
(159, 'Desert Oasis', '{0.92,0.52}', '{0.5,0.12}', '{}', '{0.5,0.4,0.04}', '{0.62,0.2,0.8,0.62,0.19999999999999996,0.2,0.38,0.62}', '{}', '{0.54,0.0,0.56,0.06}', '{}'),
(160, 'Rubenium Cup', '{0.94,0.31}', '{0.06000000000000005,0.31}', '{0.71,0.0,0.75,0.22,0.71,0.4,0.75,0.62}', '{0.5,0.2,0.04,0.5,0.42,0.04}', '{}', '{0.25,0.0,0.44999999999999996,0.62}', '{0.16000000000000003,0.0,0.21999999999999997,0.2,0.16000000000000003,0.42,0.21999999999999997,0.62}', '{0.56,0.25,0.6799999999999999,0.37,-1.2,0.0}')
on conflict (id) do update set name = excluded.name, tee = excluded.tee, cup = excluded.cup, rects = excluded.rects,
    circles = excluded.circles, sand = excluded.sand, ice = excluded.ice, water = excluded.water, boost = excluded.boost;

-- One shot from where the server last saw the ball (null = the tee). The app's own start is used when it is the
-- same spot (it keeps more decimals than the server stores), so both roll exactly the same shot.
create or replace function public.rb_golf_roll(hid integer, pos jsonb, x0 float8, y0 float8, ang float8, pw float8,
                                               out sx float8, out sy float8, out ex float8, out ey float8, out holed boolean)
language plpgsql stable security definer set search_path = '' as $$
declare h public.rb_golf_hole_defs%rowtype; s record;
begin
    select * into h from public.rb_golf_hole_defs where id = hid;
    if not found then raise exception 'rb_bad_choice'; end if;
    if ang is null or pw is null or ang <> ang or pw <> pw or abs(ang) > 100 or pw < 0 or pw > 1 then
        raise exception 'rb_bad_choice';
    end if;
    if pos is null or jsonb_typeof(pos) <> 'array' then
        sx := h.tee[1]; sy := h.tee[2];
    else
        sx := (pos ->> 0)::float8; sy := (pos ->> 1)::float8;
    end if;
    if x0 is not null and y0 is not null and abs(x0 - sx) <= 0.0006 and abs(y0 - sy) <= 0.0006 then
        sx := x0; sy := y0;
    end if;
    select * into s from public.rb_golf_sim(hid, sx, sy, ang, pw);
    ex := s.ex; ey := s.ey; holed := s.holed;
end $$;
revoke all on function public.rb_golf_roll(integer, jsonb, float8, float8, float8, float8) from public, anon, authenticated;

-- 1 v 1: same arguments and answer as before; x, y and holed sent by the app are no longer believed.
create or replace function public.rb_golf_shot(gid uuid, n integer, x0 double precision, y0 double precision,
                                               ang double precision, pow double precision, x double precision,
                                               y double precision, holed boolean)
returns json language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype; side text; done boolean; s integer; r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    if n < g.seq then return public.rb_golf_state(gid); end if;           -- already counted (sent twice)
    if g.state <> 'live' or g.turn <> me or n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    side := case when me = g.a then 'a' else 'b' end;
    select * into r from public.rb_golf_roll(g.holes[g.hole], case when side = 'a' then g.pa else g.pb end,
                                             x0, y0, ang, pow);
    s := (case when side = 'a' then g.a_strokes else g.b_strokes end)[g.hole] + 1;
    done := r.holed or s >= 6;
    if side = 'a' then
        update public.rb_golf set a_strokes[hole] = s, a_in = done, a_miss = 0,
               pa = jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)), seq = seq + 1 where id = g.id;
    else
        update public.rb_golf set b_strokes[hole] = s, b_in = done, b_miss = 0,
               pb = jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)), seq = seq + 1 where id = g.id;
    end if;
    update public.rb_golf set shots = (select coalesce(jsonb_agg(v), '[]'::jsonb) from (
               select v from jsonb_array_elements(shots) v order by (v ->> 'n')::int desc limit 11) t)
               || jsonb_build_array(jsonb_build_object('n', g.seq, 'by', side, 'hole', g.hole,
                    'x0', r.sx, 'y0', r.sy, 'ang', ang, 'pow', pow,
                    'x', round(r.ex::numeric, 4), 'y', round(r.ey::numeric, 4), 'in', r.holed))
     where id = g.id;
    perform public.rb_golf_next(g.id);
    return public.rb_golf_state(gid);
end $$;

-- Matches of 2 to 4 players: the same.
create or replace function public.rb_party_shot(pid uuid, n integer, x0 double precision, y0 double precision,
                                                ang double precision, pow double precision, x double precision,
                                                y double precision, holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf_parties%rowtype; s public.rb_golf_party_seats%rowtype; k integer;
        nxt integer; r record; fin boolean;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_party_tick(pid);
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found or g.state <> 'live' then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_golf_party_seats where party = pid and owner = me for update;
    if not found or s.gone then raise exception 'rb_duel_gone'; end if;
    if n < s.seq or s.holed then return public.rb_party_json(pid, me); end if;
    if g.turn is distinct from s.seat then raise exception 'rb_not_your_turn'; end if;
    if n <> s.seq then raise exception 'rb_not_your_turn'; end if;
    if now() - s.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    select * into r from public.rb_golf_roll(g.holes[g.hole], s.pos, x0, y0, ang, pow);
    k := s.strokes[g.hole] + 1;
    fin := r.holed or k >= 6;
    update public.rb_golf_party_seats
       set strokes[g.hole] = k, seq = s.seq + 1, last_at = now(), holed = fin,
           pos = case when fin then null else jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)) end,
           shot = jsonb_build_object('n', s.seq, 'hole', g.hole, 'x0', r.sx, 'y0', r.sy, 'ang', ang, 'pow', pow,
                                     'x', round(r.ex::numeric, 4), 'y', round(r.ey::numeric, 4)),
           aim = null
     where party = pid and seat = s.seat;
    nxt := public.rb_party_next(pid, s.seat);
    update public.rb_golf_parties set turn = coalesce(nxt, turn), turn_at = now() + interval '3 seconds' where id = pid;
    perform public.rb_party_tick(pid);
    return public.rb_party_json(pid, me);
end $$;

-- Solo: the 8.0 app sends the shot itself (where from, angle, power); the server rolls it.
create or replace function public.rb_golf_solo_shot(gid uuid, n integer, x0 double precision, y0 double precision,
                                                    ang double precision, pow double precision, x double precision,
                                                    y double precision, holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf_solo%rowtype; s integer; base integer := 0; pay integer := 0; i integer;
        r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    select * into g from public.rb_golf_solo where id = gid and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if n < g.seq or g.state <> 'live' then return public.rb_golf_solo_json(g); end if;
    if n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if now() - g.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    select * into r from public.rb_golf_roll(g.holes[g.hole], g.pos, x0, y0, ang, pow);
    s := g.strokes[g.hole] + 1;
    g.strokes[g.hole] := s;
    g.seq := g.seq + 1;
    g.last_at := now();
    if r.holed or s >= 6 then
        if g.hole >= array_length(g.holes, 1) then
            g.state := 'done';
            g.done_at := now();
            g.pos := null;
            if now() - g.at >= interval '15 seconds' then
                for i in 1..array_length(g.strokes, 1) loop
                    base := base + public.rb_golf_solo_pay(g.strokes[i]);
                end loop;
            end if;
            pay := public.rb_game_pay(me, 'golf_solo', base);
            if pay > 0 then perform public.rb_pay(me, pay, 0, 'minigame', 'golf_solo'); end if;
            g.paid := pay;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (me, 'golf_solo', 0, jsonb_build_object('strokes', g.strokes, 'solo', g.id), false, pay);
        else
            g.hole := g.hole + 1;
            g.pos := null;
        end if;
    else
        g.pos := jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4));
    end if;
    update public.rb_golf_solo set strokes = g.strokes, seq = g.seq, last_at = g.last_at, state = g.state, hole = g.hole,
           pos = g.pos, paid = g.paid, done_at = g.done_at where id = g.id;
    return public.rb_golf_solo_json(g);
end $$;
revoke all on function public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                double precision, double precision, double precision, boolean) from public, anon;
grant execute on function public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                   double precision, double precision, double precision, boolean) to authenticated;

-- The old solo call (where the ball stopped and whether it went in, from the app) cannot be checked: it asks for
-- the update, which every app since 4.x shows as "Update Rubenium to keep playing online".
create or replace function public.rb_golf_solo_shot(gid uuid, n integer, x double precision, y double precision,
                                                    holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    raise exception 'rb_update_needed';
end $$;

-- ===================================================================================== request ids (resent calls)
-- rb_remember keeps the first 64 characters of a request id: look it up the same way, so a resend of a long id
-- gets the first answer instead of playing again.
create or replace function public.rb_done(who uuid, r text)
returns jsonb language sql security definer set search_path = '' as $$
    select result from public.rb_requests where owner = who and req = left(r, 64) $$;

-- ===================================================================================== password help
-- Before: 300 asks a day for everyone together, so anyone could use them up. Now: 3 a day per PC and per name, and
-- the shared limit only counts asks for names that do not exist (so they cannot crowd out real players).
create or replace function public.rb_reset_ask(name text, pc text, msg text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare rid uuid; u uuid; nm text := left(btrim(coalesce(name, '')), 20);
begin
    if coalesce(pc, '') !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;
    select id into u from public.profiles where lower(username) = lower(nm);
    if (select count(*) from public.rb_resets r where r.device = pc and r.at > now() - interval '1 day') >= 3
       or (select count(*) from public.rb_resets r where lower(r.name) = lower(nm) and r.at > now() - interval '1 day') >= 3
       or (u is null and (select count(*) from public.rb_resets r where r.uid is null and r.at > now() - interval '1 day') >= 300) then
        raise exception 'rb_slow_down';
    end if;
    insert into public.rb_resets (name, uid, device, msg) values (nm, u, pc, left(coalesce(msg, ''), 400)) returning id into rid;
    return rid;
end $$;

-- ===================================================================================== admin: a second step
-- An admin can set a second code (at least 6 characters, kept as a bcrypt hash). Once it is set, every admin
-- action needs it to have been typed in the last 30 minutes, in this login. 5 wrong codes lock it for 15 minutes.
-- admin_step_all = 1 (rb_config) also refuses admins who have not set one yet: turn it on once 8.0 is out.
create table if not exists public.rb_admin_step (
    owner uuid primary key references public.profiles(id) on delete cascade,
    code_hash text not null,
    fails integer not null default 0,
    locked_until timestamptz,
    ok_until timestamptz,
    ok_session text,
    set_at timestamptz not null default now());
alter table public.rb_admin_step enable row level security;
revoke all on public.rb_admin_step from public, anon, authenticated;
insert into public.rb_config (key, value) values ('admin_step_all', 0) on conflict (key) do nothing;

create or replace function public.rb_admin_step_session() returns text
language sql stable security definer set search_path = '' as $$
    select coalesce(auth.jwt() ->> 'session_id', '') $$;
revoke all on function public.rb_admin_step_session() from public, anon, authenticated;

create or replace function public.rb_need_admin()
returns uuid language plpgsql stable security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid();
    if found then
        if st.ok_until is null or st.ok_until < now()
           or coalesce(st.ok_session, '') <> public.rb_admin_step_session() then
            raise exception 'rb_admin_step';
        end if;
    elsif coalesce(public.rb_cfg('admin_step_all'), 0) > 0 then
        raise exception 'rb_admin_step';
    end if;
    return auth.uid();
end $$;

create or replace function public.rb_admin_step_status() returns json
language plpgsql stable security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid();
    return json_build_object('set', found, 'required', found or coalesce(public.rb_cfg('admin_step_all'), 0) > 0,
        'ok', found and st.ok_until > now() and coalesce(st.ok_session, '') = public.rb_admin_step_session(),
        'ok_until', st.ok_until, 'locked_until', case when st.locked_until > now() then st.locked_until end);
end $$;

create or replace function public.rb_admin_step_check(code text) returns json
language plpgsql security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid() for update;
    if not found then raise exception 'rb_admin_step_unset'; end if;
    if st.locked_until > now() then raise exception 'rb_slow_down'; end if;
    if extensions.crypt(coalesce(code, ''), st.code_hash) <> st.code_hash then
        update public.rb_admin_step
           set fails = case when st.fails + 1 >= 5 then 0 else st.fails + 1 end,
               locked_until = case when st.fails + 1 >= 5 then now() + interval '15 minutes' else locked_until end
         where owner = st.owner;
        return json_build_object('ok', false, 'left', greatest(0, 4 - st.fails));
    end if;
    update public.rb_admin_step set fails = 0, locked_until = null, ok_until = now() + interval '30 minutes',
           ok_session = public.rb_admin_step_session() where owner = st.owner;
    return json_build_object('ok', true, 'ok_until', now() + interval '30 minutes');
end $$;

create or replace function public.rb_admin_step_set(old_code text, new_code text) returns json
language plpgsql security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    if length(coalesce(new_code, '')) < 6 or length(new_code) > 72 then raise exception 'rb_bad_choice'; end if;
    select * into st from public.rb_admin_step where owner = auth.uid() for update;
    if found then
        if st.locked_until > now() then raise exception 'rb_slow_down'; end if;
        if extensions.crypt(coalesce(old_code, ''), st.code_hash) <> st.code_hash then
            update public.rb_admin_step
               set fails = case when st.fails + 1 >= 5 then 0 else st.fails + 1 end,
                   locked_until = case when st.fails + 1 >= 5 then now() + interval '15 minutes' else locked_until end
             where owner = st.owner;
            return json_build_object('ok', false, 'left', greatest(0, 4 - st.fails));
        end if;
    end if;
    insert into public.rb_admin_step (owner, code_hash, ok_until, ok_session)
        values (auth.uid(), extensions.crypt(new_code, extensions.gen_salt('bf', 10)), now() + interval '30 minutes',
                public.rb_admin_step_session())
    on conflict (owner) do update set code_hash = excluded.code_hash, fails = 0, locked_until = null,
        ok_until = excluded.ok_until, ok_session = excluded.ok_session, set_at = now();
    return json_build_object('ok', true);
end $$;
revoke all on function public.rb_admin_step_status(), public.rb_admin_step_check(text),
                       public.rb_admin_step_set(text, text) from public, anon;
grant execute on function public.rb_admin_step_status(), public.rb_admin_step_check(text),
                          public.rb_admin_step_set(text, text) to authenticated;

-- ===================================================================================== who may call and write what
-- What the API roles may do before this migration is kept (rb_bak74_grants), so 074_down.sql can put it back.
create table if not exists public.rb_bak74_grants (kind text, obj text, role text, priv text);
alter table public.rb_bak74_grants enable row level security;
revoke all on public.rb_bak74_grants from public, anon, authenticated;
do $g$
declare f record; t record;
begin
    if not exists (select 1 from public.rb_bak74_grants) then          -- the first run only
        insert into public.rb_bak74_grants
        select 'function', p.oid::regprocedure::text, r.role, 'EXECUTE'
          from pg_proc p cross join (values ('public'), ('anon'), ('authenticated'), ('service_role')) r(role)
         where p.pronamespace = 'public'::regnamespace and p.prokind = 'f'
           and case when r.role = 'public' then exists (select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                                                         where a.grantee = 0 and a.privilege_type = 'EXECUTE')
                    else has_function_privilege(r.role, p.oid, 'EXECUTE') end;
        insert into public.rb_bak74_grants
        select 'table', format('%I.%I', table_schema, table_name), grantee, privilege_type
          from information_schema.role_table_grants
         where table_schema = 'public' and grantee in ('anon', 'authenticated');
    end if;
    -- Functions: players (authenticated) and the server (service_role) keep exactly what they could call;
    -- without a login only the sign-in page's calls are left.
    for f in select p.oid::regprocedure::text sig, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                    has_function_privilege('service_role', p.oid, 'EXECUTE') s
               from pg_proc p where p.pronamespace = 'public'::regnamespace and p.prokind = 'f' loop
        if f.a then execute format('grant execute on function %s to authenticated', f.sig); end if;
        if f.s then execute format('grant execute on function %s to service_role', f.sig); end if;
        execute format('revoke execute on function %s from public, anon', f.sig);
    end loop;
    for f in select p.oid::regprocedure::text sig from pg_proc p
              where p.pronamespace = 'public'::regnamespace and p.prokind = 'f'
                and p.proname in ('rb_username_free', 'rb_device_free', 'rb_login_for', 'rb_reset_ask', 'rb_reset_status',
                                  'rb_swaps_list') loop
        execute format('grant execute on function %s to anon', f.sig);
    end loop;
    -- Tables: reading stays as it was (row level security decides what each player sees); writing only ever
    -- happens through the rb_* functions, so the API roles lose insert, update, delete and the rest.
    for t in select format('%I.%I', schemaname, tablename) tn from pg_tables where schemaname = 'public' loop
        execute format('revoke insert, update, delete, truncate, references, trigger on %s from anon, authenticated', t.tn);
    end loop;
end $g$;
-- New functions and tables made later get the same rules.
alter default privileges in schema public revoke execute on functions from public;
alter default privileges in schema public revoke execute on functions from anon;
alter default privileges in schema public grant execute on functions to authenticated, service_role;
alter default privileges in schema public revoke insert, update, delete, truncate, references, trigger on tables from anon, authenticated;

-- Two backup tables from 6.3 had no row level security.
do $b$
begin
    if to_regclass('public.rb_bak63_cases') is not null then
        execute 'alter table public.rb_bak63_cases enable row level security';
        execute 'revoke all on public.rb_bak63_cases from anon, authenticated';
    end if;
    if to_regclass('public.rb_bak63_case_stock') is not null then
        execute 'alter table public.rb_bak63_case_stock enable row level security';
        execute 'revoke all on public.rb_bak63_case_stock from anon, authenticated';
    end if;
end $b$;

-- Swaps: the app saves each swap under its id and file name, so both must be plain names (no folders).
do $s$
begin
    if not exists (select 1 from pg_constraint where conname = 'rb_swaps_safe_names') then
        alter table public.rb_swaps add constraint rb_swaps_safe_names
            check (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$' and file ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$'
                   and file !~ '\.\.' and lower(file) ~ '\.(upk|bnk|tfc|pck|wem)$');
    end if;
end $s$;

-- The new tables are read only through functions.
revoke all on public.rb_golf_hole_defs, public.rb_admin_step, public.rb_bak74_grants from anon, authenticated;

commit;
