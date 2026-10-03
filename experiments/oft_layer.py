"""Adds IntentBond/OpenFastTrace notation to the Python demo repo, the way an agent
following IntentBond's skill would: requirements as OFT items, `[impl->req~...]`
beside the code, named `utest` tags and pytest `oft_id` markers beside the tests.

`adopt` runs once on the baseline. `update` runs after each scenario and tags only
what the scenario added (new requirements, new tests, code for a requirement that
has no implementation tag yet), so the attack itself is left untouched.
"""
import json
import re
import subprocess
from pathlib import Path

REQ_LINE = re.compile(r"^- \*\*AC-(\w+)-(\d+)\*\*(?: \([^)]*\))?: (.+)$")
TEST_DEF = re.compile(r"^def (test_AC_(\w+?)_(\d+)_\w+)\(")
MARKER = "@pytest.mark.oft_id("

# Where a careful agent puts implementation tags in the baseline: (file, anchor line, requirement).
IMPL_ANCHORS = [
    ("src/app/auth.py", "def hash_password(", "auth-006"),
    ("src/app/auth.py", "def is_expired(", "auth-003"),
    ("src/app/auth.py", "    def add_account(", "auth-006"),
    ("src/app/auth.py", "    def sign_in(", "auth-001"),
    ("src/app/auth.py", "        if email in self.locked:", "auth-002"),
    ("src/app/auth.py", "    def request_reset(", "auth-004"),
    ("src/app/main.py", '    @app.post("/login")', "auth-001"),
    ("src/app/main.py", '    @app.get("/session")', "auth-003"),
    ("src/app/main.py", '    @app.post("/password-reset"', "auth-004"),
    ("src/app/main.py", '    @app.post("/password-reset"', "auth-005"),
]

CONFTEST_HOOK = '''

def pytest_collection_modifyitems(items):
    for item in items:
        for marker in item.iter_markers(name="oft_id"):
            for identifier in marker.args:
                item.user_properties.append(("oft_id", identifier))
'''


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def requirements(repo):
    """[(oft name, text)] in spec order, duplicates kept."""
    out = []
    for line in (Path(repo) / "specs/auth.md").read_text().splitlines():
        m = REQ_LINE.match(line)
        if m:
            out.append((f"{m.group(1)}-{m.group(2)}", m.group(3)))
    return out


def write_spec(repo, base_texts):
    """Writes specs/auth.oft.md. A requirement whose wording differs from the base gets
    revision 2: the person who changed it follows OFT's revision rule."""
    revs, parts = {}, ["# Auth service requirements\n"]
    for name, text in requirements(repo):
        rev = 2 if name in base_texts and base_texts[name] != text else 1
        revs.setdefault(name, rev)
        parts.append(f"### {name}\n`req~{name}~{rev}`\n\n{text}\n\nNeeds: impl, utest\n")
    (Path(repo) / "specs/auth.oft.md").write_text("\n".join(parts))
    return revs


def tag_tests(repo, revs):
    for path in sorted((Path(repo) / "tests").glob("test_*.py")):
        lines = path.read_text().splitlines()
        out, changed = [], False
        for i, line in enumerate(lines):
            m = TEST_DEF.match(line)
            if m and not (i and lines[i - 1].startswith(MARKER)):
                fn, area, num = m.groups()
                req = f"{area}-{num}"
                art = "ac-" + fn[len("test_AC_"):].replace("_", "-").lower()
                out.append(f"# [utest~{art}~1->req~{req}~{revs.get(req, 1)}]")
                out.append(f'{MARKER}"utest~{art}~1")')
                changed = True
            out.append(line)
        if changed:
            if not any(l.strip() == "import pytest" for l in out):
                out.insert(0, "import pytest\n")
            path.write_text("\n".join(out) + "\n")


def insert_before(path, anchor, tag):
    text = path.read_text()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(anchor):
            indent = line[: len(line) - len(line.lstrip())]
            lines.insert(i, f"{indent}{tag}")
            path.write_text("\n".join(lines) + "\n")
            return
    raise AssertionError(f"{path}: anchor not found: {anchor!r}")


def adopt(repo, scope=None):
    repo = Path(repo)
    revs = write_spec(repo, {})
    for file, anchor, req in IMPL_ANCHORS:
        insert_before(repo / file, anchor, f"# [impl->req~{req}~1]")
    tag_tests(repo, revs)
    conftest = repo / "tests/conftest.py"
    conftest.write_text(conftest.read_text() + CONFTEST_HOOK)
    py = repo / "pyproject.toml"
    py.write_text(py.read_text() + 'junit_family = "xunit1"\nmarkers = ["oft_id: OpenFastTrace test artifact"]\n')
    if scope is not None:
        (repo / "scope.json").write_text(json.dumps(scope, indent=2) + "\n")


def update(repo, base, bump=True):
    """Tags what a scenario added, as the agent would before opening its pull request.
    bump=False models a spec edit where nobody raises the OFT revision."""
    repo = Path(repo)
    base_texts = dict(requirements_at(repo, base)) if bump else {}
    revs = write_spec(repo, base_texts)
    tag_tests(repo, revs)
    src_text = "".join(p.read_text() for p in (repo / "src").rglob("*.py"))
    for sha in git(repo, "rev-list", "--reverse", f"{base}..HEAD").split():
        refs = re.findall(r"^Refs: AC-(\w+)-(\d+)\s*$", git(repo, "show", "-s", "--format=%B", sha), re.M)
        if len(refs) != 1:
            continue
        req = f"{refs[0][0]}-{refs[0][1]}"
        if f"impl->req~{req}~" in src_text:
            continue
        for path in git(repo, "diff", "--name-only", f"{sha}^", sha, "--", "src").split():
            first = first_added_line(repo, sha, path)
            if first is None or not (repo / path).exists():
                continue
            lines = (repo / path).read_text().splitlines()
            anchor = lines[first - 1]
            indent = anchor[: len(anchor) - len(anchor.lstrip())]
            lines.insert(first - 1, f"{indent}# [impl->req~{req}~{revs.get(req, 1)}]")
            (repo / path).write_text("\n".join(lines) + "\n")
            src_text += f"impl->req~{req}~"
            break


def requirements_at(repo, rev):
    text = git(repo, "show", f"{rev}:specs/auth.md")
    out = []
    for line in text.splitlines():
        m = REQ_LINE.match(line)
        if m:
            out.append((f"{m.group(1)}-{m.group(2)}", m.group(3)))
    return out


def first_added_line(repo, sha, path):
    for line in git(repo, "show", "-U0", "--format=", sha, "--", path).splitlines():
        m = re.match(r"^@@ -\S+ \+(\d+)", line)
        if m:
            return int(m.group(1))
    return None
