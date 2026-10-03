#!/usr/bin/env python3
"""Scripted 'oracle' LLM for pipeline tests (no real model, no cost).

Speaks the Anthropic Messages API (streaming + non-streaming) and drives Claude Code through a fixed
tool-call script that writes the REAL ground-truth PoC and patch into /output, then ends the turn.
If the pipeline is sound, validation must report S1..S4 all PASS. Used to prove the success path
(artifact copy-out + staged scoring) without paying for a model that happens to succeed.

Usage: mock_oracle_llm.py <project/task> <e2e|patch-only>
Env:   PORT (default 11435), MOCK_USAGE_IN / MOCK_USAGE_OUT (usage reported per call; for cap tests)
"""
import base64, json, os, sys, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "cybergym-e2e")
TASK = sys.argv[1] if len(sys.argv) > 1 else "hunspell/arvo_52195"
MODE = sys.argv[2] if len(sys.argv) > 2 else "e2e"
PORT = int(os.environ.get("PORT", "11435"))
USAGE_IN = int(os.environ.get("MOCK_USAGE_IN", "100"))
USAGE_OUT = int(os.environ.get("MOCK_USAGE_OUT", "20"))


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


STEPS = [("Bash", {"command": "ls -la /src /output | head -30", "description": "look around"})]
if MODE == "e2e":
    poc = b64(os.path.join(REPO, "data", "projects", TASK, "poc.bin"))
    STEPS.append(("Bash", {"command": f"echo {poc} | base64 -d > /output/poc.bin && wc -c /output/poc.bin",
                           "description": "write PoC"}))
patch = b64(os.path.join(REPO, "projects", TASK, "patch.diff"))
STEPS.append(("Bash", {"command": f"echo {patch} | base64 -d > /output/fix.patch && head -4 /output/fix.patch",
                       "description": "write patch"}))
FINAL = "Wrote /output/fix.patch" + (" and /output/poc.bin." if MODE == "e2e" else ".")


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def count_tool_results(messages):
    n = 0
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            n += sum(1 for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result")
    return n


def pick(req):
    """Return a content block for this turn."""
    if not req.get("tools"):                        # background calls (titles etc.)
        return {"type": "text", "text": "ok"}, "end_turn"
    n = count_tool_results(req.get("messages", []))
    if n < len(STEPS):
        name, inp = STEPS[n]
        return {"type": "tool_use", "id": "toolu_" + uuid.uuid4().hex[:20], "name": name, "input": inp}, "tool_use"
    return {"type": "text", "text": FINAL}, "end_turn"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        if not self.path.startswith("/v1/messages"):
            self.send_response(404); self.end_headers(); return
        req = json.loads(body or b"{}")
        block, stop = pick(req)
        mid = "msg_" + uuid.uuid4().hex[:20]
        print(f"[mock] stream={bool(req.get('stream'))} tools={len(req.get('tools') or [])} -> {block['type']} {block.get('name','')} stop={stop}", flush=True)
        if not req.get("stream"):
            msg = {"id": mid, "type": "message", "role": "assistant", "model": "oracle", "content": [block],
                   "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": USAGE_IN, "output_tokens": USAGE_OUT}}
            data = json.dumps(msg).encode()
            self.send_response(200); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("connection", "close")
        self.end_headers()
        w = self.wfile.write
        w(sse("message_start", {"type": "message_start", "message": {"id": mid, "type": "message", "role": "assistant", "model": "oracle",
                                 "content": [], "stop_reason": None, "stop_sequence": None,
                                 "usage": {"input_tokens": USAGE_IN, "output_tokens": 1}}}))
        if block["type"] == "text":
            w(sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}))
            w(sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": block["text"]}}))
        else:
            w(sse("content_block_start", {"type": "content_block_start", "index": 0,
                                          "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
            js = json.dumps(block["input"])
            for i in range(0, len(js), 4096):       # chunked like a real model
                w(sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "input_json_delta", "partial_json": js[i:i + 4096]}}))
        w(sse("content_block_stop", {"type": "content_block_stop", "index": 0}))
        w(sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                "usage": {"output_tokens": USAGE_OUT}}))
        w(sse("message_stop", {"type": "message_stop"}))
        self.wfile.flush()


if __name__ == "__main__":
    print(f"mock oracle :{PORT} task={TASK} mode={MODE} steps={len(STEPS)}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
