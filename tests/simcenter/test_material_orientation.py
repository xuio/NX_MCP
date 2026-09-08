import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.material_orientation import validate_frame


def test_explicit_basis_is_right_handed_and_converted_to_native_floats():
    origin, x, y, z = validate_frame([0, 0, 0], [0, 1, 0], [-1, 0, 0])
    assert x == [0, 1, 0] and y == [-1, 0, 0] and z == [0, 0, 1]
    assert all(type(v) is float for v in origin + x + y + z)


@pytest.mark.parametrize(
    "x,y",
    [
        ([2, 0, 0], [0, 1, 0]),
        ([1, 0, 0], [1, 0, 0]),
        ([True, 0, 0], [0, 1, 0]),
        ([float("nan"), 0, 0], [0, 1, 0]),
        ([1, 0], [0, 1, 0]),
    ],
)
def test_invalid_material_frames_are_rejected(x, y):
    with pytest.raises(NXToolError):
        validate_frame([0, 0, 0], x, y)
