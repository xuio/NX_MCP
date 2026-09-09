from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.coupled_setup import SOLUTION_UNITS, initialize


def table(values):
    return NS(
        GetIntegerPropertyValue=lambda k: values[k],
        GetStringPropertyValue=lambda k: values[k],
        SetIntegerPropertyValue=lambda k, v: values.update({k: v}),
        SetStringPropertyValue=lambda k, v: values.update({k: v}),
    )


def test_uninitialized_and_repeated_setup_read_back_identically():
    values = {**dict.fromkeys(SOLUTION_UNITS, ""), "Solver Type": 0}
    actual = initialize(table(values))
    assert actual == {"solver_type": 6, "units": SOLUTION_UNITS}
    assert initialize(table(values)) == actual


@pytest.mark.parametrize("key,value", [("Pressure", "psi"), ("Solver Type", 5)])
def test_alternate_existing_settings_rejected_without_writes(key, value):
    values = {**dict.fromkeys(SOLUTION_UNITS, ""), "Solver Type": 0, key: value}
    before = dict(values)
    with pytest.raises(NXToolError):
        initialize(table(values))
    assert values == before


def test_ignored_native_write_is_not_success():
    values = {**dict.fromkeys(SOLUTION_UNITS, ""), "Solver Type": 0}
    native = table(values)
    native.SetStringPropertyValue = lambda *a: None
    with pytest.raises(NXToolError, match="readback differs"):
        initialize(native)
