from pathlib import Path
import shutil

T = Path.home() / "benchmark-evals" / "tools"


def once(path, old, new):
    s = path.read_text()
    assert s.count(old) == 1, (path.name, old[:50], s.count(old))
    path.write_text(s.replace(old, new))


shim, reg = T / "llm_shim_new.py", T / "model_registry.py"
for p in (shim, reg):
    shutil.copy2(p, str(p) + ".pre-fallbacks")
once(shim, 'PROVIDER_ORDER = [f for f in os.environ.get("PROVIDER_ORDER", "").split(",") if f]\n',
     'PROVIDER_ORDER = [f for f in os.environ.get("PROVIDER_ORDER", "").split(",") if f]\n'
     'PROVIDER_ALLOW_FALLBACKS = os.environ.get("PROVIDER_ALLOW_FALLBACKS", "1") != "0"   # the registry exports 0 unless an entry opts in; unset keeps the earlier behaviour (fallbacks on)\n')
once(shim, 'req["provider"] = {"order": PROVIDER_ORDER, "allow_fallbacks": True}',
     'req["provider"] = {"order": PROVIDER_ORDER, "allow_fallbacks": PROVIDER_ALLOW_FALLBACKS}')
once(reg, '        e["PROVIDER_ORDER"] = ",".join(route.provider_order)\n',
     '        e["PROVIDER_ORDER"] = ",".join(route.provider_order)\n'
     '        e["PROVIDER_ALLOW_FALLBACKS"] = "1" if route.allow_fallbacks else "0"\n')
print("patched")
