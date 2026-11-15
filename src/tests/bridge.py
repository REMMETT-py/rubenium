"""Test stand-in for Supabase: the same web calls, answered by the real SQL on the local test database."""
import json, subprocess, threading, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
USERS = {"ruben": "00000000-0000-0000-0000-000000000001", "max": "00000000-0000-0000-0000-000000000003", "leo": "00000000-0000-0000-0000-000000000004"}
def sql(q, sub=""):
    pre = f"set request.jwt.claim.sub='{sub}'; set role {'authenticated' if sub else 'anon'}; "
    r = subprocess.run(["psql", "-h", "/tmp", "-p", "5544", "-U", "postgres", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", pre + q], capture_output=True, text=True)
    if r.returncode != 0:
        m = re.search(r"ERROR:\s+(.*)", r.stderr)
        raise RuntimeError(m.group(1) if m else r.stderr)
    return r.stdout.strip()
def lit(v):
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _sub(self):
        tok = (self.headers.get("Authorization") or "")[7:]
        return USERS.get(tok[2:], "") if tok.startswith("A-") else ""
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); table = u.path.rsplit("/", 1)[1]
        order = q.get("order", ["1"])[0]; lim = int(q.get("limit", ["1000"])[0]); off = int(q.get("offset", ["0"])[0])
        try: out = sql(f"select coalesce(json_agg(t), '[]') from (select * from public.{table} order by {order} limit {min(lim,1000)} offset {off}) t", self._sub())
        except RuntimeError as e: return self._send(400, {"message": str(e)})
        self._send(200, json.loads(out))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if "grant_type=password" in self.path or "grant_type=refresh_token" in self.path or "signup" in self.path:
            name = (body.get("email") or body.get("refresh_token", "R-")[2:]).split("@")[0]
            if name not in USERS: return self._send(400, {"error_code": "invalid_credentials", "msg": "Invalid login credentials"})
            return self._send(200, {"access_token": "A-" + name, "refresh_token": "R-" + name, "expires_in": 3600, "user": {"id": USERS[name], "user_metadata": {"username": name.capitalize()}}})
        if "/rpc/" in self.path:
            fn = self.path.rsplit("/", 1)[1]
            args = ", ".join(f"{k} => {lit(v)}" for k, v in body.items())
            try: out = sql(f"select public.{fn}({args})", self._sub())
            except RuntimeError as e: return self._send(400, {"code": "P0001", "message": str(e)})
            try: return self._send(200, json.loads(out) if out else None)
            except ValueError: return self._send(200, out)
        self._send(200, {})
def serve(port=8766):
    s = ThreadingHTTPServer(("127.0.0.1", port), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return s
