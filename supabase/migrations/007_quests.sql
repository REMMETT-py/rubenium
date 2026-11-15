-- Rubenium 007: daily and weekly quests. Progress is counted by the server from what was really played.
-- Safe to run more than once. Needs 004 first. Run it in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.rb_quest_claims (
    owner uuid not null references public.profiles (id) on delete cascade,
    quest text not null, period date not null, at timestamptz not null default now(),
    primary key (owner, quest, period));
alter table public.rb_quest_claims enable row level security;
revoke all on public.rb_quest_claims from anon, authenticated;

-- (id, daily?, goal, reward, how far the account is)
create or replace function public.rb_quest_rows(who uuid)
returns table (quest text, daily boolean, goal integer, reward integer, progress integer, period date)
language sql stable security definer set search_path = '' as $$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         q (quest, daily, goal, reward, progress) as (values
            ('d_rounds', true, 10, 60, (select count(*) from d where game in ('slots','plinko','dice','mines','rocket','blackjack'))::int),
            ('d_case',   true,  1, 50, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_spin',   true,  1, 40, (select count(*) from d where game = 'spin')::int),
            ('w_rounds', false, 100, 300, (select count(*) from r where game in ('slots','plinko','dice','mines','rocket','blackjack'))::int),
            ('w_cases',  false,  10, 300, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    false, 5000, 400, (select coalesce(sum(paid), 0) from r where game in ('slots','plinko','dice','mines','rocket','blackjack'))::int))
    select q.quest, q.daily, q.goal, q.reward, least(q.progress, q.goal),
           (case when q.daily then date_trunc('day', now()) else date_trunc('week', now()) end)::date
      from q $$;

create or replace function public.rb_quests() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object('quest', q.quest, 'daily', q.daily, 'goal', q.goal, 'reward', q.reward,
               'progress', q.progress,
               'claimed', exists (select 1 from public.rb_quest_claims c
                                   where c.owner = auth.uid() and c.quest = q.quest and c.period = q.period))), '[]'::json)
      from public.rb_quest_rows(auth.uid()) q $$;

create or replace function public.rb_quest_claim(which text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; q record;
begin
    p := public.rb_lock_me();
    select * into q from public.rb_quest_rows(p.id) x where x.quest = which;
    if not found then raise exception 'rb_no_quest'; end if;
    if q.progress < q.goal then raise exception 'rb_not_done'; end if;
    begin
        insert into public.rb_quest_claims (owner, quest, period) values (p.id, q.quest, q.period);
    exception when unique_violation then
        raise exception 'rb_already_claimed';
    end;
    perform public.rb_pay(p.id, q.reward, 0, 'quest', q.quest);
    return jsonb_build_object('paid', q.reward, 'coins', p.coins + q.reward);
end $$;

revoke all on function public.rb_quest_rows(uuid) from public, anon, authenticated;
revoke all on function public.rb_quests() from public, anon;
revoke all on function public.rb_quest_claim(text) from public, anon;
grant execute on function public.rb_quests() to authenticated;
grant execute on function public.rb_quest_claim(text) to authenticated;
