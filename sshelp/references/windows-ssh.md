# Windows OpenSSH

## Scope First

Classify the connection before choosing commands:

| Local client | Remote host | Procedure |
|---|---|---|
| Windows | Linux | Use the full SSHelp workflow. |
| Windows | Windows OpenSSH Server | Use the native connection, authentication, transfer, and diagnostic guidance below. SSHelp runtime commands are not Windows-remote compatible. |
| bash/zsh wrapper on Windows | Any | Write commands for that wrapper, not for PowerShell. Confirm the actual launcher from error prefixes. |

Record the remote OS, default SSH shell, user privilege, actual endpoint, and whether a tunnel maps `127.0.0.1:<port>` to another machine. Do not infer the remote shell from the local terminal.

## Client Configuration

Prefer a named entry in `%USERPROFILE%\.ssh\config` instead of repeating host, port, user, and key options:

```sshconfig
Host windows-lab
    HostName 127.0.0.1
    Port 22022
    User remote-user
    IdentityFile C:/Users/local-user/.ssh/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
    HostKeyAlias windows-lab-through-tunnel
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Use forward slashes in OpenSSH configuration paths. Keep private-key ACLs restricted to the owning account; inspect and repair ACLs manually rather than weakening OpenSSH checks. Use `ssh -G windows-lab` to inspect effective configuration without connecting.

`BatchMode=yes` is for verified key/agent authentication. Initial key enrollment may require one explicitly approved interactive session; do not weaken automation to fall back to a password.

## Authentication

- Never put passwords in source files, notes, command arguments, environment variables, VBS SendKeys, or `subprocess.communicate()` input. OpenSSH reads password prompts from the terminal, not normal stdin.
- Prefer Ed25519 keys or an SSH agent. Reference the private key by path; never read or return its contents.
- For a normal Windows account, the usual key file is `%USERPROFILE%\.ssh\authorized_keys`.
- For an account matched by the default `Match Group administrators` rule, Windows OpenSSH commonly uses `%ProgramData%\ssh\administrators_authorized_keys`. Inspect `sshd_config`; do not assume the per-user file is active.
- Keep `authorized_keys` ACLs limited to the target account where applicable, or to `SYSTEM` and `Administrators` for the shared administrators file. Broad write access causes OpenSSH to reject the file and is a security defect.
- After key authentication works, disable password authentication only with explicit approval, a validated configuration, and an out-of-band recovery path.

## Host Keys And Port-Mapped Endpoints

Verify the server host-key fingerprint through an independent channel before unattended use. `StrictHostKeyChecking=accept-new` may help during a controlled first enrollment, but it does not authenticate an unknown server. Use `yes` after enrollment; never use `no`.

A loopback endpoint such as `127.0.0.1:22022` identifies the tunnel entrance, not necessarily one stable remote machine. Use a unique `HostKeyAlias` for each real server. If a mapping changes and the host key differs, stop and verify the new fingerprint; do not automatically delete `known_hosts` entries.

Before diagnosing SSH, verify the tunnel itself:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 22022
```

Bind local mappings to `127.0.0.1`, keep the tunnel provider connected, and account for remote sleep/restart. A successful TCP probe proves only that something is listening, not that it is the expected SSH server.

## Shell And Quoting Boundaries

Remote execution has at least two parsers:

1. The local launcher parses the command.
2. OpenSSH sends a command string to the remote default shell, which parses it again.

PowerShell does not support bash heredoc syntax such as `<< 'EOF'`; it reports `Missing file specification after redirection operator` before SSH starts. Conversely, zsh/bash do not understand PowerShell here-strings such as `@' ... '@` or `$env:NAME`. Use the error prefix (`ParserError`, `zsh:`, `bash:`, or a remote PowerShell error) to identify the failing layer.

Keep one-shot commands short. For multiline PowerShell, source code, Markdown, JSON, or other large text:

1. Create or edit a local file with normal file tools.
2. Transfer it with SFTP/SCP or a reviewed file workflow.
3. Execute an uploaded `.ps1` with `powershell.exe -NoProfile -NonInteractive -File <path>` when execution is required.

Do not embed large content in `ssh "..."`, POSIX heredocs, PowerShell here-strings, `cmd /c`, or nested `sh -c`/`powershell -Command` layers. Encoded commands hide auditability and are not the default solution.

## File Transfer And Paths

- Use `ssh -p <port>` but `scp -P <port>`; prefer the configured alias so neither is repeated.
- Prefer SFTP for unfamiliar Windows servers. Run `pwd` and inspect the remote filesystem before assuming path mappings.
- Use an explicit Windows destination such as `C:/Users/remote-user/Documents/file.txt` when supported by the server, quote it as one argument, and verify the resulting file.
- Transfer to a temporary sibling, verify size/hash when important, then rename on the remote side. Do not overwrite configuration or code without a backup or conflict check.
- Do not recursively transfer profiles, `.ssh` directories, credentials, caches, environments, datasets, or build trees by default.

## Windows Server Operations

Use a dedicated non-administrator SSH account when possible. Treat service, firewall, registry, `sshd_config`, and ACL changes as privileged operations requiring explicit approval.

Before restarting `sshd`, validate the configuration with the installed `sshd.exe -t`, keep a second/out-of-band administrative path available, and avoid restarting the only working remote session. Diagnose with:

- `Get-Service sshd`
- `Get-WinEvent -LogName 'OpenSSH/Operational'`
- the effective `sshd_config`, including `Match` blocks
- key-file existence and ACLs
- the configured default shell
- tunnel and local-port state

Do not disable the firewall, host-key verification, or authentication checks to make a connection succeed.

## Failure Triage

Check in this order:

1. Local command parsed successfully.
2. Tunnel/local port is listening.
3. SSH host alias expands to the expected endpoint with `ssh -G`.
4. Host key matches the independently verified server.
5. Public-key authentication selects the intended key (`ssh -vvv` only when needed; redact paths and identities in reports).
6. The remote default shell matches the submitted syntax.
7. The remote command/path exists and the account has permission.

Classify `Connection refused`, timeout, host-key mismatch, authentication failure, local parser error, remote parser error, and remote command failure separately. Do not respond to one class by weakening controls in another.
