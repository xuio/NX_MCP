import pytest

from nx_mcp.server import create_server
from nx_mcp.workspace import Workspace


class Bridge:
    async def call(self, method, params):
        return {"status": "success", "method": method, "params": params}


@pytest.mark.asyncio
async def test_simcenter_opt_in_preserves_cad_surface(tmp_path, monkeypatch):
    monkeypatch.delenv("NX_MCP_ENABLE_SIMCENTER", raising=False)
    baseline = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    base = {t.name for t in await baseline.list_tools()}
    assert "nx_sim_capabilities" not in base
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    extended = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await extended.list_tools()}
    assert base <= set(tools)
    assert "operation_id" in tools["nx_sim_create_benchmark"].inputSchema["properties"]
    assert "operation_id" not in tools["nx_sim_documents"].inputSchema["properties"]
    assert "nx_sim_mesh" in tools
    assert "nx_sim_material" in tools


def test_basework_avoids_cad_accessor_failure():
    from types import SimpleNamespace

    from nx_mcp.nx_bridge import NXOpenExecutor
    from nx_mcp.runtime import NXToolError

    class FemPart:
        pass

    fem = FemPart()

    class Parts:
        BaseWork = fem

        @property
        def Work(self):
            raise RuntimeError("The part file is not a .prt part")

    executor = object.__new__(NXOpenExecutor)
    executor.session = SimpleNamespace(Parts=Parts())
    assert executor._work_part(required=False) is fem
    with pytest.raises(NXToolError) as error:
        executor._work_part()
    assert error.value.code == "NX_DOCUMENT_TYPE"


@pytest.mark.asyncio
async def test_result_inventory_is_read_only_and_discoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_result_inventory")
    fields = tool.inputSchema["properties"]
    assert "document" in fields and "offset" in fields and "limit" in fields
    assert "operation_id" not in fields


def test_simcenter_tools_have_simulation_domain():
    from nx_mcp.agent_surface import category

    assert category("nx_sim_result_inventory") == "simulation"
    assert category("nx_sim_create_benchmark") == "simulation"
    assert category("nx_screenshot") == "display"


@pytest.mark.asyncio
async def test_result_identity_is_bounded_and_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_result_identity")
    props = tool.inputSchema["properties"]
    assert props["maximum_bytes"]["default"] == 1_073_741_824
    assert "document" in props
    assert "operation_id" not in props
    assert tool.annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_analysis_environment_choices_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_create_benchmark")
    choice = tool.inputSchema["properties"]["analysis_type"]
    assert choice["enum"] == ["thermal", "flow", "coupled_thermal_flow"]
    assert choice["default"] == "thermal"


@pytest.mark.asyncio
async def test_flow_setup_has_explicit_actions_and_operation_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_flow_setup")
    props = tool.inputSchema["properties"]
    assert props["action"]["enum"] == ["create_step", "attach_defaults", "coupled_steady"]
    assert "operation_id" in props
    assert tool.annotations.readOnlyHint is False


@pytest.mark.asyncio
async def test_flow_convergence_schema_preserves_mutation_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_flow_convergence")
    props = tool.inputSchema["properties"]
    assert {
        "document",
        "residual",
        "flow_imbalance_fraction",
        "iteration_limit",
        "operation_id",
    } <= props.keys()
    assert tool.annotations.readOnlyHint is False


@pytest.mark.asyncio
async def test_job_status_is_read_only_and_compact_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_job_status")
    props = tool.inputSchema["properties"]
    assert props["include_manifest"]["default"] is False
    assert props["include_evidence"]["default"] is False
    assert "operation_id" not in props
    assert tool.annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_sim_save_as_is_explicit_mutation_with_retry_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_save_as")
    assert {"document", "path", "operation_id"} <= tool.inputSchema["properties"].keys()
    assert tool.annotations.readOnlyHint is False


@pytest.mark.asyncio
async def test_dependency_inspection_is_paged_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_dependencies")
    assert {"document", "offset", "limit"} <= tool.inputSchema["properties"].keys()
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_temperature_result_read_only_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_temperature_result")
    props = tool.inputSchema["properties"]
    assert props["loadcase_index"]["default"] == 0
    assert props["iteration_index"]["default"] == 0
    assert "operation_id" not in props and tool.annotations.readOnlyHint


@pytest.mark.asyncio
async def test_mesh_quality_exposes_optional_criteria_and_side_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_mesh_quality")
    assert tool.inputSchema["properties"]["include_settings"]["default"] is False
    assert not tool.annotations.readOnlyHint


@pytest.mark.asyncio
async def test_solution_inventory_and_selection_have_distinct_side_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    assert tools["nx_sim_solutions"].annotations.readOnlyHint
    assert "operation_id" not in tools["nx_sim_solutions"].inputSchema["properties"]
    assert not tools["nx_sim_select_solution"].annotations.readOnlyHint
    assert "operation_id" in tools["nx_sim_select_solution"].inputSchema["properties"]


@pytest.mark.asyncio
async def test_step_inventory_requires_owner_and_solution_and_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_steps")
    assert set(tool.inputSchema["required"]) == {"document", "solution"}
    assert tool.inputSchema["properties"]["include_membership"]["default"] is False
    assert tool.annotations.readOnlyHint
    assert "operation_id" not in tool.inputSchema["properties"]


@pytest.mark.asyncio
async def test_fan_tables_expose_units_enums_and_read_only_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    create = tools["nx_sim_fan_table"]
    props = create.inputSchema["properties"]
    assert props["pressure_convention"]["enum"] == ["static", "total"]
    assert props["provenance_kind"]["enum"] == ["measured", "datasheet", "assumed"]
    assert props["points"]["items"]["minItems"] == 2
    assert props["points"]["items"]["maxItems"] == 2
    assert "operation_id" in props and not create.annotations.readOnlyHint
    inspect = tools["nx_sim_fan_tables"]
    assert inspect.annotations.readOnlyHint
    assert inspect.inputSchema["properties"]["include_samples"]["default"] is False


@pytest.mark.asyncio
async def test_simulation_object_inventory_is_read_only_and_compact(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_objects")
    assert tool.annotations.readOnlyHint
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.inputSchema["properties"]["include_properties"]["default"] is False
    assert tool.inputSchema["properties"]["include_targets"]["default"] is False


@pytest.mark.asyncio
async def test_fan_assignment_requires_typed_selections_and_operation_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_assign_fan")
    assert set(tool.inputSchema["required"]) == {"document", "inlet", "field"}
    assert "operation_id" in tool.inputSchema["properties"]
    assert not tool.annotations.readOnlyHint


@pytest.mark.asyncio
async def test_job_log_is_bounded_read_only_without_operation_id(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_job_log")
    assert tool.annotations.readOnlyHint
    assert set(tool.inputSchema["required"]) == {"job_id", "log_name"}
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.inputSchema["properties"]["maximum_bytes"]["default"] == 8192


@pytest.mark.asyncio
async def test_job_log_catalog_is_read_only_and_paged(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_job_logs")
    assert tool.annotations.readOnlyHint
    assert set(tool.inputSchema["required"]) == {"job_id"}
    assert tool.inputSchema["properties"]["limit"]["default"] == 20


@pytest.mark.asyncio
async def test_pressure_result_field_enum_and_read_only_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_pressure_result")
    assert tool.annotations.readOnlyHint
    assert tool.inputSchema["properties"]["field"]["enum"] == ["pressure", "total_pressure"]
    assert "operation_id" not in tool.inputSchema["properties"]


@pytest.mark.asyncio
async def test_variant_tools_have_required_plan_hash_and_mutation_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    for name in ("nx_sim_variant_plan", "nx_sim_variant_receipt"):
        assert tools[name].annotations.readOnlyHint is True
        assert "operation_id" not in tools[name].inputSchema["properties"]
    create = tools["nx_sim_variant_create"]
    assert create.annotations.readOnlyHint is False
    assert "expected_plan_sha256" in create.inputSchema["required"]
    assert "operation_id" in create.inputSchema["properties"]
    assert create.inputSchema["properties"]["saved_snapshot"]["default"] is False
    result = await server.call_tool(
        "nx_sim_variant_plan", {"document": "example", "folder": "../outside", "name": "Example"}
    )
    assert result.isError and result.structuredContent["code"] == "NX_PATH_OUTSIDE_WORKSPACE"


@pytest.mark.asyncio
async def test_solution_membership_is_optional_read_only_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_solutions")
    assert tool.inputSchema["properties"]["include_membership"]["default"] is False
    assert tool.annotations.readOnlyHint is True
    assert "operation_id" not in tool.inputSchema["properties"]


@pytest.mark.asyncio
async def test_temperature_nodes_requires_revision_and_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_temperature_nodes")
    assert {"document", "result_sha256"} <= set(tool.inputSchema["required"])
    assert tool.inputSchema["properties"]["limit"]["default"] == 100
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.annotations.readOnlyHint
