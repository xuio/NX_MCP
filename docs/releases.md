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
