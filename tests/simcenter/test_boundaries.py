from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.boundaries import verify_face_targets


def boundary(tags):
    return NS(
        TargetSetManager=NS(GetTargetSetMembers=lambda _: (None, [NS(Obj=NS(Tag=t)) for t in tags]))
    )


def test_face_selection_order_can_change_without_changing_members():
    assert verify_face_targets(boundary([2, 1]), [NS(Tag=1), NS(Tag=2)]) == {
        "committed_face_count": 2,
        "committed_face_tags": [1, 2],
    }


@pytest.mark.parametrize("actual", [[1], [1, 3], [1, 2, 3]])
def test_missing_rebound_or_extra_faces_are_rejected(actual):
    with pytest.raises(NXToolError):
        verify_face_targets(boundary(actual), [NS(Tag=1), NS(Tag=2)])
