# Contributing to SSHelp

Thank you for helping improve SSHelp.

## Before Opening A Change

- Search existing issues and discussions.
- Keep changes focused on one behavior or documentation concern.
- Do not include real hostnames, IP addresses, usernames, private paths, credentials, terminal logs, or research data.
- Discuss destructive behavior, authentication changes, package installation, or new remote write operations before implementation.

## Development Workflow

1. Fork the repository and create a focused branch.
2. Keep the Skill self-contained under `sshelp/`.
3. Preserve the single-JSON-object CLI contract.
4. Keep automated SSH authentication in `BatchMode=yes`.
5. Add tests proportional to the behavior and risk.
6. Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

## Compatibility

New code uses `SSHELP_*`, `sshelp-*`, and `~/.sshelp`. Compatibility with existing `SSH_RESEARCH_*`, `srd-*`, and `~/.ssh-research-debug` state must not be removed without a documented migration plan.

## Pull Requests

Describe:

- The user problem and intended behavior.
- Security and failure-mode considerations.
- Tests performed, including whether a real SSH host was used.
- Any new remote files, processes, ports, packages, or cleanup behavior.

Do not commit generated `.sshelp`, `.srd-tmp`, `__pycache__`, dashboard runtime, SSH configuration, or key material.
