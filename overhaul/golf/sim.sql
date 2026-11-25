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
