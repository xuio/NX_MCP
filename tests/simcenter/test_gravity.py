from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.gravity import validate


@pytest.mark.parametrize(
    "vector", [[], [1, 2], [0, 0, float("nan")], [True, 0, 0], [0, 0, float("inf")], "0,0,-9.8"]
)
def test_invalid_vectors(vector):
    with pytest.raises(NXToolError):
        validate(vector, "gravity")


@pytest.mark.parametrize("vector", [[0, 0, 0], [0, 0, -9.80665], [-1, 2, 3]])
def test_finite_signed_vectors(vector):
    validate(vector, "gravity")


@pytest.mark.asyncio
async def test_public_schema(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_gravity")
    assert set(["document", "bodies", "acceleration_m_s2", "name"]).issubset(
        tool.inputSchema["required"]
    )
    assert "operation_id" in tool.inputSchema["properties"]


def test_overlap_uses_native_load_descriptor_and_rejects_before_mutation(monkeypatch):
    import sys
    from nx_mcp.simcenter.gravity import create

    cae = NS()
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    body = NS(Tag=1)
    load = NS(
        Name="existing",
        DescriptorName="ComponentGravityField",
        TargetSetManager=NS(TargetSetCount=1, GetTargetSetMembers=lambda i: (0, [None, NS(Obj=None), NS(Obj=body)])),
    )
    sim = NS(Simulation=NS(ActiveSolution=NS(AnalysisType="Coupled Thermal-Flow"), Loads=[load]))
    body.OwningPart = sim
    session = NS(Parts=NS(BaseWork=sim))
    with pytest.raises(NXToolError) as error:
        create(session, sim, [body], [0, 0, -9.8], "new name")
    assert error.value.code == "NX_SIM_DUPLICATE_GRAVITY"
