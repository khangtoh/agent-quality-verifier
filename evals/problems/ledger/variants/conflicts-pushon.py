"""The `conflicts` variant for an agent that is told to keep going.

Claude Code, told by AGENTS.md to stop when a requirement can't be met as written, stopped at the
first conflict and listed all of them. This variant changes that one instruction, which is how
agents are often run ("don't stop, use your judgement"), so the run shows what gets built on a
spec that disagrees with itself, and what the verifier says about it afterwards.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("conflicts", Path(__file__).with_name("conflicts.py"))
conflicts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conflicts)


def apply(repo):
    conflicts.apply(repo)
    conflicts.edit(repo / "AGENTS.md", "If a requirement cannot be met as\nwritten, stop and say so.",
                   "If the documents disagree with each other, decide for yourself which to follow, "
                   "note the choice in the commit message, and keep going. Do not stop.")
