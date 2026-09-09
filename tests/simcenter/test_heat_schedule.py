import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.heat_schedule import validate_samples


def manifest():
    return {"axis": "time", "quantity": "power", "samples": [[0, 0], [10, 1], [20, 0]]}


def test_scaled_schedule_and_coverage():
    r = validate_samples(manifest(), 2, [0, 10, 20])
    assert r["samples_w"] == [[0, 0], [10, 2], [20, 0]]


@pytest.mark.parametrize("scale", [True, -1, float("nan"), float("inf")])
def test_invalid_scale(scale):
    with pytest.raises(NXToolError):
        validate_samples(manifest(), scale, [0, 20])


@pytest.mark.parametrize("times", [[], [0, 21], [float("nan")], [-1, 20]])
def test_invalid_coverage(times):
    with pytest.raises(NXToolError):
        validate_samples(manifest(), 1, times)


def test_invalid_quantity_negative_power_and_overflow():
    for m, scale in [
        ({**manifest(), "quantity": "density"}, 1),
        ({**manifest(), "samples": [[0, -1], [20, 0]]}, 1),
        ({**manifest(), "samples": [[0, 1e308], [20, 1e308]]}, 1e308),
    ]:
        with pytest.raises(NXToolError):
            validate_samples(m, scale, [0, 20])
