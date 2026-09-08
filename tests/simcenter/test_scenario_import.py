import json

import pytest

from nx_mcp.simcenter.scenario_import import assignment_plan, parse_scenario

META = {"name": "full-load", "workload_revision": "assumed-r1", "ambient_K": 298.15}
CSV = b"""name,region,watts,category,accounting_id,provenance_kind,provenance_source
CPU,SOC,8,internal_heat,processor,assumed,benchmark
USB,,10,exported_electrical,usb,assumed,benchmark
CHARGE,,5,battery_storage,charge,assumed,benchmark
"""


def test_csv_json_equivalence_and_separate_energy_categories():
    parsed = parse_scenario(CSV, "csv", META)
    restored = parse_scenario(json.dumps(parsed).encode(), "json")
    assert parsed == restored
    plan = assignment_plan(restored, {"SOC": "body-1"})
    assert plan["totals_W"] == {"internal_heat": 8, "exported_electrical": 10, "battery_storage": 5}
    assert len(plan["assignments"]) == 1
    assert plan["excluded_sources"] == ["USB", "CHARGE"]
    assert not plan["applied_to_nx"] and not plan["ambient_applied"]


@pytest.mark.parametrize("mapping", [{}, {"SSD": "body-1"}, {"SOC": "body-1", "SSD": "body-2"}])
def test_exact_region_mapping(mapping):
    with pytest.raises(ValueError, match="assignment mismatch"):
        assignment_plan(parse_scenario(CSV, "csv", META), mapping)


def test_duplicate_native_target_is_rejected_before_any_load():
    raw = CSV + b"SSD,SSD,2,internal_heat,ssd,assumed,benchmark\n"
    with pytest.raises(ValueError, match="Duplicate heat target"):
        assignment_plan(parse_scenario(raw, "csv", META), {"SOC": "body-1", "SSD": "body-1"})


@pytest.mark.parametrize(
    "raw",
    [
        CSV.replace(b"watts,", b"W,"),
        CSV.replace(b"CPU,SOC,8", b"CPU,SOC,nan"),
        CSV.replace(b"CPU,SOC,8", b"CPU, SOC,8"),
        CSV + b"EXTRA,SOC,1,internal_heat,extra,assumed,benchmark,ignored\n",
        CSV + b"EXTRA,SOC,1,internal_heat,extra,assumed\n",
    ],
)
def test_invalid_csv_has_no_silent_ignored_data(raw):
    with pytest.raises(ValueError):
        parse_scenario(raw, "csv", META)


def test_duplicate_json_property_and_boolean_power():
    with pytest.raises(ValueError, match="Duplicate JSON"):
        parse_scenario(b'{"name":"a","name":"b"}', "json")
    data = parse_scenario(CSV, "csv", META)
    data["sources"][0]["watts"] = True
    with pytest.raises(ValueError, match="boolean"):
        parse_scenario(json.dumps(data).encode(), "json")


def test_overflowing_total_is_not_valid_power_accounting():
    data = parse_scenario(CSV, "csv", META)
    data["sources"][0]["watts"] = 1e308
    data["sources"].append(
        {**data["sources"][0], "name": "SSD", "region": "SSD", "accounting_id": "ssd"}
    )
    with pytest.raises(ValueError, match="finite numeric range"):
        assignment_plan(
            parse_scenario(json.dumps(data).encode(), "json"), {"SOC": "body-1", "SSD": "body-2"}
        )


def test_bounded_file_and_no_metadata_override():
    with pytest.raises(ValueError, match="1 MiB"):
        parse_scenario(b" " * (1024 * 1024 + 1), "json")
    with pytest.raises(ValueError, match="overrides"):
        parse_scenario(b"{}", "json", META)


def test_preview_identity_binds_file_metadata_owner_and_selection():
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.scenario_import import preview_identity, verify_preview

    args = ["sim-1", "file-1", "scenario-1", {"SOC": "body-1"}]
    original = preview_identity(*args)
    verify_preview(original, original)
    for index, value in enumerate(["sim-2", "file-2", "scenario-2", {"SOC": "body-2"}]):
        changed = list(args)
        changed[index] = value
        with pytest.raises(NXToolError) as error:
            verify_preview(original, preview_identity(*changed))
        assert error.value.code == "NX_SIM_SCENARIO_CHANGED"
        assert error.value.details["mutation_outcome"] == "not_started"
    with pytest.raises(NXToolError, match="lowercase SHA256"):
        verify_preview("invalid", original)
