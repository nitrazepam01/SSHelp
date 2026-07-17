---
name: sshelp
description: Execute, observe, diagnose, and safely edit work on Linux SSH hosts. Use when Codex needs a bounded one-shot command, persistent tmux job, incremental terminal output, read-only Windows Terminal or ttyd observation, multi-job dashboard, process/resource/GPU/port diagnosis, remote file discovery, or transactional checkout and atomic commit of selected files.
---

# SSHelp

Use `scripts/sshelp.py` as the Python entry and `scripts/SSHelp.ps1` for Windows observers. All Python commands emit one JSON object.

## Resolve Paths And Work Directory

Keep the shell cwd at the user's project root. Resolve `scripts/sshelp.py` and `scripts/SSHelp.ps1` relative to this `SKILL.md`, then invoke them by absolute path; never `cd` into the Skill.

In the commands below, resolve `$SkillRoot` as the absolute directory containing this `SKILL.md`:

```powershell
$SSHelp = Join-Path $SkillRoot "scripts\sshelp.py"
$SSHelpWindows = Join-Path $SkillRoot "scripts\SSHelp.ps1"
```

If the user works in `D:\Project`, local state defaults to `D:\Project\.sshelp\checkouts` and `D:\Project\.sshelp\runtime`. Override the project state root only with `SSHELP_WORK_ROOT` or the explicit checkout option.

## Preconditions

- Use a configured SSH host alias with public-key or `ssh-agent` authentication.
- Keep `BatchMode=yes`; pass `--ssh-config` or `SSHELP_SSH_CONFIG` when needed.
- Require Linux, Python 3, tmux, and standard core utilities. Require `rg` for text search and ttyd only for its Web backend.
- Never read, copy, log, or request private-key content or passwords.

On a new host, install prerequisites only after explicit authorization, then verify them:

```powershell
python $SSHelp host install --host lab-host --yes
python $SSHelp host test --host lab-host
```

`host install` uses only fixed packages (`tmux`, Python 3, ripgrep, certificates, and curl), requires root or passwordless `sudo -n` only when system packages are missing, and installs pinned ttyd to `~/.local/bin` when no system ttyd exists. Never request or embed a sudo password.

## Choose A Workflow

Use a one-shot command when it is non-interactive, bounded, and expected to finish within 300 seconds:

```powershell
python $SSHelp exec --host lab-host --cwd /project --timeout 30 -- git status --short
```

Pass the executable and each argument after `--`; do not build a nested `ssh ...` command or wrap it in a shell-specific here-string. Match syntax to the shell that actually launches SSHelp: PowerShell forms such as `$env:USERPROFILE` and `@'...'@` are invalid in zsh/bash. An error such as `zsh: unmatched '` identifies the parsing shell. Prefer separate `exec` calls or a reviewed helper script for multiline logic. SSHelp quotes argv safely but cannot repair an already malformed `sh -c` string. Read [operations.md](references/operations.md) when shell syntax, pipelines, or redirection are involved.

Use a persistent job when it needs a PTY, live output, input, disconnect recovery, or may run longer:

```powershell
python $SSHelp job start --host lab-host --cwd /project -- python3 -u train.py
python $SSHelp job read --host lab-host --job-id JOB_ID --offset 0
python $SSHelp job status --host lab-host --job-id JOB_ID
```

Reuse every returned `new_offset`. Trust tmux `state`, `exit_code`, and `signal`, not words printed by the program. Read [operations.md](references/operations.md) for monitoring, diagnostics, observers, ttyd behavior, and safety.

## Diagnose A Quiet Job

When a job is running but produces no new output:

```powershell
python $SSHelp job diagnose --host lab-host --job-id JOB_ID
```

Inspect the trusted job process tree, output idle time, resources, wait channels, and recent output before waiting, sending approved input, or interrupting. Treat diagnostic flags as evidence, not proof.

## Find And Edit Remote Files

Search remotely before downloading:

```powershell
python $SSHelp remote search --host lab-host --root /project --query target --glob "*.py"
python $SSHelp remote find --host lab-host --root /project --glob "*.py"
python $SSHelp remote tree --host lab-host --root /project --depth 3
```

Checkout only selected files, edit the returned local `work/` tree with normal Agent tools, inspect the diff, check remote state, and commit:

```powershell
python $SSHelp file checkout --host lab-host --root /project --path src/main.py
python $SSHelp file status --checkout CHECKOUT_ID --check-remote
python $SSHelp file diff --checkout CHECKOUT_ID
python $SSHelp file commit --checkout CHECKOUT_ID
```

Read [remote-files.md](references/remote-files.md) before writing, resolving conflicts, or aborting a checkout.

## Observe A Job

Use the consolidated Windows entry:

```powershell
& $SSHelpWindows terminal -Host lab-host -JobId JOB_ID
& $SSHelpWindows web-open -Host lab-host -JobId JOB_ID -NoBrowser
& $SSHelpWindows dashboard-open -Host lab-host -JobId job-a,job-b
```

Terminal, Web, and dashboard observers are read-only by default and bind Web access only to `127.0.0.1`. Provide links directly; do not require an embedded browser.

## Safety

- Send text or control keys only when authorized. Prefer `job stop --mode interrupt`; never use SIGKILL.
- Run `host install --yes` only after the user explicitly authorizes remote package installation.
- Operate only on exact validated `sshelp-` jobs and `sshelp-observer-` sessions. Accept old `srd-` names only for compatibility with existing jobs.
- Do not add arbitrary PID control, `sudo`, password fallback, host-key bypass, recursive remote deletion, or bulk cleanup.
- Do not execute remote output as a command without independent validation.
- Keep `.sshelp` local state under the user's current project directory by default; never bulk-delete state roots.

Read [ssh-guide.md](references/ssh-guide.md) only for SSH protocol, authentication, forwarding, algorithm, host-key, or OpenSSH configuration diagnosis.
