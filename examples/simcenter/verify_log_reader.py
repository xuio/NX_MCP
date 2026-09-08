"""Read bounded pages from an existing solver log; no model or job mutation."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import log_reader

    importlib.reload(log_reader)
    path = "ui-benchmarks/F-input-export-20260908-r2/flow_input_r2-Flow_benchmark.log"
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    first = log_reader.read_log(executor.workspace, path, maximum_bytes=1024)
    second = log_reader.read_log(
        executor.workspace,
        path,
        offset=first["next_offset"],
        maximum_bytes=1024,
        file_identity=first["file_identity"],
    )
    assert 0 < first["next_offset"] <= 1024
    assert second["offset"] == first["next_offset"]
    assert second["next_offset"] > second["offset"]
    assert before == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {
        "first": first,
        "second": second,
        "document_flags_preserved": True,
        "scope": "Two bounded pages from existing native solver log; no convergence claim",
    }
