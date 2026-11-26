-- 9.2 (089): the pre-9.0 backups are gone, the 074 grants backup and the season backups stay, no probe account.
begin;
do $$ begin
    assert not exists (select 1 from pg_tables where schemaname = 'public'
                        and tablename ~ '^rb_bak(021|26|50|51|515|53|60|62|63)_'), 'old backups dropped';
    assert to_regclass('public.rb_bak74_grants') is not null, '074 undo data kept';
    assert not exists (select 1 from public.profiles where username = 'RbProbe7'), 'probe account gone';
end $$;
rollback;
