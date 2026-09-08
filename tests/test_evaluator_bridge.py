import pytest

from nx_mcp.evaluator_bridge import decode_result
from nx_mcp.runtime import NXToolError


def test_numeric_protocol_preserves_natural_limits_and_points():
    values = [1, 1, 2, 0, 0.002, 0] + [0] * 9 + [0, 0, 0, 0, 0, 2]
    result = decode_result(values, 2)
    assert result["limits"] == [0, 0.002]
    assert result["points"] == [[0, 0, 0], [0, 0, 2]]


@pytest.mark.parametrize("values", [[1], [1, 1, 2] + [float("nan")] * 18])
def test_malformed_helper_output_never_becomes_geometry(values):
    with pytest.raises(NXToolError) as error:
        decode_result(values, 2)
    assert error.value.code == "NX_EVALUATOR_PROTOCOL"


def test_primary_and_cleanup_errors_are_preserved_separately():
    with pytest.raises(NXToolError) as error:
        decode_result([-1, 123, 456, 1], 2)
    assert error.value.nx_code == 123
    assert error.value.details["cleanup_nx_code"] == 456
    assert error.value.code == "NX_EVALUATOR_CLEANUP_FAILED"
