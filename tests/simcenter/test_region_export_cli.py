"""The portable exporter handles native coupled field gaps without zero filling."""

import csv
import subprocess
import sys
from pathlib import Path


def test_coupled_receipt_exports_empty_region_and_coverage(tmp_path):
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "export"
    subprocess.run(
        [
            sys.executable,
            str(root / "examples/simcenter/export_region_receipt.py"),
            str(root / "tests/simcenter/evidence/room-fan-availability-public-r1.json"),
            str(output),
            "--responses",
            "regions",
            "--region-map",
            '{"fluid":0,"solid":1}',
            "--scenario-id",
            "room-fan",
            "--job-id",
            "room-fan-half-20260909-r1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with (output / "regions.csv").open() as f:
        fluid, solid = list(csv.DictReader(f))
    assert fluid["defined_nodes"] == "0" and fluid["undefined_nodes"] == "11528"
    assert fluid["minimum_degC"] == fluid["maximum_degC"] == fluid["nodal_mean_degC"] == ""
    assert solid["defined_nodes"] == "6238" and solid["undefined_nodes"] == "0"
    assert 23.89 < float(solid["nodal_mean_degC"]) < 23.90
