import pytest
from pydantic import ValidationError

from nx_mcp.simcenter.inputs import FanCurve, HeatScenario


def scenario():
    return {
        "name": "screen",
        "workload_revision": "w1",
        "ambient_K": 298.15,
        "sources": [
            {
                "name": "CPU",
                "accounting_id": "compute",
                "region": "SOC",
                "watts": 8,
                "category": "internal_heat",
                "provenance": {"kind": "assumed", "source": "benchmark"},
            }
        ],
    }


def test_ledger_does_not_apply_export_or_storage_as_heat():
    data = scenario()
    for category in ["exported_electrical", "battery_storage"]:
        data["sources"].append(
            {
                "name": category,
                "accounting_id": category,
                "watts": 10,
                "category": category,
                "provenance": {"kind": "assumed", "source": "test"},
            }
        )
    audit = HeatScenario.model_validate(data).audit({"SOC"})
    assert audit["valid"] and audit["totals_W"]["internal_heat"] == 8
    assert not audit["applied_to_nx"]
    data["sources"][-1]["region"] = "BATTERY"
    with pytest.raises(ValidationError, match="not heat loads"):
        HeatScenario.model_validate(data)


def test_duplicate_and_missing_source_mapping_are_rejected():
    data = scenario()
    assert not HeatScenario.model_validate(data).audit({"SSD"})["valid"]
    data["sources"].append(dict(data["sources"][0]))
    with pytest.raises(ValidationError, match="Duplicate"):
        HeatScenario.model_validate(data)


@pytest.mark.parametrize("power", [float("nan"), float("inf"), -1])
def test_invalid_power(power):
    data = scenario()
    data["sources"][0]["watts"] = power
    with pytest.raises(ValidationError):
        HeatScenario.model_validate(data)


def curve():
    return FanCurve.model_validate(
        {
            "name": "synthetic benchmark",
            "pressure_convention": "static",
            "rpm": 1000,
            "reference_density_kg_m3": 1.2,
            "points": [{"flow_m3_s": 0, "pressure_Pa": 100}, {"flow_m3_s": 0.01, "pressure_Pa": 0}],
            "stall_region": "not modeled; synthetic curve",
            "provenance": {"kind": "assumed", "source": "unit test"},
            "scaling_rpm_range": [500, 1500],
            "scaling_validity": "synthetic benchmark only",
        }
    )


def test_fan_interpolation_and_bounded_scaling():
    fan = curve()
    assert fan.pressure(0.005) == 50
    scaled = fan.scaled(500, 1.2)
    assert scaled.pressure(0.0025) == 12.5
    with pytest.raises(ValueError):
        fan.pressure(0.011)
    with pytest.raises(ValueError):
        fan.pressure(-0.001)
    with pytest.raises(ValueError):
        fan.scaled(2000, 1.2)


def test_curve_preserves_pressure_convention_and_requires_order():
    data = curve().model_dump()
    data["pressure_convention"] = "total"
    assert FanCurve.model_validate(data).scaled(500, 1.2).pressure_convention == "total"
    data["points"].reverse()
    with pytest.raises(ValidationError, match="strictly increasing"):
        FanCurve.model_validate(data)
