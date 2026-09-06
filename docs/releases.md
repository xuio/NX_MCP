# Versioned offline releases

Build from a clean commit on the fork with Python 3.12:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_release.py --output dist
```

The package contains the committed source, its built wheel, Windows/Python 3.12 dependency wheels, a hash-locked requirements file, a SHA256 manifest and the source commit/version. It excludes working-tree changes and machine configuration. GitHub's manual **Build offline NX release** workflow runs the same builder and retains the ZIP and checksum as artifacts. It does not publish a GitHub Release or deploy automatically.

Dependencies are refreshed deliberately with:

```sh
uv pip compile pyproject.toml -c constraints-windows.txt --python-platform windows --python-version 3.12 --generate-hashes --no-header -o requirements-windows.lock
```

Verify the downloaded ZIP checksum before extraction. Preserve the live session manifest and require all user parts to be saved before restarting NX. Stop the sidecar and its associated NX bridge, then run the package installer:

```powershell
.\install_release.ps1 -InstallRoot C:\NX-MCP -BridgeDescriptor "$env:LOCALAPPDATA\nx-mcp\interactive-bridge.json"
```

The installer checks the package manifest, saves a rollback copy of the source and virtual environment, installs the hash-locked dependencies offline, replaces the source/wheel together and runs `pip check`. A failed installation restores the prior runtime. Host-specific launchers, network/authentication settings and CAD remain managed on the host. Restart the existing sidecar launcher and restore loaded parts from the preservation manifest. Run native validation before considering deployment complete.

For an explicit rollback, stop that bridge/sidecar first and use the backup's script:

```powershell
.\restore_release.ps1 -InstallRoot C:\NX-MCP -BackupRoot C:\NX-MCP\backups\release-<timestamp> -BridgeDescriptor "$env:LOCALAPPDATA\nx-mcp\interactive-bridge.json"
```

The rollback scripts restore runtime files, not CAD geometry or unsaved edits. Preserve CAD separately before deployment. Keep backups on the NX host; virtual environments or machine receipts can contain local paths and should not be published in the fork.

## One-command installed-release acceptance

After installing the reviewed package and restarting the existing launcher safely,
run this **on the Windows NX host**, with the installed Python 3.12 environment.
Keep the trusted ZIP and obtain its SHA-256/full commit from the reviewed build
receipt. Have a saved original part open, all loaded parts saved, and NX already in
agent mode. Keep exclusive use of this NX session during acceptance. Set the
authorized STEP fixture and a loopback MCP endpoint:

```powershell
$env:NX_MCP_URL = 'http://127.0.0.1:8765/mcp'
$env:NX_VENDOR_STEP = 'C:\NX-MCP\fixtures\authorized-vendor.step'
C:\NX-MCP\venv\Scripts\python.exe C:\NX-MCP\source\scripts\accept_release.py `
  --release-zip C:\NX-MCP\releases\nx-mcp-<version>-windows-py312.zip `
  --sha256 <trusted-64-character-sha256> --expected-commit <full-40-character-commit> `
  --install-root C:\NX-MCP --output C:\NX-MCP\acceptance\<unique-run>
```

The command records atomic phase receipts in `acceptance.json`:

1. Verify the ZIP hash, exact package manifest coverage, release commit/metadata,
   every installed source file, and importable `nx_mcp` files against the packaged
   wheel. Reject a source overlay or extra executable/configuration files.
2. Check Python 3.12, all pinned dependency versions and `pip check`.
3. Inspect the live NX version/tool count and original saved session. Defaults are
   NX `v2606` and 179 tools; explicit expected-value options support later releases.
4. Run the existing six native release suites serially, retain their logs and
   receipts, and stop at the first failure. The native runner checks its own
   preservation evidence.
5. Independently compare open parts, work/display and saved flags, component
   source paths and transforms with the preflight snapshot, including on failure.

`--verify-only` ends with `state:verified` and does not run native suites. The same
command with `--resume` and without `--verify-only` rechecks the package/dependencies
and current saved session before starting native acceptance. Resume requires the
same ZIP/hash, commit, installation, interpreter, fixture hash, endpoint and runtime
expectations. A completed acceptance returns its historical receipt without running
again. An interrupted or failed native phase **cannot be resumed automatically**:
inspect its durable operation/suite receipts and reconcile NX first, then use a new
output directory for an explicitly chosen new acceptance run. Missing evidence is
never permission to replay mutations.

An installation-wide `acceptance.lock` prevents two acceptance commands from running
together. A killed process leaves that lock; verify its PID and recorded receipt,
and reconcile the session before manually removing it. Other agents, users and
tools do not honor this lock, so exclusive NX access remains an operator prerequisite.

Acceptance does not install, restart NX, save user work or force session restoration.
The native suites perform model tests in isolated test parts and restore saved user
state; errors remain visible for investigation. Deployment remains the separate
installer workflow above because it requires a stopped bridge and deliberate CAD
preservation. Installed-file hashes do **not** attest bytes already loaded by the
sidecar/NX processes; safe post-install launcher restart is still required, and the
receipt explicitly records `loaded_process_bytes_attested:false`. Dependency versions
are checked, not a byte-for-byte attestation of every third-party dependency. Native
acceptance covers `validate_native_release.py`'s selected suites; transport-disconnect
and real-restart tests remain separate exclusive-session checks. Output-schema
conformance is handled by the dedicated schema validator, not this command.
