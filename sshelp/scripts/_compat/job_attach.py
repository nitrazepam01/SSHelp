#!/usr/bin/env python3
"""Attach the current terminal to the same tmux pane observed by the Agent."""

from __future__ import annotations

import argparse
import subprocess
import sys

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    build_ssh_command,
    emit_error,
    resolve_job_session_shell,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--interactive", action="store_true")
    add_ssh_arguments(parser)
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        host = validate_host(args.host)
        job_id = validate_job_id(args.job_id)
        options = ssh_options_from_args(args)
        read_only = "" if args.interactive else "-r "
        remote = f"{resolve_job_session_shell(job_id)}; exec tmux attach-session {read_only}-t \"$session\""
        command = build_ssh_command(options, host, remote, batch=True, tty=True)
        return subprocess.call(command, shell=False)
    except SkillError as exc:
        emit_error(exc)
        return 1
    except FileNotFoundError:
        emit_error(SkillError("SSH_NOT_FOUND", "SSH executable was not found"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
