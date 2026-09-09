import hashlib

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_binding import audit_job_result, require_job_owner
from nx_mcp.workspace import Workspace


def case(tmp_path):
    sim = tmp_path / "case.sim"
    sim.write_bytes(b"original model")
    digest = hashlib.sha256(sim.read_bytes()).hexdigest()
    result = {"path": str(tmp_path / "case.bun"), "sha256": "a" * 64, "bytes": 10}
    job = {
        "job_id": "run-01",
        "state": "solver_exited",
        "manifest": {
            "analysis_path": str(sim),
            "solution": "Flow",
            "solver": "NX MULTIPHYSICS",
            "analysis_type": "Flow",
            "prepared_input": {"dependencies": [{"path": str(sim), "sha256": digest}]},
        },
        "record": {"evidence": {"observer_adapter": 1, "result": result}},
    }
    deps = {"unresolved": [], "rows": [{"path": str(sim), "modified": False, "fully_loaded": True}]}
    return Workspace(tmp_path), job, deps, result, sim


def test_owner_rejects_analysis_copy_and_other_solution(tmp_path):
    ws, job, _, _, sim = case(tmp_path)
    args = {"path": str(sim), "solution": "Flow", "solver": "NX MULTIPHYSICS", "analysis": "Flow"}
    require_job_owner(ws, job, **args)
    for change in [{"path": str(tmp_path / "copy.sim")}, {"solution": "Other"}]:
        with pytest.raises(NXToolError, match="exact analysis"):
            require_job_owner(ws, job, **{**args, **change})


def test_matching_artifact_never_hides_changed_live_or_saved_model(tmp_path):
    ws, job, deps, result, sim = case(tmp_path)
    matched = audit_job_result(ws, job, deps, [result], maximum_bytes=1000)
    assert matched["state"] == "not_verified"
    assert matched["live_mesh_state"]["reason"] == "mesh_state_missing"
    assert (
        matched["model_result_freshness"] == "not_verified" and not matched["engineering_accepted"]
    )
    deps["rows"][0]["modified"] = True
    dirty = audit_job_result(ws, job, deps, [result], maximum_bytes=1000)
    assert dirty["state"] == "not_verified" and dirty["associated_result_matches_observed_artifact"]
    deps["rows"][0]["modified"] = False
    sim.write_bytes(b"changed model")
    assert audit_job_result(ws, job, deps, [result], maximum_bytes=1000)["state"] == "not_verified"


def test_result_replacement_extra_association_and_missing_exit_fail_binding(tmp_path):
    ws, job, deps, result, _ = case(tmp_path)
    for results in [[{**result, "sha256": "b" * 64}], [result, result], []]:
        assert not audit_job_result(ws, job, deps, results, maximum_bytes=1000)[
            "associated_result_matches_observed_artifact"
        ]
    job["state"] = "launch_returned"
    assert (
        "verified_solver_exit_evidence_missing"
        in audit_job_result(ws, job, deps, [result], maximum_bytes=1000)["reasons"]
    )


def test_live_thermal_change_marks_result_stale_despite_matching_files(tmp_path):
    ws, job, deps, result, _ = case(tmp_path)
    snapshot = {"adapter": 1, "scope": "thermal", "owner_path": "case.fem", "sha256": "a" * 64}
    job["manifest"].update(analysis_type="Thermal", live_thermal_state=snapshot)
    audited = audit_job_result(
        ws,
        job,
        deps,
        [result],
        maximum_bytes=1000,
        live_thermal_state={**snapshot, "sha256": "b" * 64},
    )
    assert audited["revision"]["revision_matches"]
    assert audited["model_result_freshness"] == "stale"
    assert "live_thermal_material_or_frame_changed" in audited["reasons"]


def test_old_boundary_schema_cannot_verify_result_even_with_matching_files(tmp_path):
    ws, job, deps, result, _ = case(tmp_path)
    old = {"adapter": 2, "scope": "thermal", "owner_path": "case.sim", "sha256": "a" * 64}
    current = {**old, "adapter": 3, "boundary_scope": "boundary_v4"}
    job["manifest"].update(analysis_type="Thermal", live_thermal_state=old)
    audited = audit_job_result(
        ws, job, deps, [result], maximum_bytes=1000, live_thermal_state=current
    )
    assert audited["revision"]["revision_matches"]
    assert audited["state"] == "not_verified"
    assert audited["model_result_freshness"] == "not_verified"
    assert "live_thermal_state_scope_mismatch" in audited["reasons"]


def test_same_count_mesh_change_marks_result_stale_and_missing_baseline_is_not_invented(tmp_path):
    from nx_mcp.simcenter.mesh_state import digest

    ws, job, deps, result, _ = case(tmp_path)
    nodes = [(1, [0, 0, 0]), (2, [1, 0, 0]), (3, [0, 1, 0]), (4, [0, 0, 1])]
    elements = [(1, "Tetrahedron", "mesh", "collector", [1, 2, 3, 4])]
    before = digest(nodes, elements, units="mm", owner_path="case.fem")
    after = digest([(1, [0.01, 0, 0]), *nodes[1:]], elements, units="mm", owner_path="case.fem")
    assert before["counts"] == after["counts"]
    job["manifest"]["live_mesh_state"] = before
    matched = audit_job_result(ws, job, deps, [result], maximum_bytes=1000, live_mesh_state=before)
    assert matched["state"] == "association_and_supplied_revision_match"
    assert matched["model_result_freshness"] == "not_verified"
    changed = audit_job_result(ws, job, deps, [result], maximum_bytes=1000, live_mesh_state=after)
    assert (
        changed["associated_result_matches_observed_artifact"]
        and changed["revision"]["revision_matches"]
    )
    assert changed["model_result_freshness"] == "stale"
    assert "live_mesh_changed" in changed["reasons"]
    del job["manifest"]["live_mesh_state"]
    old = audit_job_result(ws, job, deps, [result], maximum_bytes=1000, live_mesh_state=before)
    assert old["live_mesh_state"]["state"] == "not_verified"
    assert old["model_result_freshness"] == "not_verified"


def test_mesh_inspection_failure_retains_result_association_without_freshness_claim(tmp_path):
    ws, job, deps, result, _ = case(tmp_path)
    error = {"code": "NX_SIM_INSPECTION_LIMIT", "message": "Recorded budget exceeded"}
    audited = audit_job_result(
        ws, job, deps, [result], maximum_bytes=1000, mesh_inspection_error=error
    )
    assert audited["associated_result_matches_observed_artifact"]
    assert audited["live_mesh_state"]["error"] == error
    assert audited["model_result_freshness"] == "not_verified"
    assert "live_mesh_inspection_failed" in audited["reasons"]
