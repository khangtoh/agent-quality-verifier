"""Runs the project's own tools through the runner profile in .aqv.yml.

The verifier never imports the project's test framework. It fills command
templates and reads standard outputs: JUnit XML for results, LCOV for coverage.
"""
import os
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from . import spec

AQV_DIR = str(Path(__file__).resolve().parent.parent)


def fill(template, **values):
    values.setdefault("python", shlex.quote(sys.executable))
    values.setdefault("extra", "")
    values.setdefault("filter", "")
    return template.format(**values)


def run(cmd, cwd, env=None, timeout=600):
    e = dict(os.environ)
    e["PYTHONPATH"] = AQV_DIR + os.pathsep + e.get("PYTHONPATH", "")
    e.update(env or {})
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as ex:
        return 124, f"timed out after {timeout}s: {ex}"


@dataclass
class TestCase:
    name: str
    classname: str
    outcome: str  # pass, fail, error, skipped
    message: str = ""

    @property
    def full_name(self):
        return f"{self.classname}::{self.name}" if self.classname else self.name


@dataclass
class SuiteRun:
    exit_code: int
    output: str
    cases: list
    broken: bool
    broken_reason: str = ""


def parse_junit(path):
    cases, suite_errors = [], []
    if not os.path.exists(path):
        return None, ["no JUnit report was written"]
    root = ET.parse(path).getroot()
    for tc in root.iter("testcase"):
        name, cls = tc.get("name", ""), tc.get("classname", "")
        err, fail, skip = tc.find("error"), tc.find("failure"), tc.find("skipped")
        if err is not None and not name:
            suite_errors.append(err.get("message") or "suite error")
            continue
        if err is not None:
            outcome, msg = "error", err.get("message") or ""
        elif fail is not None:
            outcome, msg = "fail", fail.get("message") or ""
        elif skip is not None:
            outcome, msg = "skipped", skip.get("message") or ""
        else:
            outcome, msg = "pass", ""
        # A test case named after a file rather than a function is a collection error.
        if outcome == "error" and "collection" in (msg or "").lower():
            suite_errors.append(f"{cls or name}: {msg}")
            continue
        cases.append(TestCase(name, cls, outcome, msg))
    return cases, suite_errors


def full_suite(cfg, repo, workdir, extra="", env=None):
    r = cfg["runner"]
    junit = os.path.join(workdir, "junit-full.xml")
    code, out = run(fill(r["test"], junit=junit, extra=extra), repo, env=env)
    cases, suite_errors = parse_junit(junit)
    broken = code in r.get("broken_exit_codes", []) or cases is None or bool(suite_errors)
    reason = "; ".join(suite_errors) if suite_errors else (f"runner exited {code}" if broken else "")
    return SuiteRun(code, out, cases or [], broken, reason)


def parse_lcov(path, repo):
    hits = {}
    current = None
    if not os.path.exists(path):
        return hits
    for line in open(path):
        line = line.strip()
        if line.startswith("SF:"):
            p = line[3:]
            current = os.path.relpath(p, repo) if os.path.isabs(p) else p
        elif line.startswith("DA:") and current:
            ln, count = line[3:].split(",")[:2]
            if int(count) > 0:
                hits.setdefault(current, set()).add(int(ln))
    return hits


def covered_lines(cfg, repo, filter_args, workdir, tag):
    """{file: {line}} executed while running only the tests selected by `filter_args`."""
    r = cfg["runner"]
    cov_data = os.path.join(workdir, f".coverage-{tag}")
    lcov = os.path.join(workdir, f"{tag}.lcov")
    code, out = run(fill(r["coverage"], filter=filter_args, cov_data=cov_data), repo)
    run(fill(r["coverage_report"], cov_data=cov_data, lcov=lcov), repo)
    return parse_lcov(lcov, repo), code


def filter_for(cfg, req_id):
    return fill(cfg["runner"]["filter"], id_underscore=spec.id_token(req_id), id=req_id)


def tests_pass(cfg, repo, filter_args, timeout=120):
    """True when the selected tests all pass. Used by mutation testing."""
    with tempfile.TemporaryDirectory() as tmp:
        code, _ = run(fill(cfg["runner"]["test"], filter=filter_args, junit=os.path.join(tmp, "j.xml")),
                      repo, timeout=timeout)
    return code == 0
