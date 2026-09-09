"""Native scalar-table rollback and corrupt-definition detection; no solver work."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import scalar_tables

    session = executor.session
    sim = session.Parts.BaseWork
    expected = json.loads(
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\scalar-tables-public.json").read_text()
    )
    assert expected["passed"] and sim.FullPath == expected["path"]

    def snapshot():
        return {
            "fields": sorted(int(f.Tag) for f in sim.FieldManager.Fields),
            "expressions": sorted(int(e.Tag) for e in sim.Expressions),
            "flags": {p.FullPath: bool(p.IsModified) for p in session.Parts},
        }

    before = snapshot()
    original = scalar_tables.inspect

    def fail(*args):
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH", "Injected native post-create readback failure"
        )

    try:
        scalar_tables.inspect = fail
        try:
            scalar_tables.create(
                session,
                sim,
                {
                    "name": "MCP_RECOVERY_TRIAL",
                    "axis": "time",
                    "quantity": "power",
                    "samples": [[0, 0], [1, 1]],
                    "provenance": "Failure injection fixture",
                },
            )
        except NXToolError as error:
            assert error.details["mutation_outcome"] == "rolled_back", error.details
            recovery = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected native creation failure")
    finally:
        scalar_tables.inspect = original
    assert snapshot() == before
    table = next(f for f in sim.FieldManager.Fields if f.Name == "MCP_POWER_TIME")
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Invisible, "Corrupt field metadata trial"
    )
    try:
        table.SetUserAttribute(scalar_tables.DATA, 0, "corrupt", executor.nxopen.Update.Option.Now)
        try:
            scalar_tables.inspect(sim, table)
        except NXToolError as error:
            assert error.code == "NX_SIM_MANIFEST_INVALID"
            corrupt_code = error.code
        else:
            raise AssertionError("Corruption was not detected")
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    assert snapshot() == before
    restored = scalar_tables.inspect(sim, table)
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    return {
        "injected_failure": recovery,
        "corrupt_metadata_error": corrupt_code,
        "restored_manifest_sha256": restored["manifest_sha256"],
        "native_rollback_verified": True,
        "document_flags_preserved": True,
        "solver_launched": False,
    }
