#!/usr/bin/env python3
"""Start a persistent command in a remote tmux pane."""

from __future__ import annotations

import argparse
import base64
import json
import shlex
import uuid
from datetime import datetime, timezone

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    build_ssh_command,
    invoke,
    legacy_session_name,
    run_ssh,
    session_name,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_cwd,
    validate_host,
    validate_job_id,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--job-id")
    add_ssh_arguments(parser)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def generate_job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    cwd = validate_cwd(args.cwd)
    options = ssh_options_from_args(args)
    job_id = validate_job_id(args.job_id or generate_job_id())
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SkillError("COMMAND_REQUIRED", "a command is required after --")
    if any("\x00" in item for item in command):
        raise SkillError("INVALID_COMMAND", "command arguments must not contain NUL")

    session = session_name(job_id)
    legacy_session = legacy_session_name(job_id)
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema_version": 1,
        "job_id": job_id,
        "host": host,
        "cwd": cwd,
        "command": command,
        "session": session,
        "created_at": created_at,
    }
    run_script = "#!/bin/sh\nset -eu\ncd -- " + shlex.quote(cwd) + "\nexec " + shlex.join(command) + "\n"
    metadata_b64 = base64.b64encode(
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    run_b64 = base64.b64encode(run_script.encode("utf-8")).decode("ascii")

    remote = f"""set -eu
job_id={shell_quote(job_id)}
session={shell_quote(session)}
cwd={shell_quote(cwd)}
root="$HOME/.sshelp/jobs"
job_dir="$root/$job_id"
umask 077
legacy_session={shell_quote(legacy_session)}
legacy_job_dir="$HOME/.ssh-research-debug/jobs/$job_id"
if tmux has-session -t "$session" 2>/dev/null || tmux has-session -t "$legacy_session" 2>/dev/null || [ -e "$job_dir" ] || [ -e "$legacy_job_dir" ]; then
  exit 73
fi
mkdir -p "$job_dir"
printf '%s' {shell_quote(metadata_b64)} | base64 -d > "$job_dir/metadata.json"
printf '%s' {shell_quote(run_b64)} | base64 -d > "$job_dir/run.sh"
chmod 700 "$job_dir" "$job_dir/run.sh"
chmod 600 "$job_dir/metadata.json"
: > "$job_dir/output.ansi"
chmod 600 "$job_dir/output.ansi"
tmux new-session -d -s "$session" -c "$cwd"
tmux set-window-option -t "$session:0" remain-on-exit on
tmux set-window-option -t "$session:0" history-limit 200000
tmux pipe-pane -O -t "$session:0.0" "cat >> \"$job_dir/output.ansi\""
tmux respawn-pane -k -t "$session:0.0" -c "$cwd" "exec \"$job_dir/run.sh\""
"""
    result = run_ssh(options, host, remote, check=False)
    if result.returncode == 73:
        raise SkillError("JOB_EXISTS", "job id or tmux session already exists")
    if result.returncode != 0:
        raise ssh_failure(
            result, "JOB_START_FAILED", "failed to create the remote tmux task"
        )

    attach_remote = f"tmux attach-session -r -t {shell_quote(session)}"
    return {
        "job_id": job_id,
        "session": session,
        "state": "running",
        "offset": 0,
        "created_at": created_at,
        "attach_argv": build_ssh_command(
            options, host, attach_remote, batch=True, tty=True
        ),
    }


if __name__ == "__main__":
    invoke(run)
