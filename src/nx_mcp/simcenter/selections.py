"""Direct FEM face inventory with explicit prototype coordinate frame."""

from nx_mcp.runtime import NXToolError


def face_inventory(session, sim):
    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.UF as uf

    if not isinstance(sim, (cae.SimPart, cae.FemPart)) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected FEM or SIM first")
    fem = sim if isinstance(sim, cae.FemPart) else sim.FemPart
    if not isinstance(fem, cae.FemPart):
        raise NXToolError("NX_SIM_UNSUPPORTED", "Face inventory requires a standalone FEM")
    component = None
    if isinstance(sim, cae.SimPart):
        components = list(sim.ComponentAssembly.RootComponent.GetChildren())
        if len(components) != 1 or components[0].Prototype != fem:
            raise NXToolError(
                "NX_SIM_UNSUPPORTED", "Expected one direct occurrence of the associated FEM"
            )
        component = components[0]
    sf = uf.UFSession.GetUFSession().Sf
    rows = []
    for body in fem.Bodies:
        count, tags = sf.BodyAskFaces(body.Tag)
        if count != len(tags):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Native face count differs from enumeration"
            )
        for tag in tags:
            prototype = nx.TaggedObjectManager.GetTaggedObject(tag)
            occurrence = component.FindOccurrence(prototype) if component else prototype
            if occurrence is None or occurrence.OwningPart != sim:
                raise NXToolError(
                    "NX_SIM_SELECTION_OWNER", "Face does not resolve into the selected SIM"
                )
            box = list(sf.FaceAskBoundingBox(tag))
            if len(box) != 6:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Native face bounds are incomplete")
            rows.append(
                {
                    "face": occurrence,
                    "body": body,
                    "bounds": {"minimum": box[:3], "maximum": box[3:]},
                }
            )
    rows.sort(key=lambda row: (int(row["body"].Tag), int(row["face"].Tag)))
    return {
        "rows": rows,
        "fem": fem,
        "component_name": component.Name if component else None,
        "selection_scope": "sim_occurrence" if component else "fem_prototype",
        "units": "mm" if str(fem.PartUnits) == "1" else "inch",
        "coordinate_frame": "fem_part_absolute",
        "bounds_kind": "native_face_bounding_box; not exact surface geometry",
        "scope": "direct standalone FEM; no nested assembly traversal",
    }
