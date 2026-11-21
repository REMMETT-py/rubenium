-- 6.2: case odds. Applied live on 21/11/2026 (backup: rb_bak62_cases).
-- * Mythic chance: Top Tier 1 / 100 000, Royal 1 / 250 000, every other case that can give one 1 / 286 000 to 1 / 500 000.
-- * Finishes among badge drops (basic stays where the case had it; the rest is split):
--     Top Tier   painted 88.75 %, shiny 10 %, titanium 1 %, gold 0.25 %
--     Royal      painted 90.75 %, shiny  8 %, titanium 0.8 %, gold 0.45 %  (better gold than Top Tier)
--     the others the same shape, scaled down with the case's price (a share of the non-basic part):
--                shiny 0.5 % .. 10 %, titanium 0.05 % .. 1 %, gold 0.03 % .. 0.25 %
-- * Tier totals (Epic / Legendary mix) are kept; the freed or taken billionths go to the biggest tier so the grid still
--   fills exactly 1 000 000 000 with myth_ppb (no coin leftover). odds / variants are derived from the grid.
do $$
declare c record; g bigint[]; ng bigint[]; tt bigint[]; bas bigint[]; t int; k int; nb bigint; newm bigint; delta bigint; mx int;
        q double precision; rs double precision; rt double precision; rg double precision; sh bigint; ti bigint; go_ bigint;
        tot bigint; od int[]; va int[]; cs bigint[]; i int; big_ int; s int;
begin
    for c in select * from public.rb_cases where grid is not null and not limited
              and id in ('mythic', 'royal', 'shiny', 'cosmos', 'painter', 'vault', 'premium', 'medieval', 'arcade', 'ocean',
                         'spooky', 'treasure', 'nature', 'standard', 'starter') loop
        g := c.grid;
        newm := case c.id when 'mythic' then 10000 when 'royal' then 4000 when 'shiny' then 3500 when 'cosmos' then 3000
                          when 'vault' then 3000 when 'premium' then 2500 when 'medieval' then 2500 when 'painter' then 0
                          when 'starter' then 0 else 2000 end;
        delta := c.myth_ppb - newm;
        tt := array[0, 0, 0, 0]; bas := array[0, 0, 0, 0];
        for t in 1 .. 4 loop
            bas[t] := g[(t - 1) * 5 + 1];
            for k in 1 .. 5 loop tt[t] := tt[t] + g[(t - 1) * 5 + k]; end loop;
        end loop;
        mx := 1;
        for t in 2 .. 4 loop if tt[t] > tt[mx] then mx := t; end if; end loop;
        tt[mx] := tt[mx] + delta;
        q := least(1, greatest(0, ln(c.price / 1350.0) / ln(20000 / 1350.0)));
        rs := 0.005 + 0.095 * q * q; rt := 0.0005 + 0.0095 * q * q; rg := 0.0003 + 0.0022 * q * q;
        if c.id = 'royal' then rs := 0.08; rt := 0.008; rg := 0.0045; end if;
        ng := g;
        for t in 1 .. 4 loop
            nb := tt[t] - bas[t];
            sh := round(nb * rs); ti := round(nb * rt); go_ := round(nb * rg);
            if t <= 2 then sh := sh + ti; ti := 0; end if;           -- no Titanium among Common / Rare badges
            ng[(t - 1) * 5 + 1] := bas[t];
            ng[(t - 1) * 5 + 2] := nb - sh - ti - go_;
            ng[(t - 1) * 5 + 3] := sh;
            ng[(t - 1) * 5 + 4] := ti;
            ng[(t - 1) * 5 + 5] := go_;
        end loop;
        tot := 0; for i in 1 .. 20 loop tot := tot + ng[i]; end loop;
        if tot + newm <> 1000000000 then raise exception 'case % does not add up: % + %', c.id, tot, newm; end if;
        -- derived arrays for old app versions: odds per 10 000 (coins, tiers 1-4, mythic), variants per 100 000
        od := array[0, round(tt[1] / 1e5)::int, round(tt[2] / 1e5)::int, round(tt[3] / 1e5)::int, round(tt[4] / 1e5)::int, round(newm / 1e5)::int];
        big_ := 2; for i in 3 .. 5 loop if od[i] > od[big_] then big_ := i; end if; end loop;
        s := 0; for i in 1 .. 6 loop s := s + od[i]; end loop;
        od[big_] := od[big_] + 10000 - s;
        cs := array[0, 0, 0, 0, 0];
        for t in 1 .. 4 loop for k in 1 .. 5 loop cs[k] := cs[k] + ng[(t - 1) * 5 + k]; end loop; end loop;
        va := array[0, 0, 0, 0, 0];
        for k in 1 .. 5 loop va[k] := round(cs[k]::numeric * 100000 / tot)::int; end loop;
        big_ := 1; for i in 2 .. 5 loop if va[i] > va[big_] then big_ := i; end if; end loop;
        s := 0; for i in 1 .. 5 loop s := s + va[i]; end loop;
        va[big_] := va[big_] + 100000 - s;
        update public.rb_cases set grid = ng, myth_ppb = newm, odds = od, variants = va where id = c.id;
    end loop;
end $$;
