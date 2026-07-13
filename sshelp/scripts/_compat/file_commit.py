#!/usr/bin/env python3
"""Safely commit local checkout changes with conflict checks and atomic remote replacement."""

from __future__ import annotations

import argparse
from pathlib import PurePosixPath

from _remote_files_common import (
    add_checkout_root_argument,
    classify_local_changes,
    load_manifest,
    manifest_ssh_options,
    remove_checkout,
    run_remote_helper,
    run_sftp_batch,
    sftp_quote,
)
from _ssh_common import JsonArgumentParser, SkillError, invoke


def parse_mode(raw: str) -> str:
    try:
        value = int(raw, 8)
    except ValueError as exc:
        raise SkillError("INVALID_MODE", "new file mode must be an octal value such as 0644") from exc
    if value < 0 or value > 0o777:
        raise SkillError("INVALID_MODE", "new file mode must be between 0000 and 0777")
    return format(value, "04o")


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--new-file-mode", default="0644")
    parser.add_argument("--keep-local", action="store_true")
    add_checkout_root_argument(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    new_file_mode = parse_mode(args.new_file_mode)
    directory, manifest = load_manifest(args.checkout_root, args.checkout)
    statuses = classify_local_changes(directory, manifest)
    deleted = [item["path"] for item in statuses if item["state"] == "deleted-local"]
    if deleted:
        raise SkillError("REMOTE_DELETE_NOT_SUPPORTED", "remote deletion is not supported; restore or abort the checkout", {"paths": deleted, "checkout_preserved": True})
    changed = [item for item in statuses if item["state"] in ("modified-local", "added-local")]
    if not changed:
        return {"checkout_id": args.checkout, "committed": [], "local_checkout_removed": False, "message": "no local changes"}

    options = manifest_ssh_options(manifest)
    remote = run_remote_helper(
        options,
        manifest["host"],
        "status",
        {"root": manifest["remote_root"], "paths": [item["path"] for item in changed]},
        timeout=120,
    )
    remote_by_path = {item["relative_path"]: item for item in remote["files"]}
    manifest_by_path = {item["relative_path"]: item for item in manifest["files"]}
    conflicts = []
    for item in changed:
        current = remote_by_path[item["path"]]
        base = manifest_by_path.get(item["path"])
        if base is None:
            if current["state"] != "missing":
                conflicts.append({"path": item["path"], "reason": "remote target was created", "current": current})
            elif not current.get("parent_exists"):
                conflicts.append({"path": item["path"], "reason": "remote parent directory does not exist", "current": current})
        elif current["state"] != "regular" or current.get("sha256") != base["base_sha256"]:
            conflicts.append({"path": item["path"], "base_sha256": base["base_sha256"], "current": current})
    if conflicts:
        raise SkillError("REMOTE_FILE_CHANGED", "one or more remote files changed after checkout", {"conflicts": conflicts, "checkout_preserved": True})

    upload_commands = []
    commit_items = []
    for item in changed:
        relative = item["path"]
        basename = PurePosixPath(relative).name
        temp_name = f".{basename}.sshelp-{args.checkout}.tmp"
        remote_parent = str(PurePosixPath(manifest["remote_root"]) / PurePosixPath(relative).parent)
        remote_temp = str(PurePosixPath(remote_parent) / temp_name)
        local_work = (directory / "work" / relative).resolve()
        upload_commands.append(f"put {sftp_quote(local_work.as_posix())} {sftp_quote(remote_temp)}")
        base = manifest_by_path.get(relative)
        commit_items.append({
            "relative_path": relative,
            "kind": "modified" if base else "added",
            "base_sha256": base["base_sha256"] if base else None,
            "new_sha256": item["work_sha256"],
            "mode": base["mode"] if base else new_file_mode,
            "temp_name": temp_name,
        })

    run_sftp_batch(options, manifest["ssh"]["sftp_bin"], manifest["host"], upload_commands)
    try:
        result = run_remote_helper(
            options,
            manifest["host"],
            "commit",
            {"root": manifest["remote_root"], "files": commit_items},
            timeout=120,
        )
    except SkillError as exc:
        exc.details.setdefault("checkout_preserved", True)
        raise

    removed = False
    if not args.keep_local:
        remove_checkout(args.checkout_root, args.checkout)
        removed = True
    return {"checkout_id": args.checkout, "committed": result["committed"], "local_checkout_removed": removed}


if __name__ == "__main__":
    invoke(run)
