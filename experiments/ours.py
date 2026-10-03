"""Runs this repo's verifier on the isolating variants, on the plain Python baseline
(no OFT notation), the same way demo/run_demo.py runs a scenario.

    .venv/bin/python experiments/ours.py --work <dir with a baseline/ from either run.py> --out <json> --gnupg <dir>
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--gnupg", required=True)
    ap.add_argument("--out", required=True, help="where to write the results JSON")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    env = dict(os.environ, GNUPGHOME=a.gnupg, DEMO=str(ROOT / "demo"), AQV_LANG="python")
    results = {}
    for script in sorted((HERE / "variants").glob("*.sh")):
        repo, out = work / f"ours-{script.stem}", work / f"ours-out-{script.stem}"
        for d in (repo, out):
            if d.exists():
                shutil.rmtree(d)
        shutil.copytree(work / "baseline", repo, symlinks=True)
        subprocess.run(["bash", str(script)], cwd=repo, env=env, check=True, capture_output=True)
        subprocess.run([sys.executable, "-m", "aqv", "check", "--repo", str(repo), "--out", str(out), "--base", "main"],
                       cwd=ROOT, env=env, capture_output=True)
        rep = json.loads((out / "results.json").read_text())
        results[script.stem] = {
            "failing": sorted(k for k, v in rep["checks"].items() if v in ("fail", "error")),
            "statuses": {r["id"]: r["status"] for r in rep["requirements"] if r["status"] != "Sync"},
        }
        print(script.stem, results[script.stem], flush=True)
    Path(a.out).write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
