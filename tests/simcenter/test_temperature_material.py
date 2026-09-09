import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.temperature_material import validate


def test_shared_domain_uses_intersection():
    m, domain = validate("M", [[270, 100], [320, 200]], [[280, 800], [330, 1000]], 2700, "assumed")
    assert domain == [280, 320]
    assert m["ThermalConductivity"]["samples"] == [[270, 100], [320, 200]]


@pytest.mark.parametrize("density", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_density(density):
    with pytest.raises(NXToolError):
        validate("M", [[270, 100], [320, 200]], [[280, 800], [330, 1000]], density, "assumed")


@pytest.mark.parametrize(
    "k,cp",
    [
        ([[270, 0], [320, 200]], [[280, 800], [330, 1000]]),
        ([[270, 100], [280, 200]], [[280, 800], [330, 1000]]),
        ([[270, 100], [270, 200]], [[280, 800], [330, 1000]]),
        ([[270, 100], [320, float("nan")]], [[280, 800], [330, 1000]]),
    ],
)
def test_invalid_property_tables(k, cp):
    with pytest.raises(NXToolError):
        validate("M", k, cp, 2700, "assumed")


def test_material_inventory_uses_current_reader(monkeypatch):
    from types import SimpleNamespace as NS

    from nx_mcp.simcenter import material_inventory, properties

    material = NS(
        Name="M",
        GetMaterialType=lambda: "Isotropic",
        GetDescription=lambda: "source",
        GetPropTable=lambda: "table",
    )
    fem = NS(MaterialManager=NS(PhysicalMaterials=[material]), FullPath="fixture.fem")
    monkeypatch.setattr(
        properties,
        "read_properties",
        lambda table, nx: [
            {"field_scale": 2, "field_definition": {"kind": "validated_scalar_table"}}
        ],
    )
    result = material_inventory.inspect_materials(fem, None, lambda *args: {"id": "M"})
    assert result["materials"][0]["properties"][0]["field_scale"] == 2
