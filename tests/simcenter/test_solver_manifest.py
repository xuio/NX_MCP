import pytest

from nx_mcp.simcenter.solver_manifest import compare_inputs, preserve_input


def deck(power=1, date="first"):
    return f'<!--export {date}--><SolutionFile><Property name="power"><Value>{power}</Value></Property></SolutionFile>'.encode()


def test_export_comment_changes_do_not_hide_physical_changes():
    same = compare_inputs(deck(), deck(date="second"))
    assert not same["byte_identical"]
    assert same["xml_content_identical"]
    assert not compare_inputs(deck(), deck(power=2))["xml_content_identical"]


def test_snapshot_replay_cannot_overwrite_different_input(tmp_path):
    first = preserve_input(tmp_path, "preflight", deck())
    assert preserve_input(tmp_path, "preflight", deck()) == first
    with pytest.raises(ValueError, match="differs"):
        preserve_input(tmp_path, "preflight", deck(power=2))
    assert (tmp_path / "preflight.xml").read_bytes() == deck()


def test_invalid_xml_and_phase_leave_no_snapshot(tmp_path):
    with pytest.raises(ValueError):
        preserve_input(tmp_path, "../escape", deck())
    with pytest.raises(ValueError):
        preserve_input(tmp_path, "preflight", b"<SolutionFile>")
    assert not list(tmp_path.iterdir())


def test_whitespace_inside_property_values_is_not_discarded():
    a = b'<SolutionFile><Value>part</Value></SolutionFile>'
    b = b'<SolutionFile><Value> part </Value></SolutionFile>'
    assert not compare_inputs(a, b)["xml_content_identical"]
