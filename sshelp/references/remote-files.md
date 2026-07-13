# Transactional Remote Files

Search remotely first, then checkout only the files that need full reading or editing. The default local parent is `<current project>/.sshelp/checkouts`; override it only with `--checkout-root`, `SSHELP_CHECKOUT_ROOT`, or `SSHELP_WORK_ROOT`.

Each checkout contains immutable `base/`, editable `work/`, and `manifest.json`. Use local `rg`, readers, tests, and `apply_patch` only inside `work/`; never edit the baseline or manifest.

## Workflow

```powershell
python $SSHelp remote search --host lab-host --root /project --query target --glob "*.py"
python $SSHelp file checkout --host lab-host --root /project --path src/a.py --path tests/test_a.py
python $SSHelp file status --checkout CHECKOUT_ID
python $SSHelp file diff --checkout CHECKOUT_ID
python $SSHelp file status --checkout CHECKOUT_ID --check-remote
python $SSHelp file commit --checkout CHECKOUT_ID
```

Checkout uses one SFTP batch. Defaults are 20 files, 8 MiB per file, and 64 MiB total. Raise limits only for a known need.

## Commit Rules

For modified files, require the current remote SHA-256 to match the checkout baseline. For new files, require the remote target to remain absent and its parent directory to exist. Reject conflicts without overwriting.

Upload to `.<basename>.sshelp-<checkout-id>.tmp` in the target directory, verify its hash, preserve or set mode, use same-directory `os.replace`, then verify final hash and mode. Atomicity is per file, not across a multi-file transaction.

On complete success, remove the exact local checkout unless `--keep-local` is used. Preserve it on conflict or failure. Use `file abort` only for one exact checkout the user has abandoned. Never delete checkout roots in bulk and never delete remote files in this version.

## Path And Secret Safety

Require an explicit absolute remote root and relative paths. Resolve parents under the real root; reject traversal, symbolic links, devices, sockets, FIFOs, unsupported Windows paths, and files outside limits.

Never checkout or return search contents for `.env`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, or `credentials.json`. Ignore normal VCS, dependency, environment, data, checkpoint, cache, build, and distribution directories.

On `REMOTE_FILE_CHANGED` or `REMOTE_FILE_CREATED`, preserve local work, checkout the new remote version separately, and merge deliberately. Never bypass conflict detection by editing `manifest.json`.
