"""Native fan metadata readback and rollback test on an isolated loaded SIM."""


def run(executor):
    import importlib

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import fan_field

    importlib.reload(fan_field)
    session = executor.session
    sim = session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "A-thermal-export-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the isolated thermal export benchmark")
    before = {field.Tag for field in sim.FieldManager.Fields}
    original_flags = {part.Tag: bool(part.IsModified) for part in session.Parts}
    manifest = {
        "name": "MCP disposable fan metadata probe",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [
            {"flow_m3_s": 0, "pressure_Pa": 1},
            {"flow_m3_s": 0.0002, "pressure_Pa": 0.5},
            {"flow_m3_s": 0.0004, "pressure_Pa": 0},
        ],
        "stall_region": "Synthetic fixture, no stall prediction",
        "provenance": {"kind": "assumed", "source": "Native metadata test → " * 30},
        "scaling_rpm_range": [800, 1200],
        "scaling_validity": "Synthetic fan-law fixture only",
    }
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Verify retained fan metadata"
    )
    result = {}
    try:
        created = fan_field.create_fan_table(session, sim, manifest)
        table = created.pop("table")
        assert fan_field.read_manifest(table) == created["manifest"]
        committed = {field.Tag for field in sim.FieldManager.Fields}
        try:
            fan_field.create_fan_table(session, sim, manifest)
        except NXToolError as error:
            assert error.code == "NX_SIM_NAME_EXISTS", str(error)
            result["duplicate_rejected"] = True
        else:
            raise AssertionError("Duplicate field accepted")
        assert {field.Tag for field in sim.FieldManager.Fields} == committed
        original_read = fan_field.read_manifest

        def fail_readback(table):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Injected metadata read failure")

        fan_field.read_manifest = fail_readback
        try:
            try:
                fan_field.create_fan_table(
                    session, sim, {**manifest, "name": "MCP failed fan metadata probe"}
                )
            except NXToolError as error:
                assert error.code == "NX_SIM_READBACK_MISMATCH", str(error)
            else:
                raise AssertionError("Injected failure was ignored")
        finally:
            fan_field.read_manifest = original_read
        assert {field.Tag for field in sim.FieldManager.Fields} == committed
        result["post_creation_failure_rollback_verified"] = True
        result.update(created)
        result["native_type"] = type(table).__name__
        result["save_reopen_tested"] = False
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    assert {field.Tag for field in sim.FieldManager.Fields} == before
    assert {part.Tag: bool(part.IsModified) for part in session.Parts} == original_flags
    result["outer_rollback_verified"] = True
    return result
