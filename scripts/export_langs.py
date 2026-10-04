"""Writes demo/langs.json: each demo language's name, stack and the stack-specific mechanism text.

The Go page writer (aqv pages) reads this file because the data lives in the Python stage
modules (demo/langs/<lang>/stages.py).

    .venv/bin/python scripts/export_langs.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
from build_baseline import LANGS, load_lang  # noqa: E402


def main():
    langs = []
    for lang in LANGS:
        L = load_lang(lang)
        langs.append({"lang": lang, "name": L.NAME, "stack": L.STACK, "mechanisms": getattr(L, "MECHANISMS", {})})
    dest = ROOT / "demo" / "langs.json"
    dest.write_text(json.dumps(langs, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(langs)} languages -> {dest}")


if __name__ == "__main__":
    main()
