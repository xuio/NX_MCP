"""Run the verified public workflow with fresh names on the authorized Windows host.

Stages are explicit. Never repeat author after a partial failure; inspect its
receipts first. Inspect may be repeated while the existing solver job runs.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

STAGES = {
    "author": [
        "verify_public_cad_topology_r1.py",
        "verify_public_full_prepare_r1.py",
        "verify_public_full_download_r1.py",
    ],
    "launch": ["verify_public_full_launch_r1.py"],
    "inspect": ["verify_public_full_results_r1.py"],
    "reopen": ["verify_public_full_reopen_r1.py"],
}


def render(source, key):
    if not re.fullmatch(r"[a-z][a-z0-9]{1,11}", key) or key == "r1":
        raise ValueError(
            "Use a fresh 2..12 character lowercase alphanumeric key, starting with a letter; r1 is reserved"
        )
    return (
        source.replace("-r1", "-" + key)
        .replace("_r1", "_" + key)
        .replace("/model.prt", "/model_" + key + ".prt")
        .replace("Public full workflow reopened", "Public reopened " + key)
        .replace("Public full workflow", "Public workflow " + key)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_key")
    parser.add_argument("stage", choices=STAGES)
    args = parser.parse_args()
    render("", args.run_key)
    root = Path(__file__).resolve().parent
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    if not shared.is_dir():
        raise RuntimeError(
            "Run on the authorized NX Windows host with the existing Z: workspace share"
        )
    audit_path = shared / f"public-full-input-audit-{args.run_key}.json"
    if args.stage == "author" and (shared / f"public-cad-topology-{args.run_key}.json").exists():
        raise RuntimeError(
            "Run key has prior receipts; inspect them instead of repeating authoring"
        )
    if args.stage == "launch":
        audit = json.loads(audit_path.read_text())
        prepared = json.loads((shared / f"public-full-prepare-{args.run_key}.json").read_text())
        input_path = shared / f"public-full-input-{args.run_key}.xml"
        digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
        if (
            not audit["passed"]
            or digest != audit["input_sha256"]
            or digest != prepared["responses"]["29_prepare"]["structuredContent"]["input_sha256"]
        ):
            raise RuntimeError("Audited input identity differs; do not launch")
    if args.stage == "reopen":
        result = json.loads((shared / f"public-full-results-{args.run_key}.json").read_text())
        if not result.get("passed"):
            raise RuntimeError("Inspect the existing solver job and results before reopening")
    for filename in STAGES[args.stage]:
        path = root / filename
        source = render(path.read_text(), args.run_key)
        exec(compile(source, str(path), "exec"), {"__name__": "__main__", "__file__": str(path)})
    if args.stage == "author":
        subprocess.run(
            [
                sys.executable,
                str(root / "audit_public_input_r1.py"),
                str(shared / f"public-full-input-{args.run_key}.xml"),
                str(audit_path),
                "25",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
