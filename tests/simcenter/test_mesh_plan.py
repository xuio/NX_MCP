import pytest

from nx_mcp.simcenter.mesh_plan import validate


@pytest.mark.parametrize(
    "regions",
    [
        [],
        [{}],
        [{"body": "a", "kind": "fluid", "size_mm": True}],
        [{"body": "a", "kind": [], "size_mm": 1}],
        [{"body": "a", "kind": "fluid", "size_mm": 0}],
        [{"body": "a", "kind": "fluid", "size_mm": float("nan")}],
        [{"body": "a", "kind": "solid", "size_mm": 1}] * 2,
    ],
)
def test_invalid_plans_rejected_before_nx(regions):
    with pytest.raises(ValueError):
        validate(regions)


def test_valid_mixed_plan():
    validate(
        [{"body": "a", "kind": "solid", "size_mm": 2}, {"body": "b", "kind": "fluid", "size_mm": 1}]
    )


@pytest.mark.asyncio
async def test_region_schema_is_explicit(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(SimpleNamespace(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_mesh_plan")
    assert "operation_id" in tool.inputSchema["properties"]
    assert tool.inputSchema["$defs"]["BodyMeshRegion"]["properties"]["kind"]["enum"] == [
        "solid",
        "fluid",
    ]


def test_maps_released_when_second_map_acquisition_fails():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock

    from nx_mcp.simcenter.mesh_plan import mesh_counts

    elements = NS(Dispose=Mock())

    class Model:
        FeelementLabelMap = elements

        @property
        def FenodeLabelMap(self):
            raise RuntimeError("native map acquisition failed")

    with pytest.raises(RuntimeError, match="native map acquisition failed"):
        mesh_counts(NS(BaseFEModel=Model()))
    elements.Dispose.assert_called_once()


def test_empty_mesh_rejects_and_releases_both_maps():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock

    from nx_mcp.simcenter.mesh_plan import mesh_counts

    elements = NS(NumElements=0, Dispose=Mock())
    nodes = NS(NumNodes=0, Dispose=Mock())
    with pytest.raises(ValueError, match="no elements"):
        mesh_counts(NS(BaseFEModel=NS(FeelementLabelMap=elements, FenodeLabelMap=nodes)))
    elements.Dispose.assert_called_once()
    nodes.Dispose.assert_called_once()


def test_late_plan_failure_rolls_back_first_body_mesh(monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    from unittest.mock import Mock

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.mesh_plan import generate

    class FemPart:
        pass

    cae = NS(FemPart=FemPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    fem = FemPart()
    body1, body2 = NS(Tag=1, OwningPart=fem), NS(Tag=2, OwningPart=fem)
    fem.Bodies = [body1, body2]
    fem.PartUnits = 1
    fem.UnitCollection = NS(FindObject=lambda _: NS(Name="MilliMeter"))
    meshes = []
    builders = []
    count = 0

    def build(existing):
        nonlocal count
        if existing is None:
            count += 1
        builder = NS(
            ElementType=NS(
                GetElementTypeNames=lambda: ["Linear Tetrahedron"] if count == 1 else [],
                DestinationCollector=NS(AutomaticMode=False),
                ElementTypeName="Linear Tetrahedron",
            ),
            AutoSizeOption=False,
            PropertyTable=NS(
                SetBaseScalarWithDataPropertyValue=lambda *a: None,
                GetBaseScalarWithDataPropertyValue=lambda *a: (1, NS(Name="MilliMeter")),
            ),
            SelectionList=NS(Add=lambda *a: None, GetArray=lambda: [body1]),
            Destroy=Mock(),
        )

        def commit():
            meshes.append("first-body-mesh")
            return ["first-body-mesh"]

        builder.CommitMesh = commit
        builders.append(builder)
        return builder

    manager = NS(GetMeshes=lambda: list(meshes), CreateMesh3dTetBuilder=build)
    fem.BaseFEModel = NS(MeshManager=manager)
    session = NS(
        Parts=NS(BaseWork=fem),
        SetUndoMark=lambda *a: 1,
        UndoToMark=lambda *a: meshes.clear(),
        DeleteUndoMark=Mock(),
    )
    executor = NS(
        nxopen=NS(BasePart=NS(Units=NS(Millimeters=1)), Session=NS(MarkVisibility=NS(Visible=1))),
        session=session,
        objects=NS(resolve=lambda ref, **k: body1 if ref == "a" else body2),
        _reference=lambda obj, *a: {"id": str(obj)},
    )
    with pytest.raises(NXToolError) as error:
        generate(
            executor,
            fem,
            [
                {"body": "a", "kind": "solid", "size_mm": 1},
                {"body": "b", "kind": "fluid", "size_mm": 1},
            ],
        )
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert count == 2 and meshes == [] and len(builders) == 3
    for builder in builders:
        builder.Destroy.assert_called_once()


def test_public_nested_regions_reject_ignored_keys_and_boolean_sizes():
    from pydantic import TypeAdapter, ValidationError

    from nx_mcp.simcenter.server import BodyMeshRegion

    adapter = TypeAdapter(BodyMeshRegion)
    for row in [
        {"body": "a", "kind": "fluid", "size_mm": 1, "ignored": True},
        {"body": "a", "kind": "fluid", "size_mm": True},
    ]:
        with pytest.raises(ValidationError):
            adapter.validate_python(row)


def test_schema_declarations_import_without_sidecar_dependencies(monkeypatch):
    import builtins
    import runpy

    from nx_mcp.simcenter import server

    original = builtins.__import__

    def native_import(name, *args, **kwargs):
        if name == "typing_extensions":
            raise ModuleNotFoundError("NX embedded Python lacks typing_extensions")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", native_import)
    namespace = runpy.run_path(server.__file__)
    assert namespace["BodyMeshRegion"].__required_keys__ == {"body", "kind", "size_mm"}
    assert "nx_sim_mesh_plan" in namespace["NON_MODEL"]


@pytest.mark.parametrize("count", [17, 64, 256])
def test_realistic_body_counts_preserve_validation(count):
    regions = [{"body": f"body-{i}", "kind": "solid", "size_mm": 2} for i in range(count)]
    regions[-1]["kind"] = "fluid"
    validate(regions)
    regions[-1]["body"] = regions[0]["body"]
    with pytest.raises(ValueError, match="distinct"):
        validate(regions)
