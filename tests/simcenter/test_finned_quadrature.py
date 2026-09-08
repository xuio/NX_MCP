"""Analytical checks for the benchmark's recovered boundary-field integration."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "finned_quadrature",
    Path(__file__).parents[2] / "examples/simcenter/inspect_finned_boundary_fields.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unordered_quad_preserves_area_and_linear_pressure_integral():
    points = {1: (0, 0, 0), 2: (0, 2, 0), 3: (0, 2, 1), 4: (0, 0, 1)}
    for ordering in ([3, 1, 4, 2], [1, 2, 3, 4], [4, 3, 2, 1]):
        triangles = module.triangulate_boundary(ordering, points)
        assert sum(area for _, area in triangles) == pytest.approx(2)
        # Integral of 3*y + 4*z over [0,2] x [0,1] is 10.
        integral = sum(
            area * sum(3 * points[n][1] + 4 * points[n][2] for n in nodes) / 3
            for nodes, area in triangles
        )
        assert integral == pytest.approx(10)


def test_degenerate_or_nonplanar_face_is_rejected():
    with pytest.raises(ValueError, match="Degenerate"):
        module.triangulate_boundary([1, 2, 3], {1: (0, 0, 0), 2: (0, 1, 0), 3: (0, 2, 0)})
    with pytest.raises(ValueError, match="planar"):
        module.triangulate_boundary([1, 2, 3], {1: (0, 0, 0), 2: (0, 1, 0), 3: (1, 0, 1)})
