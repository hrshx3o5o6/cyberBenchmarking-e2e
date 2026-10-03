#!/usr/bin/env python3
"""Tiny shim between the cybergym-e2e harness (litellm provider) and an Anthropic-format backend.

The harness' litellm provider needs three management endpoints and then points Claude Code at
LITELLM_BASE_URL. This shim provides them, forwards /v1/messages to the real backend (Ollama by
default), rewrites the model name, tallies usage, enforces caps and logs one JSON line per request.

Env:
  UPSTREAM       backend base URL, http or https, may carry a path prefix
                 (default http://127.0.0.1:11434; OpenRouter: https://openrouter.ai/api)
  TARGET_MODEL   model forced on every call  (required, e.g. gpt-oss:120b-cloud)
  UPSTREAM_KEY   key sent upstream           (default "ollama")
  UPSTREAM_KEY_FILE  read the key from this file instead (preferred for paid providers; never printed/logged)
  UPSTREAM_AUTH  x-api-key | bearer | both   (default x-api-key; OpenRouter needs bearer)
  STRIP_FIELDS   comma list of request fields to drop before forwarding (e.g. "context_management,thinking")
  PRICE_IN_PER_M / PRICE_CACHE_PER_M / PRICE_OUT_PER_M   USD per 1M tokens (fresh in / cache read / out)
  UPSTREAM_SERIAL  1 = send upstream calls one at a time (needed for Ollama's free tier, 1 concurrent request);
                 0 = allow parallel calls (default 0 for https upstreams like OpenRouter, 1 otherwise)
  UPSTREAM_TIMEOUT_STREAM  seconds of SILENCE tolerated on a streaming call before failing fast (default 150).
                 A stalled provider request then errors quickly and Claude Code retries, instead of hanging 10-15 min.
  UPSTREAM_TIMEOUT  same for non-streaming calls (default 300)
  MAX_SPEND_USD  hard USD cap per issued key (needs prices). MAX_TOTAL_SPEND_USD: cap across all keys since start.
  MAX_REQUESTS   hard cap on /v1/messages    (default 400)
  MAX_INPUT_TOKENS  hard cap, fresh input     (default 3000000)
  MAX_CACHE_TOKENS  hard cap, cache-read input (default 30000000)
  PORT           listen port                 (default 4000)
  BIND           listen address              (default 0.0.0.0, needed for :80 on macOS)
  MASTER_KEY     secret for /key/* (>=16 chars, required). Must equal the harness' LITELLM_MASTER_KEY.
  LOG_FILE       jsonl usage log             (default ../runs/shim.log)
Never logs request/response bodies or keys.
"""
import json, os, sys, threading, time, uuid, http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:11434")
TARGET_MODEL = os.environ.get("TARGET_MODEL")
_kf = os.environ.get("UPSTREAM_KEY_FILE")
UPSTREAM_KEY = open(_kf).read().strip() if _kf else os.environ.get("UPSTREAM_KEY", "ollama")
UPSTREAM_AUTH = os.environ.get("UPSTREAM_AUTH", "x-api-key")
STRIP_FIELDS = [f for f in os.environ.get("STRIP_FIELDS", "").split(",") if f]
def _f(name):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else None
PRICE_IN, PRICE_CACHE, PRICE_OUT = _f("PRICE_IN_PER_M"), _f("PRICE_CACHE_PER_M"), _f("PRICE_OUT_PER_M")
MAX_SPEND_USD, MAX_TOTAL_SPEND_USD = _f("MAX_SPEND_USD"), _f("MAX_TOTAL_SPEND_USD")
T_STREAM = float(os.environ.get("UPSTREAM_TIMEOUT_STREAM", "150"))
T_PLAIN = float(os.environ.get("UPSTREAM_TIMEOUT", "300"))
MAX_REQUESTS = int(os.environ.get("MAX_REQUESTS", "400"))
MAX_INPUT_TOKENS = int(os.environ.get("MAX_INPUT_TOKENS", "3000000"))      # fresh (non-cached) input only
MAX_CACHE_TOKENS = int(os.environ.get("MAX_CACHE_TOKENS", "30000000"))    # cache-read input, counted separately
PORT = int(os.environ.get("PORT", "4000"))
BIND = os.environ.get("BIND", "0.0.0.0")   # macOS only lets non-root bind :80 on the wildcard address
MASTER_KEY = os.environ.get("MASTER_KEY")  # required: protects /key/* ; /v1/messages needs a key issued by /key/generate
LOG_FILE = os.environ.get("LOG_FILE", os.path.join(os.path.dirname(__file__), "..", "runs", "shim.log"))

if not TARGET_MODEL:
    sys.exit("TARGET_MODEL is required")
if not MASTER_KEY or len(MASTER_KEY) < 16:
    sys.exit("MASTER_KEY (>=16 chars) is required: the shim listens on all interfaces")

up = urlparse(UPSTREAM)
UP_HTTPS = up.scheme == "https"
UP_PREFIX = up.path.rstrip("/")
UP_PORT = up.port or (443 if UP_HTTPS else 80)
if (MAX_SPEND_USD is not None or MAX_TOTAL_SPEND_USD is not None) and None in (PRICE_IN, PRICE_CACHE, PRICE_OUT):
    sys.exit("a USD cap needs PRICE_IN_PER_M, PRICE_CACHE_PER_M and PRICE_OUT_PER_M")
if UP_HTTPS and (UPSTREAM_KEY in ("", "ollama")):
    sys.exit("remote HTTPS upstream needs a real key (UPSTREAM_KEY or UPSTREAM_KEY_FILE)")
if UP_HTTPS and MAX_SPEND_USD is None:
    sys.exit("remote paid upstream requires MAX_SPEND_USD (fail-safe: no uncapped spend)")
TOTAL = {"spend": 0.0}


def _n(x):
    """Provider usage fields can be null (OpenRouter sends cache_read_input_tokens: null); treat as 0."""
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def _cost(u):
    c = u.get("cost") if isinstance(u, dict) else None
    return float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else None


def eff_cap(c):
    """Per-key USD cap = the stricter of the shim's env cap and the max_budget the harness asked for."""
    caps = [x for x in (MAX_SPEND_USD, c.get("max_budget")) if x is not None]
    return min(caps) if caps else None


def cost_of(inp, cache, out):
    if None in (PRICE_IN, PRICE_CACHE, PRICE_OUT):
        return 0.0
    return (inp * PRICE_IN + cache * PRICE_CACHE + out * PRICE_OUT) / 1e6
_ser = os.environ.get("UPSTREAM_SERIAL")
SERIAL = (_ser == "1") if _ser in ("0", "1") else (not up.scheme == "https")
import contextlib
LOCK = threading.Lock() if SERIAL else contextlib.nullcontext()   # serialise upstream calls only when required
STATE_LOCK = threading.Lock()
KEYS = {}                        # key -> counters


def new_counters(alias="", max_budget=None):
    return {"alias": alias, "max_budget": max_budget, "requests": 0, "input_tokens": 0, "cache_read_tokens": 0,
            "output_tokens": 0, "errors": 0, "started": time.time(), "spend": 0.0}


def log(rec):
    rec["ts"] = round(time.time(), 3)
    with STATE_LOCK, open(LOG_FILE, "a") as f:
        f.write(json.dumps(rec) + "\n")


def est_tokens(obj):
    return max(1, len(json.dumps(obj)) // 4)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence default access log
        pass

    # ---- helpers
    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _presented(self):
        auth = self.headers.get("authorization", "") or self.headers.get("x-api-key", "")
        return auth.replace("Bearer ", "").strip()

    def _is_master(self):
        return self._presented() == MASTER_KEY

    def _key(self):
        k = self._presented()
        with STATE_LOCK:
            return k, KEYS.get(k)

    # ---- routes
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/key/info":
            if not self._is_master():
                return self._json(401, {"error": "unauthorized"})
            k = parse_qs(p.query).get("key", [""])[0]
            with STATE_LOCK:
                c = KEYS.get(k)
            if not c:
                return self._json(404, {"error": "unknown key"})
            return self._json(200, {"info": {**c, "effective_cap_usd": eff_cap(c)}})
        if p.path in ("/health", "/"):
            return self._json(200, {"ok": True, "target": TARGET_MODEL, "upstream": f"{up.scheme}://{up.hostname}{UP_PREFIX}",
                                    "auth": UPSTREAM_AUTH, "serial_upstream": SERIAL, "timeout_stream_s": T_STREAM, "timeout_plain_s": T_PLAIN, "usd_cap_per_key": MAX_SPEND_USD, "usd_cap_total": MAX_TOTAL_SPEND_USD,
                                    "total_spend": round(TOTAL["spend"], 6)})
        if p.path.startswith("/v1/models"):
            return self._json(200, {"data": [{"id": TARGET_MODEL, "type": "model"}], "has_more": False})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        if p.startswith("/key/") and not self._is_master():
            return self._json(401, {"error": "unauthorized"})
        if p == "/key/generate":
            req = json.loads(body or b"{}")
            k = "sk-shim-" + uuid.uuid4().hex[:16]
            with STATE_LOCK:
                KEYS[k] = new_counters(req.get("key_alias", ""), req.get("max_budget"))
            log({"event": "key_generate", "alias": req.get("key_alias")})
            return self._json(200, {"key": k})
        if p == "/key/delete":
            req = json.loads(body or b"{}")
            for k in req.get("keys", []):
                log({"event": "key_delete", **{kk: vv for kk, vv in KEYS.get(k, {}).items()
                                               if kk in ("alias", "requests", "input_tokens", "cache_read_tokens", "output_tokens", "errors")}})
            return self._json(200, {"deleted_keys": req.get("keys", [])})
        if p == "/v1/messages/count_tokens":
            req = json.loads(body or b"{}")
            return self._json(200, {"input_tokens": est_tokens(req.get("messages", [])) + est_tokens(req.get("system", "")) + est_tokens(req.get("tools", []))})
        if p == "/v1/messages":
            return self._messages(body)
        return self._json(404, {"error": "not found"})

    def _messages(self, body):
        key, c = self._key()
        if c is None:
            return self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid key"}})
        try:
            req = json.loads(body)
        except Exception:
            return self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad json"}})
        orig_model = req.get("model")
        req["model"] = TARGET_MODEL
        for fld in STRIP_FIELDS:
            req.pop(fld, None)
        with STATE_LOCK:
            over = (c["requests"] >= MAX_REQUESTS or c["input_tokens"] >= MAX_INPUT_TOKENS or c["cache_read_tokens"] >= MAX_CACHE_TOKENS
                    or (eff_cap(c) is not None and c["spend"] >= eff_cap(c))
                    or (MAX_TOTAL_SPEND_USD is not None and TOTAL["spend"] >= MAX_TOTAL_SPEND_USD))
        if over:
            log({"event": "cap_hit", "requests": c["requests"], "input": c["input_tokens"], "cache": c["cache_read_tokens"],
                 "spend": round(c["spend"], 6), "total_spend": round(TOTAL["spend"], 6)})
            return self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "shim budget exhausted"}})
        stream = bool(req.get("stream"))
        payload = json.dumps(req).encode()
        t0 = time.time()
        rec = {"event": "messages", "alias": c.get("alias"), "orig_model": orig_model, "stream": stream, "tools": len(req.get("tools") or [])}
        usage = {"in": 0, "cache": 0, "out": 0, "cost": None}
        status = 0
        try:
            with LOCK:
                for attempt in range(4):  # retry 429 on the free tier
                    conn = (http.client.HTTPSConnection if UP_HTTPS else http.client.HTTPConnection)(up.hostname, UP_PORT, timeout=(T_STREAM if stream else T_PLAIN))
                    hdrs = {"content-type": "application/json",
                            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01")}
                    if UPSTREAM_AUTH in ("x-api-key", "both"):
                        hdrs["x-api-key"] = UPSTREAM_KEY
                    if UPSTREAM_AUTH in ("bearer", "both"):
                        hdrs["authorization"] = "Bearer " + UPSTREAM_KEY
                    conn.request("POST", UP_PREFIX + "/v1/messages", payload, hdrs)
                    resp = conn.getresponse()
                    status = resp.status
                    if status == 429 and attempt < 3:
                        resp.read(); conn.close(); time.sleep(3 * (attempt + 1)); continue
                    break
                ctype = resp.getheader("content-type", "application/json")
                if stream and status == 200:
                    self.send_response(200)
                    self.send_header("content-type", ctype)
                    self.send_header("cache-control", "no-cache")
                    self.send_header("connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    for line in resp:  # SSE is line oriented
                        self.wfile.write(line); self.wfile.flush()
                        if line.startswith(b"data:"):
                            try:
                                d = json.loads(line[5:])
                            except Exception:
                                continue
                            if d.get("type") == "message_start":
                                u = d.get("message", {}).get("usage", {})
                                usage["in"] = _n(u.get("input_tokens")); usage["cache"] = _n(u.get("cache_read_input_tokens"))
                                usage["out"] = max(usage["out"], _n(u.get("output_tokens")))
                            elif d.get("type") == "message_delta":
                                u = d.get("usage", {})
                                usage["in"] = _n(u.get("input_tokens")) or usage["in"]
                                usage["cache"] = _n(u.get("cache_read_input_tokens")) or usage["cache"]
                                usage["out"] = _n(u.get("output_tokens")) or usage["out"]
                                if _cost(u) is not None:
                                    usage["cost"] = _cost(u)
                else:
                    data = resp.read()
                    if status == 200:
                        try:
                            u = json.loads(data).get("usage", {})
                            usage = {"in": _n(u.get("input_tokens")), "cache": _n(u.get("cache_read_input_tokens")),
                                     "out": _n(u.get("output_tokens")), "cost": _cost(u)}
                        except Exception:
                            pass
                    self.send_response(status)
                    self.send_header("content-type", ctype)
                    self.send_header("content-length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    if status != 200:
                        rec["upstream_error"] = data[:200].decode("utf8", "replace")
                conn.close()
        except Exception as e:
            rec["exception"] = repr(e)[:200]
            rec["timeout_s"] = T_STREAM if stream else T_PLAIN
            status = status or 502
            try:
                self._json(502, {"type": "error", "error": {"type": "api_error", "message": "shim upstream failure"}})
            except Exception:
                pass
        calc = cost_of(usage["in"], usage["cache"], usage["out"])
        cost = usage["cost"] if usage.get("cost") is not None else calc   # provider-reported cost is authoritative
        try:
            with STATE_LOCK:
                c["requests"] += 1
                c["input_tokens"] += usage["in"]; c["cache_read_tokens"] += usage["cache"]; c["output_tokens"] += usage["out"]
                c["spend"] = round(c["spend"] + cost, 8); TOTAL["spend"] += cost
                if status != 200:
                    c["errors"] += 1
            rec.update(status=status, in_tok=usage["in"], cache_tok=usage["cache"], out_tok=usage["out"], secs=round(time.time() - t0, 2),
                       cost=round(cost, 8), cost_calc=round(calc, 8), cost_source="provider" if usage.get("cost") is not None else "calc",
                       spend=round(c["spend"], 6), total_spend=round(TOTAL["spend"], 6))
        except Exception as e:                                  # never let accounting fail silently
            rec.update(status=status, accounting_error=repr(e)[:200])
        log(rec)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
    print(f"shim :{PORT} -> {UPSTREAM} model={TARGET_MODEL} caps: {MAX_REQUESTS} req / {MAX_INPUT_TOKENS} fresh-in / {MAX_CACHE_TOKENS} cache-in", flush=True)
    ThreadingHTTPServer((BIND, PORT), H).serve_forever()
