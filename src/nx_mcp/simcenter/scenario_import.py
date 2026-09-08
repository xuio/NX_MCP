"""Bounded scenario ingestion and assignment preflight; no NX mutations."""

import csv
import hashlib
import io
import json
import math

_COLUMNS = {
    "name",
    "region",
    "watts",
    "category",
    "accounting_id",
    "provenance_kind",
    "provenance_source",
}
_LIMIT = 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property: " + key)
        result[key] = value
    return result


def parse_scenario(raw: bytes, format: str, metadata: dict | None = None) -> dict:
    """CSV carries source rows; its scenario metadata must be supplied separately."""
    if not isinstance(raw, bytes) or len(raw) > _LIMIT:
        raise ValueError("Scenario input must be bytes, at most 1 MiB")
    text = raw.decode("utf-8-sig")
    if format == "json":
        if metadata is not None:
            raise ValueError("JSON already contains metadata; overrides are not allowed")
        data = json.loads(text, object_pairs_hook=_unique_object)
    elif format == "csv":
        if not isinstance(metadata, dict) or "sources" in metadata:
            raise ValueError("CSV requires scenario metadata without sources")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        columns = reader.fieldnames
        if columns is None or len(columns) != len(_COLUMNS) or set(columns) != _COLUMNS:
            raise ValueError("CSV columns must be exactly: " + ", ".join(sorted(_COLUMNS)))
        rows = []
        for row in reader:
            if len(rows) >= 1000:
                raise ValueError("Scenario must contain at most 1000 sources")
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV row has missing or extra cells")
            rows.append(
                {
                    "name": row["name"],
                    "region": row["region"] or None,
                    "watts": row["watts"],
                    "category": row["category"],
                    "accounting_id": row["accounting_id"],
                    "provenance": {
                        "kind": row["provenance_kind"],
                        "source": row["provenance_source"],
                    },
                }
            )
        data = {**metadata, "sources": rows}
    else:
        raise ValueError("format must be json or csv")
    return validate_scenario(data)


def validate_scenario(data):
    """Validate on NX's standard-library-only interpreter as well as the sidecar."""

    def fields(value, required, optional=()):
        if (
            not isinstance(value, dict)
            or not set(required) <= value.keys()
            or value.keys() - set(required) - set(optional)
        ):
            raise ValueError("Missing or unsupported scenario fields")

    def identity(value):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError("Identities must be nonempty without surrounding whitespace")
        return value

    def number(value, positive=False):
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("Power/temperature must be numeric, not a boolean")
        value = float(value)
        if not math.isfinite(value) or value < 0 or (positive and value == 0):
            raise ValueError("Power/temperature must be finite and in range")
        return value

    fields(data, ("name", "workload_revision", "ambient_K", "sources"), ("schema_version",))
    if type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) != 1:
        raise ValueError("Only scenario schema_version 1 is supported")
    if not isinstance(data["sources"], list) or not 1 <= len(data["sources"]) <= 1000:
        raise ValueError("Scenario requires 1..1000 sources")
    sources, names, accounts = [], set(), set()
    for source in data["sources"]:
        fields(source, ("name", "watts", "category", "accounting_id", "provenance"), ("region",))
        name, account = identity(source["name"]), identity(source["accounting_id"])
        if name in names or account in accounts:
            raise ValueError("Duplicate source or accounting identity")
        names.add(name)
        accounts.add(account)
        category = source["category"]
        if category not in ("internal_heat", "exported_electrical", "battery_storage"):
            raise ValueError("Unsupported energy category")
        region = source.get("region")
        if category == "internal_heat":
            region = identity(region)
        elif region is not None:
            raise ValueError("Exported electrical energy and battery storage are not heat loads")
        provenance = source["provenance"]
        fields(provenance, ("kind", "source"))
        if provenance["kind"] not in ("measured", "datasheet", "assumed"):
            raise ValueError("Unsupported provenance kind")
        identity(provenance["source"])
        sources.append({**source, "region": region, "watts": number(source["watts"])})
    return {
        "schema_version": 1,
        "name": identity(data["name"]),
        "workload_revision": identity(data["workload_revision"]),
        "ambient_K": number(data["ambient_K"], positive=True),
        "sources": sources,
    }


def assignment_plan(scenario: dict, region_targets: dict[str, str]):
    """Require exact semantic mapping; returned IDs still require native resolution."""
    scenario = validate_scenario(scenario)
    if not isinstance(region_targets, dict) or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        for k, v in region_targets.items()
    ):
        raise ValueError("Region targets must map nonempty semantic names to object IDs")
    internal = [s for s in scenario["sources"] if s["category"] == "internal_heat"]
    regions = {s["region"] for s in internal}
    missing = sorted(regions - region_targets.keys())
    extra = sorted(region_targets.keys() - regions)
    if missing or extra:
        raise ValueError(f"Region assignment mismatch: missing={missing}, unused={extra}")
    targets = [region_targets[s["region"]] for s in internal]
    if len(set(targets)) != len(targets):
        raise ValueError("Duplicate heat target; consolidate sources explicitly before assignment")
    totals = {
        category: sum(s["watts"] for s in scenario["sources"] if s["category"] == category)
        for category in ("internal_heat", "exported_electrical", "battery_storage")
    }
    if not all(math.isfinite(value) for value in totals.values()):
        raise ValueError("Power totals exceed the finite numeric range")
    digest = hashlib.sha256(
        json.dumps(scenario, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return {
        "valid": True,
        "unmatched_regions": [],
        "totals_W": totals,
        "scenario_sha256": digest,
        "applied_to_nx": False,
        "name": scenario["name"],
        "workload_revision": scenario["workload_revision"],
        "ambient_K": scenario["ambient_K"],
        "ambient_applied": False,
        "target_resolution": "required_before_mutation",
        "assignments": [
            {
                "source": s["name"],
                "accounting_id": s["accounting_id"],
                "region": s["region"],
                "target": region_targets[s["region"]],
                "power_W": s["watts"],
                "provenance": s["provenance"],
            }
            for s in internal
        ],
        "excluded_sources": [
            s["name"] for s in scenario["sources"] if s["category"] != "internal_heat"
        ],
    }


def preview_identity(document_id, source_sha256, scenario_sha256, region_targets):
    """Bind bytes, scenario metadata, owner and the exact requested selections."""
    encoded = json.dumps(
        {
            "schema_version": 1,
            "document": document_id,
            "source_sha256": source_sha256,
            "scenario_sha256": scenario_sha256,
            "region_targets": region_targets,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_preview(expected, actual):
    from nx_mcp.runtime import NXToolError

    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "expected_preview_sha256 must be the lowercase SHA256 returned by scenario preview",
            details={"mutation_outcome": "not_started"},
        )
    if expected != actual:
        raise NXToolError(
            "NX_SIM_SCENARIO_CHANGED",
            "Scenario content, metadata, owner or selection differs from the preview",
            details={
                "mutation_outcome": "not_started",
                "expected_preview_sha256": expected,
                "actual_preview_sha256": actual,
                "next_step": "Review a fresh scenario preview and use its preview_sha256",
            },
        )
