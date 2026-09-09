from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.material_inventory import inspect_materials


def test_paging_reads_only_requested_materials_and_reports_failures(monkeypatch):

    def forbidden():
        raise AssertionError("Off-page material must not be inspected")

    first = NS(GetMaterialType=forbidden, GetDescription=forbidden)
    second = NS(
        GetMaterialType=lambda: "Orthotropic",
        GetDescription=lambda: "assumed",
        GetPropTable=lambda: "table",
    )

    def failed(table, nx):
        raise RuntimeError("native failure")

    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", failed)
    fem = NS(FullPath="case.fem", MaterialManager=NS(PhysicalMaterials=[first, second]))
    result = inspect_materials(fem, None, lambda *args: {"id": "second"}, offset=1, limit=1)
    assert result["total"] == 2 and result["next_offset"] is None
    row = result["materials"][0]
    assert row["native_type"] == "Orthotropic" and row["provenance"] == "assumed"
    assert row["inspection_errors"] == [
        {"field": "properties", "status": "read_failed", "nx_code": None}
    ]


@pytest.mark.parametrize(
    "offset,limit", [(-1, 1), (True, 1), (0, 0), (0, 101), (0, True), (1.5, 1)]
)
def test_invalid_page_rejected_before_native_access(offset, limit):
    with pytest.raises(NXToolError):
        inspect_materials(None, None, None, offset=offset, limit=limit)
