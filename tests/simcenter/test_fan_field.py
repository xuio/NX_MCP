import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fan_field import verify_samples


@pytest.mark.parametrize("actual", [[0, 200000, 400000], [0, 0.0002], [0, float("nan"), 0.0004]])
def test_native_unit_or_cardinality_corruption_is_rejected(actual):
    with pytest.raises(NXToolError, match="samples differ"):
        verify_samples([0, 0.0002, 0.0004], actual)


def test_si_roundtrip_allows_only_floating_point_roundoff():
    verify_samples([0, 0.0002, 0.0004], [0, 0.00020000000000000001, 0.0004])


def test_native_validation_preserves_typed_manifest():
    from nx_mcp.simcenter.fan_field import validate_manifest
    from nx_mcp.simcenter.inputs import FanCurve

    manifest = {
        "name": "synthetic",
        "pressure_convention": "total",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [{"flow_m3_s": 0, "pressure_Pa": 1}, {"flow_m3_s": 0.0004, "pressure_Pa": 0}],
        "stall_region": "unverified",
        "provenance": {"kind": "assumed", "source": "test"},
    }
    typed = FanCurve.model_validate(manifest).model_dump()
    assert validate_manifest(typed) == typed
    for changes in (
        {"rpm": float("inf")},
        {"extrapolation": "allow"},
        {"points": list(reversed(manifest["points"]))},
        {"ignored_option": 1},
    ):
        with pytest.raises(NXToolError):
            validate_manifest({**manifest, **changes})


def test_retained_manifest_checks_integrity_and_bounded_reads():
    import json

    from nx_mcp.simcenter.fan_field import encode_manifest, read_manifest

    curve = {
        "name": "Synthetic → curve",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [{"flow_m3_s": 0, "pressure_Pa": 1}, {"flow_m3_s": 0.0004, "pressure_Pa": 0}],
        "stall_region": "unverified",
        "provenance": {"kind": "assumed", "source": "Fixture only"},
    }
    header, chunks = encode_manifest(curve)

    class Table:
        def GetStringUserAttribute(self, key, index):
            return header if index == -1 else chunks[index]

    table = Table()
    assert read_manifest(table)["name"] == curve["name"]
    chunks[-1] = chunks[-1][:-1]
    with pytest.raises(NXToolError, match="missing or corrupt"):
        read_manifest(table)
    header = json.dumps({"version": 1, "chunks": 10**9, "sha256": "x"})
    with pytest.raises(NXToolError, match="missing or corrupt"):
        read_manifest(table)
    curve["provenance"]["source"] = "x" * 256001
    with pytest.raises(NXToolError, match="exceeds"):
        encode_manifest(curve)
