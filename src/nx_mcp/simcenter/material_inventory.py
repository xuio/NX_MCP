"""Bounded inspection of FEM-local physical materials; no activation or mutation."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.properties import read_properties


def inspect_materials(fem, nx, reference, *, offset=0, limit=20):
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be 1..100")
    materials = list(fem.MaterialManager.PhysicalMaterials)
    rows = []
    for material in materials[offset : offset + limit]:
        row = {
            "material": reference(material, "material", fem, "material"),
            "coordinate_frame": "material_axes",
        }
        for key, getter in (
            ("native_type", lambda material=material: str(material.GetMaterialType())),
            ("provenance", material.GetDescription),
            ("properties", lambda material=material: read_properties(material.GetPropTable(), nx)),
        ):
            try:
                row[key] = getter()
            except Exception as error:
                row.setdefault("inspection_errors", []).append(
                    {
                        "field": key,
                        "status": "read_failed",
                        "nx_code": getattr(error, "ErrorCode", None),
                    }
                )
        rows.append(row)
    return {
        "materials": rows,
        "total": len(materials),
        "next_offset": offset + limit if offset + limit < len(materials) else None,
        "owner_part_path": fem.FullPath,
        "collection_scope": "fem_local",
        "paging_consistency": "live_collection_restart_after_mutation",
    }
