"""A migration must apply twice, undo twice, and leave the server exactly as it was (functions, their grants,
tables' grants and row level security, rb_config).
Usage: RB_BASELINE=... python overhaul/db/roundtrip.py UP.sql DOWN.sql"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, PGHOST=os.environ.get("PGHOST", "/var/tmp/pg"), PGPORT=os.environ.get("PGPORT", "5433"),
           PGUSER=os.environ.get("PGUSER", "postgres"))
DB = "rb_roundtrip"
SNAP = """
select 'fn ' || p.oid::regprocedure || ' ' || md5(pg_get_functiondef(p.oid)) || ' ' ||
       coalesce((select string_agg(x, ',' order by x) from unnest(p.proacl::text[]) x), 'default')
  from pg_proc p where p.pronamespace = 'public'::regnamespace and p.prokind = 'f'
union all
select 'tb ' || c.relname || ' rls=' || c.relrowsecurity || ' ' ||
       coalesce((select string_agg(x, ',' order by x) from unnest(c.relacl::text[]) x), 'default')
  from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind in ('r', 'v', 'm', 'p')
union all
select 'cfg ' || key || '=' || value from public.rb_config
union all
select 'defacl ' || defaclobjtype::text || ' ' || (select string_agg(x, ',' order by x) from unnest(defaclacl::text[]) x)
  from pg_default_acl where defaclnamespace = 'public'::regnamespace
order by 1"""


def psql(*args, check=True):
    r = subprocess.run(["psql", "-q", "-X", "-v", "ON_ERROR_STOP=1", *args], env=ENV, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit("FAILED: " + " ".join(args[-2:]) + "\n" + r.stderr[-2000:])
    return r.stdout


def snap():
    return psql("-d", DB, "-At", "-c", SNAP).splitlines()


def main():
    up, down = sys.argv[1:3]
    psql("-d", "postgres", "-c", f"drop database if exists {DB} with (force)", "-c", f"create database {DB}")
    psql("-d", DB, "-c", f"alter database {DB} set search_path = \"$user\", public, extensions")
    psql("-d", DB, "-1", "-f", os.path.join(HERE, "shim.sql"))
    psql("-d", DB, "-1", "-f", os.environ["RB_BASELINE"])
    before = snap()
    psql("-d", DB, "-1", "-f", up)
    after_up = snap()
    psql("-d", DB, "-1", "-f", up)
    assert snap() == after_up, "the second run changed something"
    psql("-d", DB, "-1", "-f", down)
    psql("-d", DB, "-1", "-f", down)
    after = snap()
    gone = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    psql("-d", "postgres", "-c", f"drop database {DB} with (force)")
    if gone or extra:
        print("NOT THE SAME AFTER UNDO")
        for x in gone[:30]:
            print("  was:  ", x[:220])
        for x in extra[:30]:
            print("  now:  ", x[:220])
        sys.exit(1)
    print(f"ROUNDTRIP OK: applies twice, undoes twice, {len(before)} objects back exactly as they were "
          f"({len(set(after_up) - set(before))} changed while applied)")


if __name__ == "__main__":
    main()
