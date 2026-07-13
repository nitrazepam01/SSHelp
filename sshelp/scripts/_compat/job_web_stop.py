#!/usr/bin/env python3
"""Stop the exact ttyd tmux observer associated with one task."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    legacy_web_session_name,
    run_ssh,
    shell_quote,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
    web_session_name,
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
    web = web_session_name(job_id)
    legacy_web = legacy_web_session_name(job_id)
    remote = (
        f"if tmux has-session -t {shell_quote(web)} 2>/dev/null; then "
        f"tmux kill-session -t {shell_quote(web)}; printf '%s' {shell_quote(web)}; "
        f"elif tmux has-session -t {shell_quote(legacy_web)} 2>/dev/null; then "
        f"tmux kill-session -t {shell_quote(legacy_web)}; printf '%s' {shell_quote(legacy_web)}; "
        "else printf missing; fi"
    )
    result = run_ssh(options, host, remote)
    state = result.stdout.decode("utf-8", errors="replace").strip()
    return {"job_id": job_id, "web_session": None if state == "missing" else state, "state": "missing" if state == "missing" else "stopped"}


if __name__ == "__main__":
    invoke(run)
