#!/usr/bin/env python3
"""Build dist/ats-check.zip from skills/ats-check.

The zip holds exactly the skill folder at its root (ats-check/SKILL.md, ...),
which is the layout claude.ai expects for an uploaded skill. The build is
byte-for-byte reproducible: entries are sorted, timestamps and permissions
are fixed, caches are left out. tests/test_analyze.py rebuilds the zip and
compares it with the committed file.

Usage: python tools/build_dist.py [output.zip]
"""

from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skills", "ats-check")
DEFAULT_OUT = os.path.join(ROOT, "dist", "ats-check.zip")

# Earliest timestamp the zip format can store (DOS epoch); fixed so that the
# archive does not change when only file modification times change.
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644
EXEC_MODE = 0o755
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".DS_Store")


def skill_files() -> list[tuple[str, str]]:
    """Return sorted (archive name, source path) pairs."""
    pairs = []
    for dirpath, dirnames, filenames in os.walk(SKILL_DIR):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, os.path.dirname(SKILL_DIR)).replace(os.sep, "/")
            pairs.append((rel, src))
    return sorted(pairs)


def build(out: str = DEFAULT_OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in skill_files():
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = EXEC_MODE if arcname.endswith(".py") and "/scripts/" in arcname else FILE_MODE
            info.external_attr = (0o100000 | mode) << 16
            with open(src, "rb") as fh:
                zf.writestr(info, fh.read())
    return out


if __name__ == "__main__":
    path = build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
    print(path)
