"""A local stand-in for the Supabase API, backed by a local test database (never the real server).

Rubenium reads its server address from RUBENIUM_API, so with RUBENIUM_API=http://127.0.0.1:<port> the app logs in,
calls rb_* functions and reads its tables here, against a database built by overhaul/db/run_tests.py (the repo
migrations, or the private live snapshot). Used by the logged-in self-test and the screenshot crawl.

What it does, like PostgREST and GoTrue do for the calls Rubenium makes:
  POST /rest/v1/rpc/<fn>        runs public.<fn>(named args) as anon or as the logged-in player (RLS, grants apply)
  GET  /rest/v1/<table>?select=*&order=<col>&limit=&offset=   reads a table as anon
  POST /auth/v1/token?grant_type=password|refresh_token, /auth/v1/signup, /auth/v1/logout, GET /auth/v1/user
  /functions/v1/*, /storage/v1/*  answer "not available here"
Any password is accepted: test accounts only. A token is "stub.<user id>".

Usage: python overhaul/stub/server.py --db rb_stub [--port 54321]
"""
import argparse
import json
import os
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import psycopg

IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
MAIL = "@users.rubenium.app"
_LOCAL = threading.local()
DSN = ""
CALLS: dict = {}            # fn -> number of calls (written to --calls at exit: which functions the pages used)
ERRORS: dict = {}           # fn -> first error text


def db():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None or conn.closed:
        conn = _LOCAL.conn = psycopg.connect(DSN, autocommit=False)
    return conn


class Refused(Exception):
    def __init__(self, status: int, body: dict) -> None:
        super().__init__(body.get("message", ""))
        self.status, self.body = status, body


def _as(cur, who) -> None:
    claims = {"sub": str(who), "role": "authenticated"} if who else {"role": "anon"}
    cur.execute("select set_config('request.jwt.claims', %s, true), set_config('role', %s, true)",
                (json.dumps(claims), "authenticated" if who else "anon"))


def _pick(cur, fn: str, names: set):
    """The version of public.<fn> PostgREST would call: it takes exactly these argument names (the others have
    defaults)."""
    cur.execute("""select p.oid, coalesce(p.proargnames, '{}'), p.proargmodes, p.pronargs, p.pronargdefaults,
                          p.proretset, format_type(p.prorettype, null), t.typtype,
                          array(select format_type(x, null) from unnest(p.proargtypes::oid[]) x)
                     from pg_proc p join pg_namespace n on n.oid = p.pronamespace join pg_type t on t.oid = p.prorettype
                    where n.nspname = 'public' and p.proname = %s""", (fn,))
    for oid, argnames, modes, nargs, ndef, retset, rettype, typtype, types in cur.fetchall():
        ins = list(argnames[:nargs]) if not modes else [a for a, m in zip(argnames, modes) if m in ("i", "b", "v")]
        required = set(ins[:nargs - ndef])
        if names <= set(ins) and required <= names:
            return ins, types, retset, rettype
    raise Refused(404, {"code": "PGRST202", "message": f"Could not find the function public.{fn} with those arguments"})


def rpc(fn: str, args: dict, who):
    if not IDENT.match(fn):
        raise Refused(404, {"code": "PGRST202", "message": "no such function"})
    CALLS[fn] = CALLS.get(fn, 0) + 1
    conn = db()
    try:
        with conn.cursor() as cur:
            ins, types, retset, rettype = _pick(cur, fn, set(args))
            parts, vals = [], []
            for name, typ in zip(ins, types):
                if name in args:
                    v = args[name]
                    if isinstance(v, list) and typ.endswith("[]"):
                        v = [x if x is None or isinstance(x, str) else (json.dumps(x) if isinstance(x, (dict, list))
                                                                       else str(x)) for x in v]
                    elif isinstance(v, (dict, list)) or typ in ("json", "jsonb"):
                        v = json.dumps(v)
                    elif isinstance(v, bool):
                        v = "true" if v else "false"
                    elif v is not None:
                        v = str(v)
                    parts.append(f'"{name}" => %s::{typ}')
                    vals.append(v)
            call = f'public."{fn}"({", ".join(parts)})'
            _as(cur, who)
            if rettype == "void":
                cur.execute(f"select {call}", vals)
                cur.fetchall()
                conn.commit()
                return None
            if retset:
                cur.execute(f"select coalesce(json_agg(x), '[]'::json) from {call} x", vals)
            else:
                cur.execute(f"select to_json({call})", vals)
            ans = cur.fetchone()[0]
        conn.commit()
        return ans
    except Refused:
        conn.rollback()
        raise
    except psycopg.Error as exc:
        conn.rollback()
        d = exc.diag
        ERRORS.setdefault(fn, f"{d.sqlstate} {d.message_primary}")
        status = 401 if d.sqlstate == "42501" else 400
        raise Refused(status, {"code": d.sqlstate, "message": d.message_primary, "details": d.message_detail,
                               "hint": d.message_hint}) from None


def table(name: str, q: dict):
    if not IDENT.match(name):
        raise Refused(404, {"message": "no such table"})
    sql = f'select coalesce(json_agg(x), \'[]\'::json) from (select * from public."{name}"'
    order = (q.get("order") or [""])[0].split(".")[0]
    if order and IDENT.match(order):
        sql += f' order by "{order}"'
    for k in ("limit", "offset"):
        v = (q.get(k) or [""])[0]
        if v.isdigit():
            sql += f" {k} {int(v)}"
    conn = db()
    try:
        with conn.cursor() as cur:
            _as(cur, None)
            cur.execute(sql + ") x")
            ans = cur.fetchone()[0]
        conn.commit()
        return ans
    except psycopg.Error as exc:
        conn.rollback()
        raise Refused(400, {"code": exc.diag.sqlstate, "message": exc.diag.message_primary}) from None


def session_for(uid) -> dict:
    conn = db()
    with conn.cursor() as cur:
        cur.execute("select id, email, raw_user_meta_data from auth.users where id = %s", (uid,))
        row = cur.fetchone()
    conn.commit()
    if not row:
        raise Refused(400, {"error_code": "invalid_grant", "msg": "Invalid login credentials"})
    return {"access_token": f"stub.{row[0]}", "refresh_token": f"stub.{row[0]}", "token_type": "bearer",
            "expires_in": 3600, "user": {"id": str(row[0]), "email": row[1], "user_metadata": row[2] or {}}}


def auth(path: str, q: dict, body: dict, who):
    conn = db()
    if path == "/auth/v1/token":
        grant = (q.get("grant_type") or [""])[0]
        if grant == "refresh_token":
            tok = str(body.get("refresh_token", ""))
            return session_for(tok.split(".", 1)[1] if tok.startswith("stub.") else None)
        with conn.cursor() as cur:
            cur.execute("select id from auth.users where email = %s", (str(body.get("email", "")).lower(),))
            row = cur.fetchone()
        conn.commit()
        if not row:
            raise Refused(400, {"error_code": "invalid_credentials", "msg": "Invalid login credentials"})
        return session_for(row[0])
    if path == "/auth/v1/signup":
        uid = uuid.uuid4()
        try:
            with conn.cursor() as cur:
                cur.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, %s)",
                            (uid, str(body.get("email", "")).lower(), json.dumps(body.get("data") or {})))
            conn.commit()
        except psycopg.Error as exc:
            conn.rollback()
            raise Refused(500, {"msg": "Database error saving new user", "message": exc.diag.message_primary}) from None
        return session_for(uid)
    if path == "/auth/v1/logout":
        return None
    if path == "/auth/v1/user":
        if not who:
            raise Refused(401, {"msg": "no login"})
        return session_for(who)["user"]
    raise Refused(404, {"message": "not available here"})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a) -> None:        # quiet; the app's own log says what it did
        pass

    def _who(self):
        tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        return tok.split(".", 1)[1] if tok.startswith("stub.") else None

    def _send(self, status: int, ans) -> None:
        raw = b"" if ans is None and status == 204 else json.dumps(ans).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self, method: str) -> None:
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"null") if n else None
        except ValueError:
            body = None
        try:
            if u.path.startswith("/rest/v1/rpc/") and method == "POST":
                ans = rpc(u.path.rsplit("/", 1)[1], body if isinstance(body, dict) else {}, self._who())
            elif u.path.startswith("/rest/v1/") and method == "GET":
                ans = table(u.path.rsplit("/", 1)[1], q)
            elif u.path.startswith("/auth/v1/"):
                ans = auth(u.path, q, body if isinstance(body, dict) else {}, self._who())
            else:
                raise Refused(503, {"message": "not available on the local stand-in"})
            self._send(200, ans)
        except Refused as r:
            self._send(r.status, r.body)
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"message": f"stub: {type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        self._handle("POST")

    def do_GET(self) -> None:
        self._handle("GET")

    def do_PATCH(self) -> None:
        self._handle("PATCH")


def main() -> None:
    global DSN
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--port", type=int, default=54321)
    ap.add_argument("--calls", default="", help="write the functions called (and their first errors) here at exit")
    a = ap.parse_args()
    DSN = (f"host={os.environ.get('PGHOST', '/var/tmp/pg')} port={os.environ.get('PGPORT', '5433')} "
           f"user={os.environ.get('PGUSER', 'postgres')} dbname={a.db}")
    import signal

    def stop(*_a):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"stub server on http://127.0.0.1:{a.port} (database {a.db})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if a.calls:
            with open(a.calls, "w") as f:
                json.dump({"calls": CALLS, "errors": ERRORS}, f, indent=1, sort_keys=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
