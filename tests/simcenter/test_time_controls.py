import pytest

from nx_mcp.simcenter.time_controls import validate_times


@pytest.mark.parametrize(
    "times,change,minimum",
    [
        ([0, 0, 1], 0.05, 0.01),
        ([0, 2, 1], 0.05, 0.01),
        ([1, 2], 0.05, 0.01),
        ([0, float("nan")], 0.05, 0.01),
        ([0, True], 0.05, 0.01),
        ([0, 1], float("inf"), 0.01),
        ([0, 1], 0.05, 2),
        ([0, 1], 0, 0.01),
        (list(range(201)), 0.05, 0.01),
    ],
)
def test_reject_invalid_time_control_requests_before_nx(times, change, minimum):
    with pytest.raises(ValueError):
        validate_times(times, change, minimum)


def test_accept_native_refinement_schedule():
    validate_times([i * 50.625 for i in range(41)], 0.05, 0.01)
