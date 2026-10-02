"""Requirements: parsing spec lines, hashing their text, and reading their history."""
import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from . import gitx

LINE = re.compile(r"^- \*\*(?P<id>[^*]+)\*\*(?: \((?P<tags>[^)]*)\))?: (?P<text>.+?)\s*$")
ID_FORMAT = re.compile(r"^AC-[a-z0-9]+(?:-[a-z0-9]+)*-\d{3}$")
API_OP = re.compile(r"^(GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)\s+(/\S*)$")


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def text_hash(text):
    return "sha256:" + hashlib.sha256(normalize(text).encode()).hexdigest()


def id_token(req_id):
    """The form an ID takes inside a test name: case-insensitive, with -, _ and spaces equal."""
    return re.sub(r"[-_ ]", "_", req_id).lower()


def mentions(name, req_id):
    """True when a test name contains the requirement ID, in any of the usual spellings:
    test_AC_auth_002_x, TestAC_auth_002X (Go), ac_auth_002_x (Rust), "AC-auth-002 x" (JS, Kotlin)."""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)  # camelCase boundary: TestAC → Test_AC
    norm = re.sub(r"[-_ ]", "_", name).lower()
    tok = id_token(req_id)
    return re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![0-9])", norm) is not None


@dataclass
class Requirement:
    id: str
    spec: str
    line: int
    tags: str
    text: str
    api_ops: list = field(default_factory=list)
    tag_errors: list = field(default_factory=list)

    @property
    def body(self):
        """Everything after the ID: tags and wording. Any change here makes results stale."""
        return (f"({self.tags}) " if self.tags else "") + self.text

    @property
    def hash(self):
        return text_hash(self.body)

    @property
    def retired(self):
        return self.text.lower().startswith("(retired)")


def parse(spec_path, content):
    reqs = []
    for i, raw in enumerate(content.splitlines(), 1):
        m = LINE.match(raw)
        if not m:
            continue
        r = Requirement(m["id"], spec_path, i, (m["tags"] or "").strip(), m["text"])
        if r.tags:
            for tag in r.tags.split(";"):
                key, _, val = tag.partition(":")
                if key.strip() != "api":
                    r.tag_errors.append(f"unknown tag '{key.strip()}'")
                    continue
                for op in val.split(","):
                    op = " ".join(op.split())
                    mo = API_OP.match(op)
                    if mo:
                        r.api_ops.append((mo[1], mo[2]))
                    else:
                        r.tag_errors.append(f"bad api operation '{op}'")
        reqs.append(r)
    return reqs


def at(repo, sha, patterns):
    """All requirements in spec files matching `patterns` at commit `sha`."""
    reqs = []
    for path in gitx.matching(gitx.files_at(repo, sha), patterns):
        reqs += parse(path, gitx.show(repo, sha, path) or "")
    return reqs


def history(repo, head, patterns):
    """[(sha, {id: Requirement})] for every commit that touched a spec file, oldest first."""
    shas = gitx.git(repo, "log", "--reverse", "--format=%H", head, "--", *patterns).split()
    out = []
    for sha in shas:
        first = {}
        for r in at(repo, sha, patterns):
            first.setdefault(r.id, r)  # a duplicate ID is T1's problem; keep the original line
        out.append((sha, first))
    return out


def word_diff(old, new):
    a, b = old.split(), new.split()
    parts = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "equal":
            continue
        o, n = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        parts.append(f"{o} → {n}" if o and n else (f"+{n}" if n else f"−{o}"))
    return ", ".join(parts)


def word_segments(old, new):
    """`new` split into [{"t": text, "m": changed}] against `old`, for underlining changed words."""
    a, b = old.split(), new.split()
    segs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if j2 > j1:
            segs.append({"t": " ".join(b[j1:j2]), "m": op != "equal"})
    return segs
