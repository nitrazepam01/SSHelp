#!/usr/bin/env python3
"""Return the tmux pane state and exit status for a remote job."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    parse_pane_status,
    run_ssh,
    legacy_session_name,
    session_name,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    job_id = validate_job_id(args.job_id)
    options = ssh_options_from_args(args)
    session = session_name(job_id)
    legacy_session = legacy_session_name(job_id)
    remote = (
        f"if tmux has-session -t {shell_quote(session)} 2>/dev/null; then session={shell_quote(session)}; "
        f"elif tmux has-session -t {shell_quote(legacy_session)} 2>/dev/null; then session={shell_quote(legacy_session)}; "
        "else exit 44; fi; printf '%s\\n' \"$session\"; "
        "tmux display-message -p -t \"$session:0.0\" "
        "'#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}|#{pane_pid}|#{pane_current_command}'"
    )
    result = run_ssh(options, host, remote, check=False)
    if result.returncode == 44:
        return {"job_id": job_id, "session": session, "state": "missing"}
    if result.returncode != 0:
        raise ssh_failure(
            result, "JOB_STATUS_FAILED", "failed to read tmux pane state"
        )
    raw_session, separator, raw_status = result.stdout.decode("utf-8", errors="replace").partition("\n")
    if not separator:
        raise SkillError("INVALID_TMUX_STATUS", "missing resolved session name")
    status = parse_pane_status(raw_status)
    return {"job_id": job_id, "session": raw_session, **status}


if __name__ == "__main__":
    invoke(run)
