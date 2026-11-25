"""The golf holes and the shot simulation, taken from Rubenium.py itself (no copy to keep in step).

    from holes import HOLES, get_hole, simulate, CONST      (loads those parts of Rubenium.py, without Qt)
    python overhaul/golf/holes.py sql > out.sql              rows for rb_golf_hole_defs (holes 1-60 and 101-160)
"""
import ast
import json
import math
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Rubenium.py")
NAMES = {"FIELD_H", "BALL_R", "CUP_R", "GOLF_DEC", "GOLF_DMAX", "VMAX", "BOUNCE", "HOLES"}
FUNCS = {"get_hole", "_inside", "simulate"}


def _load(path=SRC) -> dict:
    tree = ast.parse(open(path, encoding="utf-8").read())
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NAMES for t in node.targets):
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCS:
            keep.append(node)
    ns = {"math": math}
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), ns)   # our own source, golf part only
    return ns


_NS = _load()
HOLES, get_hole, simulate = _NS["HOLES"], _NS["get_hole"], _NS["simulate"]
CONST = {k: _NS[k] for k in NAMES - {"HOLES"}}


def hole_ids() -> list:
    return sorted(HOLES) + [100 + h for h in sorted(HOLES)]


def _arr(vals) -> str:
    return "'{" + ",".join(repr(float(v)) for v in vals) + "}'"


def sql_rows() -> str:
    """(id, name, tee, cup, rects, circles, sand, ice, water, boost): each list flattened (4, 3, 4, 4, 4, 6 a row)."""
    out = []
    for hid in hole_ids():
        h = get_hole(hid)
        flat = lambda rs: _arr(v for r in rs for v in r)   # noqa: E731
        out.append("(%d, '%s', %s, %s, %s, %s, %s, %s, %s, %s)" % (
            hid, h["name"].replace("'", "''"), _arr(h["tee"]), _arr(h["cup"]), flat(h["rects"]), flat(h["circles"]),
            flat(h.get("sand", [])), flat(h.get("ice", [])), flat(h.get("water", [])), flat(h.get("boost", []))))
    return ",\n".join(out)


if __name__ == "__main__" and sys.argv[1:] == ["sql"]:
    print(sql_rows())
elif __name__ == "__main__":
    print(json.dumps(CONST, indent=1), len(hole_ids()), "holes")
