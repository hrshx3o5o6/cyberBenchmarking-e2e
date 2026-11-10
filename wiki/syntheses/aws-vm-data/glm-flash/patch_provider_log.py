from pathlib import Path
import shutil

T = Path.home() / "benchmark-evals" / "tools"


def once(path, old, new):
    s = path.read_text()
    assert s.count(old) == 1, (path.name, old[:50], s.count(old))
    path.write_text(s.replace(old, new))


rc, shim = T / "responses_chat.py", T / "llm_shim_new.py"
for p in (rc, shim):
    shutil.copy2(p, str(p) + ".pre-provlog")
once(rc, "        self.error = None           # message of an error object the upstream sent inside the stream\n",
     "        self.error = None           # message of an error object the upstream sent inside the stream\n"
     "        self.provider = None        # name of the upstream provider as OpenRouter reports it in the chunks (logged per call, for the record of who served the model)\n")
once(rc, '        self.stats["chunks"] += 1\n',
     '        self.stats["chunks"] += 1\n        self.provider = chunk.get("provider") or self.provider\n')
once(shim, '                        rec["chunks"] = tr.stats\n',
     '                        rec["chunks"] = tr.stats\n                        rec["provider"] = getattr(tr, "provider", None)\n')
print("patched")
