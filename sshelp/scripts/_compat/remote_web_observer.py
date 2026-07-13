#!/usr/bin/env python3
"""Serve a loopback-only, read-only live view of a tmux task log."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ANSI_RE = re.compile(
    r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\))|"
    r"(?:\x1b[@-_][0-?]*[ -/]*[@-~])"
)
MAX_CHUNK = 256 * 1024
HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SSHelp</title>
  <style>
    :root { color-scheme: dark; font-family: ui-monospace, Consolas, monospace; }
    body { margin: 0; background: #0b1020; color: #dbeafe; }
    header { position: sticky; top: 0; display: flex; gap: 18px; align-items: center;
      padding: 12px 18px; background: #111a30; border-bottom: 1px solid #263451; }
    h1 { margin: 0; font-size: 15px; color: #93c5fd; }
    #state { padding: 3px 9px; border-radius: 999px; background: #1e3a2d; color: #86efac; }
    #state.exited { background: #3f2a20; color: #fdba74; }
    label { margin-left: auto; font-size: 12px; color: #9ca3af; }
    pre { margin: 0; padding: 16px 18px 40px; white-space: pre-wrap; overflow-wrap: anywhere;
      line-height: 1.45; font-size: 13px; }
    #error { color: #fca5a5; }
  </style>
</head>
<body>
  <header><h1>SSHelp</h1><span id="state">connecting</span>
    <span id="meta"></span><label><input id="follow" type="checkbox" checked> follow output</label></header>
  <pre id="output"></pre><pre id="error"></pre>
  <script>
    let offset = 0;
    const output = document.getElementById('output');
    const errorBox = document.getElementById('error');
    const stateBox = document.getElementById('state');
    const meta = document.getElementById('meta');
    async function poll() {
      try {
        const response = await fetch('/api/output?offset=' + offset, {cache: 'no-store'});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        if (data.reset) { output.textContent = ''; }
        if (data.output) {
          output.textContent += data.output;
          if (output.textContent.length > 500000) output.textContent = output.textContent.slice(-400000);
        }
        offset = data.new_offset;
        stateBox.textContent = data.state + (data.exit_code === null ? '' : ' (' + data.exit_code + ')');
        stateBox.className = data.state;
        meta.textContent = data.session + '  |  ' + offset + ' bytes';
        errorBox.textContent = '';
        if (document.getElementById('follow').checked) window.scrollTo(0, document.body.scrollHeight);
      } catch (error) {
        errorBox.textContent = 'Observer error: ' + error.message;
      } finally {
        setTimeout(poll, 500);
      }
    }
    poll();
  </script>
</body>
</html>
"""


def normalize(text: str) -> str:
    text = ANSI_RE.sub("", text).replace("\x00", "").replace("\r\n", "\n")
    return "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))


def pane_state(session: str) -> tuple[str, int | None]:
    result = subprocess.run(
        [
            "tmux",
            "display-message",
            "-p",
            "-t",
            session + ":0.0",
            "#{pane_dead}|#{pane_dead_status}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "missing", None
    dead, _, status = result.stdout.strip().partition("|")
    return ("exited" if dead == "1" else "running"), (
        int(status) if status.lstrip("-").isdigit() else None
    )


def make_handler(log_path: Path, session: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_bytes(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
                return
            if parsed.path != "/api/output":
                self.send_bytes(404, "text/plain; charset=utf-8", b"not found")
                return
            try:
                requested = int(parse_qs(parsed.query).get("offset", ["0"])[0])
                size = log_path.stat().st_size
                offset = requested if 0 <= requested <= size else 0
                reset = offset != requested
                with log_path.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(MAX_CHUNK)
                state, exit_code = pane_state(session)
                payload = {
                    "session": session,
                    "state": state,
                    "exit_code": exit_code,
                    "old_offset": requested,
                    "new_offset": offset + len(chunk),
                    "reset": reset,
                    "output": normalize(chunk.decode("utf-8", errors="replace")),
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_bytes(200, "application/json; charset=utf-8", body)
            except Exception as error:
                body = json.dumps({"error": str(error)}).encode("utf-8")
                self.send_bytes(500, "application/json; charset=utf-8", body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), make_handler(args.log, args.session)
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
