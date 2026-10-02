"""Fills the README's result line and tables from the last demo runs (demo/.work/<lang>/demo-results.json)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT))
from build_baseline import LANGS, load_lang  # noqa: E402
from aqv.engine import CHECKS  # noqa: E402

rows, mech, total, good, langs = [], {}, 0, 0, []
for lang in LANGS:
    f = ROOT / "demo/.work" / lang / "demo-results.json"
    if not f.exists():
        continue
    L = load_lang(lang)
    res = json.loads(f.read_text())
    ok = sum(1 for r in res if r.get("ok"))
    total, good = total + len(res), good + ok
    langs.append(L)
    rows.append(f"| [{L.NAME}](demo/results/{lang}/RESULTS.md) | {L.STACK} | {ok} of {len(res)} |")
checks = sorted({c for L in langs for c in getattr(L, "MECHANISMS", {})}, key=list(CHECKS).index)
mt = ["| Check | " + " | ".join(L.NAME for L in langs) + " |", "|---|" + "---|" * len(langs)]
for c in checks:
    mt.append(f"| {c} | " + " | ".join(getattr(L, "MECHANISMS", {}).get(c, "—") for L in langs) + " |")
line = f"{good} of {total} scenarios behave as expected across {len(langs)} languages."
p = ROOT / "README.md"
s = p.read_text()
s = s.replace("RESULT_LINE", line).replace("RESULT_TABLE", "\n".join(rows)).replace("MECHANISM_TABLE", "\n".join(mt))
p.write_text(s)
print(line)
