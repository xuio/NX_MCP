"""Result selection/cleanup contracts; numerical correctness requires native evidence."""

import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.results import field_metadata, iteration_inventory, temperature_extrema


def _field(name="Mass Flux - Nodal"):
    return NS(
        Name=name,
        Quantity="MassFlux",
        Location="Nodal",
        Datatype="Scalar",
        Complex=False,
        AskComponents=lambda: (["Scalar component"], ["Scalar"]),
        AskDefaultUnitForComponent=lambda _: NS(
            Name="NativeDefault", Symbol="default_symbol", Measure="native_measure"
        ),
        AskSourceUnitForComponent=lambda _: NS(
            Name="NativeSource", Symbol="source_symbol", Measure="native_measure"
        ),
    )


@pytest.fixture
def native_result(monkeypatch):
    cae = ModuleType("NXOpen.CAE")
    cae.Result = NS(Component=NS(Scalar=0))
    cae.BaseIteration = NS(
        IterationValueType=NS(Time=0), IterationValueDataType=NS(Double=0, Integer=1)
    )
    nx = ModuleType("NXOpen")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    released = []
    selected = []
    params = NS(
        SetLoadcaseIteration=lambda *indices: selected.append(indices),
        SetGenericResultType=lambda _: None,
        SetResultComponent=lambda _: None,
        SetUnit=lambda _: None,
    )

    def iteration(time):
        return NS(
            GetResultTypes=lambda: [
                _field("Temperature - Nodal"),
                _field("Temperature - Element-Nodal"),
            ],
            GetValueTypes=lambda: [0],
            GetValueDataType=lambda _: 0,
            GetDoubleValueOfType=lambda _: time,
            GetUnitOfType=lambda _: NS(Name="Second"),
        )

    result = NS(
        GetLoadcases=lambda: [
            NS(GetIterations=lambda: [iteration(0)]),
            NS(GetIterations=lambda: [iteration(2025)]),
        ],
        AskNumNodes=lambda: 246,
    )
    manager = NS(
        CreateSolutionResult=lambda _: result,
        CreateResultParameters=lambda: params,
        CreateResultAccess=lambda *_: NS(AskMinMaxLocation=lambda: (0, 36, 36.02, 1, 2, 0, 0)),
        DeleteResultAccess=lambda _: released.append("access"),
        DeleteResultParameters=lambda _: released.append("params"),
        DeleteResult=lambda _: released.append("result"),
    )
    return (
        NS(ResultManager=manager),
        NS(
            Simulation=NS(ActiveSolution=object()), UnitCollection=NS(FindObject=lambda _: object())
        ),
        selected,
        released,
    )


def test_selects_requested_transient_loadcase(native_result):
    session, sim, selected, released = native_result
    values = temperature_extrema(session, sim, loadcase_index=1)
    assert selected == [(1, 0)]
    assert values["loadcase_index"] == 1
    assert values["result_freshness"] == "not_verified"
    assert released == ["access", "params", "result"]


def test_out_of_range_releases_loaded_result(native_result):
    session, sim, selected, released = native_result
    with pytest.raises(ValueError, match="outside"):
        temperature_extrema(session, sim, iteration_index=1)
    assert selected == []
    assert released == ["result"]


def test_paged_times_come_from_native_metadata(native_result):
    session, sim, _, released = native_result
    page = iteration_inventory(session, sim, offset=1, limit=1)
    assert page["total"] == 2
    assert page["next_offset"] is None
    assert page["items"][0]["values"] == [
        {"kind": "time", "native_type": "0", "value": 2025, "native_unit": "Second"}
    ]
    assert released == ["result"]


def test_inventory_preserves_result_used_by_visible_postview(native_result):
    session, sim, _, released = native_result
    existing = session.ResultManager.CreateSolutionResult(None)
    session.Post = NS(
        GetPostviewIds=lambda: [2], GetResultForPostview=lambda _: (existing, object())
    )
    page = iteration_inventory(session, sim)
    assert page["total"] == 2
    assert released == ["params"]  # Only the temporary postview parameter copy.


def test_selects_coupled_element_nodal_field(native_result):
    session, sim, _, released = native_result
    values = temperature_extrema(session, sim, location="element_nodal")
    assert values["field"] == "Temperature - Element-Nodal"
    assert values["field_location"] == "element_nodal"
    assert released == ["access", "params", "result"]


def test_missing_field_rejects_without_fallback(native_result):
    session, sim, _, released = native_result
    with pytest.raises(ValueError, match="selected temperature field"):
        temperature_extrema(session, sim, location="elemental")
    assert released == ["result"]


def test_invalid_field_location_does_not_load_result(native_result):
    session, sim, _, released = native_result
    with pytest.raises(ValueError, match="location must"):
        temperature_extrema(session, sim, location="fluid")
    assert released == []


def test_field_metadata_retains_distinct_source_and_default_units():
    metadata = field_metadata(_field())
    assert metadata["location"] == "Nodal"
    assert metadata["quantity"] == "MassFlux"
    assert metadata["components"] == [
        {
            "component": "Scalar",
            "description": "Scalar component",
            "default_unit": "NativeDefault",
            "source_unit": "NativeSource",
            "default_unit_symbol": "default_symbol",
            "source_unit_symbol": "source_symbol",
            "default_unit_measure": "native_measure",
            "source_unit_measure": "native_measure",
        }
    ]
    field = _field()
    field.AskComponents = lambda: (["Scalar component"], ["Scalar"])
    field.AskSourceUnitForComponent = lambda _: None
    assert field_metadata(field)["components"][0]["source_unit"] is None


@pytest.mark.parametrize(
    "components", [(2, ["Scalar"]), [], (["Scalar"] * 33, ["desc"] * 33), (["Scalar"], [])]
)
def test_invalid_component_shape_rejected(components):
    field = _field()
    field.AskComponents = lambda: components
    with pytest.raises(ValueError):
        field_metadata(field)


def test_inventory_metadata_error_releases_owned_result(native_result):
    session, sim, _, released = native_result
    result = session.ResultManager.CreateSolutionResult(None)
    field = _field()
    field.AskComponents = lambda: (2, ["Scalar"])
    result.GetLoadcases = lambda: [
        NS(GetIterations=lambda: [NS(GetValueTypes=lambda: [], GetResultTypes=lambda: [field])])
    ]
    report = iteration_inventory(session, sim)
    assert report["items"][0]["fields"] == ["Mass Flux - Nodal"]
    metadata = report["items"][0]["field_metadata"][0]
    assert metadata["state"] == "unavailable"
    assert "components" not in metadata
    assert "shape unsupported" in metadata["error"]
    assert released == ["result"]
