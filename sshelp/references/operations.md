# Operations

## Execution And Monitoring

For a new Linux host, run `host install --yes` only after explicit approval. It detects a supported package manager and installs a fixed prerequisite set. It uses root directly or passwordless `sudo -n`; interactive sudo passwords are not accepted. If ttyd is absent, it downloads a pinned official release over HTTPS, verifies that the binary runs, and installs it to `~/.local/bin/ttyd`. Run `host test` afterward.

Use `sshelp.py exec` for bounded, non-interactive commands. It returns separate stdout/stderr, exit code, duration, byte counts, and truncation flags. A nonzero remote exit is a valid result; transport and timeout failures use structured errors.

New persistent jobs live under `~/.sshelp/jobs/<job-id>/` and use `sshelp-<job-id>` tmux sessions. SSHelp still discovers and controls old `~/.ssh-research-debug` and `srd-` jobs during migration.

Use `SSHELP_SSH_CONFIG`, `SSHELP_KNOWN_HOSTS`, `SSHELP_IDENTITY_FILE`, and `SSHELP_WORK_ROOT` for configuration. Old `SSH_RESEARCH_*` variables remain compatibility fallbacks only.

Monitoring loop:

1. Start with offset zero.
2. Read and replace the saved offset with `new_offset`.
3. Immediately read again while `truncated=true`.
4. Check status after meaningful output or a quiet interval.
5. On exit, drain remaining output and report exit code and signal.

Use `job list` after context loss. If no offset is known, read from zero and do not claim old output is new.

## Quiet-Job Diagnosis

Run `job diagnose` when output is idle but status remains `running`. It derives the PID only from the exact tmux job and reports descendants, CPU, RSS, log mtime, GPU attribution, process states, and wait channels.

Check in this order: process exists, output idle time, CPU/memory/GPU, child processes, terminal-read waits, uninterruptible I/O, socket waits, then recent terminal output for a prompt. `possible_waiting_for_input` requires a terminal-read wait channel; timer sleep is reported separately.

Never send input or stop a task automatically from one heuristic. Use `job input` only for an identified prompt or explicit instruction. Prefer Ctrl+C; use SIGTERM only after authorization and an ineffective interrupt.

## Resource Checks

```powershell
python $SSHelp process list --host lab-host --pattern python
python $SSHelp process inspect --host lab-host --job-id JOB_ID
python $SSHelp resource snapshot --host lab-host --job-id JOB_ID --path /project
python $SSHelp port owner --host lab-host --port 8000
python $SSHelp gpu snapshot --host lab-host
```

Process inspection accepts a job ID, not an arbitrary PID. Port ownership is limited to information visible to the SSH user. GPU commands return `available=false` when NVIDIA tooling is absent.

## Terminal And Web Observation

`SSHelp.ps1 terminal` opens Windows Terminal and attaches with `tmux attach-session -r`. Use `-Interactive` only when direct keyboard control is explicitly wanted. Detach with `Ctrl+B`, then `D`; detaching does not stop the program.

`SSHelp.ps1 web-open` starts an exact `sshelp-observer-<job-id>` session, then creates an SSH tunnel bound to local loopback. ttyd must bind remote `127.0.0.1` and must not enable writing. The tested tmux command is:

```text
ttyd -i 127.0.0.1 -p PORT env -u TMUX tmux attach-session -r -t sshelp-JOB_ID
```

`env -u TMUX` is required when ttyd starts inside tmux; without it, nested attach may fail or reconnect. A Python read-only log viewer remains the fallback when ttyd is unavailable.

Use one observer and tunnel per job. `dashboard-open` embeds multiple loopback observer URLs in one local page. Runtime state is stored under `<current project>/.sshelp/runtime`, not the Skill or system temporary directory. Closing a dashboard stops only its exact local server/tunnels and observer sessions; it never stops jobs.

An HTTP 200 response proves only that the page is served. Confirm changing terminal output with job offsets or log growth. Diagnose `Reconnecting...` by checking the exact observer session, backend process, remote loopback listener, SSH tunnel, then browser URL.

## Safety

- Keep public-key authentication, `BatchMode=yes`, and host-key verification enabled.
- Never place secrets in commands, metadata, logs, environment snapshots, or prompts.
- Do not modify SSH configuration, firewall rules, system services, or unrelated tmux sessions.
- Install ttyd only after explicit authorization; never expose it on a public address.
- Keep diagnostics read-only. Do not add PID signaling, renice, debugger attach, or descriptor mutation.
- Preserve partial state for inspection. Do not perform recursive remote cleanup or wildcard session deletion.
