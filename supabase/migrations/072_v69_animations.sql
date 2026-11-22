-- 6.9: four Mythic animations (Supernova, Shatter, Rift, Phoenix), each in five finishes (original, prismatic, gold, black titan,
-- white titan). The originals are sold in the shop (shop price with the 33% tax lands between 250 000 and 1 000 000); the finishes
-- only come from the Profile Case (a 0.4% Mythic chance per open). They are worn in the 'anim' slot.
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
select 'anim:' || d.id || f.suffix, 'anim', d.id || f.suffix, '', 'exotic',
       (d.price * f.pm)::int, ((d.price * f.pm) / 20)::int, true, 0, (d.price * f.wm)::int, f.w, false, d.price
  from (values ('nova', 190000), ('shatter', 300000), ('rift', 500000), ('phoenix', 750000)) d(id, price)
 cross join (values ('', 1.0, 1.0, 1.0), ('-prismatic', 2.0, 2.5, 0.25), ('-gold', 3.0, 3.5, 0.10),
                    ('-blacktitan', 2.5, 3.0, 0.08), ('-whitetitan', 2.5, 3.0, 0.08)) f(suffix, pm, wm, w)
on conflict (id) do nothing;

update public.rb_cases set odds = '{3560,3800,2000,500,100,40}', mode = 'kinds:banner,frame,anim' where id = 'profile';

do $m$
declare s text;
begin
    s := pg_get_functiondef('public.rb_equip(text,text)'::regprocedure);
    if position('''anim''' in s) = 0 then
        s := replace(s, 'when ''tag'' then ''tag'' end;', 'when ''tag'' then ''tag'' when ''anim'' then ''anim'' end;');
        execute s;
    end if;
    s := pg_get_functiondef('public.rb_buy(text,text)'::regprocedure);
    if position('''anim''' in s) = 0 then
        s := replace(s, 'if c.kind = ''badge'' and (c.cls >= 4 or c.rarity = ''exotic'') then raise exception ''rb_not_for_sale''; end if;',
                        'if c.kind = ''badge'' and (c.cls >= 4 or c.rarity = ''exotic'') then raise exception ''rb_not_for_sale''; end if;
    if c.kind = ''anim'' and position(''-'' in c.base) > 0 then raise exception ''rb_not_for_sale''; end if;');
        execute s;
    end if;
    s := pg_get_functiondef('public.rb_case_drop(public.rb_cases)'::regprocedure);
    if position('not like ''kinds:%''' in s) = 0 then
        s := replace(s, 'if tier = 5 then tier := 0; end if;', 'if tier = 5 and c.mode not like ''kinds:%'' then tier := 0; end if;');
        execute s;
    end if;
end $m$;
