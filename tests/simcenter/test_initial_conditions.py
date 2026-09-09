import pytest

from nx_mcp.simcenter.initial_conditions import validate


@pytest.mark.parametrize(
    "mode,value",
    [
        ("automatic", 293.15),
        ("uniform", None),
        ("uniform", True),
        ("uniform", -1),
        ("uniform", float("nan")),
        ("uniform", float("inf")),
        ("file", None),
    ],
)
def test_reject_inactive_invalid_or_unimplemented_values(mode, value):
    with pytest.raises(ValueError):
        validate(mode, value)


@pytest.mark.parametrize("mode,value", [("automatic", None), ("uniform", 0), ("uniform", 313.15)])
def test_documented_mode_inputs(mode, value):
    validate(mode, value)


@pytest.mark.asyncio
async def test_public_initial_conditions_modes_and_replay_schema(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    class Bridge:
        async def call(self, method, params):
            return {"status": "success", "params": params}

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_initial_conditions")
    props = tool.inputSchema["properties"]
    assert props["mode"]["enum"] == ["automatic", "uniform"]
    assert "operation_id" in props
    assert props["temperature_k"]["default"] is None
