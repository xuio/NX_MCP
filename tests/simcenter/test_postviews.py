from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.postviews import show_temperature


@pytest.mark.parametrize(
    "kwargs", [{"loadcase_index": -1}, {"iteration_index": True}, {"name": ""}, {"name": "x" * 101}]
)
def test_invalid_arguments_fail_before_nx_access(kwargs):
    with pytest.raises(NXToolError) as exc:
        show_temperature(None, None, {}, **kwargs)
    assert exc.value.code == "NX_INVALID_ARGUMENT"


def test_batch_session_rejected_before_postview_mutation():
    with pytest.raises(NXToolError) as exc:
        show_temperature(NS(IsBatch=True), None, {})
    assert exc.value.code == "NX_SIM_DOCUMENT_NOT_ACTIVE"


def test_unknown_pressure_field_is_rejected_before_nx_access():
    from nx_mcp.simcenter.postviews import show_pressure

    with pytest.raises(NXToolError) as exc:
        show_pressure(None, None, {}, field="invented")
    assert exc.value.code == "NX_INVALID_ARGUMENT"


def test_retention_never_overwrites_reused_postview_or_part_ids():
    from nx_mcp.simcenter.postviews import retain_result

    handles = {}
    first, second, third = object(), object(), object()
    retain_result(handles, NS(Tag=1), 1, first)
    retain_result(handles, NS(Tag=2), 1, second)
    retain_result(handles, NS(Tag=1), 1, third)
    assert len(handles) == 3 and set(handles.values()) == {first, second, third}
