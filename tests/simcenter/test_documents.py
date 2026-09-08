import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.documents import save_sim_as
from nx_mcp.workspace import Workspace


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae

    class SimPart:
        pass

    cae.SimPart = SimPart
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    source = tmp_path / "source.sim"
    source.write_bytes(b"original")
    sim = SimPart()
    sim.FullPath = str(source)
    sim.FemPart = NS(FullPath=str(tmp_path / "shared.fem"))

    class Parts(list):
        BaseWork = sim
        BaseDisplay = sim

    return NS(Parts=Parts([sim])), Workspace(tmp_path), sim, source


def test_existing_target_rejected_before_native_call(fixture):
    session, workspace, sim, source = fixture
    with pytest.raises(NXToolError) as exc:
        save_sim_as(session, workspace, sim, str(source))
    assert exc.value.details["mutation_outcome"] == "not_started"
    assert source.read_bytes() == b"original"


def test_partial_native_save_is_reported_and_retained(fixture):
    session, workspace, sim, _ = fixture

    def failed(path):
        from pathlib import Path

        Path(path).write_bytes(b"partial")
        raise RuntimeError("native save error")

    sim.SaveAs = failed
    with pytest.raises(NXToolError) as exc:
        save_sim_as(session, workspace, sim, "copies/variant.sim")
    assert exc.value.details["mutation_outcome"] == "partial"
    assert exc.value.details["target_exists"] is True
    assert (workspace.root / "copies/variant.sim").read_bytes() == b"partial"


def test_save_preserves_backup_and_does_not_save_components(fixture, monkeypatch):
    from nx_mcp.simcenter.documents import save_document

    session, workspace, sim, source = fixture
    nx, cae = sys.modules["NXOpen"], sys.modules["NXOpen.CAE"]
    cae.FemPart = type("FemPart", (), {})
    nx.BasePart = NS(SaveComponents=NS(FalseValue=False), CloseAfterSave=NS(FalseValue=False))
    sim.Tag, sim.IsModified, sim.IsFullyLoaded = 1, True, True

    def save(components, close):
        assert components is False and close is False
        source.write_bytes(b"saved")
        sim.IsModified = False
        return NS(NumberUnsavedParts=0, NumberUnsavedObjects=0, Dispose=lambda: None)

    sim.Save = save
    result = save_document(session, workspace, sim)
    from pathlib import Path

    assert result["saved"] and Path(result["backup_path"]).read_bytes() == b"original"
    assert Path(result["backup_path"]).parent.parent == workspace.root / "simcenter-save-backups"
    assert not (Path(sim.FullPath).parent / ".nx-mcp-save-backups").exists()
    assert source.read_bytes() == b"saved"


def test_native_save_failure_retains_backup(fixture):
    from nx_mcp.simcenter.documents import save_document

    session, workspace, sim, source = fixture
    nx, cae = sys.modules["NXOpen"], sys.modules["NXOpen.CAE"]
    cae.FemPart = type("FemPart", (), {})
    nx.BasePart = NS(SaveComponents=NS(FalseValue=False), CloseAfterSave=NS(FalseValue=False))
    sim.Tag, sim.IsModified, sim.IsFullyLoaded = 1, True, True
    sim.Save = lambda *_: NS(NumberUnsavedParts=1, NumberUnsavedObjects=0, Dispose=lambda: None)
    with pytest.raises(NXToolError) as exc:
        save_document(session, workspace, sim)
    assert exc.value.code == "NX_SIM_SAVE_FAILED"
    from pathlib import Path

    assert Path(exc.value.details["backup_path"]).read_bytes() == b"original"
    assert exc.value.details["mutation_outcome"] == "partial"
