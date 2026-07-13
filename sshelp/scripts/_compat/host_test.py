#!/usr/bin/env python3
"""Validate SSH authentication and remote task prerequisites."""

from __future__ import annotations

import argparse

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    invoke,
    run_ssh,
    run_ssh_config,
    ssh_options_from_args,
    validate_host,
)


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="SSH host alias.")
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    options = ssh_options_from_args(args)
    resolved = run_ssh_config(options, host)
    remote = r"""set -eu
printf 'kernel=%s\n' "$(uname -s 2>/dev/null || true)"
printf 'machine=%s\n' "$(uname -m 2>/dev/null || true)"
printf 'tmux=%s\n' "$(command -v tmux 2>/dev/null || true)"
printf 'tmux_version=%s\n' "$(tmux -V 2>/dev/null || true)"
ttyd_path=$(command -v ttyd 2>/dev/null || true)
[ -n "$ttyd_path" ] || [ ! -x "$HOME/.local/bin/ttyd" ] || ttyd_path="$HOME/.local/bin/ttyd"
printf 'ttyd=%s\n' "$ttyd_path"
printf 'home_writable=%s\n' "$([ -w "$HOME" ] && printf yes || printf no)"
for tool in sh base64 dd wc tr cat chmod mkdir; do
  command -v "$tool" >/dev/null 2>&1 || printf 'missing=%s\n' "$tool"
done
"""
    result = run_ssh(options, host, remote)
    values: dict[str, str] = {}
    missing: list[str] = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key == "missing":
            missing.append(value)
        else:
            values[key] = value
    if values.get("kernel") != "Linux":
        raise SkillError("UNSUPPORTED_REMOTE", "remote host must run Linux", values)
    if not values.get("tmux"):
        raise SkillError("TMUX_MISSING", "tmux is required on the remote host", values)
    if values.get("home_writable") != "yes":
        raise SkillError("HOME_NOT_WRITABLE", "remote home directory is not writable", values)
    if missing:
        raise SkillError(
            "REMOTE_TOOLS_MISSING", "required remote tools are missing", {"tools": missing}
        )
    return {
        "host": host,
        "resolved": {
            "hostname": resolved.get("hostname"),
            "user": resolved.get("user"),
            "port": resolved.get("port"),
        },
        "remote": {
            "kernel": values.get("kernel"),
            "machine": values.get("machine"),
            "tmux_version": values.get("tmux_version"),
            "ttyd_available": bool(values.get("ttyd")),
        },
    }


if __name__ == "__main__":
    invoke(run)
