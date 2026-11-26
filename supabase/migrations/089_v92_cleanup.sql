-- Rubenium 9.2: clean-up before the source repo goes private. Safe to run twice. CANNOT BE UNDONE (no down file):
-- the dropped backups and the test account are gone for good, which is the point (privacy policy: season backups are
-- kept 12 months at most).
--
-- 1. Drops every server backup made before 9.0 (rb_bak021_* to rb_bak63_*, from v0.21 to 6.3). Kept: rb_bak74_grants
--    (the undo of 074, no player data) and the season backups rb_bak90_*, rb_bak91_*, rb_bak92_*.
-- 2. Deletes the CI probe account RbProbe7: its password was written in .github/workflows/probe.yml, which has been
--    public. That workflow is removed from the repository in 9.2.
begin;

do $$
declare t text; n int := 0;
begin
    for t in select c.relname from pg_class c join pg_namespace s on s.oid = c.relnamespace
              where s.nspname = 'public' and c.relkind = 'r'
                and c.relname ~ '^rb_bak(021|26|50|51|515|53|60|62|63)_' loop
        execute format('drop table public.%I', t);
        n := n + 1;
    end loop;
    raise notice '089: dropped % old backup tables', n;
end $$;

delete from auth.users u using public.profiles p
 where p.id = u.id and p.username = 'RbProbe7' and not p.admin;

commit;
