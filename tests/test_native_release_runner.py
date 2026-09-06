"""Native release receipts must distinguish failures and changed user sessions."""

import hashlib
import runpy
from pathlib import Path

import pytest

RUNNER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/validate_native_release.py")
)


def test_session_verification_checks_placements_and_unsaved_state():
    before = {
        "parts": [{"path": "a.prt", "work": True, "display": True, "modified": False}],
        "components": [{"path": "p.prt", "translation": [1, 2, 3]}],
    }
    RUNNER["verify_session"](before, before)
    with pytest.raises(RuntimeError, match="component source"):
        RUNNER["verify_session"](before, {**before, "components": []})
    with pytest.raises(RuntimeError, match="saved state"):
        RUNNER["verify_session"](
            before, {**before, "parts": [{**before["parts"][0], "modified": True}]}
        )


def test_receipt_manifest_hashes_nested_artifacts(tmp_path):
    (tmp_path / "sheets").mkdir()
    (tmp_path / "sheets" / "view.png").write_bytes(b"fixture")
    (tmp_path / "release-validation.json").write_text("not self-hashed")
    assert RUNNER["manifest_files"](tmp_path) == [
        {"path": "sheets/view.png", "size": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}
    ]
