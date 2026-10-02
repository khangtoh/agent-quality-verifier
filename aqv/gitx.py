"""Thin git helpers. Everything the verifier knows about history comes through here."""
import fnmatch
import subprocess
from dataclasses import dataclass, field

SEP_FIELD = "\x1f"
SEP_RECORD = "\x1e"


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def git_ok(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0


def rev(repo, ref):
    return git(repo, "rev-parse", "--verify", ref + "^{commit}").strip()


def is_ancestor(repo, a, b):
    return git_ok(repo, "merge-base", "--is-ancestor", a, b)


def show(repo, sha, path):
    r = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def files_at(repo, sha):
    return git(repo, "ls-tree", "-r", "--name-only", sha).split("\n")


def matching(paths, patterns):
    return [p for p in paths if p and any(fnmatch.fnmatch(p, pat) for pat in patterns)]


def under(path, prefixes):
    return any(path.startswith(p) for p in prefixes)


@dataclass
class Commit:
    sha: str
    parents: list
    author_email: str
    subject: str
    signature: str
    refs: list
    coauthors: list
    files: list = field(default_factory=list)
    added: int = 0
    deleted: int = 0
    numstat: list = field(default_factory=list)

    @property
    def is_merge(self):
        return len(self.parents) > 1

    @property
    def short(self):
        return self.sha[:7]


def _split_trailer(value):
    out = []
    for part in value.replace("\n", ",").split(","):
        part = part.strip()
        if part:
            out.append(part)
    return out


def commits(repo, rev_range, agent_trailer="Co-Authored-By"):
    """Commits in `rev_range` (oldest first) with trailers, signature status and numstat."""
    fmt = SEP_FIELD.join([
        "%H", "%P", "%ae", "%s", "%G?",
        "%(trailers:key=Refs,valueonly,separator=%x2C)",
        f"%(trailers:key={agent_trailer},valueonly,separator=%x2C)",
    ]) + SEP_RECORD
    out = git(repo, "log", "--reverse", f"--format={fmt}", *rev_range)
    result = []
    for rec in out.split(SEP_RECORD):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, parents, email, subject, sig, refs, co = rec.split(SEP_FIELD)
        c = Commit(sha, parents.split(), email, subject, sig, _split_trailer(refs), _split_trailer(co))
        if not c.is_merge:
            for line in git(repo, "show", "--numstat", "--format=", "-M", sha).splitlines():
                parts = line.split("\t")
                if len(parts) != 3:
                    continue
                a, dl, path = parts
                if " => " in path:
                    path = path.split(" => ")[-1].replace("}", "").replace("{", "")
                a = 0 if a == "-" else int(a)
                dl = 0 if dl == "-" else int(dl)
                c.numstat.append((path, a, dl))
                c.files.append(path)
                c.added += a
                c.deleted += dl
        result.append(c)
    return result


def blame_owners(repo, path, ref="HEAD", comment_prefix="#"):
    """{commit_sha: [line_no]} for non-blank, non-comment lines of `path` at `ref`.

    -w ignores whitespace-only changes; -M and -C keep credit with the commit that
    wrote a line when the line is moved or copied, instead of the commit that moved it.
    """
    owners = {}
    out = git(repo, "blame", "-w", "-M", "-C", "--line-porcelain", ref, "--", path, check=False)
    sha, lineno = None, None
    for ln in out.splitlines():
        if len(ln) >= 41 and ln[40] == " " and all(ch in "0123456789abcdef" for ch in ln[:40]):
            parts = ln.split()
            sha, lineno = parts[0], int(parts[2])
        elif ln.startswith("\t") and sha:
            text = ln[1:].strip()
            if text and not text.startswith(comment_prefix):
                owners.setdefault(sha, []).append(lineno)
    return owners
