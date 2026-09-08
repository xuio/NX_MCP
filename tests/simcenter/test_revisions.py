import hashlib

import pytest

from nx_mcp.simcenter.revisions import audit_saved_revision
from nx_mcp.workspace import Workspace


@pytest.fixture
def revision(tmp_path):
    path = tmp_path / "model.fem"
    path.write_bytes(b"mesh revision one")
    expected = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
    documents = [{"path": str(path), "modified": False, "fully_loaded": True}]
    return Workspace(tmp_path), expected, documents, path


def test_matching_saved_file_does_not_hide_unsaved_native_edits(revision):
    workspace, expected, docs, _ = revision
    docs[0]["modified"] = True
    audit = audit_saved_revision(workspace, expected, docs)
    assert audit["files"][0]["matches"] is True
    assert audit["revision_matches"] is False
    assert audit["issues"][0]["reason"] == "unsaved_edits"


def test_changed_mesh_rejected_even_with_same_size(revision):
    workspace, expected, docs, path = revision
    path.write_bytes(b"mesh revision two")
    audit = audit_saved_revision(workspace, expected, docs)
    assert audit["issues"][0]["reason"] == "saved_file_changed"


def test_new_dependency_invalidates_binding(revision):
    workspace, expected, docs, path = revision
    docs.append({"path": str(path.with_suffix(".prt")), "modified": False, "fully_loaded": True})
    assert audit_saved_revision(workspace, expected, docs)["state"] == "dependency_set_changed"


def test_unknown_flags_and_duplicate_snapshot_rejected(revision):
    workspace, expected, docs, _ = revision
    with pytest.raises(ValueError, match="Duplicate"):
        audit_saved_revision(workspace, expected * 2, docs)
    docs[0]["modified"] = None
    with pytest.raises(ValueError, match="explicit booleans"):
        audit_saved_revision(workspace, expected, docs)


def test_matching_revision_does_not_assert_engineering_acceptance(revision):
    workspace, expected, docs, _ = revision
    result = audit_saved_revision(workspace, expected, docs)
    assert result["revision_matches"] is True
    assert result["engineering_accepted"] is False
