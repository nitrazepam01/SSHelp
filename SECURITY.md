# Security Policy

## Reporting A Vulnerability

Use GitHub private vulnerability reporting when it is enabled for the repository. Do not publish credentials, private keys, host addresses, terminal output, or exploit details in a public issue.

Include the affected command, expected boundary, observed behavior, and a minimal reproduction that uses non-sensitive test data.

## Security Boundaries

SSHelp is designed to:

- Use public-key or ssh-agent authentication for automated commands.
- Keep host-key verification enabled.
- Avoid reading or transporting private-key contents.
- Restrict task control to validated SSHelp tmux sessions.
- Keep observers read-only and bound to loopback.
- Reject path traversal, symlink writes, secret filenames, and remote file conflicts.
- Require explicit confirmation for prerequisite installation.
- Avoid SIGKILL, arbitrary PID control, and recursive remote cleanup.

Report any behavior that crosses these boundaries privately.

## Supported Versions

Until formal releases exist, only the latest commit on the default branch is supported.
