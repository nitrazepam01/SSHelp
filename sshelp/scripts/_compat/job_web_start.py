#!/usr/bin/env python3
"""Start a loopback-only ttyd observer and return the SSH tunnel command."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from _ssh_common import (
    JsonArgumentParser,
    SkillError,
    add_ssh_arguments,
    build_ssh_command,
    invoke,
    legacy_session_name,
    legacy_web_session_name,
    run_ssh,
    session_name,
    shell_quote,
    ssh_failure,
    ssh_options_from_args,
    validate_host,
    validate_job_id,
    web_session_name,
)


def valid_port(value: str) -> int:
    port = int(value)
    if port < 1024 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1024 and 65535")
    return port


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--remote-port", type=valid_port, default=7681)
    parser.add_argument("--local-port", type=valid_port, default=7681)
    add_ssh_arguments(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    host = validate_host(args.host)
    job_id = validate_job_id(args.job_id)
    options = ssh_options_from_args(args)
    target = session_name(job_id)
    legacy_target = legacy_session_name(job_id)
    web = web_session_name(job_id)
    legacy_web = legacy_web_session_name(job_id)
    observer_path = Path(__file__).with_name("remote_web_observer.py")
    observer_b64 = base64.b64encode(observer_path.read_bytes()).decode("ascii")
    remote = f"""set -eu
if tmux has-session -t {shell_quote(target)} 2>/dev/null; then target={shell_quote(target)}
elif tmux has-session -t {shell_quote(legacy_target)} 2>/dev/null; then target={shell_quote(legacy_target)}
else exit 44; fi
tmux has-session -t {shell_quote(web)} 2>/dev/null && exit 76
tmux has-session -t {shell_quote(legacy_web)} 2>/dev/null && exit 76
web_root="$HOME/.sshelp/web"
observer="$web_root/observer.py"
log="$HOME/.sshelp/jobs/{job_id}/output.ansi"
[ -f "$log" ] || log="$HOME/.ssh-research-debug/jobs/{job_id}/output.ansi"
mkdir -p "$web_root"
printf '%s' {shell_quote(observer_b64)} | base64 -d > "$observer"
chmod 700 "$web_root" "$observer"
ttyd_bin=$(command -v ttyd 2>/dev/null || true)
[ -n "$ttyd_bin" ] || [ ! -x "$HOME/.local/bin/ttyd" ] || ttyd_bin="$HOME/.local/bin/ttyd"
if [ -n "$ttyd_bin" ]; then
  tmux new-session -d -s {shell_quote(web)} "exec $ttyd_bin -i 127.0.0.1 -p {args.remote_port} env -u TMUX tmux attach-session -r -t $target"
  backend=ttyd
elif command -v python3 >/dev/null 2>&1; then
  tmux new-session -d -s {shell_quote(web)} "exec python3 $observer --log $log --session $target --port {args.remote_port}"
  backend=python-read-only
else
  exit 69
fi
sleep 1
tmux has-session -t {shell_quote(web)} 2>/dev/null || exit 75
printf '%s' "$backend"
"""
    result = run_ssh(options, host, remote, check=False)
    if result.returncode == 44:
        raise SkillError("JOB_NOT_FOUND", "target tmux task does not exist")
    if result.returncode == 69:
        raise SkillError(
            "WEB_BACKEND_MISSING",
            "neither ttyd nor Python 3 is available on the remote host",
        )
    if result.returncode == 75:
        raise SkillError(
            "WEB_BACKEND_START_FAILED",
            "the Web observer backend exited before becoming available",
        )
    if result.returncode == 76:
        raise SkillError(
            "WEB_ALREADY_RUNNING",
            "a Web observer already exists; stop it before selecting new ports",
        )
    if result.returncode != 0:
        raise ssh_failure(
            result, "WEB_START_FAILED", "failed to start remote web observer"
        )
    forward = f"127.0.0.1:{args.local_port}:127.0.0.1:{args.remote_port}"
    tunnel = build_ssh_command(
        options,
        host,
        None,
        batch=True,
        extra_options=("-N", "-L", forward),
    )
    return {
        "job_id": job_id,
        "web_session": web,
        "browser_url": f"http://127.0.0.1:{args.local_port}",
        "tunnel_argv": tunnel,
        "read_only": True,
        "backend": result.stdout.decode("utf-8", errors="replace").strip(),
    }


if __name__ == "__main__":
    invoke(run)
