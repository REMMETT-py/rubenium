"""Writes the undo file of a migration from the server as it is before it (functions put back exactly, new functions
dropped, triggers put back, settings put back).

  RB_BASELINE=... python overhaul/db/make_down.py supabase/migrations/076_v90_remaster.sql supabase/migrations/076_down.sql

The server before the migration is the baseline plus every earlier migration numbered 074 or higher. Rows the
migration changes (other than rb_config) are not put back: the migration's header says which ones.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ENV = dict(os.environ, PGHOST=os.environ.get("PGHOST", "/var/tmp/pg"), PGPORT=os.environ.get("PGPORT", "5433"),
           PGUSER=os.environ.get("PGUSER", "postgres"))
DB = "rb_before"


def psql(*args, db=DB):
    r = subprocess.run(["psql", "-q", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-d", db, *args], env=ENV,
                       capture_output=True)                  # bytes: some bodies were written with CR LF line ends
    if r.returncode:
        raise SystemExit(r.stderr.decode(errors="replace"))
    return r.stdout.decode("utf-8")


def main(up: str, down: str) -> None:
    num = int(re.match(r"(\d+)", os.path.basename(up)).group(1))
    psql("-c", f"drop database if exists {DB} with (force)", "-c", f"create database {DB}", db="postgres")
    psql("-c", f"alter database {DB} set search_path = \"$user\", public, extensions")
    psql("-1", "-f", os.path.join(HERE, "shim.sql"))
    psql("-1", "-f", os.environ["RB_BASELINE"])
    mig = os.path.join(REPO, "supabase", "migrations")
    for f in sorted(os.listdir(mig)):
        m = re.match(r"(\d+)_", f)
        if m and 74 <= int(m.group(1)) < num and not f.endswith("_down.sql"):
            psql("-1", "-f", os.path.join(mig, f))
    text = open(up).read()
    names = set(re.findall(r"create or replace function public\.(\w+)\(", text, re.I))
    names |= set(re.findall(r"'(rb_market_\w+)'", text))
    out = [f"-- Undo of {os.path.basename(up)}: made by overhaul/db/make_down.py from the server as it was before it.",
           "begin;"]
    for name in sorted(names):
        rows = psql("-c", f"select p.oid::regprocedure from pg_proc p where p.proname = '{name}' "
                          "and p.pronamespace = 'public'::regnamespace").split("\n")
        rows = [r for r in rows if r.strip()]
        if not rows:
            out.append(f"drop function if exists public.{name} cascade;")
            continue
        for sig in rows:
            body = psql("-c", f"select pg_get_functiondef('{sig}'::regprocedure)")
            out.append(body.rstrip() + ";")
    for trig in re.findall(r"drop trigger if exists (\w+) on public\.(\w+)", text):
        d = psql("-c", f"select pg_get_triggerdef(oid) from pg_trigger where tgname = '{trig[0]}' "
                       f"and tgrelid = 'public.{trig[1]}'::regclass")
        if d.strip():
            out.append(f"drop trigger if exists {trig[0]} on public.{trig[1]};")
            out.append(d.strip() + ";")
    keys = set(re.findall(r"\('([a-z0-9_]+)', [0-9.e]+\)", text))
    for k in sorted(keys):
        v = psql("-c", f"select value from public.rb_config where key = '{k}'").strip()
        out.append(f"update public.rb_config set value = {v} where key = '{k}';" if v else
                   f"delete from public.rb_config where key = '{k}';")
    out.append("commit;")
    with open(down, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    psql("-c", f"drop database if exists {DB} with (force)", db="postgres")
    print(f"{down}: {len(names)} functions, {len(keys)} settings")


if __name__ == "__main__":
    main(*sys.argv[1:3])
