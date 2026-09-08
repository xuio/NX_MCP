"""Fixture-specific rejection tests; native membership/scale coverage is separate."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "finned_effective_inputs",
    Path(__file__).parents[2] / "examples/simcenter/audit_coupled_effective_inputs.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def snapshot():
    data = json.loads(
        (Path(__file__).parent / "evidence/coupled-effective-input-audit.json").read_text()
    )
    # Older native receipt omitted SimulationObjects and table bindings. Supply
    # explicit test doubles here; this augmentation is not native evidence.
    table = next(t for t in data["tables"] if t["descriptor"] == "External Conditions")
    table["reference"] = {
        "journal_id": "External[1]",
        "name": table["name"],
        "owner": data["solution"]["owner"]["owner"],
    }
    table["temperature_option"] = 0
    for ref in data["solution"]["bcs"][1:]:
        data["document_boundaries"].append(
            {**copy.deepcopy(ref), "fields": [], "external_conditions": table["reference"]}
        )
    return data


def test_exact_fixture_does_not_claim_general_freshness(snapshot):
    result = module.validate_finned_snapshot(snapshot)
    assert result["general_freshness"] == "not_verified"
    assert result["physical_acceptance"] is False


@pytest.mark.parametrize("change", ["remove", "step", "owner", "folder", "override"])
def test_membership_changes_rejected_even_with_unchanged_inventory(snapshot, change):
    if change == "remove":
        snapshot["solution"]["bcs"].pop()
    elif change == "step":
        snapshot["steps"][0]["bcs"] = [snapshot["solution"]["bcs"][0]]
    elif change == "owner":
        snapshot["solution"]["bcs"][0]["owner"] = "other.sim"
    elif change == "folder":
        snapshot["solution"]["folders"] = [{}]
    else:
        snapshot["solution"]["conflict_override_count"] = 1
    with pytest.raises(ValueError):
        module.validate_finned_snapshot(snapshot)


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_field_backed_heat_cannot_satisfy_fixture_guard(snapshot, scale):
    heat = snapshot["document_boundaries"][0]["fields"][0]
    heat.update(
        representation="field", expression=None, field={"journal_id": "field[1]"}, scale=scale
    )
    with pytest.raises(ValueError, match="Field definition/scale"):
        module.validate_finned_snapshot(snapshot)


def test_head_loss_requires_selector_audit(snapshot):
    snapshot["tables"].append({"descriptor": "Head Loss"})
    with pytest.raises(ValueError, match="Head-loss selectors"):
        module.validate_finned_snapshot(snapshot)


def test_unbound_opening_temperature_rejected(snapshot):
    snapshot["document_boundaries"][-1]["external_conditions"] = None
    with pytest.raises(ValueError, match="binding"):
        module.validate_finned_snapshot(snapshot)


def test_nonfinite_heat_is_rejected(snapshot):
    snapshot["document_boundaries"][0]["fields"][0]["expression"]["value"] = float("nan")
    with pytest.raises(ValueError, match="value or units"):
        module.validate_finned_snapshot(snapshot)
