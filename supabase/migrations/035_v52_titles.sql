-- ================================================================ Rubenium 5.2: leaderboard titles
-- Every player has every game title ("RICH", "VALUE", "BLOCKBLAST"...). Shown grey, or, while the player is in the top 3
-- of that leaderboard (everyone, not only friends), as "#1 RICH" in gold, "#2" silver, "#3" bronze. Ranks are worked out
-- from the leaderboards every time they are asked, so they can never be out of date or shared: ties go to the name
-- first in the alphabet. Up to 3 titles can be worn at once (the OG tag counts as one). Safe to run again.
begin;

create or replace function public.rb_title_kinds() returns text[]
language sql immutable set search_path to '' as $$
    select array['coins', 'worth', 'level', 'hours', 'badges', 'streak', 'blocks', 'wave', 'tap', 'park', 'memory'] $$;

-- the value of one leaderboard for every player (the same numbers as the Leaderboards screen)
create or replace function public.rb_title_values(kind text)
 returns table(id uuid, username text, val bigint)
 language sql stable security definer set search_path to '' as $$
    select w.id, w.username, (case kind
        when 'coins' then w.coins
        when 'level' then w.xp
        when 'hours' then w.minutes / 60
        when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
        when 'worth' then (select coalesce(sum(public.rb_worth(it.item)), 0) from public.rb_items it where it.owner = w.id)
        when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
        when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini')
        when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park')
        when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory')
        when 'blocks' then (select coalesce(max(g.score), 0) from public.rb_mg g where g.owner = w.id and g.game = 'blocks'
                              and not g.open and not g.void)
        when 'wave' then public.rb_wave_best(w.id)
        else 0 end)::bigint
      from public.profiles w where not w.banned and not w.bot $$;

-- who holds #1, #2 and #3 of every leaderboard right now: {username: {kind: rank}}
create or replace function public.rb_ranks() returns json
language sql stable security definer set search_path to '' as $$
    select coalesce(json_object_agg(username, r), '{}'::json) from (
        select username, json_object_agg(kind, rk) r from (
            select k.kind, t.username, row_number() over (partition by k.kind order by t.val desc, lower(t.username)) rk
              from unnest(public.rb_title_kinds()) k(kind), lateral public.rb_title_values(k.kind) t
             where t.val > 0) x
         where rk <= 3 group by username) y $$;
revoke all on function public.rb_ranks() from public, anon;
grant execute on function public.rb_ranks() to authenticated;
revoke all on function public.rb_title_values(text) from public, anon, authenticated;

-- wearing up to 3 titles: 'tag:og' (if yours) and 'rank:<kind>'
create or replace function public.rb_titles_set(ids text[]) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; x text;
begin
    p := public.rb_lock_me();
    ids := coalesce(ids, '{}');
    if array_length(ids, 1) > 3 or (select count(distinct v) from unnest(ids) v) <> coalesce(array_length(ids, 1), 0) then
        raise exception 'rb_bad_choice';
    end if;
    foreach x in array ids loop
        if x like 'rank:%' then
            if substr(x, 6) <> all (public.rb_title_kinds()) then raise exception 'rb_bad_choice'; end if;
        elsif x like 'tag:%' then
            if not exists (select 1 from public.rb_items i where i.owner = p.id and i.item = x) then raise exception 'rb_not_yours'; end if;
        else
            raise exception 'rb_bad_choice';
        end if;
    end loop;
    p.equip := coalesce(p.equip, '{}'::jsonb) - 'titles';
    if array_length(ids, 1) > 0 then p.equip := p.equip || jsonb_build_object('titles', to_jsonb(ids)); end if;
    -- the old single tag follows the first tag:* worn (older parts of the app still read it)
    p.equip := p.equip - 'tag';
    x := (select v from unnest(ids) v where v like 'tag:%' limit 1);
    if x is not null then p.equip := p.equip || jsonb_build_object('tag', x); end if;
    update public.profiles set equip = p.equip where id = p.id;
    return p.equip;
end $$;
revoke all on function public.rb_titles_set(text[]) from public, anon;
grant execute on function public.rb_titles_set(text[]) to authenticated;

-- everyone's looks include the titles they wear
create or replace function public.rb_looks() returns json
language plpgsql stable security definer set search_path to '' as $function$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(p.username, jsonb_strip_nulls(jsonb_build_object(
                         'tag', p.equip ->> 'tag', 'frame', p.equip ->> 'frame', 'banner', p.equip ->> 'banner',
                         'theme', p.equip ->> 'theme', 'titles', p.equip -> 'titles',
                         'gold', nullif(least(coalesce((p.equip ->> 'banner_gold')::int, 3), public.rb_gold_level(p.equip ->> 'banner',
                                    (select w.minutes from public.rb_wear w where w.owner = p.id and w.item = p.equip ->> 'banner'))), 0))))
                       from public.profiles p
                      where not p.banned and p.equip ?| array['tag', 'frame', 'banner', 'theme', 'titles']), '{}'::json);
end $function$;

-- the equip cleaner keeps the titles (it only drops an OG-style tag you no longer own)
create or replace function public.rb_fix_equip(who uuid) returns void
language plpgsql security definer set search_path to '' as $function$
declare p public.profiles%rowtype; e jsonb; k text; v text; t jsonb;
begin
    select * into p from public.profiles where id = who;
    e := coalesce(p.equip, '{}'::jsonb);
    for k, v in select key, value from jsonb_each_text(e) loop
        if k = 'titles' then continue; end if;
        if not public.rb_can_wear(p, v) then e := e - k; end if;
    end loop;
    if jsonb_typeof(e -> 'titles') = 'array' then
        select coalesce(jsonb_agg(x), '[]'::jsonb) into t from jsonb_array_elements_text(e -> 'titles') x
         where x like 'rank:%' or exists (select 1 from public.rb_items i where i.owner = who and i.item = x);
        e := case when jsonb_array_length(t) = 0 then e - 'titles' else e || jsonb_build_object('titles', t) end;
    end if;
    update public.profiles set equip = e where id = who;
end $function$;

commit;
