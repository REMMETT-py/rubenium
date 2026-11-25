#!/usr/bin/env python3
"""Database tests. Builds a template database once (Supabase stand-in + the server's schema), then runs every test in
the given folders, each in its own fresh copy of the template.

  python overhaul/db/run_tests.py tests/db [more folders...]

Server schema: the file named by RB_BASELINE (a snapshot of the live server) when set, otherwise every migration in
supabase/migrations replayed in order. After that, every migration numbered 074 or higher is applied on top, so a new
migration is always tested against what players really use.

A test that shows a known problem not fixed yet starts with a line `-- xfail: <why>` (.sql) or `XFAIL = "<why>"` (.py):
its failure is expected (XFAIL) and does not fail the run; once it passes it is reported as XPASS so the mark is removed.

A .sql test passes when it runs without an error (tests use `assert`). A .py test defines test(connect), where
connect() opens a new connection to the test's database (several of them = calls running at the same time).
"""
import os, subprocess, sys, time, glob, re
import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ENV = dict(os.environ, PGHOST=os.environ.get("PGHOST", "/var/tmp/pg"), PGPORT=os.environ.get("PGPORT", "5433"),
           PGUSER=os.environ.get("PGUSER", "postgres"))
TEMPLATE = "rb_template"


def psql(db, *args, check=True):
    r = subprocess.run(["psql", "-q", "-X", "-v", "ON_ERROR_STOP=1", "-d", db, *args], env=ENV,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r


def dsn(db):
    return f"host={ENV['PGHOST']} port={ENV['PGPORT']} user={ENV['PGUSER']} dbname={db}"


def new_migrations():
    files = sorted(glob.glob(os.path.join(REPO, "supabase", "migrations", "*.sql")))
    return [f for f in files if not f.endswith("_down.sql") and int(re.match(r"(\d+)", os.path.basename(f)).group(1)) >= 74]


def build_template():
    if "PGHOST" not in os.environ:                     # the throwaway local server; CI brings its own
        subprocess.run([os.path.join(HERE, "pg_start.sh")], check=True)
    psql("postgres", "-c", f"drop database if exists {TEMPLATE}", "-c", f"create database {TEMPLATE}")
    psql(TEMPLATE, "-c", f"alter database {TEMPLATE} set search_path = \"$user\", public, extensions")
    psql(TEMPLATE, "-1", "-f", os.path.join(HERE, "shim.sql"))
    base = os.environ.get("RB_BASELINE", "")
    if base:
        psql(TEMPLATE, "-1", "-f", base)
        src = "live snapshot " + os.path.basename(base)
    else:
        bad = []
        for f in sorted(glob.glob(os.path.join(REPO, "supabase", "migrations", "*.sql"))):
            if f.endswith("_down.sql") or f in new_migrations():
                continue
            if psql(TEMPLATE, "-1", "-f", f, check=False).returncode != 0:
                bad.append(os.path.basename(f))
        src = "repo migrations" + (f" ({len(bad)} failed: {', '.join(bad)})" if bad else "")
    for f in new_migrations():
        psql(TEMPLATE, "-1", "-f", f)
        src += " + " + os.path.basename(f)
    psql(TEMPLATE, "-1", "-f", os.path.join(REPO, "tests", "db", "_fixtures.sql"))
    return src


def run(path):
    db = "rb_t_" + re.sub(r"\W", "_", os.path.basename(path))[:40].lower()
    psql("postgres", "-c", f"drop database if exists {db}", "-c", f"create database {db} template {TEMPLATE}")
    try:
        if path.endswith(".sql"):
            r = psql(db, "-f", path, check=False)
            lines = r.stderr.strip().splitlines()
            return r.returncode == 0, next((x for x in lines if "ERROR" in x), lines[-1] if lines else "")
        ns = {"__file__": os.path.abspath(path)}
        exec(compile(open(path).read(), path, "exec"), ns)
        ns["test"](lambda: psycopg.connect(dsn(db), autocommit=True))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        psql("postgres", "-c", f"drop database if exists {db} with (force)", check=False)


def main():
    folders = sys.argv[1:] or [os.path.join(REPO, "tests", "db")]
    t0 = time.time()
    print("server schema:", build_template())
    tests = sorted(p for f in folders for p in glob.glob(os.path.join(f, "test_*")) if p.endswith((".sql", ".py")))
    failed = passed = xfail = xpass = skipped = 0
    live = bool(os.environ.get("RB_BASELINE"))
    for p in tests:
        if not live and re.search(r'^(?:-- needs_live_snapshot|NEEDS_LIVE_SNAPSHOT = True)', open(p).read(), re.M):
            skipped += 1
            print("SKIP  " + os.path.relpath(p, REPO) + "  (needs the live snapshot, RB_BASELINE)")
            continue
        m = re.search(r'^(?:-- xfail:|XFAIL = )\s*"?(.*?)"?\s*$', open(p).read(), re.M)
        ok, why = run(p)
        rel = os.path.relpath(p, REPO)
        if m and not ok:
            xfail += 1
            print(f"XFAIL {rel}  ({m.group(1)})")
        elif m:
            xpass += 1
            print(f"XPASS {rel}  (fixed: remove the xfail mark)")
        elif ok:
            passed += 1
            print("PASS  " + rel)
        else:
            failed += 1
            print("FAIL  " + rel + "  ->  " + why[:300])
    print(f"{passed} passed, {failed} failed, {xfail} known problems, {xpass} newly fixed, {skipped} skipped ({time.time() - t0:.0f} s)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
