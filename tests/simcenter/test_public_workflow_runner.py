import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "examples/simcenter/public_workflow.py"
spec = importlib.util.spec_from_file_location("public_workflow", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("key", ["r1", "../bad", "a;bad", "a", "ABCDEFGHI", "abcdefghijklmnop"])
def test_rejects_unsafe_or_reserved_run_keys(key):
    with pytest.raises(ValueError):
        runner.render("", key)


def test_stages_have_unique_files_and_operation_names():
    for files in runner.STAGES.values():
        for filename in files:
            source = runner.render((SCRIPT.parent / filename).read_text(), "verify11")
            compile(source, filename, "exec")
            assert "-r1" not in source and "_r1" not in source
    cad = runner.render((SCRIPT.parent / runner.STAGES["author"][0]).read_text(), "verify11")
    assert "/model_verify11.prt" in cad
    assert "/model.prt" not in cad

    reopen = runner.render((SCRIPT.parent / runner.STAGES["reopen"][0]).read_text(), "verify11")
    assert "Public reopened verify11" in reopen
    assert "Public full workflow reopened" not in reopen
