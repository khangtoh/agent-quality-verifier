"""Runs the project's own tools through the runner profile in .aqv.yml.

The verifier never imports the project's test framework. It fills command
templates and reads standard outputs: JUnit XML for results, and LCOV, Go cover
profiles or JaCoCo XML for coverage.
"""
import glob
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


def placeholders(req_id=None):
    v = {"python": shlex.quote(sys.executable), "aqv": shlex.quote(AQV_DIR), "extra": "", "filter": ""}
    if req_id:
        v.update(id=req_id, id_underscore=spec.id_token(req_id), id_underscore_raw=req_id.replace("-", "_"))
    return v


def fill(template, **values):
    v = placeholders()
    v.update(values)
    return template.format(**v)


def run(cmd, cwd, env=None, timeout=900):
    e = dict(os.environ)
    e["PYTHONPATH"] = AQV_DIR + os.pathsep + e.get("PYTHONPATH", "")
    e.update(env or {})
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout,
                           start_new_session=True)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as ex:
        return 124, f"timed out after {timeout}s: {ex}"


def profile_env(cfg, repo):
    return {k: str(v).format(repo=repo) for k, v in (cfg["runner"].get("env") or {}).items()}


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


def parse_junit(paths):
    """Test cases from one or more JUnit XML files. None when no report exists."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return None, ["no JUnit report was written"]
    cases, suite_errors = [], []
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            suite_errors.append(f"unreadable JUnit report {os.path.basename(path)}: {e}")
            continue
        for tc in root.iter("testcase"):
            name, cls = tc.get("name", ""), tc.get("classname", "")
            err, fail, skip = tc.find("error"), tc.find("failure"), tc.find("skipped")
            if err is not None:
                outcome, msg = "error", " ".join(x for x in (err.get("message"), err.text) if x)
            elif fail is not None:
                outcome, msg = "fail", " ".join(x for x in (fail.get("message"), fail.text) if x)
            elif skip is not None:
                outcome, msg = "skipped", skip.get("message") or ""
            else:
                outcome, msg = "pass", ""
            # Collection and build failures show up as cases that aren't real tests:
            # pytest "collection" errors, gotestsum's "TestMain ... [build failed]".
            low = msg.lower()
            if outcome in ("error", "fail") and (not name or "collection" in low or "[build failed]" in low
                                                  or "[setup failed]" in low):
                suite_errors.append(f"{cls or name}: {msg[:200]}")
                continue
            cases.append(TestCase(name, cls, outcome, msg))
    # Runners that run tests in parallel (cargo-nextest, Gradle forks) write them in the
    # order they finished; sort so the same commit always gives the same report.
    cases.sort(key=lambda c: (c.classname, c.name))
    return cases, suite_errors


def junit_paths(cfg, repo, junit):
    jdir = cfg["runner"].get("junit_dir")
    if jdir:
        return sorted(glob.glob(os.path.join(repo, jdir, "**", "*.xml"), recursive=True))
    return [junit]


def clear_junit(cfg, repo):
    jdir = cfg["runner"].get("junit_dir")
    if jdir:
        for p in glob.glob(os.path.join(repo, jdir, "**", "*.xml"), recursive=True):
            os.remove(p)


def full_suite(cfg, repo, workdir, extra="", env=None):
    r = cfg["runner"]
    junit = os.path.join(workdir, "junit-full.xml")
    if os.path.exists(junit):
        os.remove(junit)
    clear_junit(cfg, repo)
    e = profile_env(cfg, repo)
    e.update(env or {})
    code, out = run(fill(r["test"], junit=junit, extra=extra), repo, env=e)
    cases, suite_errors = parse_junit(junit_paths(cfg, repo, junit))
    # A non-zero exit that no failing test explains means part of the suite didn't run
    # (for example a Go package that failed to compile, which JUnit lists as 0 tests).
    unexplained = code != 0 and not any(c.outcome in ("fail", "error") for c in (cases or []))
    broken = (code in r.get("broken_exit_codes", []) or cases is None or bool(suite_errors) or unexplained)
    reason = "; ".join(suite_errors) if suite_errors else (f"runner exited {code}" if broken else "")
    if broken and not suite_errors:
        tail = [l for l in out.strip().splitlines() if l.strip()][-3:]
        reason += (": " + " | ".join(tail)[:300]) if tail else ""
    return SuiteRun(code, out, cases or [], broken, reason)


# ---------------------------------------------------------------------------- coverage


def _rel(path, repo):
    if os.path.isabs(path):
        try:
            return os.path.relpath(os.path.realpath(path), os.path.realpath(repo))
        except ValueError:
            return path
    return path


def parse_lcov(path, repo):
    hits, current = {}, None
    for line in open(path):
        line = line.strip()
        if line.startswith("SF:"):
            current = _rel(line[3:], repo)
        elif line.startswith("DA:") and current:
            ln, count = line[3:].split(",")[:2]
            if int(float(count)) > 0:
                hits.setdefault(current, set()).add(int(ln))
    return hits


def parse_gocover(path, repo):
    """Go cover profile: `file.go:startLine.col,endLine.col numStmts count` per block."""
    module = ""
    gomod = os.path.join(repo, "go.mod")
    if os.path.exists(gomod):
        for line in open(gomod):
            if line.startswith("module "):
                module = line.split()[1].strip()
                break
    hits = {}
    for line in open(path):
        if line.startswith("mode:") or not line.strip():
            continue
        loc, _, count = line.rsplit(" ", 2)
        if int(count) == 0:
            continue
        fname, rng = loc.rsplit(":", 1)
        start, end = rng.split(",")
        if module and fname.startswith(module + "/"):
            fname = fname[len(module) + 1:]
        lines = range(int(start.split(".")[0]), int(end.split(".")[0]) + 1)
        hits.setdefault(_rel(fname, repo), set()).update(lines)
    return hits


def parse_jacoco(path, repo, roots):
    hits = {}
    root = ET.parse(path).getroot()
    for pkg in root.iter("package"):
        pname = pkg.get("name", "")
        for sf in pkg.iter("sourcefile"):
            rel = None
            for r in roots:
                cand = os.path.join(r, pname, sf.get("name"))
                if os.path.exists(os.path.join(repo, cand)):
                    rel = cand
                    break
            if rel is None:
                continue
            for ln in sf.iter("line"):
                if int(ln.get("ci", "0")) > 0:
                    hits.setdefault(rel, set()).add(int(ln.get("nr")))
    return hits


def read_coverage(cfg, repo, path):
    if not os.path.exists(path):
        return {}
    fmt = cfg["runner"].get("coverage_format", "lcov")
    if fmt == "gocover":
        return parse_gocover(path, repo)
    if fmt == "jacoco":
        return parse_jacoco(path, repo, cfg["runner"].get("coverage_source_roots", ["src/main/kotlin"]))
    return parse_lcov(path, repo)


def covered_lines(cfg, repo, filter_args, workdir, tag):
    """{file: {line}} executed while running only the tests selected by `filter_args`."""
    r = cfg["runner"]
    cov_data = os.path.join(workdir, f".coverage-{tag}")
    lcov = os.path.join(workdir, f"{tag}.cov")
    out_path = fill(r.get("coverage_out", "{lcov}"), lcov=lcov, cov_data=cov_data)
    if not os.path.isabs(out_path):
        out_path = os.path.join(repo, out_path)
    if os.path.exists(out_path):
        os.remove(out_path)
    env = profile_env(cfg, repo)
    code, out = run(fill(r["coverage"], filter=filter_args, cov_data=cov_data, lcov=lcov,
                         junit=os.path.join(workdir, f"junit-{tag}.xml")), repo, env=env)
    if r.get("coverage_report"):
        run(fill(r["coverage_report"], cov_data=cov_data, lcov=lcov), repo, env=env)
    return read_coverage(cfg, repo, out_path), code


def filter_for(cfg, req_id):
    return fill(cfg["runner"]["filter"], **placeholders(req_id))


def run_selected(cfg, repo, filter_args, timeout=900):
    """Exit code of the selected tests. Used by mutation testing."""
    with tempfile.TemporaryDirectory() as tmp:
        code, _ = run(fill(cfg["runner"]["test"], filter=filter_args, junit=os.path.join(tmp, "j.xml")),
                      repo, env=profile_env(cfg, repo), timeout=timeout)
    return code


def tests_pass(cfg, repo, filter_args, timeout=900):
    return run_selected(cfg, repo, filter_args, timeout) == 0
