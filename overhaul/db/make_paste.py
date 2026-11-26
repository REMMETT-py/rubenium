#!/usr/bin/env python3
"""Joins migrations into one file to paste into the Supabase SQL editor, in order, with an optional last statement.

  python overhaul/db/make_paste.py OUT.sql MIGRATION.sql... [--then "select public.rb_reset_94();"]
"""
import os
import sys

args = sys.argv[1:]
then = None
if "--then" in args:
    i = args.index("--then")
    then = args[i + 1]
    args = args[:i] + args[i + 2:]
out, files = args[0], args[1:]
parts = ["-- Rubenium: paste all of this into the Supabase SQL editor and run it once.",
         "-- Made from: " + ", ".join(os.path.basename(f) for f in files) + "\n"]
for f in files:
    parts.append(f"-- ================================================================ {os.path.basename(f)}")
    parts.append(open(f, encoding="utf-8").read().rstrip() + "\n")
if then:
    parts.append("-- ================================================================ last\n" + then.strip() + "\n")
open(out, "w", encoding="utf-8").write("\n".join(parts))
print(out, sum(os.path.getsize(f) for f in files), "bytes from", len(files), "files")
