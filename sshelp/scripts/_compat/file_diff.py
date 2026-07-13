#!/usr/bin/env python3
"""Generate a unified base-to-work diff for a file checkout transaction."""

from __future__ import annotations

import argparse
import difflib

from _remote_files_common import add_checkout_root_argument, classify_local_changes, load_manifest
from _ssh_common import JsonArgumentParser, invoke


def text_lines(path):
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace").splitlines(keepends=True)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    add_checkout_root_argument(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    directory, manifest = load_manifest(args.checkout_root, args.checkout)
    diffs = []
    for item in classify_local_changes(directory, manifest):
        if item["state"] == "clean":
            continue
        relative = item["path"]
        base_path = directory / "base" / relative
        work_path = directory / "work" / relative
        before = text_lines(base_path) if base_path.exists() else []
        after = text_lines(work_path) if work_path.exists() else []
        if before is None or after is None:
            diffs.append({"path": relative, "state": item["state"], "binary": True, "diff": None})
            continue
        value = "".join(difflib.unified_diff(before, after, fromfile=f"base/{relative}", tofile=f"work/{relative}"))
        diffs.append({"path": relative, "state": item["state"], "binary": False, "diff": value})
    return {"checkout_id": args.checkout, "files": diffs}


if __name__ == "__main__":
    invoke(run)
