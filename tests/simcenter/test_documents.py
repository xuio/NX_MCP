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
    assert exc.value.details["native_save_status"]["unsaved_parts"] == 1
    assert (
        exc.value.details["native_save_status"]["parts"][0]["code_read_error"] == "AttributeError"
    )


def test_native_save_codes_are_captured_before_dispose(fixture):
    from nx_mcp.simcenter.documents import save_document

    session, workspace, sim, source = fixture
    nx, cae = sys.modules["NXOpen"], sys.modules["NXOpen.CAE"]
    cae.FemPart = type("FemPart", (), {})
    nx.BasePart = NS(SaveComponents=NS(FalseValue=False), CloseAfterSave=NS(FalseValue=False))
    sim.Tag, sim.IsModified, sim.IsFullyLoaded = 1, True, True
    disposed = []

    def code(_):
        assert not disposed
        return 12345

    status = NS(
        NumberUnsavedParts=1,
        NumberUnsavedObjects=1,
        GetStatus=code,
        GetObjectStatus=code,
        GetPart=lambda _: sim,
        Dispose=lambda: disposed.append(True),
    )
    sim.Save = lambda *_: status
    with pytest.raises(NXToolError) as exc:
        save_document(session, workspace, sim)
    audit = exc.value.details["native_save_status"]
    assert audit["parts"] == [{"index": 0, "nx_code": 12345, "path": str(source)}]
    assert audit["objects"] == [{"index": 0, "nx_code": 12345}]
    assert disposed == [True] and sim.IsModified


def test_native_save_diagnostics_are_bounded_and_keep_total_counts():
    from nx_mcp.simcenter.documents import inspect_save_status

    seen = []

    def code(i):
        seen.append(i)
        return 999

    status = NS(NumberUnsavedParts=0, NumberUnsavedObjects=10000, GetObjectStatus=code)
    result = inspect_save_status(status)
    assert seen == list(range(50))
    assert result["unsaved_objects"] == 10000 and result["omitted_objects"] == 9950


@pytest.fixture
def recovery(fixture):
    from pathlib import Path

    session, workspace, _, _ = fixture
    cae = sys.modules["NXOpen.CAE"]
    cae.FemPart = type("FemPart", (), {})
    fem = cae.FemPart()
    fem.FullPath = str(workspace.root / "missing.fem")
    fem.Tag, fem.IsModified, fem.IsFullyLoaded = 2, True, True
    session.Parts.append(fem)
    session.Parts.BaseWork = fem
    session.Parts[0].Tag, session.Parts[0].IsModified = 1, False
    calls = []

    def save(path):
        calls.append(path)
        Path(path).write_bytes(b"recovered FEM")
        fem.FullPath, fem.IsModified = path, False
        return NS(NumberUnsavedParts=0, NumberUnsavedObjects=0, Dispose=lambda: None)

    fem.SaveAs = save
    return session, workspace, fem, calls


@pytest.mark.parametrize("existing_source", [False, True])
def test_preserve_fem_with_missing_or_existing_source(recovery, existing_source):
    from pathlib import Path

    from nx_mcp.simcenter.documents import preserve_fem_as

    session, workspace, fem, calls = recovery
    source = Path(fem.FullPath)
    if existing_source:
        source.write_bytes(b"original FEM")
    result = preserve_fem_as(session, workspace, fem, "recovery/new.fem")
    assert result["saved"] and result["source_was_missing"] is not existing_source
    assert len(calls) == 1
    assert source.read_bytes() == b"original FEM" if existing_source else not source.exists()


@pytest.mark.parametrize(
    "bad",
    ["inactive", "partial_load", "existing_target", "loaded_name", "extension", "same", "escape"],
)
def test_fem_preservation_preconditions_do_not_call_save(recovery, bad):
    from nx_mcp.simcenter.documents import preserve_fem_as

    session, workspace, fem, calls = recovery
    target = "new.fem"
    if bad == "inactive":
        session.Parts.BaseWork = session.Parts[0]
    elif bad == "partial_load":
        fem.IsFullyLoaded = False
    elif bad == "existing_target":
        (workspace.root / target).write_bytes(b"do not replace")
    elif bad == "loaded_name":
        session.Parts[0].FullPath = str(workspace.root / "elsewhere/NEW.FEM")
    elif bad == "extension":
        target = "new.sim"
    elif bad == "same":
        target = "MISSING.FEM"
    else:
        target = "../outside.fem"
    with pytest.raises((NXToolError, ValueError)):
        preserve_fem_as(session, workspace, fem, target)
    assert not calls


@pytest.mark.parametrize("failure", ["native_error", "unsaved", "other_modified", "source_created"])
def test_fem_partial_output_is_retained(recovery, failure):
    from pathlib import Path

    from nx_mcp.simcenter.documents import preserve_fem_as

    session, workspace, fem, calls = recovery
    original_save, source = fem.SaveAs, Path(fem.FullPath)

    def save(path):
        status = original_save(path)
        if failure == "native_error":
            raise RuntimeError("SaveAs partially committed")
        if failure == "unsaved":
            status.NumberUnsavedParts = 1
        if failure == "other_modified":
            session.Parts[0].IsModified = True
        if failure == "source_created":
            source.write_bytes(b"unexpected")
        return status

    fem.SaveAs = save
    with pytest.raises(NXToolError) as exc:
        preserve_fem_as(session, workspace, fem, "recovery/new.fem")
    assert exc.value.details["mutation_outcome"] == "partial"
    assert (workspace.root / "recovery/new.fem").read_bytes() == b"recovered FEM"
    assert len(calls) == 1
