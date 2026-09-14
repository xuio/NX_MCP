import pytest
from nx_mcp.divide_face import rectangle_points, check_preservation
from nx_mcp.runtime import NXToolError


def test_rectangular_loop_at_native_plane():
    assert rectangle_points([2, 3, 7, 8], [0, 0, -4, 10, 10, -4]) == [
        [2, 3, -4], [7, 3, -4], [7, 8, -4], [2, 8, -4]]


@pytest.mark.parametrize('rectangle', [[0, 2, 5, 5], [2, 2, 10, 5],
                                      [5, 2, 2, 5], [2, 2, 2, 5],
                                      [2, 2, float('nan'), 5], [2, 2, 5]])
def test_bad_rectangles_rejected(rectangle):
    with pytest.raises(NXToolError):
        rectangle_points(rectangle, [0, 0, 1, 10, 10, 1])


def test_nonhorizontal_bounds_rejected():
    with pytest.raises(NXToolError):
        rectangle_points([2, 2, 5, 5], [0, 0, 1, 10, 10, 2])


def test_surface_partition_preserves_solid():
    mass = {'volume_m3': 1e-5, 'area_m2': .01}
    check_preservation(mass, mass.copy(), 6, 7)


@pytest.mark.parametrize('fault', ['volume_m3', 'area_m2', 'faces', 'nan'])
def test_material_change_or_wrong_partition_rejected(fault):
    before = {'volume_m3': 1e-5, 'area_m2': .01}
    after = before.copy()
    if fault in before: after[fault] *= 1.001
    if fault == 'nan': after['area_m2'] = float('nan')
    with pytest.raises(NXToolError):
        check_preservation(before, after, 6, 8 if fault == 'faces' else 7)
