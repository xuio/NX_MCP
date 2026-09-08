import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.benchmark_geometry import validate_block_origins


def test_default_and_touching_blocks():
    assert validate_block_origins(None, (10, 10, 10)) == [(0, 0, 0)]
    assert len(validate_block_origins([[0, 0, 0], [10, 0, 0], [0, 20, 0]], (10, 10, 10))) == 3


@pytest.mark.parametrize(
    "origins",
    [
        [],
        [[0, 0]],
        [[True, 0, 0]],
        [[float("nan"), 0, 0]],
        [[10001, 0, 0]],
        [[0, 0, 0], [9.99, 0, 0]],
        [[0, 0, 0], [0, 0, 0]],
        [[0, 0, 0]] * 17,
    ],
)
def test_invalid_geometry_is_rejected_without_nx(origins):
    with pytest.raises(NXToolError) as error:
        validate_block_origins(origins, (10, 10, 10))
    assert error.value.details["mutation_outcome"] == "not_started"
