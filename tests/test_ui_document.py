from types import SimpleNamespace as NS
from unittest.mock import Mock

from nx_mcp.ui_document import update_document_caption


def test_caption_uses_base_display_for_sim_documents_without_cad_work_access():
    class Parts:
        BaseDisplay = NS(FullPath=r"D:\analysis\current.sim", IsModified=True)

        BaseWork = BaseDisplay

        @property
        def Work(self):
            raise AssertionError("CAD-only Work getter must not be used for SIM")

    panel = NS(user=NS(SetWindowTextW=Mock()), hwnd=1)
    host = NS(session=NS(Parts=Parts()), panel=panel)
    update_document_caption(host)
    panel.user.SetWindowTextW.assert_called_once_with(1, "NX MCP — current.sim *")
    assert host._visible_document["path"] == r"D:\analysis\current.sim"


def test_caption_identifies_different_work_document_without_activating_it():
    display = NS(FullPath=r"D:\analysis\visible.sim", IsModified=False)
    work = NS(FullPath=r"D:\analysis\editing.fem", IsModified=True)
    panel = NS(user=NS(SetWindowTextW=Mock()), hwnd=1)
    host = NS(session=NS(Parts=NS(BaseDisplay=display, BaseWork=work)), panel=panel)
    update_document_caption(host)
    panel.user.SetWindowTextW.assert_called_once_with(
        1, "NX MCP — visible.sim | Work: editing.fem *"
    )
    assert host._work_document["path"] == work.FullPath
    assert host.session.Parts.BaseDisplay is display


def test_fit_mutation_but_preserve_camera_inspection_and_drawing():
    from nx_mcp.ui_document import refresh_model_view

    view = NS(Fit=Mock(), UpdateDisplay=Mock())
    part = NS(ModelingViews=NS(WorkView=view))
    session = NS(Parts=NS(BaseDisplay=part))
    refresh_model_view(session, "nx_create_part", {})
    view.Fit.assert_called_once()
    view.UpdateDisplay.assert_called_once()
    view.Fit.reset_mock()
    for method in ("nx_set_camera", "nx_fit_view", "nx_list_bodies"):
        refresh_model_view(session, method, {})
    view.Fit.assert_not_called()
    part.DrawingSheets = NS(CurrentDrawingSheet=object())
    refresh_model_view(session, "nx_create_part", {})
    view.Fit.assert_not_called()


def test_fit_failure_keeps_committed_result_and_still_redraws():
    from nx_mcp.ui_document import refresh_model_view

    view = NS(Fit=Mock(side_effect=RuntimeError("empty view")), UpdateDisplay=Mock())
    session = NS(Parts=NS(BaseDisplay=NS(ModelingViews=NS(WorkView=view))))
    result = {"status": "success", "object": "committed"}
    refresh_model_view(session, "nx_create_part", result)
    assert result["status"] == "success" and result["object"] == "committed"
    assert result["warnings"] == ["View fit: empty view"]
    view.UpdateDisplay.assert_called_once()
