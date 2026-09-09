import sys
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import mesh_guard


@pytest.mark.parametrize("budget", [True, 0, 1000001, 1.5, None])
def test_invalid_budget_before_native_import(budget):
    with pytest.raises(NXToolError) as error:
        mesh_guard.validate_budget(budget)
    assert error.value.code == "NX_INVALID_ARGUMENT"


def test_native_reader_error_is_explicit_and_preserves_code(monkeypatch):
    class FemPart:
        pass

    cae = NS(FemPart=FemPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)

    class NativeFailure(Exception):
        ErrorCode = 1234

    def fail(*a, **k):
        raise NativeFailure("native mesh read failed")

    monkeypatch.setattr("nx_mcp.simcenter.mesh_state.capture", fail)
    with pytest.raises(NXToolError) as error:
        mesh_guard.capture(NS(FemPart=FemPart()))
    assert error.value.code == "NX_SIM_MESH_STATE_UNAVAILABLE"
    assert error.value.nx_code == 1234
    assert error.value.details["mutation_outcome"] == "not_started"
