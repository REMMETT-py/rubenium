-- 5.11: roulette with several picks in one spin (the bet goes on each pick), Gold pays x25. Cup game.

create or replace function public.rb_roulette_multi(bet integer, picks text[], req text) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; slot integer; colour text; pay bigint := 0; x text; num integer;
        n integer; wins jsonb := '[]'::jsonb; m integer; total integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('roulette');
    n := coalesce(array_length(picks, 1), 0);
    if n < 1 or n > 12 or (select count(distinct v) from unnest(picks) v) <> n then raise exception 'rb_bad_choice'; end if;
    foreach x in array picks loop
        if x ~ '^n:[0-9]{1,2}$' then
            if substr(x, 3)::int not between 1 and 24 then raise exception 'rb_bad_choice'; end if;
        elsif x not in ('red', 'black', 'gold', 'low', 'high') then
            raise exception 'rb_bad_choice';
        end if;
    end loop;
    if bet is null or bet < public.rb_cfg('bet_min') then raise exception 'rb_bad_bet'; end if;
    total := bet * n;
    perform public.rb_bet(p, total, 'roulette');
    slot := floor(public.rb_rand() * 25)::int;                     -- 0 = gold, odd = red, even = black
    colour := case when slot = 0 then 'gold' when slot % 2 = 1 then 'red' else 'black' end;
    foreach x in array picks loop
        num := case when x like 'n:%' then substr(x, 3)::int end;
        m := case when num is not null and slot = num then 24
                  when x = 'gold' and slot = 0 then 25
                  when x = 'low' and slot between 1 and 12 then 2
                  when x = 'high' and slot between 13 and 24 then 2
                  when x in ('red', 'black') and colour = x then 2
                  else 0 end;
        if m > 0 then
            pay := pay + bet::bigint * m;
            wins := wins || to_jsonb(x);
        end if;
    end loop;
    if pay > 0 then pay := public.rb_win(p.id, pay, 'roulette'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'roulette', total, jsonb_build_object('slot', slot, 'picks', to_jsonb(picks)), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('slot', slot, 'colour', colour, 'win', pay > 0, 'wins', wins,
                                                            'paid', pay, 'coins', p.coins - total + pay));
end $$;
grant execute on function public.rb_roulette_multi(integer, text[], text) to authenticated;
