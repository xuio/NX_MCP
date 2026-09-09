from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_remesh import fixture  # noqa: F401

from nx_mcp.runtime import NXToolError


@pytest.fixture
def sync_fixture(fixture, monkeypatch):  # noqa: F811
    import NXOpen.CAE as cae

    from nx_mcp.simcenter import geometry_sync

    _, executor, fem, state, builders = fixture
    cae.FemPart.UseBodiesOption = NS(AllBodies=2)
    fem.Bodies = [NS(Tag=11)]
    cad = NS(Bodies=[NS(Tag=101), NS(Tag=102)])
    fem.MasterCadPart = cad
    opts = NS(Dispose=Mock())
    fem.GetGeometryDataWithAttributes = lambda: (2, [], opts, object())
    fem.SetGeometryDataWithAttributes = Mock()
    fem.BaseFEModel.UpdateFemodel = lambda: fem.Bodies.append(NS(Tag=12))
    monkeypatch.setattr(
        "nx_mcp.simcenter.remesh.settings", lambda *a: {"size_mm": 2, "body_tags": [11]}
    )
    monkeypatch.setattr("nx_mcp.simcenter.postviews.present_result", lambda *a: {})
    executor.session.UndoToMark = lambda *a: setattr(fem, "Bodies", [NS(Tag=11)])
    return geometry_sync, executor, fem, opts


def test_added_body_reported_unmeshed_and_references_retired(sync_fixture):
    module, executor, fem, opts = sync_fixture
    result = module.synchronize(executor, fem)
    assert result["before_body_count"] == 1 and result["body_count"] == 2
    assert result["unmeshed_body_tags"] == [12]
    assert not result["mesh_coverage_complete"] and result["results_stale"]
    opts.Dispose.assert_called_once()
    assert executor.objects.invalidate_part.call_count == 2


def test_mismatch_rolls_back_and_retires_references(sync_fixture):
    module, executor, fem, opts = sync_fixture
    fem.BaseFEModel.UpdateFemodel = lambda: None
    with pytest.raises(NXToolError) as error:
        module.synchronize(executor, fem)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    opts.Dispose.assert_called_once()
    assert executor.objects.invalidate_part.call_count == 2


def test_selected_body_policy_rejected_before_mutation(sync_fixture):
    module, executor, fem, opts = sync_fixture
    fem.GetGeometryDataWithAttributes = lambda: (1, [], opts, object())
    with pytest.raises(NXToolError, match="all-body"):
        module.synchronize(executor, fem)
    fem.SetGeometryDataWithAttributes.assert_not_called()
    executor.objects.invalidate_part.assert_not_called()
    opts.Dispose.assert_called_once()
