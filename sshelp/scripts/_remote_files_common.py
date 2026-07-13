#!/usr/bin/env python3
"""Shared helpers for transactional remote file checkouts."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import heapq
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from _ssh_common import (
    SSHOptions,
    SkillError,
    shell_quote,
    ssh_failure,
    validate_host,
)


CHECKOUT_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")
DEFAULT_MAX_FILES = 20
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 64 * 1024 * 1024
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json"}
SENSITIVE_SUFFIXES = {".pem", ".key"}


REMOTE_HELPER = r'''
import fnmatch
import hashlib
import heapq
import json
import os
import stat
import subprocess
import sys
import time

SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json"}
SENSITIVE_SUFFIXES = {".pem", ".key"}
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "checkpoints", "data", "datasets", "build", "dist"}

def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            value.update(block)
    return value.hexdigest()

def sensitive(relative):
    name = relative.rsplit("/", 1)[-1].lower()
    return name in SENSITIVE_NAMES or any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)

def relative_parts(relative):
    if not relative or relative.startswith("/") or "\x00" in relative or "\\" in relative:
        raise ValueError("invalid relative path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("invalid relative path")
    return parts

def root_path(raw):
    if not raw.startswith("/") or "\x00" in raw:
        raise ValueError("remote root must be absolute")
    root = os.path.realpath(raw)
    info = os.stat(root)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("remote root is not a directory")
    return root

def target_path(root, relative, allow_missing=False):
    parts = relative_parts(relative)
    parent = os.path.realpath(os.path.join(root, *parts[:-1]))
    if os.path.commonpath([root, parent]) != root:
        raise ValueError("path escapes remote root")
    target = os.path.join(parent, parts[-1])
    if not allow_missing:
        info = os.lstat(target)
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symbolic links are not allowed")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("target is not a regular file")
    return target

def inspect(payload):
    root = root_path(payload["root"])
    files = []
    for relative in payload["paths"]:
        if sensitive(relative):
            raise ValueError("sensitive file checkout is denied: " + relative)
        target = target_path(root, relative)
        info = os.lstat(target)
        files.append({
            "relative_path": relative,
            "remote_absolute_path": target,
            "base_sha256": digest(target),
            "size": info.st_size,
            "mode": format(stat.S_IMODE(info.st_mode), "04o"),
            "mtime_ns": info.st_mtime_ns,
        })
    return {"remote_root_real": root, "files": files}

def statuses(payload):
    root = root_path(payload["root"])
    values = []
    for relative in payload["paths"]:
        try:
            target = target_path(root, relative, allow_missing=True)
            info = os.lstat(target)
            if stat.S_ISLNK(info.st_mode):
                values.append({"relative_path": relative, "state": "symlink"})
            elif not stat.S_ISREG(info.st_mode):
                values.append({"relative_path": relative, "state": "not-regular"})
            else:
                values.append({
                    "relative_path": relative,
                    "state": "regular",
                    "sha256": digest(target),
                    "size": info.st_size,
                    "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                    "mtime_ns": info.st_mtime_ns,
                })
        except FileNotFoundError:
            parent = os.path.dirname(target)
            values.append({
                "relative_path": relative,
                "state": "missing",
                "parent_exists": os.path.isdir(parent) and not os.path.islink(parent),
            })
    return {"remote_root_real": root, "files": values}

def commit(payload):
    root = root_path(payload["root"])
    prepared = []
    for item in payload["files"]:
        relative = item["relative_path"]
        target = target_path(root, relative, allow_missing=True)
        parent = os.path.dirname(target)
        temp = os.path.join(parent, item["temp_name"])
        if os.path.dirname(temp) != parent:
            raise ValueError("invalid temporary file name")
        temp_info = os.lstat(temp)
        if stat.S_ISLNK(temp_info.st_mode) or not stat.S_ISREG(temp_info.st_mode):
            raise ValueError("uploaded temporary path is not a regular file")
        if digest(temp) != item["new_sha256"]:
            raise ValueError("uploaded temporary file hash mismatch")
        if item["kind"] == "modified":
            target_info = os.lstat(target)
            if stat.S_ISLNK(target_info.st_mode) or not stat.S_ISREG(target_info.st_mode):
                raise ValueError("remote target type changed")
            current = digest(target)
            if current != item["base_sha256"]:
                error = RuntimeError("REMOTE_FILE_CHANGED")
                error.details = {"path": relative, "base_sha256": item["base_sha256"], "current_remote_sha256": current}
                raise error
            mode = int(item["mode"], 8)
        else:
            if os.path.lexists(target):
                error = RuntimeError("REMOTE_FILE_CREATED")
                error.details = {"path": relative}
                raise error
            mode = int(item["mode"], 8)
        os.chmod(temp, mode)
        prepared.append((item, temp, target, mode))
    committed = []
    for item, temp, target, mode in prepared:
        os.replace(temp, target)
        final_hash = digest(target)
        final_mode = stat.S_IMODE(os.lstat(target).st_mode)
        if final_hash != item["new_sha256"] or final_mode != mode:
            raise ValueError("final remote verification failed")
        committed.append({
            "path": item["relative_path"],
            "old_sha256": item.get("base_sha256"),
            "new_sha256": final_hash,
            "kind": item["kind"],
        })
    return {"committed": committed}

def walk_files(root):
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not os.path.islink(os.path.join(current, name))]
        for name in files:
            full = os.path.join(current, name)
            if os.path.islink(full):
                continue
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            if not sensitive(relative):
                yield relative

def find_files(payload):
    root = root_path(payload["root"])
    maximum = payload["max_results"]
    name_pattern = payload.get("name")
    globs = payload.get("globs") or []
    modified_within = payload.get("modified_within_seconds")
    cutoff_ns = time.time_ns() - int(modified_within * 1000000000) if modified_within is not None else None
    candidates = []
    matched = 0
    for relative in walk_files(root):
        name = relative.rsplit("/", 1)[-1]
        if name_pattern and not fnmatch.fnmatch(name, name_pattern):
            continue
        if globs and not any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern) for pattern in globs):
            continue
        full = os.path.join(root, *relative.split("/"))
        info = os.lstat(full)
        if cutoff_ns is not None and info.st_mtime_ns < cutoff_ns:
            continue
        item = {
            "path": relative,
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "mode": format(stat.S_IMODE(info.st_mode), "04o"),
        }
        matched += 1
        key = (item["mtime_ns"], item["path"], item)
        if len(candidates) < maximum:
            heapq.heappush(candidates, key)
        elif key[:2] > candidates[0][:2]:
            heapq.heapreplace(candidates, key)
    results = [entry[2] for entry in sorted(candidates, key=lambda entry: (-entry[0], entry[1]))]
    return {"remote_root_real": root, "results": results, "truncated": matched > maximum}

def tree(payload):
    root = root_path(payload["root"])
    relative_root = payload.get("path") or "."
    maximum_depth = payload["depth"]
    maximum = payload["max_results"]
    start = root if relative_root == "." else target_path(root, relative_root, allow_missing=True)
    start_info = os.lstat(start)
    if stat.S_ISLNK(start_info.st_mode) or not stat.S_ISDIR(start_info.st_mode):
        raise ValueError("tree path is not a normal directory")
    results = []
    truncated = False
    start_depth = start.rstrip(os.sep).count(os.sep)
    for current, dirs, files in os.walk(start, followlinks=False):
        depth = current.rstrip(os.sep).count(os.sep) - start_depth
        dirs[:] = sorted(
            name for name in dirs
            if name not in IGNORED_DIRS and not os.path.islink(os.path.join(current, name))
        )
        if depth >= maximum_depth:
            dirs[:] = []
        for name in dirs:
            full = os.path.join(current, name)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            results.append({"path": relative, "type": "directory", "depth": depth + 1})
            if len(results) >= maximum:
                truncated = True
                return {"remote_root_real": root, "results": results, "truncated": truncated}
        if depth < maximum_depth:
            for name in sorted(files):
                full = os.path.join(current, name)
                if os.path.islink(full):
                    continue
                relative = os.path.relpath(full, root).replace(os.sep, "/")
                if sensitive(relative):
                    continue
                info = os.lstat(full)
                if not stat.S_ISREG(info.st_mode):
                    continue
                results.append({"path": relative, "type": "file", "depth": depth + 1, "size": info.st_size, "mtime_ns": info.st_mtime_ns})
                if len(results) >= maximum:
                    truncated = True
                    return {"remote_root_real": root, "results": results, "truncated": truncated}
    return {"remote_root_real": root, "results": results, "truncated": truncated}

def search(payload):
    root = root_path(payload["root"])
    maximum = payload["max_results"]
    query = payload.get("query")
    globs = payload.get("globs") or []
    name_pattern = payload.get("name")
    list_dir = payload.get("list_dir")
    results = []
    truncated = False
    if query is not None:
        command = ["rg", "--json", "--color", "never", "--no-messages", "--max-filesize", "8M"]
        for pattern in globs:
            command.extend(["--glob", pattern])
        for pattern in ("!*.pem", "!*.key", "!.env", "!id_rsa", "!id_ed25519", "!credentials.json"):
            command.extend(["--glob", pattern])
        command.extend([query, "."])
        try:
            process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            error = RuntimeError("RG_NOT_FOUND")
            error.details = {}
            raise error
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "match":
                continue
            data = event["data"]
            relative = data["path"].get("text", "").lstrip("./")
            if sensitive(relative):
                continue
            results.append({
                "path": relative,
                "line_number": data.get("line_number"),
                "text": data["lines"].get("text", "")[:4000],
                "submatches": data.get("submatches", []),
            })
            if len(results) >= maximum:
                truncated = True
                process.terminate()
                break
        _, stderr = process.communicate()
        if process.returncode not in (0, 1, -15) and not truncated:
            raise ValueError("remote rg failed: " + stderr[-1000:])
    elif list_dir is not None:
        directory = root if list_dir == "." else target_path(root, list_dir, allow_missing=True)
        if not os.path.isdir(directory) or os.path.islink(directory):
            raise ValueError("list target is not a directory")
        for entry in sorted(os.scandir(directory), key=lambda value: value.name.lower()):
            relative = os.path.relpath(entry.path, root).replace(os.sep, "/")
            if sensitive(relative):
                continue
            results.append({"path": relative, "type": "directory" if entry.is_dir(follow_symlinks=False) else "file"})
            if len(results) >= maximum:
                truncated = True
                break
    else:
        patterns = globs or ([name_pattern] if name_pattern else [])
        for relative in walk_files(root):
            name = relative.rsplit("/", 1)[-1]
            if name_pattern and not fnmatch.fnmatch(name, name_pattern):
                continue
            if globs and not any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern) for pattern in globs):
                continue
            results.append({"path": relative, "type": "file"})
            if len(results) >= maximum:
                truncated = True
                break
    return {"remote_root_real": root, "results": results, "truncated": truncated}

def main():
    try:
        request = json.load(sys.stdin)
        operation = request.pop("operation")
        handlers = {"inspect": inspect, "status": statuses, "commit": commit, "search": search, "find": find_files, "tree": tree}
        result = handlers[operation](request)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    except Exception as exc:
        code = str(exc) if str(exc) in {"REMOTE_FILE_CHANGED", "REMOTE_FILE_CREATED", "RG_NOT_FOUND"} else "REMOTE_FILE_OPERATION_FAILED"
        print(json.dumps({"ok": False, "error": {"code": code, "message": str(exc), "details": getattr(exc, "details", {})}}, ensure_ascii=False))
        sys.exit(1)

main()
'''


def default_checkout_root() -> Path:
    configured = os.environ.get("SSHELP_CHECKOUT_ROOT") or os.environ.get("SSH_RESEARCH_CHECKOUT_ROOT")
    if configured:
        return Path(configured)
    work_root = os.environ.get("SSHELP_WORK_ROOT")
    return (Path(work_root) if work_root else Path.cwd() / ".sshelp") / "checkouts"


def add_checkout_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--checkout-root",
        type=Path,
        default=default_checkout_root(),
        help="Checkout parent. Defaults to <current project>/.sshelp/checkouts.",
    )


def add_sftp_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sftp-bin",
        default=os.environ.get("SSHELP_SFTP_BIN") or os.environ.get("SSH_RESEARCH_SFTP_BIN", "sftp"),
        help="OpenSSH SFTP client executable.",
    )


def validate_checkout_id(checkout_id: str) -> str:
    if not CHECKOUT_ID_RE.fullmatch(checkout_id):
        raise SkillError("INVALID_CHECKOUT_ID", "checkout id must be 8-32 lowercase hexadecimal characters")
    return checkout_id


def validate_relative_path(raw: str) -> str:
    if not raw or raw.startswith("/") or "\x00" in raw or "\\" in raw:
        raise SkillError("INVALID_REMOTE_PATH", "file path must be a relative POSIX path")
    path = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        raise SkillError("INVALID_REMOTE_PATH", "file path cannot contain empty, dot, or parent components")
    normalized = path.as_posix()
    for part in path.parts:
        if any(character in '<>:"|?*' for character in part) or part.endswith((" ", ".")):
            raise SkillError("UNSUPPORTED_LOCAL_PATH", f"path cannot be represented safely on Windows: {raw}")
    if is_sensitive_path(normalized):
        raise SkillError("SENSITIVE_FILE_DENIED", f"checkout of sensitive file is denied: {normalized}")
    return normalized


def is_sensitive_path(relative: str) -> bool:
    name = PurePosixPath(relative).name.lower()
    return name in SENSITIVE_NAMES or any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def checkout_directory(checkout_root: Path, checkout_id: str) -> Path:
    checkout_id = validate_checkout_id(checkout_id)
    root = checkout_root.resolve()
    candidate = (root / checkout_id).resolve()
    if candidate.parent != root:
        raise SkillError("INVALID_CHECKOUT_PATH", "checkout path escapes checkout root")
    return candidate


def create_checkout_directory(checkout_root: Path) -> tuple[str, Path]:
    checkout_root.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        checkout_id = uuid.uuid4().hex[:8]
        directory = checkout_directory(checkout_root, checkout_id)
        try:
            if os.name == "nt":
                directory.mkdir()
            else:
                directory.mkdir(mode=0o700)
        except FileExistsError:
            continue
        (directory / "base").mkdir()
        (directory / "work").mkdir()
        return checkout_id, directory
    raise SkillError("CHECKOUT_ID_EXHAUSTED", "could not allocate a unique checkout id")


def manifest_path(checkout_root: Path, checkout_id: str) -> Path:
    return checkout_directory(checkout_root, checkout_id) / "manifest.json"


def load_manifest(
    checkout_root: Path,
    checkout_id: str,
    *,
    require_ready: bool = True,
) -> tuple[Path, dict[str, Any]]:
    directory = checkout_directory(checkout_root, checkout_id)
    path = directory / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillError("CHECKOUT_NOT_FOUND", f"checkout does not exist: {checkout_id}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillError("INVALID_MANIFEST", "checkout manifest is unreadable") from exc
    if data.get("checkout_id") != checkout_id or data.get("schema_version") != 1:
        raise SkillError("INVALID_MANIFEST", "checkout manifest identity or version is invalid")
    if require_ready and data.get("state") != "ready":
        raise SkillError(
            "CHECKOUT_INCOMPLETE",
            "checkout did not finish downloading; inspect it or discard it with file_abort.py",
            {"state": data.get("state")},
        )
    return directory, data


def write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    temporary = directory / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, directory / "manifest.json")


def hash_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def manifest_ssh_options(manifest: dict[str, Any]) -> SSHOptions:
    values = manifest["ssh"]
    return SSHOptions(
        ssh_bin=values["ssh_bin"],
        config=values.get("config"),
        known_hosts=values.get("known_hosts"),
        connect_timeout=int(values["connect_timeout"]),
        identity_file=values.get("identity_file"),
    )


def serialize_ssh_options(options: SSHOptions, sftp_bin: str) -> dict[str, Any]:
    return {
        "ssh_bin": options.ssh_bin,
        "sftp_bin": sftp_bin,
        "config": options.config,
        "known_hosts": options.known_hosts,
        "identity_file": options.identity_file,
        "connect_timeout": options.connect_timeout,
    }


def run_remote_helper(options: SSHOptions, host: str, operation: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    import base64

    validate_host(host)
    encoded = base64.b64encode(REMOTE_HELPER.encode("utf-8")).decode("ascii")
    launcher = f"import base64;exec(base64.b64decode({encoded!r}))"
    command = [options.ssh_bin]
    if options.config:
        command.extend(["-F", options.config])
    if options.known_hosts:
        command.extend(["-o", f"UserKnownHostsFile={options.known_hosts}"])
    if options.identity_file:
        command.extend(["-i", options.identity_file, "-o", "IdentitiesOnly=yes"])
    command.extend(["-o", "BatchMode=yes", "-o", f"ConnectTimeout={options.connect_timeout}", host, f"python3 -c {shell_quote(launcher)}"])
    body = json.dumps({"operation": operation, **payload}, ensure_ascii=False).encode("utf-8")
    try:
        result = subprocess.run(command, input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False, shell=False)
    except FileNotFoundError as exc:
        raise SkillError("SSH_NOT_FOUND", f"SSH executable not found: {options.ssh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError("REMOTE_FILE_TIMEOUT", "remote file operation timed out") from exc
    try:
        response = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        if result.returncode != 0:
            raise ssh_failure(result, "REMOTE_FILE_FAILED", "remote file operation failed")
        raise SkillError("INVALID_REMOTE_RESPONSE", "remote file helper returned invalid JSON")
    if not response.get("ok"):
        error = response.get("error", {})
        raise SkillError(error.get("code", "REMOTE_FILE_FAILED"), error.get("message", "remote file operation failed"), error.get("details") or {})
    if result.returncode != 0:
        raise ssh_failure(result, "REMOTE_FILE_FAILED", "remote file operation failed")
    return response


def sftp_quote(path: str) -> str:
    if "\n" in path or "\r" in path or "\x00" in path:
        raise SkillError("INVALID_SFTP_PATH", "SFTP paths cannot contain line breaks or NUL")
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_sftp_batch(options: SSHOptions, sftp_bin: str, host: str, commands: Iterable[str], timeout: int = 120) -> None:
    validate_host(host)
    command = [sftp_bin]
    if options.config:
        command.extend(["-F", options.config])
    if options.known_hosts:
        command.extend(["-o", f"UserKnownHostsFile={options.known_hosts}"])
    if options.identity_file:
        command.extend(["-i", options.identity_file, "-o", "IdentitiesOnly=yes"])
    command.extend(["-o", "BatchMode=yes", "-o", f"ConnectTimeout={options.connect_timeout}", "-b", "-", host])
    body = ("\n".join(commands) + "\n").encode("utf-8")
    try:
        result = subprocess.run(command, input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False, shell=False)
    except FileNotFoundError as exc:
        raise SkillError("SFTP_NOT_FOUND", f"SFTP executable not found: {sftp_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError("SFTP_TIMEOUT", "SFTP batch operation timed out") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise SkillError("SFTP_FAILED", "SFTP batch operation failed", {"returncode": result.returncode, "stderr": stderr[-2000:]})


def local_files(root: Path) -> dict[str, Path]:
    values: dict[str, Path] = {}
    if not root.exists():
        return values
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SkillError("LOCAL_SYMLINK_DENIED", f"local checkout contains a symbolic link: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            validate_relative_path(relative)
            values[relative] = path
    return values


def classify_local_changes(directory: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    base_files = {item["relative_path"]: item for item in manifest["files"]}
    work_paths = local_files(directory / "work")
    statuses: list[dict[str, Any]] = []
    for relative, item in base_files.items():
        work_path = work_paths.pop(relative, None)
        if work_path is None:
            statuses.append({"path": relative, "state": "deleted-local", "base_sha256": item["base_sha256"]})
            continue
        work_hash = hash_file(work_path)
        statuses.append({
            "path": relative,
            "state": "clean" if work_hash == item["base_sha256"] else "modified-local",
            "base_sha256": item["base_sha256"],
            "work_sha256": work_hash,
            "size": work_path.stat().st_size,
        })
    for relative, work_path in sorted(work_paths.items()):
        statuses.append({"path": relative, "state": "added-local", "work_sha256": hash_file(work_path), "size": work_path.stat().st_size})
    return statuses


def remove_checkout(checkout_root: Path, checkout_id: str) -> None:
    directory = checkout_directory(checkout_root, checkout_id)
    if not directory.exists():
        raise SkillError("CHECKOUT_NOT_FOUND", f"checkout does not exist: {checkout_id}")
    if directory.is_symlink() or not directory.is_dir():
        raise SkillError("INVALID_CHECKOUT_PATH", "checkout path is not a normal directory")
    shutil.rmtree(directory)
