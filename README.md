# SSHelp

SSHelp is an agent-oriented SSH toolkit for running, observing, diagnosing, and safely editing work on remote Linux hosts. It combines bounded SSH commands, persistent tmux jobs, read-only terminal observation, process/resource diagnostics, and transactional remote file editing.

SSHelp is distributed as a repository-local Codex Skill under [`sshelp/`](sshelp/).

## Features

- Run short, non-interactive SSH commands with structured JSON results.
- Keep long-running or interactive work alive in tmux.
- Read terminal output incrementally by byte offset.
- Observe one job in Windows Terminal or a loopback-only ttyd page.
- Display several jobs in a local read-only dashboard.
- Diagnose quiet jobs using trusted tmux PIDs, process trees, resources, wait channels, ports, and GPU state.
- Search remote source trees before downloading files.
- Checkout selected files locally, edit with normal tools, detect conflicts, and commit with per-file atomic replacement.
- Bootstrap fixed prerequisites on a new Linux host after explicit authorization.
- Diagnose Windows OpenSSH client/server authentication, host-key, port-mapping, quoting, and transfer boundaries without pretending the Linux runtime supports Windows remotes.

## Quick Start

Requirements:

- Python 3.11 or newer on the local machine.
- OpenSSH client with a configured host alias and public-key authentication.
- A Linux SSH host. SSHelp can install its fixed remote prerequisites with explicit approval.

The automated `exec`, tmux job, observer, diagnostic, search, and transactional file workflows target Linux remotes. The Skill also contains guarded Windows OpenSSH guidance, but does not yet provide a Windows remote runtime backend.

From the cloned repository, resolve the Skill entry once, then keep your shell in the project you are actually working on:

```powershell
$SSHelpRepo = (Resolve-Path .).Path
$SSHelp = Join-Path $SSHelpRepo "sshelp\scripts\sshelp.py"
$SSHelpWindows = Join-Path $SSHelpRepo "sshelp\scripts\SSHelp.ps1"

Set-Location D:\Project
python $SSHelp host test --host lab-host
python $SSHelp exec --host lab-host --cwd /home/user/project -- git status --short
```

For a new server, install the fixed prerequisite set only after reviewing the action:

```powershell
python $SSHelp host install --host lab-host --yes
python $SSHelp host test --host lab-host
```

Start and monitor a persistent job:

```powershell
python $SSHelp job start --host lab-host --cwd /home/user/project -- python3 -u train.py
python $SSHelp job read --host lab-host --job-id JOB_ID --offset 0
python $SSHelp job status --host lab-host --job-id JOB_ID
```

Run `python $SSHelp --help` for the complete command tree. See [`sshelp/SKILL.md`](sshelp/SKILL.md) for the Agent workflow.

## Project-Local State

SSHelp does not place file checkouts in the Skill repository. Local state is created under the current project:

```text
<project>/.sshelp/
├── checkouts/
└── runtime/
```

These paths are ignored by Git. Set `SSHELP_WORK_ROOT` to override the project state root.

## Repository Layout

```text
sshelp/
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── docs/
├── sshelp/                 # Codex Skill
│   ├── SKILL.md
│   ├── agents/
│   ├── assets/
│   ├── references/
│   └── scripts/
└── tests/
```

The Skill remains self-contained. The root documentation is for contributors and GitHub readers.

## Development

SSHelp has no third-party local runtime dependency. Run the test suite with:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

The test suite uses mocked SSH/SFTP for safety. Lenovo-specific integration tests used during development are not encoded as public defaults.

## Security Model

- Public-key or ssh-agent authentication only for automated operations.
- Host-key verification remains enabled.
- No private-key contents, stored passwords, arbitrary package names, SIGKILL, or recursive remote cleanup.
- Web observers bind to loopback on both remote and local machines.
- File commits use path validation, SHA-256 conflict detection, and same-directory atomic replacement.

Read [`SECURITY.md`](SECURITY.md) before reporting a vulnerability.

## Project Status

The current implementation is tested on Windows clients and Linux SSH hosts. Contributions for additional platforms, distributions, diagnostics, documentation, and test coverage are welcome.

## License

SSHelp is licensed under the [Apache License 2.0](LICENSE).
