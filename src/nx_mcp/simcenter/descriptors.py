"""Installed load/constraint names from documented UF language enumeration."""

from nx_mcp.runtime import NXToolError


def descriptor_inventory(sim, kind="load", offset=0, limit=50, name_contains=None):
    import NXOpen.CAE as cae
    import NXOpen.UF

    if not isinstance(sim, cae.SimPart):
        raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a loaded SIM document")
    if kind not in ("load", "constraint", "solution_step"):
        raise NXToolError("NX_INVALID_ARGUMENT", "kind must be load, constraint or solution_step")
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0 and limit 1..100")
    if name_contains is not None and (
        not isinstance(name_contains, str) or len(name_contains) > 100
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "name_contains must be a string of at most 100 characters"
        )
    # UF_SFL_*_descriptor*_nx requires a Simulation work part for all categories.
    if not isinstance(NXOpen.Session.GetSession().Parts.BaseWork, cae.SimPart):
        raise NXToolError(
            "NX_SIM_DOCUMENT_NOT_ACTIVE",
            "Descriptor discovery requires a SIM work part; activate the selected SIM first",
            details={"mutation_outcome": "not_started", "next_step": "nx_sim_activate"},
        )
    solution = sim.Simulation.ActiveSolution
    if solution is None:
        raise NXToolError("NX_SIM_SOLUTION_REQUIRED", "Select a solution in this SIM first")
    uf = NXOpen.UF.UFSession.GetUFSession()
    language = uf.Sf.SolutionAskLanguageNx(solution.Tag)
    category = "Load" if kind == "load" else "Bc"
    if kind == "solution_step":
        descriptor = uf.Sf.SolutionAskDescriptorNx(solution.Tag)
        count = uf.Sfl.SolutionAskNumAllowableStepDescriptorsNx(descriptor)
    else:
        count = getattr(uf.Sfl, "AskNum" + category + "DescriptorsNx")(language)
    if not 0 <= count <= 4096:
        raise NXToolError(
            "NX_SIM_DESCRIPTOR_LIMIT",
            "Native descriptor count exceeds the 4096-entry discovery limit",
        )
    rows = []
    for index in range(count):
        if kind == "solution_step":
            tag = uf.Sfl.SolutionAskNthAllowableStepDescriptorNx(descriptor, index)
            name = uf.Sfl.StepDescriptorAskNameNx(tag)
        else:
            tag = getattr(uf.Sfl, "AskNth" + category + "DescriptorNx")(language, index)
            name = getattr(uf.Sfl, "Ask" + category + "DescriptorNameNx")(tag)
        if name_contains is None or name_contains.casefold() in name.casefold():
            row = {"descriptor_name": name, "kind": kind}
            if kind == "solution_step":
                row["step_type_index"] = index
            rows.append(row)
    return {
        "descriptors": rows[offset : offset + limit],
        "total": len(rows),
        "unfiltered_total": count,
        "next_offset": offset + limit if offset + limit < len(rows) else None,
        "solver": solution.SolverType,
        "analysis_type": solution.AnalysisType,
        "solution": solution.Name,
        "owner_path": sim.FullPath,
        "units": None,
        "scope": "installed descriptor names; allowable steps for selected solution or language loads/constraints; not object instances",
        "builder_creation_tested_by_call": False,
        "solution_applicability": "native_allowable_step"
        if kind == "solution_step"
        else "not_tested",
        "simulation_object_descriptors": "not_enumerated_by_this_API",
        "licence_checkout": "not_tested",
    }
