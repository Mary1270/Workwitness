import ast
import io
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_DIR = os.path.join(ROOT, "contracts")
HEADER_VERSION = re.compile(r"^# v\d+\.\d+\.\d+$")
HEADER_DEPENDS = re.compile(r'^# \{ "Depends": "py-genlayer:[0-9a-z]+" \}$')
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "requests", "urllib.request", "random", "time"}
FORBIDDEN_CALLS = {"print", "open", "eval", "exec", "input"}
STORAGE_TYPES = {"TreeMap", "DynArray"}
ACCEPTED_MESSAGES_ALLOWED = {"open_job"}


def storage_fields(tree):
    fields = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    ann = stmt.annotation
                    base = ann.value if isinstance(ann, ast.Subscript) else ann
                    if isinstance(base, ast.Name) and base.id in STORAGE_TYPES:
                        fields.add(stmt.target.id)
    return fields


def check_source(source, name="contract"):
    problems = []
    lines = source.splitlines()
    if len(lines) < 3 or not HEADER_VERSION.match(lines[0]):
        problems.append(name + ": line 1 must be the runner version comment")
    if len(lines) < 3 or not HEADER_DEPENDS.match(lines[1]):
        problems.append(name + ": line 2 must be the pinned py-genlayer Depends comment")
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and tok.start[0] > 2:
            problems.append(name + ": comment on line " + str(tok.start[0]) + " (Studio rejects commented contracts)")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                problems.append(name + ": docstring found in " + getattr(node, "name", "module"))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    problems.append(name + ": forbidden import " + alias.name)
        if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_IMPORTS:
            problems.append(name + ": forbidden import " + str(node.module))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            problems.append(name + ": forbidden call " + node.func.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            problems.append(name + ": float literal on line " + str(node.lineno) + " (use integers)")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            inner = node.func.value
            if isinstance(inner.func, ast.Attribute) and inner.func.attr == "emit":
                timing = [k.value.value for k in inner.keywords if k.arg == "on" and isinstance(k.value, ast.Constant)]
                if timing != ["finalized"] and node.func.attr not in ACCEPTED_MESSAGES_ALLOWED:
                    problems.append(name + ": message " + node.func.attr + " must use on=\"finalized\"")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run_nondet_unsafe":
            if len(node.args) != 2 or node.keywords:
                problems.append(name + ": run_nondet_unsafe must take two positional functions")
            for arg in node.args:
                for inner in ast.walk(arg):
                    if isinstance(inner, ast.Name) and inner.id == "self":
                        problems.append(name + ": non-deterministic closure captures self")
    fields = storage_fields(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    for target in inner.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr in fields:
                            problems.append(name + ": __init__ assigns storage field " + target.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            owner = node.func.value
            if isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Name) and owner.value.id == "self" and owner.attr in fields:
                problems.append(name + ": .get() on storage field " + owner.attr)
    return problems


def main():
    problems = []
    names = sorted(n for n in os.listdir(CONTRACT_DIR) if n.endswith(".py"))
    if not names:
        problems.append("no contracts found")
    for fname in names:
        with open(os.path.join(CONTRACT_DIR, fname), encoding="utf-8") as handle:
            problems.extend(check_source(handle.read(), fname))
    for line in problems:
        print("FAIL " + line)
    if not problems:
        print("OK " + str(len(names)) + " contracts pass the deploy checks")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
