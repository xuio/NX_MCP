import copy

import pytest

from nx_mcp.simcenter.boundary_geometry import inspect_rectangular_patch


def node(label, y, z):
    return {"label": label, "xyz": [1.0, y, z]}


def inspect(faces):
    return inspect_rectangular_patch(
        faces, plane_x_mm=1, minimum_yz_mm=[1, 1], maximum_yz_mm=[21, 21]
    )


@pytest.fixture
def triangles():
    a, b, c, d = node(1, 1, 1), node(2, 21, 1), node(3, 21, 21), node(4, 1, 21)
    return [[a, b, c], [a, c, d]]


def test_complete_rectangle_accepts_reversed_input_winding(triangles):
    report = inspect([triangles[0][::-1], triangles[1]])
    assert report["area_mm2"] == 400 and report["perimeter_mm"] == 80
    assert report["connected_components"] == 1


def test_missing_face_rejects_interior_free_edge(triangles):
    with pytest.raises(ValueError, match="Interior free edge"):
        inspect(triangles[:1])


def test_duplicate_face_rejected(triangles):
    with pytest.raises(ValueError, match="Duplicate face"):
        inspect(triangles + triangles[:1])


def test_wrong_plane_and_stale_label_coordinates_rejected(triangles):
    wrong = [copy.deepcopy(face) for face in triangles]
    wrong[0][0]["xyz"][0] = 2
    with pytest.raises(ValueError, match="outside"):
        inspect(wrong)
    wrong = [copy.deepcopy(face) for face in triangles]
    wrong[1][0]["xyz"][1] += 0.01
    with pytest.raises(ValueError, match="Inconsistent"):
        inspect(wrong)


def test_overlapping_triangles_rejected(triangles):
    extra = [triangles[0][0], triangles[0][1], node(5, 15, 10)]
    with pytest.raises(ValueError, match="orientations overlap"):
        inspect(triangles + [extra])


def test_quad_and_nonfinite_rejection():
    quad = [[node(1, 1, 1), node(2, 21, 1), node(3, 21, 21), node(4, 1, 21)]]
    assert inspect(quad)["area_mm2"] == 400
    quad[0][0]["xyz"][1] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        inspect(quad)
