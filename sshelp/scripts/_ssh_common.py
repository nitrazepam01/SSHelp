#!/usr/bin/env python3
"""Shared OpenSSH, validation, and JSON helpers for SSHelp."""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable


SESSION_PREFIX = "sshelp-"
LEGACY_SESSION_PREFIX = "srd-"
WEB_SESSION_PREFIX = "sshelp-observer-"
LEGACY_WEB_SESSION_PREFIX = "srd-observer-"
REMOTE_JOB_ROOT = "$HOME/.sshelp/jobs"
LEGACY_REMOTE_JOB_ROOT = "$HOME/.ssh-research-debug/jobs"
DEFAULT_CONNECT_TIMEOUT = 8
DEFAULT_COMMAND_TIMEOUT = 30
DEFAULT_MAX_READ_BYTES = 256 * 1024
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ANSI_RE = re.compile(
    r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\))|"
    r"(?:\x1b[@-_][0-?]*[ -/]*[@-~])"
)


class SkillError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SkillError("INVALID_ARGUMENTS", message)


@dataclass(frozen=True)
class SSHOptions:
    ssh_bin: str
    config: str | None
    known_hosts: str | None
    connect_timeout: int
    identity_file: str | None = None


def _env(primary: str, legacy: str, default: str | None = None) -> str | None:
    """Prefer SSHelp names while accepting legacy configuration during migration."""
    return os.environ.get(primary) or os.environ.get(legacy) or default


def add_ssh_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ssh-bin",
        default=_env("SSHELP_SSH_BIN", "SSH_RESEARCH_SSH_BIN", "ssh"),
        help="OpenSSH client executable.",
    )
    parser.add_argument(
        "--ssh-config",
        default=_env("SSHELP_SSH_CONFIG", "SSH_RESEARCH_CONFIG"),
        help="Explicit SSH config path. Defaults to OpenSSH discovery.",
    )
    parser.add_argument(
        "--known-hosts",
        default=_env("SSHELP_KNOWN_HOSTS", "SSH_RESEARCH_KNOWN_HOSTS"),
        help="Explicit known_hosts path.",
    )
    parser.add_argument(
        "--identity-file",
        default=_env("SSHELP_IDENTITY_FILE", "SSH_RESEARCH_IDENTITY_FILE"),
        help="Explicit private key path. The key content is never read by the script.",
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=DEFAULT_CONNECT_TIMEOUT,
        help="SSH connection timeout in seconds.",
    )


def ssh_options_from_args(args: argparse.Namespace) -> SSHOptions:
    if args.connect_timeout < 1 or args.connect_timeout > 300:
        raise SkillError(
            "INVALID_TIMEOUT", "connect timeout must be between 1 and 300 seconds"
        )
    return SSHOptions(
        ssh_bin=args.ssh_bin,
        config=args.ssh_config,
        known_hosts=args.known_hosts,
        connect_timeout=args.connect_timeout,
        identity_file=getattr(args, "identity_file", None),
    )


def validate_host(host: str) -> str:
    if not host or host.startswith("-") or len(host) > 255:
        raise SkillError("INVALID_HOST", "invalid SSH host or alias")
    if any(ch.isspace() or ch == "\x00" for ch in host):
        raise SkillError("INVALID_HOST", "SSH host must not contain whitespace")
    return host


def validate_job_id(job_id: str) -> str:
    if not JOB_ID_RE.fullmatch(job_id):
        raise SkillError(
            "INVALID_JOB_ID",
            "job id must contain only letters, digits, underscore, and hyphen",
        )
    return job_id


def validate_cwd(cwd: str) -> str:
    if not cwd.startswith("/") or "\x00" in cwd:
        raise SkillError("INVALID_CWD", "remote working directory must be absolute")
    return cwd


def session_name(job_id: str) -> str:
    return SESSION_PREFIX + validate_job_id(job_id)


def legacy_session_name(job_id: str) -> str:
    return LEGACY_SESSION_PREFIX + validate_job_id(job_id)


def session_names(job_id: str) -> tuple[str, str]:
    return session_name(job_id), legacy_session_name(job_id)


def resolve_job_session_shell(job_id: str, variable: str = "session") -> str:
    """Return safe remote shell code that prefers the new session name."""
    current, legacy = session_names(job_id)
    return (
        f"if tmux has-session -t {shell_quote(current)} 2>/dev/null; then {variable}={shell_quote(current)}; "
        f"elif tmux has-session -t {shell_quote(legacy)} 2>/dev/null; then {variable}={shell_quote(legacy)}; "
        "else exit 44; fi"
    )


def web_session_name(job_id: str) -> str:
    return WEB_SESSION_PREFIX + validate_job_id(job_id)


def legacy_web_session_name(job_id: str) -> str:
    return LEGACY_WEB_SESSION_PREFIX + validate_job_id(job_id)


def web_session_names(job_id: str) -> tuple[str, str]:
    return web_session_name(job_id), legacy_web_session_name(job_id)


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def build_ssh_command(
    options: SSHOptions,
    host: str,
    remote_command: str | None = None,
    *,
    batch: bool = True,
    tty: bool = False,
    extra_options: Iterable[str] = (),
) -> list[str]:
    validate_host(host)
    command = [options.ssh_bin]
    if options.config:
        command.extend(["-F", options.config])
    if options.known_hosts:
        command.extend(["-o", f"UserKnownHostsFile={options.known_hosts}"])
    if options.identity_file:
        command.extend(["-i", options.identity_file, "-o", "IdentitiesOnly=yes"])
    if batch:
        command.extend(["-o", "BatchMode=yes"])
    command.extend(
        [
            "-o",
            f"ConnectTimeout={options.connect_timeout}",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
        ]
    )
    if tty:
        command.append("-tt")
    command.extend(extra_options)
    command.append(host)
    if remote_command is not None:
        command.append(remote_command)
    return command


def _classify_ssh_error(stderr: str) -> tuple[str, str]:
    lowered = stderr.lower()
    if "permission denied" in lowered:
        return "AUTH_FAILED", "SSH public-key or ssh-agent authentication failed"
    if "host key verification failed" in lowered or "remote host identification has changed" in lowered:
        return "HOST_KEY_FAILED", "SSH host key verification failed"
    if "could not resolve hostname" in lowered:
        return "HOST_NOT_FOUND", "SSH host name could not be resolved"
    if "connection timed out" in lowered or "operation timed out" in lowered:
        return "CONNECTION_TIMEOUT", "SSH connection timed out"
    if "connection refused" in lowered:
        return "CONNECTION_REFUSED", "SSH connection was refused"
    return "SSH_FAILED", "SSH command failed"


def ssh_failure(
    result: subprocess.CompletedProcess[bytes],
    default_code: str,
    default_message: str,
) -> SkillError:
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    code, message = _classify_ssh_error(stderr)
    if code == "SSH_FAILED":
        code, message = default_code, default_message
    return SkillError(
        code,
        message,
        {"returncode": result.returncode, "stderr": stderr[-2000:]},
    )


def run_ssh(
    options: SSHOptions,
    host: str,
    remote_command: str,
    *,
    input_bytes: bytes | None = None,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = build_ssh_command(options, host, remote_command)
    try:
        result = subprocess.run(
            command,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("SSH_NOT_FOUND", f"SSH executable not found: {options.ssh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError("SSH_TIMEOUT", "SSH command exceeded its timeout") from exc

    if check and result.returncode != 0:
        raise ssh_failure(result, "SSH_FAILED", "SSH command failed")
    return result


def run_ssh_config(options: SSHOptions, host: str) -> dict[str, str]:
    validate_host(host)
    command = [options.ssh_bin]
    if options.config:
        command.extend(["-F", options.config])
    command.extend(["-G", host])
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("SSH_NOT_FOUND", f"SSH executable not found: {options.ssh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError("SSH_CONFIG_TIMEOUT", "ssh -G timed out") from exc
    if result.returncode != 0:
        raise SkillError(
            "SSH_CONFIG_FAILED",
            "could not expand SSH configuration",
            {"stderr": result.stderr.decode("utf-8", errors="replace")[-2000:]},
        )
    parsed: dict[str, str] = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        key, separator, value = line.partition(" ")
        if separator and key not in parsed:
            parsed[key] = value.strip()
    return parsed


def decode_utf8_prefix(data: bytes) -> tuple[str, int]:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text = decoder.decode(data, final=False)
    buffered, _ = decoder.getstate()
    return text, len(data) - len(buffered)


def normalize_terminal_text(text: str) -> str:
    text = ANSI_RE.sub("", text).replace("\x00", "")
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    normalized = [line.rsplit("\r", 1)[-1] for line in lines]
    return "\n".join(normalized)


def parse_pane_status(raw: str) -> dict[str, Any]:
    fields = raw.strip().split("|", 4)
    if len(fields) != 5:
        raise SkillError("INVALID_TMUX_STATUS", "unexpected tmux pane status response")
    dead, exit_code, signal, pid, command = fields
    state = "exited" if dead == "1" else "running"
    return {
        "state": state,
        "pid": int(pid) if pid.isdigit() else None,
        "exit_code": int(exit_code) if exit_code.lstrip("-").isdigit() else None,
        "signal": int(signal) if signal.isdigit() else (signal or None),
        "command": command or None,
    }


def emit_success(data: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"ok": True}
    if data:
        payload.update(data)
    print(json.dumps(payload, ensure_ascii=False))


def emit_error(error: SkillError) -> None:
    payload = {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        },
    }
    print(json.dumps(payload, ensure_ascii=False))


def cli_main(callback: Callable[[], dict[str, Any] | None]) -> int:
    try:
        emit_success(callback())
        return 0
    except SkillError as exc:
        emit_error(exc)
        return 1
    except KeyboardInterrupt:
        emit_error(SkillError("INTERRUPTED", "operation interrupted locally"))
        return 130
    except Exception as exc:  # Keep the CLI contract stable for unexpected failures.
        emit_error(SkillError("INTERNAL_ERROR", str(exc)))
        return 1


def invoke(callback: Callable[[], dict[str, Any] | None]) -> None:
    sys.exit(cli_main(callback))
