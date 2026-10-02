"""T7: small, deterministic line mutations for Python.

Each mutant changes one line written for the requirement. If the requirement's
own tests still pass with the change, the mutant "survived": the tests run that
line but don't check what it does. This module is the per-language part of T7
(tier E); mutmut or another mutation tool could replace it.
"""
import re

SWAPS = [
    (r">=", ">"), (r"<=", "<"), (r"(?<![<>=!])>(?!=)", ">="), (r"(?<![<>=!])<(?!=)", "<="),
    (r"==", "!="), (r"!=", "=="),
    (r"\bnot in\b", "in"), (r"(?<!not )\bin\b(?=\s)", "not in"),
    (r"\bTrue\b", "False"), (r"\bFalse\b", "True"),
    (r"\band\b", "or"), (r"\bor\b", "and"),
    (r"(?<![\w.])\+(?![+=])", "-"), (r"(?<![\w.eE])-(?![-=>])", "+"),
]
BLOCK_STARTERS = ("def ", "class ", "if ", "elif ", "else", "for ", "while ", "try", "except", "finally",
                  "with ", "@", "async def ", "import ", "from ", "return", '"""', "'''")
INT = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def _strings_masked(line):
    """The line with string literals blanked, so swaps never edit text inside quotes."""
    return re.sub(r"(\"[^\"]*\"|'[^']*')", lambda m: " " * len(m.group(0)), line)


def mutants(line):
    """[(description, new_line)] for one source line, in a fixed order."""
    out = []
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return out
    indent = line[: len(line) - len(line.lstrip())]
    masked = _strings_masked(line)
    code_start = len(indent)
    for pattern, repl in SWAPS:
        m = re.search(pattern, masked[code_start:])
        if m:
            s, e = m.start() + code_start, m.end() + code_start
            out.append((f"'{line[s:e]}' → '{repl}'", line[:s] + repl + line[e:]))
    m = INT.search(masked[code_start:])
    if m:
        s, e = m.start() + code_start, m.end() + code_start
        n = int(line[s:e])
        out.append((f"{n} → {n + 1}", line[:s] + str(n + 1) + line[e:]))
    if stripped.startswith("return ") and stripped != "return None":
        out.append(("return value → None", f"{indent}return None\n"))
    if not stripped.startswith(BLOCK_STARTERS) and not stripped.endswith((":", ",", "(", "[", "{", "\\")):
        out.append(("line removed", f"{indent}pass\n"))
    return out


def compiles(source):
    try:
        compile(source, "<mutant>", "exec")
        return True
    except SyntaxError:
        return False
