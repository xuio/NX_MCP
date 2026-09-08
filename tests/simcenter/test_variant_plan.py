import copy

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.variant_plan import plan_variant
from nx_mcp.workspace import Workspace, WorkspaceViolation


@pytest.fixture
def fixture(tmp_path):
    rows = []
    for suffix, role in [("sim", "simulation"), ("fem", "mesh"), ("prt", "AssociatedCadPart")]:
        p = tmp_path / ("source." + suffix)
        p.write_bytes(b"source revision")
        rows.append(
            {
                "path": str(p),
                "roles": [role],
                "modified": False,
                "file_state": "exists",
                "fully_loaded": True,
                "units": "mm",
            }
        )
    return Workspace(tmp_path), {"rows": rows, "unresolved": []}


def plan(fixture, **kw):
    ws, deps = fixture
    return plan_variant(ws, deps, folder="variants/case1", name="CaseOne", **kw)


def test_plan_is_read_only_and_names_all_native_files(fixture):
    ws, _ = fixture
    result = plan(fixture)
    assert not (ws.root / "variants").exists()
    assert [r["destination"].split("/")[-1] for r in result["mapping"]] == [
        "CaseOne_analysis.sim",
        "CaseOne_mesh.fem",
        "CaseOne_cad_01.prt",
    ]
    assert result["source_bytes"] == 45
    assert plan(fixture)["plan_sha256"] == result["plan_sha256"]
    (ws.root / "source.prt").write_bytes(b"different saved revision")
    assert plan(fixture)["plan_sha256"] != result["plan_sha256"]


def test_unsaved_requires_explicit_saved_snapshot(fixture):
    fixture[1]["rows"][0]["modified"] = True
    with pytest.raises(NXToolError) as caught:
        plan(fixture)
    assert caught.value.code == "NX_SIM_UNSAVED_DOCUMENT"
    result = plan(fixture, saved_snapshot=True)
    assert result["unsaved_sources_excluded"] == [fixture[1]["rows"][0]["path"]]


def test_unresolved_and_duplicate_dependencies_fail(fixture):
    bad = copy.deepcopy(fixture[1])
    bad["unresolved"] = [{"path": "missing.prt"}]
    with pytest.raises(NXToolError):
        plan((fixture[0], bad))
    bad["unresolved"] = []
    bad["rows"].append(copy.deepcopy(bad["rows"][2]))
    with pytest.raises(NXToolError):
        plan((fixture[0], bad))


def test_existing_output_and_loaded_basename_fail(fixture):
    with pytest.raises(NXToolError) as caught:
        plan(fixture, loaded_paths=["/another/CASEONE_MESH.fem"])
    assert caught.value.code == "NX_SIM_NAME_CONFLICT"
    (fixture[0].root / "variants/case1").mkdir(parents=True)
    with pytest.raises(NXToolError) as caught:
        plan(fixture)
    assert caught.value.code == "NX_SIM_OUTPUT_CONFLICT"


def test_hash_budget_and_workspace_escape_fail(fixture):
    with pytest.raises(NXToolError) as caught:
        plan(fixture, maximum_bytes=20)
    assert caught.value.code == "NX_SIM_SOURCE_SNAPSHOT_FAILED"
    with pytest.raises(WorkspaceViolation):
        plan_variant(fixture[0], fixture[1], folder="../outside", name="Case")
