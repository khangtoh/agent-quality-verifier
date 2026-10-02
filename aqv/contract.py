"""The OpenAPI contract: operations, their requirement links, and response validation."""
import re
from dataclasses import dataclass, field

import yaml
from jsonschema import Draft202012Validator

HTTP = {"get", "put", "post", "delete", "patch", "head", "options"}


@dataclass
class Operation:
    method: str
    path: str
    requirements: list
    responses: dict
    pattern: re.Pattern = field(repr=False, default=None)

    @property
    def key(self):
        return f"{self.method} {self.path}"


def load(text):
    return yaml.safe_load(text) if text else None


def operations(doc):
    ops = []
    for path, item in (doc or {}).get("paths", {}).items():
        for method, op in (item or {}).items():
            if method.lower() not in HTTP or not isinstance(op, dict):
                continue
            rx = re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(path)) + "$")
            reqs = op.get("x-requirements") or []
            ops.append(Operation(method.upper(), path, list(reqs), op.get("responses") or {}, rx))
    return ops


def deref(node, doc, depth=0):
    if depth > 50:
        return node
    if isinstance(node, dict):
        if "$ref" in node and node["$ref"].startswith("#/"):
            target = doc
            for part in node["$ref"][2:].split("/"):
                target = target[part]
            return deref(target, doc, depth + 1)
        return {k: deref(v, doc, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(x, doc, depth + 1) for x in node]
    return node


def find(ops, method, path):
    for op in ops:
        if op.method == method.upper() and op.pattern.match(path):
            return op
    return None


def check_response(doc, op, status, body):
    """Problems with one observed response, as short sentences. Empty means it conforms."""
    code = str(status)
    resp = op.responses.get(code) or op.responses.get(code[0] + "XX") or op.responses.get("default")
    if resp is None:
        return [f"{op.key} returned {code}, which the contract doesn't document"]
    schema = (((resp.get("content") or {}).get("application/json") or {}).get("schema"))
    if schema is None:
        return []
    errors = []
    for e in Draft202012Validator(deref(schema, doc)).iter_errors(body):
        errors.append(f"{op.key} {code} body breaks the schema: {e.message}")
    return errors
