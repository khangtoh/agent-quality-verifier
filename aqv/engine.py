"""Runs every check against one repo state and returns results plus requirement statuses."""
import fnmatch
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config as cfgmod
from . import contract as oas
from . import gitx, mutate, runner, spec

TOOLS = Path(__file__).resolve().parent.parent / ".tools"

CHECKS = {
    "T1": "Requirement IDs are valid and never reused",
    "T2": "A code commit references the requirement",
    "T3": "The code from those commits still exists",
    "T4": "Tests are tagged to the requirement",
    "T5": "The tagged tests pass",
    "T6": "The tagged tests run the requirement's code",
    "T7": "The tagged tests fail when the code is broken",
    "T8": "Results reset when the requirement changes",
    "A1": "Every API requirement has an operation",
    "A2": "Every operation references a requirement",
    "A3": "The contract passes the lint rules",
    "A4": "No breaking change unless the spec changed",
    "A5": "The service serves exactly the documented routes",
    "A6": "Responses in the tagged tests match the contract",
    "A7": "The running service conforms to the contract",
    "H1": "Subjects follow Conventional Commits",
    "H2": "Code commits carry a Refs: trailer",
    "H3": "One requirement per code commit",
    "H4": "refactor and chore commits change no status",
    "H5": "Commit size under the limit",
    "H6": "Branch names follow the pattern",
    "H7": "Main is never rewritten",
    "H8": "The agent is named on its commits",
    "H9": "Commits are signed",
}
LIGHT = {"T2", "T3", "T4", "T5", "T6", "A1", "A5", "A6"}

# Status order: the first problem found decides what a requirement shows.
STATUS_ORDER = ["Missing", "Gone", "Untested", "Failing", "Unexercised", "Weak", "Contract", "Drift", "Sync"]
STATUS_BY_CHECK = {"T2": "Missing", "T3": "Gone", "T4": "Untested", "T5": "Failing", "T6": "Unexercised",
                   "T7": "Weak", "A1": "Contract", "A5": "Contract", "A6": "Contract", "A7": "Contract",
                   "T8": "Drift"}


@dataclass
class Result:
    check: str
    scope: str        # requirement, operation, commit, project
    subject: str
    verdict: str      # pass, fail, error, skip, not_covered
    summary: str
    details: dict = field(default_factory=dict)


class Engine:
    def __init__(self, repo, head="HEAD", base=None, skip=(), only=None, light=False, workdir=None,
                 head_branch=None):
        self.repo = str(Path(repo).resolve())
        self.head = gitx.rev(self.repo, head)
        if self.head != gitx.rev(self.repo, "HEAD"):
            raise SystemExit("check out the head commit first: tests run against the working tree")
        self.base_ref = base
        self.base = gitx.rev(self.repo, base) if base else None
        self.merge_base = (gitx.git(self.repo, "merge-base", self.base, self.head).strip()
                           if self.base else None)
        self.light = light
        wanted = set(only) if only else set(CHECKS)
        if light:
            wanted &= LIGHT
        self.wanted = wanted - set(skip)
        self.workdir = os.path.abspath(workdir or tempfile.mkdtemp(prefix="aqv-"))
        os.makedirs(self.workdir, exist_ok=True)
        self.head_branch = head_branch or gitx.git(self.repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        # Config comes from the base when there is one, so a PR can't loosen its own checks.
        self.cfg = cfgmod.load(gitx.show(self.repo, self.base or self.head, ".aqv.yml"))
        self.results = []

    # ------------------------------------------------------------------ helpers

    def add(self, check, scope, subject, verdict, summary, **details):
        if check in self.wanted:
            self.results.append(Result(check, scope, subject, verdict, summary, details))

    def want(self, *checks):
        return any(c in self.wanted for c in checks)

    def range_args(self):
        return [f"{self.base}..{self.head}"] if self.base else [self.head]

    def touches(self, commit, prefixes):
        return any(gitx.under(f, prefixes) for f in commit.files)

    # ------------------------------------------------------------------ load

    def load(self):
        c = self.cfg
        self.reqs = [r for r in spec.at(self.repo, self.head, c["specs"])]
        self.active = {}
        for r in self.reqs:
            if not r.retired and r.id not in self.active:
                self.active[r.id] = r
        self.contract_text = gitx.show(self.repo, self.head, c["contract"])
        self.contract = oas.load(self.contract_text)
        self.ops = oas.operations(self.contract)
        trailer = c["git"]["agent_trailer"]
        self.history = gitx.commits(self.repo, [self.head], trailer)
        self.range = gitx.commits(self.repo, self.range_args(), trailer)
        self.code_paths, self.test_paths = c["code_paths"], c["test_paths"]
        self.linked_code, self.linked_any = {}, {}
        for cm in self.history:
            if cm.is_merge:
                continue
            for rid in cm.refs:
                if self.touches(cm, self.code_paths):
                    self.linked_code.setdefault(rid, []).append(cm)
                if self.touches(cm, self.code_paths + self.test_paths):
                    self.linked_any.setdefault(rid, []).append(cm)

    # ------------------------------------------------------------------ run

    def run(self):
        self.load()
        if self.want("T1"):
            self.check_t1()
        needs_suite = self.want("T4", "T5", "T6", "T7", "A6")
        self.suite = None
        if needs_suite:
            self.run_suite()
        self.lines = {}
        for rid, req in self.active.items():
            self.check_requirement(rid, req)
        if self.want("T8"):
            self.check_t8()
        self.check_contract()
        self.check_history()
        return self.report()

    def run_suite(self):
        extra, env = "", {}
        self.capture_path = os.path.join(self.workdir, "capture.json")
        if self.cfg["api"].get("capture") == "pytest-testclient":
            extra = "-p aqv.pytest_capture"
            env["AQV_CAPTURE_OUT"] = self.capture_path
        self.suite = runner.full_suite(self.cfg, self.repo, self.workdir, extra=extra, env=env)
        self.import_only = None

    def import_lines(self):
        if self.import_only is None:
            sel = self.cfg["runner"].get("select_nothing", "")
            self.import_only, _ = runner.covered_lines(self.cfg, self.repo, sel, self.workdir, "import-only")
        return self.import_only

    # ------------------------------------------------------------------ T1

    def check_t1(self):
        c, problems = self.cfg, []
        registry_text = gitx.show(self.repo, self.head, c["ids_registry"])
        registry = set((registry_text or "").split())
        seen = {}
        for r in self.reqs:
            if not spec.ID_FORMAT.match(r.id):
                problems.append(f"{r.id}: ID doesn't match AC-<area>-<nnn>")
            if r.id in seen:
                problems.append(f"{r.id}: used twice ({seen[r.id]} and {r.spec}:{r.line})")
            seen.setdefault(r.id, f"{r.spec}:{r.line}")
            if r.id not in registry:
                problems.append(f"{r.id}: not in the ID registry {c['ids_registry']}")
            for e in r.tag_errors:
                problems.append(f"{r.id}: {e}")
        log = gitx.git(self.repo, "log", "-p", "--format=", self.head, "--", c["ids_registry"])
        for line in log.splitlines():
            if line.startswith("-") and not line.startswith("---") and line[1:].strip():
                problems.append(f"{line[1:].strip()}: removed from the ID registry (IDs are never removed)")
        ever = {}
        for sha, reqs in spec.history(self.repo, self.head, c["specs"]):
            for rid, r in reqs.items():
                if rid in ever and ever[rid].retired and not r.retired:
                    problems.append(f"{rid}: reused after it was retired")
                ever[rid] = r
        current = {r.id for r in self.reqs}
        for rid in ever:
            if rid not in current:
                problems.append(f"{rid}: deleted from the spec instead of marked (retired)")
        problems = sorted(set(problems))
        if problems:
            self.add("T1", "project", "spec", "fail", f"{len(problems)} ID problem(s): " + "; ".join(problems[:4]),
                     problems=problems)
        else:
            self.add("T1", "project", "spec", "pass", f"{len(self.reqs)} requirement IDs valid and registered")

    # ------------------------------------------------------------------ T2–T7, per requirement

    def check_requirement(self, rid, req):
        c = self.cfg
        code_commits = self.linked_code.get(rid, [])
        if code_commits:
            self.add("T2", "requirement", rid, "pass",
                     f"{len(code_commits)} commit(s) reference it: " + ", ".join(cm.short for cm in code_commits))
        else:
            self.add("T2", "requirement", rid, "fail", "No commit that changes code references it")

        linked = {}
        if code_commits:
            shas = {cm.sha for cm in code_commits}
            for path in gitx.files_at(self.repo, self.head):
                if not path or not gitx.under(path, self.code_paths):
                    continue
                owners = gitx.blame_owners(self.repo, path, self.head, c["runner"].get("comment_prefix", "#"))
                lines = sorted(l for sha, ls in owners.items() if sha in shas for l in ls)
                if lines:
                    linked[path] = lines
            n = sum(len(v) for v in linked.values())
            if n:
                self.add("T3", "requirement", rid, "pass", f"{n} line(s) from its commits still exist",
                         lines=linked)
            else:
                self.add("T3", "requirement", rid, "fail",
                         "Its commits are referenced, but none of their code lines exist now")
        else:
            self.add("T3", "requirement", rid, "skip", "No linked commits")
        self.lines[rid] = linked

        if self.suite is None:
            return
        tagged = [tc for tc in self.suite.cases if spec.mentions(tc.name, rid)]
        if self.suite.broken:
            self.add("T4", "requirement", rid, "error", f"The test suite failed to load: {self.suite.broken_reason}")
            self.add("T5", "requirement", rid, "error", f"The test suite failed to load: {self.suite.broken_reason}")
            for chk in ("T6", "T7"):
                self.add(chk, "requirement", rid, "skip", "Test suite failed to load")
            self.tagged = getattr(self, "tagged", {})
            self.tagged[rid] = []
            return
        self.tagged = getattr(self, "tagged", {})
        self.tagged[rid] = tagged
        if not tagged:
            self.add("T4", "requirement", rid, "fail", "No test name mentions it")
            for chk in ("T5", "T6", "T7"):
                self.add(chk, "requirement", rid, "skip", "No tagged tests")
            return
        self.add("T4", "requirement", rid, "pass", f"{len(tagged)} tagged test(s)",
                 tests=[tc.full_name for tc in tagged])
        bad = [tc for tc in tagged if tc.outcome != "pass"]
        if bad:
            self.add("T5", "requirement", rid, "fail",
                     f"{len(bad)} of {len(tagged)} tagged test(s) don't pass: " + ", ".join(tc.name for tc in bad[:3]),
                     failing=[{"test": tc.full_name, "outcome": tc.outcome, "message": tc.message[:300]} for tc in bad])
        else:
            self.add("T5", "requirement", rid, "pass", f"All {len(tagged)} tagged test(s) pass")

        if not self.want("T6", "T7"):
            return
        n_linked = sum(len(v) for v in linked.values())
        if not n_linked:
            self.add("T6", "requirement", rid, "skip", "No linked code lines")
            self.add("T7", "requirement", rid, "skip", "No linked code lines")
            return
        hits, _ = runner.covered_lines(self.cfg, self.repo, runner.filter_for(self.cfg, rid), self.workdir,
                                       spec.id_token(rid))
        base_hits = self.import_lines()
        executed = {}
        for path, lines in linked.items():
            run_lines = hits.get(path, set()) - base_hits.get(path, set())
            ex = sorted(set(lines) & run_lines)
            if ex:
                executed[path] = ex
        n_ex = sum(len(v) for v in executed.values())
        if n_ex:
            self.add("T6", "requirement", rid, "pass", f"Its tests run {n_ex} of its {n_linked} code line(s)",
                     executed=executed)
        else:
            self.add("T6", "requirement", rid, "fail",
                     f"Its tests run none of its {n_linked} code line(s) (import-time lines don't count)")
        if self.want("T7") and n_ex and self.in_mutation_scope(rid):
            self.check_t7(rid, executed)
        elif self.want("T7"):
            self.add("T7", "requirement", rid, "skip",
                     "Not changed in this range" if n_ex else "No executed lines to mutate")

    def in_mutation_scope(self, rid):
        if not self.base:
            return True
        return any(rid in cm.refs for cm in self.range if not cm.is_merge)

    def check_t7(self, rid, executed):
        m = self.cfg["mutation"]
        tmp = tempfile.mkdtemp(prefix="aqv-mut-", dir=self.workdir)
        work = os.path.join(tmp, "tree")
        shutil.copytree(self.repo, work, ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"))
        flt = runner.filter_for(self.cfg, rid)
        tried, killed, survivors = 0, 0, []
        for path in sorted(executed):
            fpath = os.path.join(work, path)
            original = open(fpath).read()
            src_lines = original.splitlines(True)
            for ln in executed[path]:
                for desc, new_line in mutate.mutants(src_lines[ln - 1]):
                    if tried >= m["max_mutants"]:
                        break
                    candidate = src_lines[:ln - 1] + [new_line if new_line.endswith("\n") else new_line + "\n"] + src_lines[ln:]
                    source = "".join(candidate)
                    if not mutate.compiles(source):
                        continue
                    tried += 1
                    with open(fpath, "w") as f:
                        f.write(source)
                    if runner.tests_pass(self.cfg, work, flt):
                        survivors.append(f"{path}:{ln} {desc}")
                    else:
                        killed += 1
                    with open(fpath, "w") as f:
                        f.write(original)
        shutil.rmtree(tmp, ignore_errors=True)
        if not tried:
            self.add("T7", "requirement", rid, "skip", "No mutants could be made from its lines")
            return
        ratio = killed / tried
        verdict = "pass" if ratio >= m["min_kill_ratio"] else "fail"
        self.add("T7", "requirement", rid, verdict,
                 f"Its tests caught {killed} of {tried} broken versions ({ratio:.0%}; needs {m['min_kill_ratio']:.0%})",
                 survivors=survivors)

    # ------------------------------------------------------------------ T8

    def check_t8(self):
        hist = spec.history(self.repo, self.head, self.cfg["specs"])
        for rid, req in self.active.items():
            impl = self.linked_any.get(rid, [])
            if not impl:
                self.add("T8", "requirement", rid, "skip", "Not implemented yet")
                continue
            changed_at, before, prev = None, None, None
            for sha, reqs in hist:
                r = reqs.get(rid)
                body = r.body if r else None
                if body is not None and body != prev:
                    changed_at, before = sha, prev
                prev = body
            if changed_at is None:
                self.add("T8", "requirement", rid, "skip", "Requirement not found in spec history")
                continue
            fresh = [cm for cm in impl if gitx.is_ancestor(self.repo, changed_at, cm.sha)]
            if fresh:
                self.add("T8", "requirement", rid, "pass",
                         f"Implemented or re-verified after its last wording change ({changed_at[:7]})")
            else:
                diff = spec.word_diff(before, req.body) if before else "new"
                self.add("T8", "requirement", rid, "fail",
                         f"Wording changed in {changed_at[:7]} ({diff}) after its last code or test commit",
                         changed_in=changed_at, change=diff)

    # ------------------------------------------------------------------ A1–A7

    def check_contract(self):
        api_reqs = {rid: r for rid, r in self.active.items() if r.api_ops}
        if self.contract is None:
            for rid in api_reqs:
                self.add("A1", "requirement", rid, "fail", "No contract file")
            return
        by_key = {op.key: op for op in self.ops}

        for rid, r in self.active.items():
            if not r.api_ops:
                self.add("A1", "requirement", rid, "skip", "Not an API requirement")
                continue
            problems = []
            for method, path in r.api_ops:
                op = by_key.get(f"{method} {path}")
                if op is None:
                    problems.append(f"{method} {path} is not in the contract")
                elif rid not in op.requirements:
                    problems.append(f"{method} {path} doesn't list {rid} in x-requirements")
            if problems:
                self.add("A1", "requirement", rid, "fail", "; ".join(problems))
            else:
                self.add("A1", "requirement", rid, "pass",
                         "Contract covers " + ", ".join(f"{m} {p}" for m, p in r.api_ops))

        for op in self.ops:
            unknown = [x for x in op.requirements if x not in self.active]
            if not op.requirements:
                self.add("A2", "operation", op.key, "fail", f"{op.key} references no requirement")
            elif unknown:
                self.add("A2", "operation", op.key, "fail",
                         f"{op.key} references unknown or retired requirement(s): {', '.join(unknown)}")
            else:
                self.add("A2", "operation", op.key, "pass", f"{op.key} → {', '.join(op.requirements)}")

        if self.want("A3"):
            self.check_a3()
        if self.want("A4"):
            self.check_a4()
        if self.want("A5"):
            self.check_a5(api_reqs)
        if self.want("A6"):
            self.check_a6(api_reqs)
        if self.want("A7"):
            self.check_a7(api_reqs)

    def tool(self, name, rel):
        env = os.environ.get(f"AQV_{name.upper()}")
        if env:
            return env
        p = TOOLS / rel
        return str(p) if p.exists() else shutil.which(name)

    def check_a3(self):
        spectral = self.tool("spectral", "node_modules/.bin/spectral")
        if not spectral:
            self.add("A3", "project", "contract", "not_covered", "Spectral is not installed")
            return
        ruleset = os.path.join(self.repo, ".spectral.yaml")
        args = [spectral, "lint", self.cfg["contract"], "-f", "json", "--fail-severity", "error", "--quiet"]
        if os.path.exists(ruleset):
            args += ["--ruleset", ruleset]
        r = subprocess.run(args, cwd=self.repo, capture_output=True, text=True)
        try:
            found = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            self.add("A3", "project", "contract", "error", f"Spectral failed: {(r.stderr or r.stdout)[:300]}")
            return
        errors = [f"{'.'.join(map(str, f.get('path', [])))}: {f.get('message')} ({f.get('code')})"
                  for f in found if f.get("severity") == 0]
        if errors:
            self.add("A3", "project", "contract", "fail", f"{len(errors)} lint error(s): " + "; ".join(errors[:3]),
                     errors=errors)
        else:
            self.add("A3", "project", "contract", "pass", "Contract passes the lint rules")

    def check_a4(self):
        if not self.base:
            self.add("A4", "project", "contract", "skip", "No base to compare against")
            return
        oasdiff = self.tool("oasdiff", "bin/oasdiff")
        if not oasdiff:
            self.add("A4", "project", "contract", "not_covered", "oasdiff is not installed")
            return
        old = gitx.show(self.repo, self.merge_base, self.cfg["contract"])
        if old is None:
            self.add("A4", "project", "contract", "skip", "No contract at the base")
            return
        base_file = os.path.join(self.workdir, "contract-base.yaml")
        open(base_file, "w").write(old)
        head_file = os.path.join(self.repo, self.cfg["contract"])
        r = subprocess.run([oasdiff, "breaking", base_file, head_file, "--fail-on", "ERR", "--format", "text"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            self.add("A4", "project", "contract", "pass", "No breaking API change")
            return
        changes = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        old_reqs = {x.id: x.hash for x in spec.at(self.repo, self.merge_base, self.cfg["specs"])}
        changed = [rid for rid, x in self.active.items() if old_reqs.get(rid) != x.hash]
        if changed:
            self.add("A4", "project", "contract", "pass",
                     f"Breaking change allowed: requirement(s) {', '.join(changed)} changed in the same range",
                     changes=changes)
        else:
            self.add("A4", "project", "contract", "fail",
                     "Breaking API change with no requirement change: " + "; ".join(changes[:3]), changes=changes)

    def check_a5(self, api_reqs):
        cmd = self.cfg["api"].get("openapi_from_code")
        if not cmd:
            self.add("A5", "project", "routes", "not_covered", "No way to list the service's routes for this stack")
            return
        code, out = runner.run(runner.fill(cmd), self.repo)
        try:
            served_doc = json.loads(out.strip().splitlines()[-1])
        except Exception:
            self.add("A5", "project", "routes", "error", f"Couldn't read routes from the code: {out[-300:]}")
            return
        served = {op.key for op in oas.operations(served_doc)}
        documented = {op.key for op in self.ops}
        for key in sorted(served - documented):
            self.add("A5", "operation", key, "fail", f"{key} is served but not in the contract")
        for rid, r in api_reqs.items():
            missing = [f"{m} {p}" for m, p in r.api_ops if f"{m} {p}" in documented and f"{m} {p}" not in served]
            if missing:
                self.add("A5", "requirement", rid, "fail", "Documented but not served: " + ", ".join(missing))
            else:
                self.add("A5", "requirement", rid, "pass", "Its operations are served")

    def check_a6(self, api_reqs):
        if self.cfg["api"].get("capture") != "pytest-testclient":
            for rid in api_reqs:
                self.add("A6", "requirement", rid, "not_covered", "No test-traffic adapter for this framework")
            return
        if self.suite is None or self.suite.broken:
            for rid in api_reqs:
                self.add("A6", "requirement", rid, "skip", "Test suite didn't run")
            return
        calls = json.load(open(self.capture_path)) if os.path.exists(self.capture_path) else []
        for rid, r in api_reqs.items():
            names = {tc.name for tc in self.tagged.get(rid, [])}
            mine = [c for c in calls if c["test"] in names]
            own_ops = {f"{m} {p}" for m, p in r.api_ops}
            problems, hit = [], set()
            for c in mine:
                op = oas.find(self.ops, c["method"], c["path"])
                if op is None:
                    problems.append(f"{c['test']} called {c['method']} {c['path']}, which the contract doesn't have")
                    continue
                hit.add(op.key)
                for p in oas.check_response(self.contract, op, c["status"], c["body"]):
                    problems.append(f"{c['test']}: {p}")
            problems = sorted(set(problems))
            if problems:
                self.add("A6", "requirement", rid, "fail", "; ".join(problems[:3]), violations=problems)
            elif not (own_ops & hit):
                self.add("A6", "requirement", rid, "fail",
                         f"No tagged test calls {', '.join(sorted(own_ops))}")
            else:
                self.add("A6", "requirement", rid, "pass", f"{len(mine)} call(s) from tagged tests match the contract")

    def check_a7(self, api_reqs):
        serve = self.cfg["api"].get("serve")
        st = self.tool("schemathesis", "../.venv/bin/schemathesis")
        if not serve or not st:
            self.add("A7", "project", "service", "not_covered", "No way to start the service or Schemathesis missing")
            return
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.path.join(self.repo, "src"))
        proc = subprocess.Popen(runner.fill(serve, port=port), shell=True, cwd=self.repo, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            for _ in range(100):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                self.add("A7", "project", "service", "error", "The service didn't start")
                return
            junit = os.path.join(self.workdir, "schemathesis.xml")
            args = [st, "run", os.path.join(self.repo, self.cfg["contract"]), "--url", f"http://127.0.0.1:{port}",
                    "--mode", "positive", "--seed", "1", "--max-examples", "30",
                    "--checks", "not_a_server_error,status_code_conformance,response_schema_conformance",
                    "--report", "junit", "--report-junit-path", junit, "--no-shrink", "--warnings", "off"]
            r = subprocess.run(args, capture_output=True, text=True, timeout=300, cwd=self.workdir)
        finally:
            try:
                os.killpg(proc.pid, 15)
            except ProcessLookupError:
                pass
        failed_ops = {}
        if os.path.exists(junit):
            import xml.etree.ElementTree as ET
            for tc in ET.parse(junit).getroot().iter("testcase"):
                f = tc.find("failure")
                if f is None:
                    f = tc.find("error")
                if f is not None:
                    name = tc.get("name", "")
                    failed_ops[name] = ((f.get("message") or "") + " " + (f.text or "")).strip()[:400]
        elif r.returncode:
            self.add("A7", "project", "service", "error", f"Schemathesis didn't run: {(r.stdout + r.stderr)[-300:]}")
            return
        bad = {op.key: msg for op in self.ops for name, msg in failed_ops.items()
               if name.startswith(op.key) or name == op.key}
        for op in self.ops:
            if op.key in bad:
                self.add("A7", "operation", op.key, "fail",
                         f"{op.key} failed generated requests: {first_line(bad[op.key])}", output=bad[op.key])
        for rid, r in api_reqs.items():
            failing = [f"{m} {p}" for m, p in r.api_ops if f"{m} {p}" in bad]
            if failing:
                self.add("A7", "requirement", rid, "fail", "Generated requests failed on " + ", ".join(failing))
            else:
                self.add("A7", "requirement", rid, "pass", "Generated requests got documented responses")

    # ------------------------------------------------------------------ H1–H9

    def check_history(self):
        g = self.cfg["git"]
        rng = self.range
        plain = [cm for cm in rng if not cm.is_merge]
        code = [cm for cm in plain if self.touches(cm, self.code_paths)]

        def verdict(check, offenders, ok_msg, bad_msg):
            if offenders:
                self.add(check, "project", "history", "fail", bad_msg + ": " + "; ".join(offenders[:4]),
                         offenders=offenders)
            else:
                self.add(check, "project", "history", "pass", ok_msg)

        if self.want("H1"):
            rx = re.compile(cfgmod.CONVENTIONAL)
            verdict("H1", [f"{cm.short} '{cm.subject}'" for cm in plain if not rx.match(cm.subject)],
                    f"{len(plain)} commit subject(s) follow Conventional Commits", "Not Conventional Commits")
        if self.want("H2"):
            off = []
            for cm in code:
                ctype = cm.subject.split("(")[0].split(":")[0].rstrip("!")
                if not cm.refs:
                    off.append(f"{cm.short} has no Refs: trailer")
                elif cm.refs == ["none"] and ctype in cfgmod.NO_BEHAVIOR_TYPES:
                    continue
                else:
                    bad = [x for x in cm.refs if x not in self.active]
                    if bad:
                        off.append(f"{cm.short} refers to unknown requirement(s) {', '.join(bad)}")
            verdict("H2", off, f"{len(code)} code commit(s) reference a requirement", "Missing or bad Refs")
        if self.want("H3"):
            verdict("H3", [f"{cm.short} cites {', '.join(cm.refs)}" for cm in code if len(cm.refs) > 1],
                    "Each code commit serves one requirement", "Several requirements in one commit")
        if self.want("H4"):
            self.check_h4(plain)
        if self.want("H5"):
            limit, off = g["max_commit_lines"], []
            for cm in plain:
                n = sum(a + d for p, a, d in cm.numstat
                        if not any(fnmatch.fnmatch(p, pat) for pat in g["size_exclude"]))
                if n > limit:
                    off.append(f"{cm.short} changes {n} lines")
            verdict("H5", off, f"Every commit changes at most {limit} lines", f"Commits over {limit} lines")
        if self.want("H6"):
            rx = re.compile(g["branch_pattern"])
            names = []
            if self.base and self.base != self.head:
                names.append(self.head_branch)
            for cm in rng:
                m = re.match(r"^Merge branch '([^']+)'", cm.subject)
                if cm.is_merge and m:
                    names.append(m.group(1))
            verdict("H6", [n for n in names if not rx.match(n)],
                    f"{len(names)} branch name(s) follow the pattern", "Branch names off pattern")
        if self.want("H7"):
            ref = g["verified_ref"]
            target = self.base or self.head
            if not gitx.git_ok(self.repo, "rev-parse", "--verify", ref):
                self.add("H7", "project", "history", "not_covered", f"No {ref} recorded yet")
            elif gitx.is_ancestor(self.repo, gitx.rev(self.repo, ref), target):
                self.add("H7", "project", "history", "pass", f"Last verified commit is still in history")
            else:
                self.add("H7", "project", "history", "fail",
                         f"Last verified commit {gitx.rev(self.repo, ref)[:7]} is no longer in main's history")
        if self.want("H8"):
            humans = set(g["humans"])
            verdict("H8", [f"{cm.short} by {cm.author_email} has no {g['agent_trailer']} trailer"
                           for cm in plain if cm.author_email not in humans and not cm.coauthors],
                    "Every agent commit names the agent", "Agent commits without attribution")
        if self.want("H9"):
            verdict("H9", [f"{cm.short} signature '{cm.signature}'" for cm in rng if cm.signature not in ("G", "U")],
                    f"{len(rng)} commit(s) carry good signatures", "Unsigned or unverifiable commits")

    def check_h4(self, plain):
        cands = [cm for cm in plain
                 if cm.subject.split("(")[0].split(":")[0].rstrip("!") in cfgmod.NO_BEHAVIOR_TYPES
                 and self.touches(cm, self.code_paths + self.test_paths)]
        if not cands:
            self.add("H4", "project", "history", "pass", "No refactor or chore commits change code")
            return
        offenders = []
        for cm in cands:
            before = light_statuses(self.repo, cm.parents[0], self.workdir)
            after = light_statuses(self.repo, cm.sha, self.workdir)
            changed = [f"{rid} {before.get(rid)} → {after.get(rid)}" for rid in sorted(set(before) | set(after))
                       if before.get(rid) != after.get(rid)]
            if changed:
                offenders.append(f"{cm.short} '{cm.subject}' changed {', '.join(changed)}")
        if offenders:
            self.add("H4", "project", "history", "fail", "Behavior changed in no-behavior commits: " + "; ".join(offenders),
                     offenders=offenders)
        else:
            self.add("H4", "project", "history", "pass",
                     f"{len(cands)} refactor/chore commit(s) left every status unchanged")

    # ------------------------------------------------------------------ statuses and report

    def statuses(self):
        out = {}
        for rid in self.active:
            failing = {r.check for r in self.results if r.scope == "requirement" and r.subject == rid
                       and r.verdict in ("fail", "error")}
            # A suite that won't load can't list tagged tests; show it as Failing, not Untested.
            if any(r.check == "T4" and r.subject == rid and r.verdict == "error" for r in self.results):
                failing.discard("T4")
                failing.add("T5")
            status = "Sync"
            for name in STATUS_ORDER:
                if any(STATUS_BY_CHECK.get(chk) == name for chk in failing):
                    status = name
                    break
            out[rid] = status
        return out

    def report(self):
        statuses = self.statuses()
        summary = {}
        for chk in CHECKS:
            rs = [r for r in self.results if r.check == chk]
            if chk not in self.wanted:
                summary[chk] = "not_run"
            elif not rs:
                summary[chk] = "skip"
            elif any(r.verdict == "fail" for r in rs):
                summary[chk] = "fail"
            elif any(r.verdict == "error" for r in rs):
                summary[chk] = "error"
            elif any(r.verdict == "pass" for r in rs):
                summary[chk] = "pass"
            elif any(r.verdict == "not_covered" for r in rs):
                summary[chk] = "not_covered"
            else:
                summary[chk] = "skip"
        not_covered = sorted(c for c, v in summary.items() if v == "not_covered")
        return {
            "repo": self.repo,
            "head": self.head,
            "base": self.base,
            "head_branch": self.head_branch,
            "checks": summary,
            "requirements": [
                {"id": rid, "text": r.text, "api": [f"{m} {p}" for m, p in r.api_ops], "status": statuses[rid],
                 "not_covered": not_covered,
                 "failing_checks": sorted({x.check for x in self.results if x.subject == rid
                                           and x.verdict in ("fail", "error")})}
                for rid, r in self.active.items()],
            "results": [asdict(r) for r in self.results],
            "scorecard": self.scorecard(),
        }

    def scorecard(self):
        agents = {}
        failing_commits = {}
        for r in self.results:
            if r.check.startswith("H") and r.verdict == "fail":
                for off in r.details.get("offenders", []):
                    failing_commits.setdefault(off.split(" ")[0], set()).add(r.check)
        humans = set(self.cfg["git"]["humans"])
        for cm in self.range:
            if cm.is_merge or cm.author_email in humans:
                continue
            who = (cm.coauthors[0] if cm.coauthors else cm.author_email)
            a = agents.setdefault(who, {"commits": 0, "commits_breaking_git_rules": 0, "requirements_referenced": set()})
            a["commits"] += 1
            if cm.short in failing_commits:
                a["commits_breaking_git_rules"] += 1
            a["requirements_referenced"].update(cm.refs)
        for a in agents.values():
            a["requirements_referenced"] = sorted(a["requirements_referenced"])
            a["git_rule_pass_rate"] = round(1 - a["commits_breaking_git_rules"] / a["commits"], 2) if a["commits"] else None
        return agents


def first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


_LIGHT_CACHE = {}


def light_statuses(repo, sha, workdir):
    """Requirement statuses at `sha`, using only the fast checks. Used by H4."""
    key = (repo, sha)
    if key in _LIGHT_CACHE:
        return _LIGHT_CACHE[key]
    wt = tempfile.mkdtemp(prefix="aqv-wt-", dir=workdir)
    gitx.git(repo, "worktree", "add", "--detach", "-f", wt, sha)
    try:
        eng = Engine(wt, head=sha, light=True, workdir=os.path.join(wt, ".aqv-work"))
        report = eng.run()
        result = {r["id"]: r["status"] for r in report["requirements"]}
    finally:
        gitx.git(repo, "worktree", "remove", "--force", wt, check=False)
    _LIGHT_CACHE[key] = result
    return result
