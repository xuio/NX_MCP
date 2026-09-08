"""Read-only live handler/schema audit; detects stale bindings without restarting NX."""


def run(executor):
    import hashlib
    import importlib
    import inspect
    import json
    from pathlib import Path

    server = importlib.reload(importlib.import_module("nx_mcp.simcenter.server"))
    names = sorted(server.READ_ONLY | server.NON_MODEL)
    mismatches = []
    checked = []
    private_optional = []

    def contract(function):
        return [
            (
                p.name,
                "required" if p.default is inspect.Parameter.empty else repr(p.default),
                str(p.kind),
            )
            for p in inspect.signature(function).parameters.values()
        ]

    for name in names:
        expected = contract(getattr(server, name))
        handler = executor._handlers.get(name)
        actual = None if handler is None else contract(handler)
        public_names = {row[0] for row in expected}
        extras = [] if actual is None else [row for row in actual if row[0] not in public_names]
        shared = None if actual is None else [row for row in actual if row[0] in public_names]
        if expected != shared or any(row[1] == "required" for row in extras):
            mismatches.append({"tool": name, "public": expected, "handler": actual})
        elif extras:
            private_optional.append({"tool": name, "internal_only_parameters": extras})
        checked.append(name)
    root = Path(server.__file__).parent
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.py")}
    result = {
        "passed": not mismatches,
        "checked_count": len(checked),
        "tools": checked,
        "mismatches": mismatches,
        "private_optional_extensions": private_optional,
        "deployed_source_sha256": hashes,
        "scope": "Live handler argument names, required/default values and parameter kinds; not per-tool behavior verification",
        "work_path": executor.session.Parts.BaseWork.FullPath,
        "display_path": executor.session.Parts.BaseDisplay.FullPath,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\deployed-signatures.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
