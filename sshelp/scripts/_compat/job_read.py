#!/usr/bin/env python3
"""Read only new bytes from a persistent remote task log."""

from __future__ import annotations

import argparse
import re

from _ssh_common import (
    DEFAULT_MAX_READ_BYTES,
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    decode_utf8_prefix,
    invoke,
    normalize_terminal_text,
    run_ssh,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
)


HEADER_RE = re.compile(rb"^SRD1 ([0-9]+) ([0-9]+) ([01])$")


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_READ_BYTES)
    parser.add_argument("--raw-ansi", action="store_true")
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    job_id = validate_job_id(args.job_id)
    if args.offset < 0:
        raise SkillError("INVALID_OFFSET", "offset must be non-negative")
    if args.max_bytes < 1 or args.max_bytes > DEFAULT_MAX_READ_BYTES:
        raise SkillError(
            "INVALID_MAX_BYTES", f"max bytes must be between 1 and {DEFAULT_MAX_READ_BYTES}"
        )
    options = ssh_options_from_args(args)
    remote = f"""set -eu
file="$HOME/.sshelp/jobs/{job_id}/output.ansi"
[ -f "$file" ] || file="$HOME/.ssh-research-debug/jobs/{job_id}/output.ansi"
[ -f "$file" ] || exit 44
size=$(wc -c < "$file" | tr -d ' ')
offset={args.offset}
reset=0
if [ "$offset" -gt "$size" ]; then
  offset=0
  reset=1
fi
printf 'SRD1 %s %s %s\n' "$size" "$offset" "$reset"
dd if="$file" bs=1 skip="$offset" count={args.max_bytes} 2>/dev/null
"""
    result = run_ssh(options, host, remote, check=False)
    if result.returncode == 44:
        raise SkillError("JOB_NOT_FOUND", "remote job log does not exist")
    if result.returncode != 0:
        raise ssh_failure(
            result, "JOB_READ_FAILED", "failed to read remote task output"
        )
    header, separator, data = result.stdout.partition(b"\n")
    match = HEADER_RE.fullmatch(header)
    if not separator or not match:
        raise SkillError("INVALID_READ_RESPONSE", "unexpected remote log response")
    observed_size = int(match.group(1))
    effective_offset = int(match.group(2))
    reset = match.group(3) == b"1"
    text, consumed = decode_utf8_prefix(data)
    if not args.raw_ansi:
        text = normalize_terminal_text(text)
    new_offset = effective_offset + consumed
    return {
        "job_id": job_id,
        "old_offset": args.offset,
        "new_offset": new_offset,
        "observed_size": max(observed_size, effective_offset + len(data)),
        "bytes_read": len(data),
        "bytes_consumed": consumed,
        "reset": reset,
        "truncated": observed_size > new_offset or len(data) >= args.max_bytes,
        "output": text,
    }


if __name__ == "__main__":
    invoke(run)
