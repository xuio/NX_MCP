from types import SimpleNamespace as NS

from nx_mcp.simcenter.thermal_state import capture_thermal_state


def test_empty_or_unsupported_collection_never_claims_a_fingerprint():
    fem = NS(
        FullPath="case.fem",
        PartUnits=1,
        BaseFEModel=NS(
            MeshManager=NS(GetMeshCollectors=lambda: [NS(CollectorNeutralType="Fluid")])
        ),
    )
    nx = NS(BasePart=NS(Units=NS(Millimeters=1)))
    result = capture_thermal_state(fem, nx)
    assert result["sha256"] is None
    assert result["full_model_freshness"] == "not_verified"


def test_failed_assignment_inspection_cannot_produce_hash(monkeypatch):
    import nx_mcp.simcenter.thermal_state as module

    monkeypatch.setattr(module, "inspect_collector", lambda *args: {"collector": {"id": "c"}})
    fem = NS(
        FullPath="case.fem",
        PartUnits=1,
        BaseFEModel=NS(
            MeshManager=NS(GetMeshCollectors=lambda: [NS(CollectorNeutralType="Solid")])
        ),
    )
    nx = NS(BasePart=NS(Units=NS(Millimeters=1)))
    result = capture_thermal_state(fem, nx)
    assert result["sha256"] is None
    assert result["errors"][0]["reason"] == "assignment_read_failed"


def test_live_comparison_does_not_promote_partial_match_to_full_freshness():
    from nx_mcp.simcenter.thermal_state import compare_thermal_state

    state = {"adapter": 1, "scope": "thermal", "owner_path": "case.fem", "sha256": "a" * 64}
    assert compare_thermal_state(state, state)["full_model_freshness"] == "not_verified"
    assert compare_thermal_state(state, {**state, "sha256": "b" * 64})["state"] == "changed"
    assert (
        compare_thermal_state(state, {**state, "owner_path": "copy.fem"})["state"] == "not_verified"
    )
    assert compare_thermal_state(None, state)["state"] == "not_verified"


def test_boundary_schema_change_is_unverified_even_with_identical_digest():
    import pytest

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.thermal_state import compare_thermal_state, require_thermal_state

    current = {
        "adapter": 3,
        "scope": "thermal boundaries",
        "owner_path": "case.sim",
        "boundary_scope": "boundary_v4",
        "sha256": "a" * 64,
    }
    old = {**current, "adapter": 2}
    old.pop("boundary_scope")
    for incompatible in [old, {**current, "boundary_scope": "boundary_v3"}]:
        comparison = compare_thermal_state(incompatible, current)
        assert comparison == {
            "state": "not_verified",
            "reason": "live_thermal_state_scope_mismatch",
        }
        with pytest.raises(NXToolError) as error:
            require_thermal_state(incompatible, current)
        assert error.value.details["mutation_outcome"] == "not_started"
    assert compare_thermal_state(current, current)["state"] == "matches"
    assert (
        compare_thermal_state(current, {**current, "sha256": "b" * 64})["reason"]
        == "live_thermal_state_changed"
    )
