#!/usr/bin/env python3
"""Interrupt or terminate a remote tmux task without using SIGKILL."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    resolve_job_session_shell,
    run_ssh,
    ssh_failure,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--mode", choices=("interrupt", "terminate"), default="interrupt")
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    job_id = validate_job_id(args.job_id)
    options = ssh_options_from_args(args)
    resolver = resolve_job_session_shell(job_id)
    if args.mode == "interrupt":
        action = "tmux send-keys -t \"$session:0.0\" C-c"
    else:
        action = (
            "pid=$(tmux display-message -p -t \"$session:0.0\" '#{pane_pid}'); "
            "[ -n \"$pid\" ] && kill -TERM -- \"$pid\""
        )
    remote = f"{resolver}; {action}"
    result = run_ssh(options, host, remote, check=False)
    if result.returncode == 44:
        raise SkillError("JOB_NOT_FOUND", "tmux task session does not exist")
    if result.returncode != 0:
        raise ssh_failure(
            result, "JOB_STOP_FAILED", "failed to stop remote task"
        )
    return {"job_id": job_id, "mode": args.mode, "signal_sent": True}


if __name__ == "__main__":
    invoke(run)
