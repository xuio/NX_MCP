"""Read-only live handler/schema audit; detects stale bindings without restarting NX."""


def run(executor):
    import dis
    import hashlib
    import importlib
    import inspect
    import json
    import sys
    import types
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
    from nx_mcp.simcenter import properties

    reader_bindings = []
    for module_name, module in sorted(sys.modules.items()):
        if not module_name.startswith("nx_mcp.simcenter.") or module is None:
            continue
        for fn in list(vars(module).values()):
            if not isinstance(fn, types.FunctionType) or fn.__module__ != module_name:
                continue
            instructions = list(dis.get_instructions(fn))
            if any(
                i.opname == "LOAD_GLOBAL" and i.argval == "read_properties" for i in instructions
            ):
                reader_bindings.append(
                    {
                        "function": module_name + "." + fn.__name__,
                        "mode": "global",
                        "current": getattr(module, "read_properties", None)
                        is properties.read_properties,
                    }
                )
            elif any(
                i.opname == "IMPORT_FROM" and i.argval == "read_properties" for i in instructions
            ):
                reader_bindings.append(
                    {
                        "function": module_name + "." + fn.__name__,
                        "mode": "call_time",
                        "current": True,
                    }
                )
    stale_readers = [row for row in reader_bindings if not row["current"]]
    result = {
        "passed": not mismatches and not stale_readers,
        "property_reader_bindings": reader_bindings,
        "stale_property_readers": stale_readers,
        "reader_audit_scope": "Loaded module-owned functions: direct global or local-import read_properties references; not all dependency bindings",
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
