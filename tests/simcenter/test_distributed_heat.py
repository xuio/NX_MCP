import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.distributed_heat import validate_density


@pytest.mark.parametrize("value", [True, False, -1, float("nan"), float("inf"), "100"])
def test_reject_invalid_density(value):
    with pytest.raises(NXToolError):
        validate_density("surface_flux", value)


def test_explicit_si_units():
    assert validate_density("surface_flux", 10000) == ("Heat Flux", "HeatFlux_Metric5", "W/m^2")
    assert validate_density("volume_generation", 100000) == (
        "Heat Generation",
        "HeatGeneration_Metric3",
        "W/m^3",
    )


def test_reject_unknown_distribution():
    with pytest.raises(NXToolError):
        validate_density("total_power", 1)


def test_preflight_preserves_domain_error_and_classifies_no_mutation():
    from nx_mcp.simcenter.distributed_heat import preflight

    original = NXToolError("NX_SIM_DUPLICATE_HEAT_SOURCE", "duplicate", nx_code=42)
    with pytest.raises(NXToolError) as caught, preflight():
        raise original
    assert caught.value is original
    assert caught.value.nx_code == 42
    assert caught.value.details["mutation_outcome"] == "not_started"
    assert caught.value.details["next_step"]


def test_preflight_native_inspection_failure_is_not_authoring_failure():
    from nx_mcp.simcenter.distributed_heat import preflight

    class NativeError(Exception):
        ErrorCode = 999

    with pytest.raises(NXToolError) as caught, preflight():
        raise NativeError("native inspection failed")
    assert caught.value.code == "NX_SIM_PREFLIGHT_FAILED"
    assert caught.value.nx_code == 999
    assert caught.value.details["mutation_outcome"] == "not_started"


def test_preflight_does_not_overwrite_explicit_partial_outcome():
    from nx_mcp.simcenter.distributed_heat import preflight

    with pytest.raises(NXToolError) as caught, preflight():
        raise NXToolError(
            "NX_SIM_RECOVERY_INCOMPLETE", "partial", details={"mutation_outcome": "partial"}
        )
    assert caught.value.details["mutation_outcome"] == "partial"


def test_native_geometry_integration_converts_mm_to_si(monkeypatch):
    import sys
    from types import ModuleType
    from types import SimpleNamespace as NS

    from nx_mcp.simcenter.distributed_heat import measure_applied_power

    nx, uf = ModuleType("NXOpen"), ModuleType("NXOpen.UF")
    sf = NS(
        FaceAskArea=lambda tag: 100.0, BodyAskVolumeAndCentroid=lambda tag: (10000.0, [50, 5, 5])
    )
    uf.UFSession = NS(GetUFSession=lambda: NS(Sf=sf))
    nx.UF = uf
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    fem = NS(PartUnits=1)
    sim = NS(PartUnits=1, FemPart=fem)
    target = NS(Prototype=NS(Tag=1, OwningPart=fem))
    flux = measure_applied_power(sim, [target], "surface_flux", 10000)
    volume = measure_applied_power(sim, [target], "volume_generation", 100000)
    assert flux["total_power_w"] == pytest.approx(1)
    assert volume["total_power_w"] == pytest.approx(1)
    assert flux["measure_units"] == "m^2" and volume["measure_units"] == "m^3"
    fem.PartUnits = 2
    with pytest.raises(NXToolError):
        measure_applied_power(sim, [target], "volume_generation", 100000)
