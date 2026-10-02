"""Loads .aqv.yml from the repo under check, filling in defaults."""
import copy

import yaml

DEFAULTS = {
    "specs": ["specs/*.md"],
    "ids_registry": "specs/.ids",
    "contract": "contracts/openapi.yaml",
    "code_paths": ["src/"],
    "test_paths": ["tests/"],
    "protected_paths": ["specs/", ".aqv.yml"],
    "runner": {"broken_exit_codes": [], "comment_prefix": "#"},
    "api": {},
    "git": {
        "humans": [],
        "agent_trailer": "Co-Authored-By",
        "branch_pattern": r"^(feat|fix|refactor|test|docs|chore)/AC-[a-z0-9]+-[0-9]{3}(-[a-z0-9-]+)?$",
        "max_commit_lines": 400,
        "size_exclude": ["*.lock"],
        "verified_ref": "refs/aqv/verified",
    },
    "mutation": {"min_kill_ratio": 0.6, "max_mutants": 20},
}

CONVENTIONAL = r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: \S.*$"
NO_BEHAVIOR_TYPES = ("refactor", "chore", "style")


def merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load(text):
    return merge(DEFAULTS, yaml.safe_load(text) if text else {})
