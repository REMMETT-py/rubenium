"""French check: every literal passed to tr() (and every NEWS line) has a French translation, and no French key is
defined twice. Usage: python overhaul/i18n/check.py [--list]. Exit 1 when something is missing."""
import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load():
    src = open(os.path.join(REPO, "Rubenium.py"), encoding="utf-8").read()
    return src, ast.parse(src)


def fr_dicts(tree):
    """The FR dict(s): module-level assignments named FR (or FR.update({...}))."""
    keys, dups = {}, []
    for node in ast.walk(tree):
        d = None
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FR" for t in node.targets):
            d = node.value
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update"
              and isinstance(node.func.value, ast.Name) and node.func.value.id == "FR" and node.args):
            d = node.args[0]
        if isinstance(d, ast.Dict):
            for k, v in zip(d.keys, d.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if k.value in keys and isinstance(v, ast.Constant) and keys[k.value][1] != v.value:
                        dups.append((k.lineno, k.value))
                    keys[k.value] = (k.lineno, v.value if isinstance(v, ast.Constant) else None)
    return keys, dups


def used(tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append((a.lineno, a.value))
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEWS" for t in node.targets):
            for elt in ast.walk(node.value):
                if isinstance(elt, ast.List):
                    for s in elt.elts:
                        if isinstance(s, ast.Constant) and isinstance(s.value, str):
                            out.append((s.lineno, s.value))
    return out


def main():
    src, tree = load()
    fr, dups = fr_dicts(tree)
    missing = sorted({(ln, s) for ln, s in used(tree) if s not in fr and any(c.isalpha() for c in s)})
    if "--list" in sys.argv:
        for ln, s in missing:
            print(f"{ln}\t{s!r}")
        for ln, s in dups:
            print(f"DUP {ln}\t{s!r}")
    print(f"{len(missing)} strings without French, {len(dups)} French keys defined twice with different text")
    return 1 if missing or dups else 0


if __name__ == "__main__":
    sys.exit(main())
