import json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
USERS={}; MIN={"n":0}
FRIENDS=[{"username":"Max","state":"asks","online":False,"seen":None,"badges":None},{"username":"Leo","state":"friend","online":True,"seen":"x","badges":[None,None,None]},{"username":"Sarah2008","state":"friend","online":False,"seen":"x","badges":[None,None,None]},{"username":"Tom","state":"asked","online":False,"seen":None,"badges":None}]
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,code,obj):
        b=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n) or b"{}")
        tok=lambda e:{"access_token":"A-"+e,"refresh_token":"R-"+e,"expires_in":3600,"user":{"id":"u1","user_metadata":{"username":USERS[e]["name"]}}}
        if self.path.startswith("/auth/v1/signup"):
            e=body["email"]
            if e in USERS: return self._send(422,{"code":422,"error_code":"user_already_exists","msg":"User already registered"})
            USERS[e]={"pw":body["password"],"name":body["data"]["username"]}; return self._send(200,tok(e))
        if "grant_type=password" in self.path:
            e=body["email"]
            if e not in USERS or USERS[e]["pw"]!=body["password"]: return self._send(400,{"code":400,"error_code":"invalid_credentials","msg":"Invalid login credentials"})
            return self._send(200,tok(e))
        if "grant_type=refresh_token" in self.path:
            e=body["refresh_token"][2:]
            return self._send(200,tok(e)) if e in USERS else self._send(400,{"error_code":"refresh_token_not_found","msg":"Invalid Refresh Token"})
        if self.path.endswith("rb_username_free"): return self._send(200, (body["name"].lower()+"@users.rubenium.app") not in USERS)
        if self.path.endswith("rb_heartbeat"):
            MIN["n"]+=1; e=self.headers["Authorization"][9:]; return self._send(200,{"username":USERS[e]["name"],"minutes":MIN["n"],"credited":True,"elsewhere":False})
        if self.path.endswith("rb_delete_account"):
            e=self.headers["Authorization"][9:]
            if body.get("confirm")!=USERS[e]["name"]: return self._send(400,{"code":"P0001","message":"rb_confirm_mismatch"})
            USERS.pop(e); return self._send(200,True)
        if self.path.endswith("rb_friends_list"): return self._send(200, FRIENDS)
        if self.path.endswith("rb_friend_add"):
            if body["name"].lower()=="nobody": return self._send(400,{"code":"P0001","message":"rb_no_such_user"})
            FRIENDS.append({"username":body["name"],"state":"asked","online":False,"seen":None,"badges":None}); return self._send(200,"asked")
        if self.path.endswith("rb_friend_remove"):
            FRIENDS[:]=[f for f in FRIENDS if f["username"].lower()!=body["name"].lower()]; return self._send(200,True)
        if self.path.endswith("rb_profile"): return self._send(200,{"username":body["name"],"minutes":754,"since":"2026-11-15T12:00:00+00:00","equip":{},"me":False,"friend":True,"state":"friend","online":True,"badges":[],"items":3})
        if self.path.endswith("rb_history"): return self._send(200,{"rows":[{"game":"slots","bet":100,"paid":150,"item":None,"keys":None,"at":"x"},{"game":"case:vault","bet":2000,"paid":19200,"item":"badge:galaxy:gold","keys":None,"at":"x"},{"game":"blackjack","bet":500,"paid":0,"item":None,"keys":None,"at":"x"},{"game":"spin","bet":0,"paid":60,"item":None,"keys":"0","at":"x"}],"bet":600,"won":150,"best":150,"cases":1})
        self._send(200,{})
def serve(port=8765):
    s=HTTPServer(("127.0.0.1",port),H); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
