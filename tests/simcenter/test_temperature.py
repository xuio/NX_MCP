import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.boundaries import create_temperature


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_invalid_absolute_temperature_rejected_before_creation(monkeypatch, value):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim = NS()
    with pytest.raises(NXToolError) as exc:
        create_temperature(NS(Parts=NS(BaseWork=sim)), sim, [], value, "cold end", "prescribed")
    assert exc.value.code == "NX_INVALID_ARGUMENT"
