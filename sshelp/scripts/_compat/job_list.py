#!/usr/bin/env python3
"""List SSHelp-managed tmux tasks on a remote host."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    parse_pane_status,
    run_ssh,
    ssh_options_from_args,
    validate_host,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    options = ssh_options_from_args(args)
    remote = r"""tmux list-sessions -F '#{session_name}' 2>/dev/null | while IFS= read -r name; do
case "$name" in
  sshelp-observer-*|srd-observer-*) continue ;;
  sshelp-*|srd-*)
    pane_info=$(tmux display-message -p -t "$name:0.0" '#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}|#{pane_pid}|#{pane_current_command}')
    printf '%s|%s\n' "$name" "$pane_info"
    ;;
esac
done
"""
    result = run_ssh(options, host, remote)
    jobs: list[dict[str, object]] = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        session, separator, raw_status = line.partition("|")
        if not separator or not session.startswith(("sshelp-", "srd-")):
            continue
        status = parse_pane_status(raw_status)
        prefix = "sshelp-" if session.startswith("sshelp-") else "srd-"
        jobs.append(
            {"job_id": session[len(prefix) :], "session": session, **status}
        )
    return {"host": host, "jobs": jobs}


if __name__ == "__main__":
    invoke(run)
