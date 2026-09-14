import inspect
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.analysis_documents import (
    analysis_environment,
    create,
    initialize_steady_thermal,
)
from nx_mcp.simcenter.server import nx_sim_create_analysis


class Properties:
    def __init__(self, reject=False):
        self.values = {}
        self.reject = reject

    def SetNamedPropertyTablePropertyValue(self, key, value):
        self.values[key] = value

    def GetNamedPropertyTablePropertyValue(self, key):
        return None if self.reject else self.values[key]

    def SetIntegerPropertyValue(self, key, value):
        self.values[key] = value

    def GetIntegerPropertyValue(self, key):
        return 1 if self.reject else self.values[key]


def fixture(allowed=None, table_reject=False, step_reject=False, activate=True):
    allowed = ["Other step", "Step - Thermal"] if allowed is None else allowed
    calls = []

    def table(descriptor, environment, solver, key, index):
        calls.append((descriptor, environment, solver, key, index))
        return NS(DescriptorType=descriptor, Name=key)

    sim = NS(ModelingObjectPropertyTables=NS(CreateModelingObjectPropertyTable=table))
    solution = NS(
        PropertyTable=Properties(table_reject),
        Tag=9,
        AllowedStepTypeCount=len(allowed),
        ActiveStep=None,
    )

    def step(index, active, name):
        assert allowed[index] == "Step - Thermal"
        assert active
        result = NS(Name=name, PropertyTable=Properties(step_reject))
        if activate:
            solution.ActiveStep = result
        return result

    solution.CreateStep = step
    native = NS(
        Sf=NS(SolutionAskDescriptorNx=lambda tag: tag),
        Sfl=NS(
            SolutionAskNthAllowableStepDescriptorNx=lambda desc, i: i,
            StepDescriptorAskNameNx=lambda i: allowed[i],
        ),
    )
    return sim, solution, native, calls


def test_existing_call_defaults_remain_coupled():
    for call in (create, nx_sim_create_analysis):
        assert inspect.signature(call).parameters["analysis_type"].default == "coupled_thermal_flow"
    assert analysis_environment("coupled_thermal_flow") == ("Coupled Thermal-Flow", "Thermal-Flow")
    assert analysis_environment("thermal") == ("Thermal", "Thermal")


@pytest.mark.parametrize("value", ["flow", "", None, [], 5])
def test_invalid_environment_rejected_before_native_import(value):
    with pytest.raises(NXToolError):
        create(None, None, None, None, value)


def test_thermal_tables_and_active_steady_step_committed():
    sim, solution, native, calls = fixture()
    result = initialize_steady_thermal(sim, solution, native)
    assert result["step"] == {
        "name": "Conduction",
        "descriptor": "Step - Thermal",
        "active": True,
        "solution_type": 0,
    }
    assert len(calls) == 2
    assert all(c[1:3] == ("NX MULTIPHYSICS - Thermal", "NX MULTIPHYSICS") for c in calls)
    assert calls[1][0] == "Multiphysics Thermal Output Requests"
    assert solution.ActiveStep.PropertyTable.values["Solution Type"] == 0


@pytest.mark.parametrize("allowed", [[], ["Other"], ["Step - Thermal", "Step - Thermal"]])
def test_missing_or_ambiguous_step_rejected(allowed):
    sim, solution, native, _ = fixture(allowed=allowed)
    with pytest.raises(NXToolError):
        initialize_steady_thermal(sim, solution, native)


@pytest.mark.parametrize(
    "kwargs", [{"table_reject": True}, {"step_reject": True}, {"activate": False}]
)
def test_bad_native_readback_rejected(kwargs):
    sim, solution, native, _ = fixture(**kwargs)
    with pytest.raises(NXToolError):
        initialize_steady_thermal(sim, solution, native)
