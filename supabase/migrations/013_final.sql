-- Rubenium 013 (2.7): better AFK money, new winter looks. Run it once in Supabase, after 012:
-- SQL Editor > New query > paste everything > Run. Safe to run again.

-- AFK money: 25 coins every 10 minutes (150 an hour), up to 1 800 a day. Keys stay 1 an hour.
update public.rb_config set value = 25 where key = 'coin_amount';
update public.rb_config set value = 1800 where key = 'coin_day_cap';

-- new profile looks (rarer = more detail and animation, and more expensive)
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('banner:snow', 'banner', 'snow', '', 'rare', 1200, 1200, true, 0),
    ('banner:ember', 'banner', 'ember', '', 'special', 3500, 3500, true, 0),
    ('banner:nebula', 'banner', 'nebula', '', 'epic', 9000, 9000, true, 0),
    ('frame:frost', 'frame', 'frost', '', 'rare', 1000, 1000, true, 0),
    ('frame:star', 'frame', 'star', '', 'special', 3000, 3000, true, 0),
    ('frame:halo', 'frame', 'halo', '', 'epic', 8000, 8000, true, 0)
on conflict (id) do update set kind = excluded.kind, base = excluded.base, rarity = excluded.rarity,
    price = excluded.price, value = excluded.value, tradeable = excluded.tradeable;
