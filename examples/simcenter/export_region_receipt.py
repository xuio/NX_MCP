"""Export captured native region pages as JSON/CSV; performs no NX operations."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


def collect(receipt, response_names, mapping, scenario, job_id):
    pages = []
    for name in response_names:
        response = receipt["responses"][name]
        if response["isError"]:
            raise ValueError("Cannot export failed MCP response")
        pages.append(response["structuredContent"])
    first = pages[0]
    for page in pages:
        for key in (
            "result_file",
            "total",
            "loadcase_index",
            "iteration_index",
            "units",
            "coordinate_units",
            "coordinate_frame",
            "field",
            "mean_semantics",
        ):
            if page[key] != first[key]:
                raise ValueError("Pages differ in result/field identity or units")
    rows = [row for page in pages for row in page["items"]]
    if len({row["dimension"] for row in rows}) != 1:
        raise ValueError("Cannot combine different group dimensions")
    indices = [row["group_index"] for row in rows]
    if len(set(indices)) != len(indices) or set(indices) != set(range(first["total"])):
        raise ValueError("Require all group pages exactly once")
    if (
        not mapping
        or len(set(mapping.values())) != len(mapping)
        or any(type(v) is not int or v not in indices for v in mapping.values())
    ):
        raise ValueError("Supply distinct explicit region-name to group-index mappings")
    named = [
        {"region": name, **next(row for row in rows if row["group_index"] == index)}
        for name, index in mapping.items()
    ]
    return {
        "schema": 1,
        "scenario_id": scenario,
        "job_id": job_id,
        "job_binding": "caller-supplied; retain and inspect the job manifest separately",
        "region_mapping_source": "caller-supplied; verify against geometry",
        **{
            key: first[key]
            for key in (
                "result_file",
                "loadcase_index",
                "iteration_index",
                "field",
                "units",
                "coordinate_units",
                "coordinate_frame",
                "mean_semantics",
            )
        },
        "regions": named,
        "model_freshness": "not_verified",
        "engineering_accepted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("output", type=Path, help="New output directory; never overwrite")
    parser.add_argument("--responses", nargs="+", required=True)
    parser.add_argument("--region-map", required=True, help='JSON, e.g. {"sink":0,"heated":1}')
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    raw = args.receipt.read_bytes()
    result = collect(
        json.loads(raw), args.responses, json.loads(args.region_map), args.scenario_id, args.job_id
    )
    result["source_receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "regions.json").write_text(json.dumps(result, indent=2))
    with (args.output / "regions.csv").open("x", newline="") as stream:
        fields = [
            "region",
            "group_index",
            "nodes",
            "defined_nodes",
            "undefined_nodes",
            "minimum_degC",
            "maximum_degC",
            "nodal_mean_degC",
            "result_sha256",
            "scenario_id",
        ]
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in result["regions"]:
            writer.writerow(
                dict(
                    zip(
                        fields,
                        [
                            row["region"],
                            row["group_index"],
                            row["node_count"],
                            row.get("defined_node_count", row["node_count"]),
                            row.get("undefined_node_count", 0),
                            row["minimum"]["temperature"] if row["minimum"] is not None else None,
                            row["maximum"]["temperature"] if row["maximum"] is not None else None,
                            row["arithmetic_nodal_mean"],
                            result["result_file"]["sha256"],
                            args.scenario_id,
                        ],
                        strict=True,
                    )
                )
            )
    print(args.output)


if __name__ == "__main__":
    main()
