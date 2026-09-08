from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.native import SimcenterMixin


def executor(analysis):
    sim = NS(Simulation=NS(ActiveSolution=NS(SolverType="NX MULTIPHYSICS", AnalysisType=analysis)))
    return NS(session=NS(Parts=NS(BaseWork=sim)), objects=NS(resolve=lambda *args, **kwargs: sim))


@pytest.mark.parametrize("analysis", ["Flow", "Coupled Thermal-Flow"])
def test_solved_flow_interfaces_are_rejected_before_face_resolution(analysis):
    with pytest.raises(NXToolError) as exc:
        SimcenterMixin._sim_convection(executor(analysis), "sim", ["face"], 10, "name", "assumed")
    assert exc.value.code == "NX_SIM_UNSUPPORTED"
    assert exc.value.details["mutation_outcome"] == "not_started"


def test_repeated_face_ids_rejected_before_native_builder():
    with pytest.raises(NXToolError) as exc:
        SimcenterMixin._sim_convection(
            executor("Thermal"), "sim", ["face", "face"], 10, "name", "assumed"
        )
    assert exc.value.code == "NX_INVALID_ARGUMENT"
