import json
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.scalar_tables import (
    DATA,
    HEADER,
    compact,
    encode,
    read_manifest,
    validate,
    verify_values,
)


def manifest():
    return {
        "name": "Power",
        "axis": "time",
        "quantity": "power",
        "samples": [[0, 0], [10, 1], [20, 0]],
        "provenance": "Assumed unit fixture",
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("axis", "position"),
        ("quantity", "unsupported"),
        ("samples", [[0, 0], [0, 1]]),
        ("samples", [[0, 0], [10, float("nan")]]),
        ("samples", [[True, 0], [10, 1]]),
        ("samples", [[0, 0]]),
        ("version", True),
        ("outside_table", "extrapolate"),
    ],
)
def test_invalid_scalar_manifest(key, value):
    m = manifest()
    m[key] = value
    with pytest.raises(NXToolError):
        validate(m)


def test_metadata_roundtrip_and_checksum_rejection():
    header, chunks = encode(manifest())
    data = {(HEADER, -1): header, **{(DATA, i): v for i, v in enumerate(chunks)}}
    table = NS(GetStringUserAttribute=lambda key, index: data[(key, index)])
    assert read_manifest(table) == validate(manifest())
    data[(DATA, 0)] = data[(DATA, 0)].replace("Power", "Other")
    with pytest.raises(NXToolError) as error:
        read_manifest(table)
    assert error.value.code == "NX_SIM_MANIFEST_INVALID"


def test_header_chunk_count_is_bounded():
    table = NS(
        GetStringUserAttribute=lambda *args: json.dumps(
            {"version": 1, "chunks": 10**9, "sha256": "bad"}
        )
    )
    with pytest.raises(NXToolError):
        read_manifest(table)


@pytest.mark.parametrize("actual", [[0, 1], [0, 1, float("nan")], [0, 2, 0]])
def test_changed_native_values_or_cardinality_rejected(actual):
    with pytest.raises(NXToolError):
        verify_values([0, 1, 0], actual)


def test_compact_readback_omits_sample_arrays_without_changing_source():
    full = {"manifest": manifest(), "readback": {"samples_si": [[0, 0], [10, 1], [20, 0]]}}
    short = compact(full)
    assert short["sample_count"] == 3 and short["axis_range_si"] == [0, 20]
    assert "samples" not in short["manifest"] and "samples_si" not in short["readback"]
    assert len(full["manifest"]["samples"]) == 3
