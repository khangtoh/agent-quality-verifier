"""T7: small, deterministic line mutations.

Each mutant changes one line written for the requirement. If the requirement's
own tests still pass with the change, the mutant "survived": the tests run that
line but don't check what it does. Two operator families cover the demo's
languages: Python, and C-style syntax (JavaScript, TypeScript, Go, Rust, Kotlin).
Mutants that don't compile are discarded, never counted as caught.
"""
import re

PY_SWAPS = [
    (r">=", ">"), (r"<=", "<"), (r"(?<![<>=!])>(?!=)", ">="), (r"(?<![<>=!-])<(?!=)", "<="),
    (r"==", "!="), (r"!=", "=="),
    (r"\bnot in\b", "in"), (r"(?<!not )\bin\b(?=\s)", "not in"),
    (r"\bTrue\b", "False"), (r"\bFalse\b", "True"),
    (r"\band\b", "or"), (r"\bor\b", "and"),
    (r"(?<![\w.])\+(?![+=])", "-"), (r"(?<![\w.eE])-(?![-=>])", "+"),
]
C_SWAPS = [
    (r"===", "!=="), (r"!==", "==="),
    (r"(?<![=!<>])>=", ">"), (r"(?<![=<])<=(?!>)", "<"),
    (r"(?<![-=<>!])>(?![=>])", ">="), (r"(?<![<!])<(?![=<-])", "<="),
    (r"(?<![=!<>])==(?!=)", "!="), (r"!=(?!=)", "=="),
    (r"&&", "||"), (r"\|\|", "&&"),
    (r"\btrue\b", "false"), (r"\bfalse\b", "true"),
    (r"(?<![\w.+])\+(?![+=])", "-"), (r"(?<![\w.eE-])-(?![-=>])", "+"),
]
PY_SKIP = ("def ", "class ", "if ", "elif ", "else", "for ", "while ", "try", "except", "finally",
           "with ", "@", "async def ", "import ", "from ", "return", '"""', "'''")
C_SKIP = ("import ", "package ", "use ", "mod ", "#[", "@", "func ", "fun ", "fn ", "pub fn ", "class ",
          "interface ", "type ", "struct ", "impl ", "export ", "}", "{", "//", "/*", "*")
INT = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def _mask(line):
    """Blank out string literals so swaps never edit text inside quotes."""
    return re.sub(r"(\"(?:\\.|[^\"\\])*\"|`[^`]*`|'(?:\\.|[^'\\])')", lambda m: " " * len(m.group(0)), line)


def mutants(line, family="python"):
    """[(description, new_line)] for one source line, in a fixed order."""
    out = []
    stripped = line.strip()
    comment = "#" if family == "python" else "//"
    if not stripped or stripped.startswith(comment):
        return out
    if family != "python" and (stripped.startswith(("import ", "package ", "use ")) or "require(" in stripped):
        return out
    indent = line[: len(line) - len(line.lstrip())]
    masked = _mask(line)
    start = len(indent)
    for pattern, repl in (PY_SWAPS if family == "python" else C_SWAPS):
        m = re.search(pattern, masked[start:])
        if m:
            s, e = m.start() + start, m.end() + start
            out.append((f"'{line[s:e]}' → '{repl}'", line[:s] + repl + line[e:]))
    m = INT.search(masked[start:])
    if m:
        s, e = m.start() + start, m.end() + start
        n = int(line[s:e])
        out.append((f"{n} → {n + 1}", line[:s] + str(n + 1) + line[e:]))
    if family == "python":
        if stripped.startswith("return ") and stripped != "return None":
            out.append(("return value → None", f"{indent}return None\n"))
        if not stripped.startswith(PY_SKIP) and not stripped.endswith((":", ",", "(", "[", "{", "\\")):
            out.append(("line removed", f"{indent}pass\n"))
    else:
        if not stripped.startswith(C_SKIP) and not stripped.endswith(("{", ",", "(", "[", "=>", "->", "=")) \
                and not stripped.startswith(("return", "let ", "const ", "val ", "var ")):
            out.append(("line removed", "\n"))
    return out


def compiles_python(source):
    try:
        compile(source, "<mutant>", "exec")
        return True
    except SyntaxError:
        return False
