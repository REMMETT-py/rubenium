-- 6.7: catalog rows of ten new banners, ten new themes and their colourways.
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select k.kind || ':' || k.base, k.kind, k.base, '', k.rarity, a.price, a.value, true, 0, a.worth, 1.0, false, a.base_worth
  from (values
    ('banner','ripples','standard'),('banner','pinwheel','standard'),('banner','ticker','standard'),
    ('banner','lightleaks','rare'),('banner','nixie','rare'),('banner','tvstatic','rare'),
    ('banner','vinyl','special'),('banner','pendulum','special'),('banner','hologram','epic'),('banner','mandala','epic'),
    ('theme','monsoon','rare'),('theme','sahara','rare'),('theme','bamboo','rare'),
    ('theme','neonrain','special'),('theme','lanterns','special'),('theme','quartz','special'),('theme','lavalamp','special'),
    ('theme','wormhole','epic'),('theme','polarlights','epic'),('theme','chrome','epic')
  ) as k(kind, base, rarity)
  join lateral (select round(avg(c.price))::int price, round(avg(c.value))::int value, round(avg(c.worth))::int worth, round(avg(c.base_worth))::int base_worth
                  from public.rb_catalog c where c.kind = k.kind and c.rarity = k.rarity and c.price is not null and not c.limited) a on true
on conflict (id) do nothing;

with src(s) as (values
 ('banner|ripples=lime,magenta,emerald,indigo,crimson,silver;pinwheel=azure,lime,emerald,orange,violet,silver;ticker=orange,indigo,lime,teal,azure,silver;lightleaks=indigo,emerald,lime,rose,azure,silver;nixie=violet,emerald,lime,rose,azure,silver;tvstatic=lime,emerald,cyan,indigo,magenta,silver;vinyl=cyan,lime,teal,gold,violet,silver;pendulum=lime,rose,violet,emerald,orange,silver;hologram=lime,magenta,indigo,crimson,emerald,silver;mandala=emerald,crimson,gold,lime,teal,silver'),
 ('theme|monsoon=lime,magenta,indigo,crimson,emerald,silver;sahara=violet,emerald,lime,rose,azure,silver;bamboo=orange,indigo,rose,azure,lime,silver;neonrain=emerald,orange,magenta,lime,teal,silver;lanterns=indigo,emerald,gold,lime,teal,silver;quartz=emerald,crimson,cyan,magenta,gold,silver;lavalamp=cyan,lime,crimson,emerald,indigo,silver;wormhole=lime,rose,violet,emerald,orange,silver;polarlights=lime,rose,violet,emerald,orange,silver;chrome=emerald,crimson,gold,lime,teal,silver')),
kinds as (select split_part(s, '|', 1) kind, split_part(s, '|', 2) rest from src),
designs as (select kind, split_part(d, '=', 1) base, split_part(d, '=', 2) cols from kinds, unnest(string_to_array(rest, ';')) d),
v as (select kind, base, base || '-' || col id from designs, unnest(string_to_array(cols, ',')) col)
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select v.kind || ':' || v.id, v.kind, v.id, '', c.rarity, c.price, c.value, c.tradeable, c.cls, c.worth, c.weight, false, c.base_worth
  from v join public.rb_catalog c on c.id = v.kind || ':' || v.base
on conflict (id) do nothing;
