"""Topological heat-source overlap; no inferred geometric intersection test."""

from nx_mcp.runtime import NXToolError


def conflicts(a, b):
    """Keys are (face/body, prototype tag, prototype body tag)."""
    return a == b or (a[2] == b[2] and (a[0] == "body" or b[0] == "body"))


def inspect_heat_overlap(sim, targets):
    import NXOpen.CAE as cae
    import NXOpen.UF

    sf = NXOpen.UF.UFSession.GetUFSession().Sf

    def key(obj):
        prototype = obj.Prototype if obj.IsOccurrence else obj
        if prototype.OwningPart != sim.FemPart:
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Heat target lies outside the direct FEM")
        if isinstance(prototype, cae.CAEFace):
            return ("face", int(prototype.Tag), int(sf.FaceAskBody(prototype.Tag)))
        if isinstance(prototype, cae.CAEBody):
            return ("body", int(prototype.Tag), int(prototype.Tag))
        raise NXToolError(
            "NX_SIM_UNSUPPORTED", "Cannot check overlap with a non-face/body heat target"
        )

    requested = [key(t) for t in targets]
    rows = []
    for load in sim.Simulation.Loads:
        if load.PropertyTable.DescriptorNeutralName not in (
            "Heat Load",
            "Heat Flux",
            "Heat Generation",
        ):
            continue
        for index in range(load.TargetSetManager.TargetSetCount):
            _, members = load.TargetSetManager.GetTargetSetMembers(index)
            for member in members:
                if member is None or member.Obj is None:
                    continue
                existing = key(member.Obj)
                for requested_index, candidate in enumerate(requested):
                    if conflicts(candidate, existing):
                        rows.append(
                            {
                                "load_name": load.Name,
                                "load_journal_id": load.JournalIdentifier,
                                "requested_target_index": requested_index,
                                "relation": "same_target"
                                if candidate == existing
                                else "face_within_heated_body",
                            }
                        )
    return rows
