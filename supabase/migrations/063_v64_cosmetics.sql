-- 6.4: twelve more banners, frames and app colour themes (none seasonal) and a sixth Nature badge (Leaf).
-- Each new look copies the shop price, value and worth of its rarity; they join the shop and every style case that draws
-- from that kind (Banner Case, Frame Case, Banner & Frame Case, App Colour Case) automatically.
create temporary table _look64 (id text, kind text, base text, rarity text) on commit drop;
insert into _look64 values
  ('banner:meadow','banner','meadow','standard'), ('banner:paper','banner','paper','standard'), ('banner:clouds','banner','clouds','standard'),
  ('banner:bokeh','banner','bokeh','rare'), ('banner:pixels','banner','pixels','rare'), ('banner:ribbons','banner','ribbons','rare'),
  ('banner:glitch','banner','glitch','special'), ('banner:sunbeams','banner','sunbeams','special'), ('banner:stardesert','banner','stardesert','special'),
  ('banner:kaleido','banner','kaleido','epic'), ('banner:liquidgold','banner','liquidgold','epic'), ('banner:meteors','banner','meteors','epic'),
  ('frame:gold','frame','gold','standard'), ('frame:emerald','frame','emerald','standard'), ('frame:sapphire','frame','sapphire','standard'),
  ('frame:beads','frame','beads','rare'), ('frame:chain','frame','chain','rare'), ('frame:daisy','frame','daisy','rare'),
  ('frame:plasma','frame','plasma','special'), ('frame:sparks','frame','sparks','special'), ('frame:constellation','frame','constellation','special'),
  ('frame:spectrum','frame','spectrum','epic'), ('frame:void','frame','void','epic'), ('frame:wings','frame','wings','epic'),
  ('theme:cherry','theme','cherry','rare'), ('theme:mocha','theme','mocha','rare'), ('theme:mint','theme','mint','rare'), ('theme:cobalt','theme','cobalt','rare'),
  ('theme:lavender','theme','lavender','special'), ('theme:rust','theme','rust','special'), ('theme:emerald','theme','emerald','special'), ('theme:graphite','theme','graphite','special'),
  ('theme:goldrush','theme','goldrush','epic'), ('theme:pulse','theme','pulse','epic'), ('theme:abyss','theme','abyss','epic'), ('theme:rosegold','theme','rosegold','epic');

insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select n.id, n.kind, n.base, '', n.rarity, t.price, t.value, true, 0, t.worth, 1.0, false, t.value
  from _look64 n
  join (select kind, rarity, (round(avg(price) / 100) * 100)::integer price, round(avg(value))::integer value, round(avg(worth))::integer worth
          from public.rb_catalog where kind in ('banner', 'frame', 'theme') and limited = false and price is not null
         group by kind, rarity) t on t.kind = n.kind and t.rarity = n.rarity
on conflict (id) do nothing;

-- the sixth Nature badge: a Common design that copies the Heart's colours, finishes, worth and weight
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select 'badge:leaf:' || c.variant, c.kind, 'leaf', c.variant, c.rarity, c.price, c.value, c.tradeable, c.cls,
       c.worth, c.weight, true, c.base_worth
  from public.rb_catalog c where c.kind = 'badge' and c.base = 'heart'
on conflict (id) do nothing;

update public.rb_cases set mode = mode || ',leaf' where id = 'nature' and mode not like '%leaf%';
