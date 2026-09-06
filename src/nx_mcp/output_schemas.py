"""JSON Schema payload contracts for the integration surface.

Schemas describe committed results; they do not run a second validation step after
an NX mutation. Errors have a separate branch so success cardinality requirements
never hide a useful kernel error. Additive native metadata remains permitted.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

S = {"type": "string"}
N = {"type": "number"}
COUNT = {"type": "integer", "minimum": 0}
B = {"type": "boolean"}
NULL = {"type": "null"}
OUTCOMES = [
    "not_started",
    "running",
    "committed",
    "rolled_back",
    "partial",
    "unknown",
    "not_applicable",
]


def arr(item: dict, count: int | None = None) -> dict:
    result: dict[str, Any] = {"type": "array", "items": item}
    if count is not None:
        result.update(minItems=count, maxItems=count)
    return result


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": True,
    }


VEC = arr(N, 3)
REF = obj(
    {
        "id": S,
        "kind": S,
        "name": S,
        "part_id": S,
        "session_id": S,
        "generation_id": S,
        "owner_part_path": S,
        "journal_id": S,
        "display_name": S,
    },
    ["id", "kind", "name", "part_id"],
)
REF["description"] = (
    "Opaque identity, separate from display name. Reacquire after close, rollback or manual handoff; use occurrence context for assemblies."
)
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
META = {"path": S, "size": COUNT, "sha256": HASH}
PAIR = obj(
    {
        "objects": arr(REF, 2),
        "distance": N,
        "closest_points": arr(VEC, 2),
        "classification": {"enum": ["clear", "contact", "penetration", "below_clearance"]},
        "interference_volume_mm3": N,
    }
)

# Required fields follow actual bridge implementations; optional metadata remains typed.
PAYLOADS: dict[str, dict[str, Any]] = {
    "nx_get_bounding_box": obj(
        {
            "min": VEC,
            "max": VEC,
            "dimensions": VEC,
            "coordinate_frame": S,
            "bounds_type": {"enum": ["exact", "conservative"]},
            "body_count": COUNT,
            "scope": S,
            "bodies": arr(obj({"body": REF, "box": arr(N, 6), "solid": B})),
        }
    ),
    "nx_measure_distance": obj(
        {
            "distance": N,
            "closest_points": arr(VEC, 2),
            "references": arr(S, 2),
            "resolved_tags": arr(COUNT, 2),
            "coordinate_frame": S,
            "pair_count": COUNT,
            "method": S,
            "accuracy": NULL,
        }
    ),
    "nx_measure_volume": obj(
        {
            "volume_mm3": N,
            "volume_units": {"const": "mm^3"},
            "semantics": {"const": "sum_of_included_bodies"},
            "body_count": COUNT,
            "scope": S,
            "bodies": arr(obj({"body": REF, "volume_mm3": N})),
        }
    ),
    "nx_list_topology": obj({"body": REF, "faces": arr(REF), "edges": arr(REF), "solid": B}),
    "nx_list_components": obj(
        {
            "count": COUNT,
            "matrix_convention": S,
            "components": arr(
                obj(
                    {
                        "object": REF,
                        "name": S,
                        "part_path": S,
                        "depth": COUNT,
                        "translation": VEC,
                        "rotation_matrix": arr(VEC, 3),
                        "coordinate_frame": S,
                        "suppressed": B,
                        "reference_set": S,
                    }
                )
            ),
        }
    ),
    "nx_operation_status": obj(
        {
            "operation_id": S,
            "state": {"enum": ["running", "committed", "failed", "unknown", "rolled_back"]},
            "mutation_outcome": {"enum": OUTCOMES},
            "method": S,
            "reason": S,
            "session_id": S,
            "started_at": S,
            "finished_at": S,
            "result": {"type": "object"},
            "error": {"type": "object"},
            "reverted_by": S,
            "query_operation_id": S,
            "query_session_id": S,
        },
        ["operation_id", "state", "mutation_outcome"],
    ),
    "nx_checkpoint": obj({"checkpoint_id": S, "message": S}),
    "nx_rollback": obj({"checkpoint_id": S, "message": S}),
    "nx_checkpoint_state": obj(
        {
            "checkpoints": arr(
                obj({"checkpoint_id": S, "part_id": S, "index": COUNT, "label": S, "available": B})
            ),
            "undo_depth": COUNT,
            "save_semantics": S,
            "retention": S,
        }
    ),
    "nx_workspace_list": obj(
        {
            "path": S,
            "count": COUNT,
            "total_count": COUNT,
            "offset": COUNT,
            "next_offset": {"anyOf": [COUNT, NULL]},
            "entries": arr(
                {
                    "oneOf": [
                        obj({**META, "kind": {"const": "file"}}),
                        obj({"path": S, "kind": {"const": "directory"}}),
                    ]
                }
            ),
        }
    ),
    "nx_download_file": {
        "oneOf": [
            obj({**META, "delivery": {"const": "metadata"}}),
            obj(
                {
                    **META,
                    "delivery": {"const": "image"},
                    "mime_type": {"const": "image/png"},
                    "resolution": arr(COUNT, 2),
                }
            ),
            obj(
                {
                    **META,
                    "offset": COUNT,
                    "bytes_returned": COUNT,
                    "next_offset": {"anyOf": [COUNT, NULL]},
                    "data_base64": S,
                    "eof": B,
                }
            ),
        ]
    },
}
for name in ("nx_check_interference", "nx_check_clearance"):
    PAYLOADS[name] = obj(
        {
            "pairs": arr(PAIR),
            "counts": {"type": "object", "additionalProperties": COUNT},
            "body_count": COUNT,
            "pair_count": COUNT,
            "reported_pair_count": COUNT,
            "broad_phase_clear_pairs": COUNT,
            "minimum_clearance": N,
            "volume_units": {"const": "mm^3"},
            "coordinate_frame": S,
            "complete": B,
            "semantics": S,
        }
    )
for name in ("nx_extrude", "nx_pattern"):
    PAYLOADS[name] = obj(
        {"feature": REF, "body": {"anyOf": [REF, NULL]}, "bodies": arr(REF), "body_count": COUNT},
        ["feature", "bodies"],
    )
PAYLOADS["nx_revolve"] = obj({"feature": REF, "angle": N, "axis": S})
for name in (
    "nx_screenshot",
    "nx_render_view",
    "nx_export_step",
    "nx_export_drawing_pdf",
    "nx_export_flat_pattern",
    "nx_package_assembly",
):
    PAYLOADS[name] = obj({**META, "mime_type": S, "resolution": arr(COUNT, 2)}, ["path", "sha256"])


def output_schema(name: str, common: dict) -> dict:
    """Keep an object root for MCP; discriminate errors before success payloads."""
    schema = deepcopy(common)
    schema["title"] = name + " result"
    schema["description"] = "Structured success/error envelope with additive metadata. " + (
        "Tool-specific payload is typed."
        if name in PAYLOADS
        else "Tool-specific payload remains extensible."
    )
    schema["properties"].update(
        {
            "code": S,
            "message": S,
            "retryable": B,
            "suggestion": S,
            "nx_code": {"type": ["integer", "string"]},
            "details": obj({"operation_id": S, "mutation_outcome": {"enum": OUTCOMES}}, []),
        }
    )
    schema["properties"]["mutation_outcome"] = {"anyOf": [{"enum": OUTCOMES}, NULL]}
    schema["allOf"] = [
        {
            "if": {"properties": {"status": {"const": "error"}}},
            "then": {"required": ["code", "message", "retryable"]},
        }
    ]
    if name in PAYLOADS:
        schema["allOf"].append(
            {
                "if": {"properties": {"status": {"const": "success"}}},
                "then": deepcopy(PAYLOADS[name]),
            }
        )
    return schema
