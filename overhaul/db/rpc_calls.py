#!/usr/bin/env python3
"""Lists every server function a Rubenium.py calls, with the argument names it sends.

  python overhaul/db/rpc_calls.py Rubenium.py > tests/db/compat_7_0.json

Finds calls of the forms ask("rb_x", {...}), rpc("rb_x", {...}), in_background/edge helpers and
_request("/rest/v1/rpc/rb_x", {...}). Argument names come from the dict literal; a call whose arguments are built
elsewhere is listed with "args": null (only the function's existence is checked then)."""
import ast, json, sys


def _names(node):
    """Server function names a node can evaluate to: a constant, or either side of `a if c else b`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value
        if v.startswith("/rest/v1/rpc/"):
            v = v.rsplit("/", 1)[1]
        return [v] if v.startswith("rb_") and v.replace("_", "").isalnum() else []
    if isinstance(node, ast.IfExp):
        return _names(node.body) + _names(node.orelse)
    return []


def _keys(node):
    if isinstance(node, ast.Dict) and all(isinstance(k, ast.Constant) for k in node.keys):
        return sorted(k.value for k in node.keys)
    return None


def calls(path, known=None):
    """known: the set of server function names (to tell them from error codes like rb_not_enough)."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    found = {}

    def add(name, args, line):
        if known is not None and name not in known:
            return
        key = (name, json.dumps(args))
        found.setdefault(key, {"fn": name, "args": args, "lines": []})["lines"].append(line)

    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and n.args:
            for name in _names(n.args[0]):
                add(name, _keys(n.args[1]) if len(n.args) > 1 else None, n.lineno)
        elif isinstance(n, ast.Tuple) and len(n.elts) >= 2:          # fn, args = ("rb_x", {...})
            for name in _names(n.elts[0]):
                add(name, _keys(n.elts[1]), n.lineno)
        elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple) and n.value.elts:   # RPC, CFG = "rb_x", ...
            for name in _names(n.value.elts[0]):
                add(name, None, n.lineno)
    return sorted(found.values(), key=lambda x: (x["fn"], json.dumps(x["args"])))


if __name__ == "__main__":
    # second argument: a file with the server's function names, one per line (to drop error codes)
    known = set(open(sys.argv[2]).read().split()) if len(sys.argv) > 2 else None
    print(json.dumps(calls(sys.argv[1], known), indent=1))
