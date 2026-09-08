"""Read native discovery; no licence checkout or model mutation."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import capabilities, release_evidence
    from nx_mcp.simcenter.server import NON_MODEL, READ_ONLY

    importlib.reload(release_evidence)
    importlib.reload(capabilities)
    inspect_capabilities = capabilities.inspect_capabilities
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    result = inspect_capabilities(executor.session)
    evidence = result["public_tool_evidence"]
    names = {row["tool"] for row in evidence["tools"]}
    assert len(names) == evidence["indexed_tool_count"] == 36
    assert names | set(evidence["unindexed_tools"]) == READ_ONLY | NON_MODEL
    assert names.isdisjoint(evidence["unindexed_tools"])
    assert {"nx_sim_fan_table", "nx_sim_fan_tables", "nx_sim_objects", "nx_sim_assign_fan"} <= names
    assert all(row["status"] == "implemented_and_tested" for row in evidence["tools"])
    assert all(row["licence_checkout"] == "not_tested" for row in evidence["tools"])
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert before == after
    return {
        "nx_version": result["nx_version"],
        "public_tool_evidence": evidence,
        "modified_flags_preserved": True,
        "licensing_configuration_modified": False,
    }
