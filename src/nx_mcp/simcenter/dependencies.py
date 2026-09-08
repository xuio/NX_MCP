"""Inspect direct SIM/FEM/CAD associations without loading or saving documents."""

from nx_mcp.runtime import NXToolError
from nx_mcp.workspace import WorkspaceViolation


def inspect_direct(session, sim, workspace):
    import NXOpen.CAE as cae

    if not isinstance(sim, cae.SimPart):
        raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
    fem = sim.FemPart
    if not isinstance(fem, cae.FemPart):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_DOCUMENT_TYPE",
            "Direct dependency inspection currently requires a standalone FEM, not an assembly FEM",
        )
    parts = [sim, fem]
    roles = {sim.Tag: ["simulation"], fem.Tag: ["mesh"]}
    links = []
    unresolved = []
    for role in ("AssociatedCadPart", "IdealizedPart", "MasterCadPart"):
        part = getattr(fem, role)
        links.append({"association": role, "path": part.FullPath if part else None})
        if part is not None:
            if part.Tag not in roles:
                parts.append(part)
                roles[part.Tag] = []
            roles[part.Tag].append(role)
    path = fem.FullPathForAssociatedCadPart
    if path and not any(p.FullPath.casefold() == path.casefold() for p in parts):
        unresolved.append(
            {"association": "AssociatedCadPart", "path": path, "reason": "not_loaded_or_unresolved"}
        )
    rows = []
    for part in parts:
        try:
            candidate = workspace.ensure_inside(part.FullPath)
            file_state = "exists" if candidate.is_file() else "missing"
        except WorkspaceViolation:
            file_state = "outside_workspace"
        assembly = getattr(part, "ComponentAssembly", None) if part not in (sim, fem) else None
        root = assembly.RootComponent if assembly else None
        children = list(root.GetChildren()) if root else []
        if children:
            unresolved.append(
                {
                    "association": "component_dependencies",
                    "path": part.FullPath,
                    "reason": "assembly_children_not_enumerated",
                    "child_count": len(children),
                }
            )
        rows.append(
            {
                "part": part,
                "path": part.FullPath,
                "roles": roles[part.Tag],
                "document_type": type(part).__name__,
                "modified": bool(part.IsModified),
                "fully_loaded": bool(part.IsFullyLoaded),
                "file_state": file_state,
                "work": part == session.Parts.BaseWork,
                "display": part == session.Parts.BaseDisplay,
                "units": "mm" if str(part.PartUnits) == "1" else "inch",
            }
        )
    return {
        "rows": rows,
        "associations": links,
        "unresolved": unresolved,
        "scope": "direct_sim_fem_cad_associations",
        "complete_analysis_package": False,
        "excluded": "recursive components, external fields/material files, solver artifacts and result dependencies",
    }
