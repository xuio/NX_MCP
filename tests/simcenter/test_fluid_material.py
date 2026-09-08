import sys
from types import ModuleType, SimpleNamespace

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fluid_material import assign_fluid_material


@pytest.mark.parametrize("density", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_density_rejected_before_material_mutation(monkeypatch, density):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")

    class FemPart:
        pass

    cae.FemPart = FemPart
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    fem = FemPart()
    session = SimpleNamespace(Parts=SimpleNamespace(BaseWork=fem))
    # No material manager or undo methods: accessing either before validation fails.
    with pytest.raises(NXToolError) as error:
        assign_fluid_material(session, fem, [], "air", "assumed", density, 1.8e-5, 0.026, 1005)
    assert error.value.code == "NX_INVALID_ARGUMENT"
