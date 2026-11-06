#!/usr/bin/env python3
"""Probe a Qwen3.8-27B vLLM endpoint on Vertex AI (dedicated endpoint): prefix caching, warm capacity, decode speed, concurrent agents.

Environment: QWEN_PROJECT_NUMBER, QWEN_REGION (default asia-southeast1), QWEN_ENDPOINT_ID; log in with `gcloud auth application-default login`.
usage: qwen_endpoint_probe.py cache | conversation | residency [--tokens 30000 --count 9] | decode | agents [--counts 1 2 4 --turns 6 --start-words 7900] | needle [--tokens 90000 --trials 6]
  cache         time to first token of a ~28.6k-token prompt: new, identical, shared prefix, identical again, different
  conversation  a growing append-only conversation (about +3.8k tokens per turn): time to first token per turn
  residency     send N distinct prompts, re-send newest first until a miss: how many stay warm
  decode        tokens/s for one stream and aggregate with 2, 4, 8 parallel streams, plus a tool-call round trip
  agents        N agents (default 1, 2, 4) with growing ~50k-token conversations calling back to back
  needle        retrieval of a hidden code at long context (quality check, for example for a quantized KV cache)
Prompts are random words (nothing shared by accident). A cache hit answers in about a second, a miss costs the full prefill (about 3,300 tokens/s).
Results of 2026-11-04: wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs.md
"""
import argparse, concurrent.futures as cf, json, os, random, statistics as st, subprocess, threading, time, urllib.request

P, R, E = os.environ["QWEN_PROJECT_NUMBER"], os.environ.get("QWEN_REGION", "asia-southeast1"), os.environ["QWEN_ENDPOINT_ID"]
URL = f"https://{E}.{R}-{P}.prediction.vertexai.goog/v1/projects/{P}/locations/{R}/endpoints/{E}/chat/completions"
M = "Qwen/Qwen3.8-27B"
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]


def headers():
    tok = subprocess.check_output(["gcloud", "auth", "application-default", "print-access-token"]).decode().strip()
    return {"authorization": "Bearer " + tok, "x-goog-user-project": P, "content-type": "application/json"}


def text(words, seed):
    r = random.Random(seed)
    return " ".join(r.choice(WORDS) + str(r.randint(0, 99999)) for _ in range(words))        # about 6.25 tokens per word


def stream(messages, max_tokens=1, thinking=False, tools=None):
    body = {"model": M, "stream": True, "stream_options": {"include_usage": True}, "max_tokens": max_tokens, "messages": messages, "chat_template_kwargs": {"enable_thinking": thinking}}
    if tools: body["tools"] = tools
    t0 = time.time(); first = None; usage = None; out = []
    for line in urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), headers()), timeout=900):
        if line.startswith(b"data: ") and b"[DONE]" not in line:
            j = json.loads(line[6:]); first = first or time.time(); usage = j.get("usage") or usage
            out.extend(c.get("delta", {}).get("content") or "" for c in j.get("choices") or [])
    t1 = time.time()
    return dict(ttft=round((first or t1) - t0, 2), decode_s=(t1 - first) if first else 0, usage=usage or {}, text="".join(out))


def ttft(messages): r = stream(messages); return r["ttft"], r["usage"].get("prompt_tokens")


def cmd_cache(a):
    base = text(4500, 11); tail = lambda s: "\n\nQuestion " + text(60, s) + " Answer in one word."
    for label, c in (("new prompt", base + tail(1)), ("same prompt again", base + tail(1)), ("same prefix, different last ~100 tokens", base + tail(2)), ("same prompt, third time", base + tail(1)), ("a different new prompt", text(4500, 12) + tail(1))):
        s, n = ttft([{"role": "user", "content": c}]); print("%-42s %6.2fs  prompt tokens %s" % (label, s, n))


def cmd_conversation(a):
    msgs = [{"role": "user", "content": text(3150, 501) + "\nAcknowledge."}]
    for t in range(1, 8):
        s, n = ttft(msgs); print("turn %d: %6s tokens, time to first token %5.2fs" % (t, n, s))
        msgs += [{"role": "assistant", "content": "Acknowledged."}, {"role": "user", "content": "Next part:\n" + text(600, 600 + t) + "\nAcknowledge."}]


def cmd_residency(a):
    words = int(a.tokens / 6.25); prompts = [text(words, 3000 + i) + "\nAcknowledge." for i in range(a.count)]
    for i, p in enumerate(prompts): print("send #%d cold: %.2fs" % (i + 1, ttft([{"role": "user", "content": p}])[0]))
    warm = 0
    for i in reversed(range(a.count)):
        s = ttft([{"role": "user", "content": prompts[i]}])[0]; hit = s < 3; warm += hit; print("re-send #%d: %.2fs %s" % (i + 1, s, "WARM" if hit else "evicted"))
        if not hit: break
    print("warm prompts, newest first:", warm, "about", warm * a.tokens // 1000, "thousand tokens")


def cmd_decode(a):
    q = "Write a detailed 400-word explanation of topic number %d in computer science, with examples."
    r = stream([{"role": "user", "content": q % 0}], 500); print("one stream: %.1f tokens/s (first token %.2fs)" % (r["usage"]["completion_tokens"] / r["decode_s"], r["ttft"]))
    for k in (2, 4, 8):
        t = time.time()
        with cf.ThreadPoolExecutor(k) as p: res = list(p.map(lambda i: stream([{"role": "user", "content": q % (i + 1)}], 400), range(k)))
        tot = sum(x["usage"]["completion_tokens"] for x in res); print("%d parallel: %.1f tokens/s in total" % (k, tot / (time.time() - t)))
    tools = [{"type": "function", "function": {"name": "sh", "description": "run a shell command", "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}}]
    body = {"model": M, "messages": [{"role": "user", "content": "List the files in /tmp using the sh tool."}], "tools": tools, "max_tokens": 1500}
    t = time.time(); d = json.loads(urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), headers()), timeout=300).read())
    print("tool call: finish=%s in %.1fs" % (d["choices"][0]["finish_reason"], time.time() - t))


def cmd_agents(a):
    def agent(i, out, seed):
        msgs = [{"role": "user", "content": text(a.start_words, seed) + "\nAcknowledge."}]
        for t in range(a.turns):
            out.append((t, ttft(msgs)[0])); msgs += [{"role": "assistant", "content": "Acknowledged."}, {"role": "user", "content": "Next part:\n" + text(480, seed * 100 + t) + "\nAcknowledge."}]
    for k in a.counts:
        out = []; t0 = time.time(); th = [threading.Thread(target=agent, args=(i, out, 7000 + 100 * k + i)) for i in range(k)]
        [x.start() for x in th]; [x.join() for x in th]
        later = sorted(s for t, s in out if t > 0)
        print("%d agent(s): first call %.1fs, later calls mean %.1fs p90 %.1fs max %.1fs, wall %.0fs (start ~%dk tokens, +3k per turn, %d turns)" % (k, st.mean([s for t, s in out if t == 0]), st.mean(later), later[int(.9 * len(later))], max(later), time.time() - t0, a.start_words * 6.25 // 1000, a.turns), flush=True)


def cmd_needle(a):
    """Retrieval at long context (quality check for a quantized KV cache): a code hidden at 10%, 50% or 90% of a random-word prompt; thinking off, 200 tokens."""
    ok = 0
    for i in range(a.trials):
        code = "K%05d" % random.Random(900 + i).randint(0, 99999); body = text(int(a.tokens / 6.25), 5000 + i).split(" ")
        body.insert(int(len(body) * (0.1, 0.5, 0.9)[i % 3]), "The secret code is %s ." % code)
        r = stream([{"role": "user", "content": " ".join(body) + "\nWhat is the secret code? Answer with the code only."}], 200)
        hit = code in r["text"]; ok += hit
        print("trial %d (needle at %d%%, prompt %s tokens): %s, answer %r, first token %.1fs" % (i + 1, (10, 50, 90)[i % 3], r["usage"].get("prompt_tokens"), "OK" if hit else "MISS", r["text"].strip()[:40], r["ttft"]), flush=True)
    print("needle retrieval: %d of %d" % (ok, a.trials))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0]); sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("cache", "conversation", "decode"): sp.add_parser(n)
    g = sp.add_parser("agents"); g.add_argument("--counts", type=int, nargs="+", default=[1, 2, 4]); g.add_argument("--turns", type=int, default=6); g.add_argument("--start-words", type=int, default=7900)
    n = sp.add_parser("needle"); n.add_argument("--tokens", type=int, default=90000); n.add_argument("--trials", type=int, default=6)
    r = sp.add_parser("residency"); r.add_argument("--tokens", type=int, default=30000); r.add_argument("--count", type=int, default=9)
    a = ap.parse_args(); globals()["cmd_" + a.cmd](a)
