#!/usr/bin/env python3
"""Local test of llm_shim.py routes against a fake upstream (no network, no spend).
Checks: Anthropic route unchanged, Responses route accounting (input_tokens includes cached), streaming,
provider injection, caps, error shape. Run: python3 test_routes.py"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEEN = []


class Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
        SEEN.append((self.path, body, dict(self.headers)))
        stream = bool(body.get("stream"))
        if self.path == "/v1/messages":
            u = {"input_tokens": 100, "cache_creation_input_tokens": 40, "cache_read_input_tokens": 900, "output_tokens": 50}
            if stream:
                lines = [b"event: message_start\n", b"data: " + json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 100, "cache_creation_input_tokens": 40, "cache_read_input_tokens": 900, "output_tokens": 1}}}).encode() + b"\n", b"\n",
                         b"event: message_delta\n", b"data: " + json.dumps({"type": "message_delta", "usage": {"output_tokens": 50}}).encode() + b"\n", b"\n"]
                self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("connection", "close"); self.end_headers()
                for l in lines: self.wfile.write(l)
                return
            data = json.dumps({"type": "message", "content": [], "usage": u}).encode()
        elif self.path == "/v1/responses":
            u = {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 900}, "output_tokens": 50, "cost": 0.000123}
            if stream:
                lines = [b"event: response.created\n", b"data: " + json.dumps({"type": "response.created", "response": {}}).encode() + b"\n", b"\n",
                         b"event: response.completed\n", b"data: " + json.dumps({"type": "response.completed", "response": {"usage": u}}).encode() + b"\n", b"\n"]
                self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("connection", "close"); self.end_headers()
                for l in lines: self.wfile.write(l)
                return
            data = json.dumps({"id": "resp_1", "object": "response", "output": [], "usage": u}).encode()
        else:
            self.send_response(404); self.send_header("content-length", "0"); self.end_headers(); return
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)


def call(base, path, body, key):
    r = urllib.request.Request(base + path, json.dumps(body).encode(), {"authorization": "Bearer " + key, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=20) as f:
            return f.status, f.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(); logf = os.path.join(tmp, "shim.log")
    env = dict(os.environ, TARGET_MODEL="test/model", MASTER_KEY="m" * 20, UPSTREAM=f"http://127.0.0.1:{fake.server_address[1]}", PORT="14000",
               BIND="127.0.0.1", LOG_FILE=logf, PRICE_IN_PER_M="1", PRICE_CACHE_PER_M="0.1", PRICE_OUT_PER_M="2",
               PROVIDER_ORDER="wafer", COUNT_CACHE_CREATION="1", MAX_SPEND_USD="0.002", MAX_TOTAL_SPEND_USD="1", UPSTREAM_SERIAL="0")
    sh = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_shim.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1.5); base = "http://127.0.0.1:14000"; fails = []
    def check(name, cond, extra=""):
        print(("PASS " if cond else "FAIL ") + name, extra)
        if not cond: fails.append(name)
    try:
        r = urllib.request.Request(base + "/key/generate", b"{}", {"authorization": "Bearer " + "m" * 20, "content-type": "application/json"})
        key = json.load(urllib.request.urlopen(r))["key"]
        for path, kind, stream in [("/v1/messages", "messages", False), ("/v1/messages", "messages", True), ("/v1/responses", "responses", False), ("/responses", "responses", True)]:
            SEEN.clear()
            st, _ = call(base, path, {"model": "x", "stream": stream, "input": "hi", "messages": []}, key)
            up_path, up_body, up_hdr = SEEN[0]
            check(f"{path} stream={stream} status", st == 200, st)
            check(f"{path} upstream path", up_path == ("/v1/messages" if kind == "messages" else "/v1/responses"), up_path)
            check(f"{path} model rewritten + provider injected", up_body["model"] == "test/model" and up_body["provider"]["order"] == ["wafer"] and up_body["provider"]["allow_fallbacks"] is True)
        time.sleep(0.5)
        recs = [json.loads(l) for l in open(logf) if '"event": "messages"' in l]
        check("4 request records", len(recs) == 4, len(recs))
        for rc in recs:
            exp = (140, 900, 50) if rc["route"] == "messages" else (100, 900, 50)   # messages: 100 + 40 cache-creation counted as fresh; responses: 1000 incl 900 cached -> fresh 100
            check(f'{rc["route"]} stream={rc["stream"]} tokens fresh/cache/out', (rc["in_tok"], rc["cache_tok"], rc["out_tok"]) == exp, (rc["in_tok"], rc["cache_tok"], rc["out_tok"]))
        resp_recs = [r for r in recs if r["route"] == "responses"]
        check("responses cost uses provider usage.cost", all(abs(r["cost"] - 0.000123) < 1e-9 and r["cost_source"] == "provider" for r in resp_recs))
        msg_recs = [r for r in recs if r["route"] == "messages"]
        check("messages cost calculated from prices", all(abs(r["cost"] - (140 * 1 + 900 * 0.1 + 50 * 2) / 1e6) < 1e-9 for r in msg_recs))
        # cap: per-key cap 0.002 USD; keep calling until refused, then check error shape per route
        refused = None
        for _ in range(40):
            st, txt = call(base, "/v1/responses", {"model": "x", "input": "hi"}, key)
            if st == 400: refused = txt; break
        check("cap refuses responses route", refused is not None)
        rj = json.loads(refused) if refused else {}
        check("responses error shape is OpenAI style", "error" in rj and rj.get("type") != "error" and rj["error"].get("code") == "invalid_request_error", refused)
        st, txt = call(base, "/v1/messages", {"model": "x", "messages": []}, key)
        check("cap refuses messages route with Anthropic shape", st == 400 and json.loads(txt).get("type") == "error", txt[:80])
        st, txt = call(base, "/v1/responses", {"model": "x"}, "bad-key")
        check("bad key rejected on responses", st == 401)
    finally:
        sh.terminate()
    print("ALL PASS" if not fails else f"FAILED: {fails}"); sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
