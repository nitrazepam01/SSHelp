#!/usr/bin/env python3
"""Checkout a small set of remote files into an isolated local base/work transaction."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from _remote_files_common import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_TOTAL_BYTES,
    add_checkout_root_argument,
    add_sftp_argument,
    create_checkout_directory,
    hash_file,
    run_remote_helper,
    run_sftp_batch,
    serialize_ssh_options,
    sftp_quote,
    validate_relative_path,
    write_manifest,
)
from _ssh_common import JsonArgumentParser, SkillError, add_ssh_arguments, invoke, ssh_options_from_args, validate_cwd, validate_host


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    add_checkout_root_argument(parser)
    add_sftp_argument(parser)
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    root = validate_cwd(args.root)
    options = ssh_options_from_args(args)
    paths = list(dict.fromkeys(validate_relative_path(value) for value in args.paths))
    if not 1 <= args.max_files <= 1000 or len(paths) > args.max_files:
        raise SkillError("TOO_MANY_FILES", f"checkout contains {len(paths)} files; limit is {args.max_files}")
    if args.max_file_bytes < 1 or args.max_total_bytes < 1:
        raise SkillError("INVALID_LIMIT", "file size limits must be positive")

    inspected = run_remote_helper(options, host, "inspect", {"root": root, "paths": paths}, timeout=120)
    files = inspected["files"]
    oversized = [item["relative_path"] for item in files if item["size"] > args.max_file_bytes]
    total = sum(item["size"] for item in files)
    if oversized:
        raise SkillError("FILE_TOO_LARGE", "one or more files exceed the checkout limit", {"paths": oversized, "max_file_bytes": args.max_file_bytes})
    if total > args.max_total_bytes:
        raise SkillError("CHECKOUT_TOO_LARGE", "checkout total exceeds the configured limit", {"total_bytes": total, "max_total_bytes": args.max_total_bytes})

    checkout_id, directory = create_checkout_directory(args.checkout_root)
    manifest = {
        "schema_version": 1,
        "state": "downloading",
        "checkout_id": checkout_id,
        "host": host,
        "remote_root": inspected["remote_root_real"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ssh": serialize_ssh_options(options, args.sftp_bin),
        "files": files,
    }
    write_manifest(directory, manifest)
    commands: list[str] = []
    for item in files:
        local = directory / "base" / Path(*item["relative_path"].split("/"))
        local.parent.mkdir(parents=True, exist_ok=True)
        commands.append(f"get {sftp_quote(item['remote_absolute_path'])} {sftp_quote(local.resolve().as_posix())}")
    run_sftp_batch(options, args.sftp_bin, host, commands)

    output_files = []
    for item in files:
        base = directory / "base" / Path(*item["relative_path"].split("/"))
        actual = hash_file(base)
        if actual != item["base_sha256"]:
            raise SkillError("REMOTE_FILE_CHANGED", "remote file changed while it was being checked out", {"path": item["relative_path"], "expected_sha256": item["base_sha256"], "downloaded_sha256": actual, "checkout_preserved": True})
        work = directory / "work" / Path(*item["relative_path"].split("/"))
        work.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base, work)
        output_files.append({"remote_path": item["relative_path"], "local_path": str(work.resolve())})

    manifest["state"] = "ready"
    write_manifest(directory, manifest)
    return {
        "checkout_id": checkout_id,
        "local_root": str((directory / "work").resolve()),
        "manifest": str((directory / "manifest.json").resolve()),
        "total_bytes": total,
        "files": output_files,
    }


if __name__ == "__main__":
    invoke(run)
