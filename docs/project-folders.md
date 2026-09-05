# Project folders and explicit file paths

The integration profile accepts either workspace-relative paths or absolute paths inside the configured `NX_MCP_WORKSPACE`. Paths refer to the **NX server**, not the Mac running the client. Call `nx_workspace_info({})` to discover the actual root. Forward slashes work on Windows and avoid JSON backslash escaping.

For a workspace at `D:/CAD/NX_MCP_WORKSPACE`, these identify the same file:

- `projects/controller/parts/controller_base.prt`
- `D:/CAD/NX_MCP_WORKSPACE/projects/controller/parts/controller_base.prt`

There is no mutable current-directory setting. Include the project prefix on every file call so multiple tasks cannot redirect each other's files.

## Example workflow

```json
{"tool":"nx_workspace_info","arguments":{}}
{"tool":"nx_create_directory","arguments":{"path":"projects/controller/parts"}}
{"tool":"nx_create_part","arguments":{"path":"projects/controller/parts/controller_base.prt","units":"mm"}}
{"tool":"nx_save_part","arguments":{}}
{"tool":"nx_save_as","arguments":{"path":"projects/controller/revisions/controller_base_r02.prt"}}
{"tool":"nx_open_part","arguments":{"path":"D:/CAD/NX_MCP_WORKSPACE/projects/controller/parts/controller_base.prt","work":true,"display":true}}
{"tool":"nx_workspace_list","arguments":{"path":"projects/controller"}}
```

`nx_create_directory` creates missing parents and succeeds when the directory already exists. Part creation, Save As, and upload also create missing parent directories. Save As rejects existing files and changes the active part's filename. `nx_save_part` saves at the part's current filename; it takes no destination path. Opening an already-loaded file reuses it and supports explicit work/display activation.

Use subfolders such as `parts/`, `assemblies/`, `revisions/`, `vendor/`, and `exports/`. Give simultaneously loaded parts unique basenames: native NX can reject two different files named `base.prt`, even in different directories. Save As does not relocate an assembly's referenced prototypes. Use `nx_package_assembly` for a package with dependencies; moving a whole existing project requires updating references separately.

Absolute paths outside the workspace, traversal escapes, symlink escapes, and internal `.nx-mcp` state are rejected. To use another root, configure `NX_MCP_WORKSPACE` consistently for both bridge and sidecar and restart them after preserving the session. Local Mac files require `nx_upload_file` or an existing shared folder; a Mac path is not a Windows path.

This changes path support only; it does not reorganize existing CAD files.

## Live acceptance

With a saved work part open in NX, set `NX_MCP_URL` to the integration endpoint and run `python examples/validate_project_folders.py`. Set `NX_VALIDATION_OUTPUT` for the local receipt directory. The runner creates disposable parts in a unique workspace subfolder, verifies a 1,000 mm³ solid across Save As and reopen, checks loaded-part reuse and activation, tests STEP artifact checksums and uploads, and rejects outside-root and reserved-state paths. It closes its fixtures and restores the original work part. Validation artifacts remain in the unique test subfolder.
