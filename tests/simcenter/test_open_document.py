import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.documents import open_document
from nx_mcp.workspace import Workspace


def environment(monkeypatch, tmp_path):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.SimPart = type("SimPart", (), {})
    cae.FemPart = type("FemPart", (), {})
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    part = cae.SimPart()
    part.FullPath, part.IsModified, part.IsFullyLoaded = str(tmp_path / "case.sim"), True, True

    class Parts(list):
        def SetWork(self, value):
            self.BaseWork = value

        def SetDisplay(self, value, *_):
            self.BaseDisplay = value
            return None, None

        def OpenBaseDisplay(self, *_):
            raise AssertionError("Loaded document must not be opened again")

    parts = Parts([part])
    parts.BaseWork = parts.BaseDisplay = part
    return part, NS(Parts=parts, ApplicationName="UG_APP_SFEM"), Workspace(tmp_path)


def test_loaded_unsaved_document_is_reused_even_if_disk_file_missing(monkeypatch, tmp_path):
    part, session, workspace = environment(monkeypatch, tmp_path)
    result = open_document(session, workspace, "case.sim")
    assert result["part"] is part and result["already_loaded"]
    assert result["modified"] and not result["saved"]
    assert result["changed_existing_part_flags"] == []


@pytest.mark.parametrize(
    "path,code", [("missing.sim", "NX_NOT_FOUND"), ("case.prt", "NX_SIM_DOCUMENT_TYPE")]
)
def test_invalid_open_preflight(monkeypatch, tmp_path, path, code):
    _, session, workspace = environment(monkeypatch, tmp_path)
    with pytest.raises(NXToolError) as error:
        open_document(session, workspace, path)
    assert error.value.code == code and error.value.details["mutation_outcome"] == "not_started"


def test_cross_extension_basename_conflict_is_preflighted(monkeypatch, tmp_path):
    _, session, workspace = environment(monkeypatch, tmp_path)
    (tmp_path / "case.fem").write_bytes(b"fixture")
    with pytest.raises(NXToolError) as error:
        open_document(session, workspace, "case.fem")
    assert error.value.code == "NX_SIM_NAME_CONFLICT"
    assert error.value.details["mutation_outcome"] == "not_started"


@pytest.mark.parametrize("fail", [False, True])
def test_fresh_open_uses_saved_dependencies_and_restores_preference(monkeypatch, tmp_path, fail):
    part, session, workspace = environment(monkeypatch, tmp_path)
    session.Parts.clear()
    part.IsModified = False
    (tmp_path / "case.sim").write_bytes(b"fixture")

    class Options:
        LoadMethod = NS(AsSaved="saved")
        ComponentLoadMethod = "directory"

    session.Parts.LoadOptions = Options()

    def opening(path):
        assert session.Parts.LoadOptions.ComponentLoadMethod == "saved"
        if fail:
            raise RuntimeError("native load failure")
        session.Parts.append(part)
        return part, None

    session.Parts.OpenBaseDisplay = opening
    if fail:
        with pytest.raises(NXToolError):
            open_document(session, workspace, "case.sim")
    else:
        assert open_document(session, workspace, "case.sim")["part"] is part
    assert session.Parts.LoadOptions.ComponentLoadMethod == "directory"
