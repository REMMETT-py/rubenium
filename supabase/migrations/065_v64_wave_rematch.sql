-- 6.4: Wave Rush duel rematch. After a duel both players can press "Rematch"; when both have, a new live duel starts
-- with the same bet and a new course (same sides), no lobby in between. A ready flag expires after 2 minutes.
create table if not exists public.rb_wave_rematch (
    old uuid primary key, a_ready boolean not null default false, b_ready boolean not null default false,
    new_id uuid, at timestamptz not null default now());
alter table public.rb_wave_rematch enable row level security;

create or replace function public.rb_wave_rematch(did uuid, go boolean default false) returns jsonb
language plpgsql security definer set search_path = '' as $f$
declare me uuid := auth.uid(); w public.rb_wave_duels%rowtype; r public.rb_wave_rematch%rowtype; pa public.profiles%rowtype;
        pb public.profiles%rowtype; n public.rb_wave_duels%rowtype; ra uuid; rb uuid; mine boolean; theirs boolean; other text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into w from public.rb_wave_duels where id = did and (a = me or b = me);
    if not found or w.state <> 'done' or w.b is null then raise exception 'rb_duel_gone'; end if;
    insert into public.rb_wave_rematch (old) values (did) on conflict do nothing;
    select * into r from public.rb_wave_rematch where old = did for update;
    if r.new_id is null and r.at < now() - interval '2 minutes' and (r.a_ready or r.b_ready) then
        update public.rb_wave_rematch set a_ready = false, b_ready = false, at = now() where old = did;
        r.a_ready := false; r.b_ready := false;
    end if;
    other := (select username from public.profiles where id = case when w.a = me then w.b else w.a end);
    if go and r.new_id is null then
        perform public.rb_rate(me, 'duel', 10);
        perform public.rb_need_feature('wave');
        if w.a = me then r.a_ready := true; else r.b_ready := true; end if;
        update public.rb_wave_rematch set a_ready = r.a_ready, b_ready = r.b_ready, at = now() where old = did;
        if r.a_ready and r.b_ready then
            -- both want it: lock both players (lowest id first), check coins and that nobody is in another duel
            if w.a < w.b then
                select * into pa from public.profiles where id = w.a for update;
                select * into pb from public.profiles where id = w.b for update;
            else
                select * into pb from public.profiles where id = w.b for update;
                select * into pa from public.profiles where id = w.a for update;
            end if;
            if public.rb_wave_busy(w.a) or public.rb_wave_busy(w.b) then
                update public.rb_wave_rematch set a_ready = false, b_ready = false where old = did;
                raise exception 'rb_one_lobby';
            end if;
            if w.bet > 0 and (pa.coins < w.bet or pb.coins < w.bet) then
                update public.rb_wave_rematch set a_ready = false, b_ready = false where old = did;
                raise exception 'rb_not_enough';
            end if;
            perform public.rb_pay(w.a, -w.bet, 0, 'wave_bet', null);
            perform public.rb_pay(w.b, -w.bet, 0, 'wave_bet', null);
            insert into public.rb_wave_duels (a, bet, seed) values (w.a, w.bet, floor(public.rb_rand() * 2147483647)::bigint)
                returning * into n;
            insert into public.rb_wave_runs (owner, seed, duel, started_at) values (n.a, n.seed, n.id, now() + interval '4 seconds')
                returning id into ra;
            insert into public.rb_wave_runs (owner, seed, duel, started_at) values (w.b, n.seed, n.id, now() + interval '4 seconds')
                returning id into rb;
            update public.rb_wave_duels set b = w.b, state = 'live', live_at = now(), a_run = ra, b_run = rb where id = n.id;
            update public.rb_wave_rematch set new_id = n.id where old = did;
            r.new_id := n.id;
            perform public.rb_notice(case when w.a = me then w.b else w.a end, 'wave_yes',
                                     jsonb_build_object('from', (select username from public.profiles where id = me), 'id', n.id));
        end if;
    end if;
    mine := case when w.a = me then r.a_ready else r.b_ready end;
    theirs := case when w.a = me then r.b_ready else r.a_ready end;
    return jsonb_build_object('mine', coalesce(mine, false), 'theirs', coalesce(theirs, false), 'other', other,
                              'bet', w.bet, 'new_id', r.new_id);
end $f$;
revoke all on function public.rb_wave_rematch(uuid, boolean) from public, anon;
grant execute on function public.rb_wave_rematch(uuid, boolean) to authenticated;
