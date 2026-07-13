#!/usr/bin/env python3
"""Send approved text or control keys to a remote tmux task."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    resolve_job_session_shell,
    run_ssh,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
)


KEYS = {"ENTER": "Enter", "CTRL_C": "C-c", "CTRL_D": "C-d"}


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--key", choices=sorted(KEYS))
    parser.add_argument("--enter", action="store_true", help="Press Enter after text.")
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    job_id = validate_job_id(args.job_id)
    options = ssh_options_from_args(args)
    resolver = resolve_job_session_shell(job_id)

    if args.text is not None:
        if "\x00" in args.text:
            raise SkillError("INVALID_INPUT", "input text must not contain NUL")
        buffer_name = "sshelp-input-" + job_id
        remote = (
            f"{resolver}; "
            f"tmux load-buffer -b {shell_quote(buffer_name)} -; "
            f"tmux paste-buffer -b {shell_quote(buffer_name)} -t \"$session:0.0\" -d"
        )
        if args.enter:
            remote += "; tmux send-keys -t \"$session:0.0\" Enter"
        payload = args.text.encode("utf-8")
        action = "text"
    else:
        remote = (
            f"{resolver}; tmux send-keys -t \"$session:0.0\" {KEYS[args.key]}"
        )
        payload = None
        action = args.key

    result = run_ssh(options, host, remote, input_bytes=payload, check=False)
    if result.returncode == 44:
        raise SkillError("JOB_NOT_FOUND", "tmux task session does not exist")
    if result.returncode != 0:
        raise ssh_failure(
            result, "JOB_INPUT_FAILED", "failed to send input to remote task"
        )
    return {"job_id": job_id, "action": action, "sent": True}


if __name__ == "__main__":
    invoke(run)
