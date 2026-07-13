#!/usr/bin/env python3
"""SSHelp's unified command-line entry point."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from _diagnostics_common import run_remote_diagnostics
from _remote_files_common import run_remote_helper
from _ssh_common import (
    DEFAULT_COMMAND_TIMEOUT,
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    build_ssh_command,
    invoke,
    run_ssh,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_cwd,
    validate_host,
    validate_job_id,
)


DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024

# Keep proven action implementations behind one public command.
DELEGATED_ACTIONS = {
    ("host", "test"): "host_test.py",
    ("job", "start"): "job_start.py",
    ("job", "read"): "job_read.py",
    ("job", "status"): "job_status.py",
    ("job", "list"): "job_list.py",
    ("job", "input"): "job_input.py",
    ("job", "stop"): "job_stop.py",
    ("job", "attach"): "job_attach.py",
    ("web", "start"): "job_web_start.py",
    ("web", "stop"): "job_web_stop.py",
    ("file", "checkout"): "file_checkout.py",
    ("file", "status"): "file_status.py",
    ("file", "diff"): "file_diff.py",
    ("file", "commit"): "file_commit.py",
    ("file", "abort"): "file_abort.py",
}


def add_connection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", required=True)
    add_ssh_arguments(parser)


def add_remote_root(parser: argparse.ArgumentParser) -> None:
    add_connection(parser)
    parser.add_argument("--root", required=True)
    parser.add_argument("--max-results", type=int, default=200)


def nested(parent: argparse.ArgumentParser, name: str) -> argparse._SubParsersAction:
    group = parent.add_subparsers(dest=name, required=True, parser_class=JsonArgumentParser)
    return group


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    commands = nested(parser, "area")

    host = commands.add_parser("host", help="Validate an SSH host and SSHelp prerequisites.")
    host_commands = nested(host, "host_action")
    host_commands.add_parser("test", help="Test authentication and remote dependencies.")
    install = host_commands.add_parser("install", help="Install fixed SSHelp prerequisites on a new Linux host.")
    add_connection(install)
    install.add_argument("--yes", action="store_true", help="Confirm remote package installation.")
    install.add_argument("--skip-ttyd", action="store_true", help="Install core tools without ttyd.")
    install.add_argument("--ttyd-version", default="1.7.7", help="Pinned official ttyd release version.")

    execute = commands.add_parser("exec", help="Run one bounded non-interactive SSH command.")
    add_connection(execute)
    execute.add_argument("--cwd", required=True)
    execute.add_argument("--timeout", type=int, default=DEFAULT_COMMAND_TIMEOUT)
    execute.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES)
    execute.add_argument("command", nargs=argparse.REMAINDER)

    remote = commands.add_parser("remote", help="Locate remote files without checking them out.")
    remote_commands = nested(remote, "remote_action")
    search = remote_commands.add_parser("search")
    add_remote_root(search)
    search.add_argument("--query", required=True)
    search.add_argument("--glob", action="append", default=[])

    find = remote_commands.add_parser("find")
    add_remote_root(find)
    find.add_argument("--name")
    find.add_argument("--glob", action="append", default=[])
    find.add_argument("--modified-within-seconds", type=int)

    tree = remote_commands.add_parser("tree")
    add_remote_root(tree)
    tree.add_argument("--path", default=".")
    tree.add_argument("--depth", type=int, default=2)

    process = commands.add_parser("process", help="Inspect read-only process state.")
    process_commands = nested(process, "process_action")
    process_list = process_commands.add_parser("list")
    add_connection(process_list)
    process_list.add_argument("--pattern")
    process_list.add_argument("--max-results", type=int, default=50)
    process_inspect = process_commands.add_parser("inspect")
    add_connection(process_inspect)
    process_inspect.add_argument("--job-id", required=True)

    resource = commands.add_parser("resource", help="Inspect host and optional job resources.")
    resource_commands = nested(resource, "resource_action")
    snapshot = resource_commands.add_parser("snapshot")
    add_connection(snapshot)
    snapshot.add_argument("--job-id")
    snapshot.add_argument("--path", default="/")

    port = commands.add_parser("port", help="Inspect a listening port owner.")
    port_commands = nested(port, "port_action")
    owner = port_commands.add_parser("owner")
    add_connection(owner)
    owner.add_argument("--port", type=int, required=True)

    gpu = commands.add_parser("gpu", help="Inspect NVIDIA GPU state when available.")
    gpu_commands = nested(gpu, "gpu_action")
    gpu_snapshot = gpu_commands.add_parser("snapshot")
    add_connection(gpu_snapshot)

    job = commands.add_parser("job", help="Start, observe, control, or diagnose a persistent job.")
    job_commands = nested(job, "job_action")
    for action, description in (
        ("start", "Start a persistent tmux job."),
        ("read", "Read new output by byte offset."),
        ("status", "Read pane state and exit status."),
        ("list", "List SSHelp-managed jobs."),
        ("input", "Send approved text or control keys."),
        ("stop", "Interrupt or terminate an exact job."),
        ("attach", "Attach the current terminal to a job."),
    ):
        job_commands.add_parser(action, help=description)
    diagnose = job_commands.add_parser("diagnose", help="Diagnose a quiet or suspicious running job.")
    add_connection(diagnose)
    diagnose.add_argument("--job-id", required=True)

    web = commands.add_parser("web", help="Manage a loopback-only read-only Web observer.")
    web_commands = nested(web, "web_action")
    web_commands.add_parser("start", help="Start an observer and return tunnel arguments.")
    web_commands.add_parser("stop", help="Stop the exact observer for one job.")

    file_group = commands.add_parser("file", help="Manage transactional local file checkouts.")
    file_commands = nested(file_group, "file_action")
    for action, description in (
        ("checkout", "Download selected files into the project work area."),
        ("status", "Compare base, work, and optional remote state."),
        ("diff", "Return the base-to-work diff."),
        ("commit", "Conflict-check and atomically commit changes."),
        ("abort", "Discard one exact local checkout."),
    ):
        file_commands.add_parser(action, help=description)
    return parser.parse_args()


def validate_limit(value: int, *, maximum: int = 5000) -> int:
    if value < 1 or value > maximum:
        raise SkillError("INVALID_LIMIT", f"limit must be between 1 and {maximum}")
    return value


def validate_directory_relative(value: str) -> str:
    if value == ".":
        return value
    if not value or value.startswith("/") or "\x00" in value or "\\" in value:
        raise SkillError("INVALID_REMOTE_PATH", "tree path must be a relative POSIX directory")
    path = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in path.parts):
        raise SkillError("INVALID_REMOTE_PATH", "tree path cannot contain dot or parent components")
    return path.as_posix()


def decode_output(data: bytes, maximum: int) -> tuple[str, bool, int]:
    original = len(data)
    truncated = original > maximum
    return data[:maximum].decode("utf-8", errors="replace"), truncated, original


def run_exec(args: argparse.Namespace) -> dict[str, object]:
    host = validate_host(args.host)
    cwd = validate_cwd(args.cwd)
    if not 1 <= args.timeout <= 300:
        raise SkillError("INVALID_TIMEOUT", "exec timeout must be between 1 and 300 seconds")
    if not 1024 <= args.max_output_bytes <= 16 * 1024 * 1024:
        raise SkillError("INVALID_OUTPUT_LIMIT", "max output bytes must be between 1024 and 16777216")
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SkillError("COMMAND_REQUIRED", "a command is required after --")
    if any("\x00" in value for value in command):
        raise SkillError("INVALID_COMMAND", "command arguments cannot contain NUL")
    options = ssh_options_from_args(args)
    remote = f"cd -- {shell_quote(cwd)} && exec {shlex.join(command)}"
    ssh_command = build_ssh_command(options, host, remote)
    started = time.perf_counter()
    try:
        result = subprocess.run(
            ssh_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("SSH_NOT_FOUND", f"SSH executable not found: {options.ssh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"") if isinstance(exc.stdout, bytes) else str(exc.stdout or "").encode()
        stderr = (exc.stderr or b"") if isinstance(exc.stderr, bytes) else str(exc.stderr or "").encode()
        raise SkillError(
            "EXEC_TIMEOUT",
            "one-shot SSH command exceeded its timeout",
            {
                "timeout_seconds": args.timeout,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "stdout": decode_output(stdout, args.max_output_bytes)[0],
                "stderr": decode_output(stderr, args.max_output_bytes)[0],
            },
        ) from exc
    duration_ms = round((time.perf_counter() - started) * 1000)
    if result.returncode == 255:
        raise ssh_failure(result, "EXEC_SSH_FAILED", "one-shot SSH command failed before returning a reliable exit status")
    stdout, stdout_truncated, stdout_bytes = decode_output(result.stdout, args.max_output_bytes)
    stderr, stderr_truncated, stderr_bytes = decode_output(result.stderr, args.max_output_bytes)
    return {
        "host": host,
        "cwd": cwd,
        "command": command,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


def run_host_install(args: argparse.Namespace) -> dict[str, object]:
    """Install a fixed prerequisite set; never accept arbitrary package names."""
    if not args.yes:
        raise SkillError(
            "INSTALL_CONFIRMATION_REQUIRED",
            "host install changes the remote system; rerun with --yes after explicit authorization",
        )
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", args.ttyd_version):
        raise SkillError("INVALID_TTYD_VERSION", "ttyd version must contain only numeric dot-separated components")
    host = validate_host(args.host)
    options = ssh_options_from_args(args)
    install_ttyd = "no" if args.skip_ttyd else "yes"
    remote = f"""set -eu
install_ttyd={shell_quote(install_ttyd)}
ttyd_version={shell_quote(args.ttyd_version)}
package_manager=none
missing_core=0
for tool in tmux python3 rg; do command -v "$tool" >/dev/null 2>&1 || missing_core=1; done
need_downloader=0
if [ "$install_ttyd" = yes ] && ! command -v ttyd >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/ttyd" ]; then
  command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || need_downloader=1
fi
if [ "$missing_core" -eq 1 ] || [ "$need_downloader" -eq 1 ]; then
  if [ "$(id -u)" -eq 0 ]; then elevate=""
  elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then elevate="sudo -n"
  else exit 77; fi
  if command -v apt-get >/dev/null 2>&1; then
    package_manager=apt
    $elevate apt-get update
    $elevate env DEBIAN_FRONTEND=noninteractive apt-get install -y tmux ripgrep python3 ca-certificates curl
  elif command -v dnf >/dev/null 2>&1; then
    package_manager=dnf
    $elevate dnf install -y tmux ripgrep python3 ca-certificates curl
  elif command -v pacman >/dev/null 2>&1; then
    package_manager=pacman
    $elevate pacman -Sy --noconfirm tmux ripgrep python ca-certificates curl
  elif command -v zypper >/dev/null 2>&1; then
    package_manager=zypper
    $elevate zypper --non-interactive install tmux ripgrep python3 ca-certificates curl
  elif command -v apk >/dev/null 2>&1; then
    package_manager=apk
    $elevate apk add tmux ripgrep python3 ca-certificates curl
  else exit 78; fi
fi
ttyd_path=$(command -v ttyd 2>/dev/null || true)
if [ "$install_ttyd" = yes ] && [ -z "$ttyd_path" ]; then
  if [ -x "$HOME/.local/bin/ttyd" ]; then ttyd_path="$HOME/.local/bin/ttyd"
  else
    case "$(uname -m)" in
      x86_64|amd64) asset=ttyd.x86_64 ;;
      aarch64|arm64) asset=ttyd.aarch64 ;;
      armv7l|armhf) asset=ttyd.armhf ;;
      *) exit 80 ;;
    esac
    mkdir -p "$HOME/.local/bin"
    tmp="$HOME/.local/bin/.ttyd.sshelp.$$"
    trap 'rm -f -- "$tmp"' EXIT
    url="https://github.com/tsl0922/ttyd/releases/download/$ttyd_version/$asset"
    if command -v curl >/dev/null 2>&1; then curl --fail --location --proto '=https' --tlsv1.2 "$url" --output "$tmp"
    elif command -v wget >/dev/null 2>&1; then wget --https-only -O "$tmp" "$url"
    else exit 81; fi
    chmod 700 "$tmp"
    "$tmp" --version >/dev/null 2>&1 || exit 82
    mv -f -- "$tmp" "$HOME/.local/bin/ttyd"
    trap - EXIT
    ttyd_path="$HOME/.local/bin/ttyd"
  fi
fi
printf 'package_manager=%s\n' "$package_manager"
printf 'tmux=%s\n' "$(tmux -V 2>/dev/null || true)"
printf 'python=%s\n' "$(python3 --version 2>&1 || true)"
printf 'rg=%s\n' "$(rg --version 2>/dev/null | head -n 1 || true)"
printf 'ttyd_path=%s\n' "$ttyd_path"
printf 'ttyd=%s\n' "$([ -n "$ttyd_path" ] && "$ttyd_path" --version 2>&1 || true)"
"""
    result = run_ssh(options, host, remote, timeout=900, check=False)
    errors = {
        77: ("INSTALL_PRIVILEGE_REQUIRED", "missing core packages require root or passwordless sudo"),
        78: ("PACKAGE_MANAGER_UNSUPPORTED", "no supported Linux package manager was found"),
        80: ("TTYD_ARCH_UNSUPPORTED", "no pinned ttyd binary is configured for this architecture"),
        81: ("TTYD_DOWNLOADER_MISSING", "curl or wget is required to install ttyd"),
        82: ("TTYD_VERIFY_FAILED", "downloaded ttyd binary failed its version check"),
    }
    if result.returncode in errors:
        raise SkillError(*errors[result.returncode])
    if result.returncode != 0:
        raise ssh_failure(result, "HOST_INSTALL_FAILED", "failed to install SSHelp prerequisites")
    values = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return {
        "host": host,
        "package_manager": values.get("package_manager"),
        "tools": {
            "tmux": values.get("tmux"),
            "python": values.get("python"),
            "ripgrep": values.get("rg"),
            "ttyd": values.get("ttyd") or None,
            "ttyd_path": values.get("ttyd_path") or None,
        },
    }


def run_remote(args: argparse.Namespace) -> dict[str, object]:
    host = validate_host(args.host)
    root = validate_cwd(args.root)
    maximum = validate_limit(args.max_results)
    options = ssh_options_from_args(args)
    if args.remote_action == "search":
        if not args.query or "\x00" in args.query or len(args.query) > 4096:
            raise SkillError("INVALID_QUERY", "query must contain 1-4096 characters and no NUL")
        response = run_remote_helper(options, host, "search", {"root": root, "query": args.query, "name": None, "globs": args.glob, "list_dir": None, "max_results": maximum}, timeout=120)
    elif args.remote_action == "find":
        if not args.name and not args.glob and args.modified_within_seconds is None:
            raise SkillError("FIND_FILTER_REQUIRED", "remote find requires --name, --glob, or --modified-within-seconds")
        if args.modified_within_seconds is not None and args.modified_within_seconds < 1:
            raise SkillError("INVALID_TIME_RANGE", "modified-within-seconds must be positive")
        response = run_remote_helper(options, host, "find", {"root": root, "name": args.name, "globs": args.glob, "modified_within_seconds": args.modified_within_seconds, "max_results": maximum}, timeout=120)
    else:
        if not 1 <= args.depth <= 8:
            raise SkillError("INVALID_DEPTH", "tree depth must be between 1 and 8")
        response = run_remote_helper(options, host, "tree", {"root": root, "path": validate_directory_relative(args.path), "depth": args.depth, "max_results": maximum}, timeout=120)
    return {"host": host, "remote_root": response["remote_root_real"], "results": response["results"], "truncated": response["truncated"]}


def run_diagnostic(args: argparse.Namespace) -> dict[str, object]:
    host = validate_host(args.host)
    options = ssh_options_from_args(args)
    if args.area == "process" and args.process_action == "list":
        operation = "process_list"
        payload = {"pattern": args.pattern, "max_results": validate_limit(args.max_results, maximum=500)}
    elif args.area == "process":
        operation = "process_inspect"
        payload = {"job_id": validate_job_id(args.job_id)}
    elif args.area == "resource":
        operation = "resource_snapshot"
        payload = {"job_id": validate_job_id(args.job_id) if args.job_id else None, "path": validate_cwd(args.path)}
    elif args.area == "port":
        if not 1 <= args.port <= 65535:
            raise SkillError("INVALID_PORT", "port must be between 1 and 65535")
        operation = "port_owner"
        payload = {"port": args.port}
    elif args.area == "gpu":
        operation = "gpu_snapshot"
        payload = {}
    else:
        operation = "job_diagnose"
        payload = {"job_id": validate_job_id(args.job_id)}
    response = run_remote_diagnostics(options, host, operation, payload, timeout=90)
    response.pop("ok", None)
    return {"host": host, **response}


def run() -> dict[str, object]:
    args = parse_args()
    if args.area == "host":
        return run_host_install(args)
    if args.area == "exec":
        return run_exec(args)
    if args.area == "remote":
        return run_remote(args)
    return run_diagnostic(args)


def run_legacy_action(argv: list[str]) -> int | None:
    """Forward compatibility commands without changing their JSON contracts."""
    if len(argv) < 2:
        return None
    script_name = DELEGATED_ACTIONS.get((argv[0], argv[1]))
    if script_name is None:
        return None
    scripts_dir = Path(__file__).resolve().parent
    command = [sys.executable, str(scripts_dir / "_compat" / script_name), *argv[2:]]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(scripts_dir) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.call(command, shell=False, env=env)


def main() -> int:
    delegated = run_legacy_action(sys.argv[1:])
    if delegated is not None:
        return delegated
    invoke(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
