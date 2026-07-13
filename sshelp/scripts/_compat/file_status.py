#!/usr/bin/env python3
"""Report local and optional remote state for a file checkout transaction."""

from __future__ import annotations

import argparse

from _remote_files_common import add_checkout_root_argument, classify_local_changes, load_manifest, manifest_ssh_options, run_remote_helper
from _ssh_common import JsonArgumentParser, invoke


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--check-remote", action="store_true")
    add_checkout_root_argument(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    directory, manifest = load_manifest(args.checkout_root, args.checkout)
    values = classify_local_changes(directory, manifest)
    if args.check_remote:
        remote = run_remote_helper(
            manifest_ssh_options(manifest),
            manifest["host"],
            "status",
            {"root": manifest["remote_root"], "paths": [item["path"] for item in values]},
            timeout=120,
        )
        remote_by_path = {item["relative_path"]: item for item in remote["files"]}
        base_by_path = {item["relative_path"]: item for item in manifest["files"]}
        for item in values:
            current = remote_by_path[item["path"]]
            base = base_by_path.get(item["path"])
            if base is None:
                remote_changed = current["state"] != "missing"
            else:
                remote_changed = current["state"] != "regular" or current.get("sha256") != base["base_sha256"]
            item["remote"] = current
            item["remote_changed"] = remote_changed
            if remote_changed and item["state"] in ("modified-local", "added-local", "deleted-local"):
                item["state"] = "conflict"
            elif remote_changed and item["state"] == "clean":
                item["state"] = "modified-remote"
    return {"checkout_id": args.checkout, "local_root": str((directory / "work").resolve()), "files": values}


if __name__ == "__main__":
    invoke(run)
