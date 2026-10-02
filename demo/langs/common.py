"""Pieces every language's demo shares."""
import textwrap


def d(text):
    return textwrap.dedent(text).lstrip("\n")


def aqv_config(code_paths, test_paths, profile, size_exclude=("*.lock",), max_mutants=20):
    """The demo repo's .aqv.yml: shared rules plus the language's runner profile.

    `profile` is the YAML for the runner, api and mutation sections, already indented.
    """
    return (
        "# Agent Quality Verifier config. Owned by humans; agents must not change it.\n"
        'specs: ["specs/*.md"]\n'
        "ids_registry: specs/.ids\n"
        "contract: contracts/openapi.yaml\n"
        f"code_paths: {list(code_paths)}\n".replace("'", '"')
        + f"test_paths: {list(test_paths)}\n".replace("'", '"')
        + 'protected_paths: ["specs/", ".aqv.yml", ".spectral.yaml"]\n\n'
        + profile.rstrip() + "\n\n"
        + "git:\n"
        '  humans: ["pat@example.com"]\n'
        '  agent_trailer: "Co-Authored-By"\n'
        '  branch_pattern: "^(feat|fix|refactor|test|docs|chore)/AC-[a-z0-9]+-[0-9]{3}(-[a-z0-9-]+)?$"\n'
        "  max_commit_lines: 400\n"
        f"  size_exclude: {list(size_exclude)}\n".replace("'", '"')
        + "  verified_ref: refs/aqv/verified\n"
    )
