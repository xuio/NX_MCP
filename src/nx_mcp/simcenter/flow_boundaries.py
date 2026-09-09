"""Owned face inlet/opening authoring using NX 2606 documented descriptors.

Source: copied opencae Coupled Thermal-Flow/SSSOS Inlet and Opening tables.
Normal-to-face alignment only; vector/swirl definitions require another adapter.
"""

import math

from nx_mcp.runtime import NXToolError


def validate(kind, name, value, alignment):
    if kind not in ("inlet", "opening") or alignment != "normal_to_face":
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Select inlet/opening and normal_to_face alignment"
        )
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a nonempty boundary name")
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Supply positive finite velocity m/s or absolute pressure Pa"
        )


def snapshot(sim):
    return {
        "objects": sorted(int(o.Tag) for o in sim.Simulation.SimulationObjects),
        "expressions": sorted(int(o.Tag) for o in sim.Expressions),
        "solution_bcs": sorted(int(o.Tag) for o in sim.Simulation.ActiveSolution.GetBcs()),
    }


def create(session, sim, faces, kind, name, value, alignment="normal_to_face"):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.boundaries import verify_face_targets
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(kind, name, value, alignment)
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Coupled Thermal-Flow"
    ):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Coupled Thermal-Flow")
    if not faces or len({int(f.Tag) for f in faces}) != len(faces):
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply distinct owned occurrence faces")
    if any(f.OwningPart != sim or not f.IsOccurrence for f in faces):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select SIM occurrence faces from nx_sim_faces")
    objects = list(sim.Simulation.SimulationObjects)
    if any(o.Name.casefold() == name.casefold() for o in objects):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Boundary name already exists")
    # Reject duplicate flow boundary selections, including partial overlap.
    requested = {int(f.Tag) for f in faces}
    for existing in objects:
        if existing.DescriptorName in ("Inlet", "Opening"):
            _, members = existing.TargetSetManager.GetTargetSetMembers(0)
            if requested.intersection(int(m.Obj.Tag) for m in members):
                raise NXToolError("NX_SIM_SELECTION_OVERLAP", "Face already has an inlet/opening")
    require_solver_idle()
    descriptor = "Inlet" if kind == "inlet" else "Opening"
    key, unit_name = (
        ("Velocity", "MeterPerSecond") if kind == "inlet" else ("Pressure Value", "PressurePascals")
    )
    unit = sim.UnitCollection.FindObject(unit_name)
    before = snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP " + descriptor)
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(descriptor, name)
        props = builder.PropertyTable
        selectors = {"Alignment": 0}
        selectors.update(
            {"Mode Option": 0, "Swirl": 0}
            if kind == "inlet"
            else {"External Pressure Type": 0, "Pressure": 1}
        )
        for key_name, setting in selectors.items():
            props.SetIntegerPropertyValue(key_name, setting)
        expression = sim.Expressions.CreateSystemNumberExpression(str(float(value)), unit)
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        props.SetScalarFieldWrapperPropertyValue(key, wrapper)
        members = []
        for face in faces:
            member = cae.SetObject()
            member.Obj, member.SubType, member.SubId = face, cae.CaeSetObjectSubType.NotSet, 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
        boundary = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        actual = boundary.PropertyTable
        scalar, actual_unit = actual.GetScalarWithDataPropertyValue(key)
        if (
            any(actual.GetIntegerPropertyValue(k) != v for k, v in selectors.items())
            or actual_unit.Name != unit_name
            or not math.isclose(scalar, value, rel_tol=1e-12)
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Boundary value, unit or selector differs"
            )
        targets = verify_face_targets(boundary, faces)
        if int(boundary.Tag) not in {int(o.Tag) for o in solution.GetBcs()}:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Boundary missing from selected solution")
        return {
            "boundary": boundary,
            "kind": kind,
            "alignment": alignment,
            "value": scalar,
            "units": "m/s" if kind == "inlet" else "Pa",
            "pressure_convention": "absolute"
            if kind == "opening"
            else "not_applicable_to_velocity",
            "properties": read_properties(actual, nx),
            "targets": targets,
            "solution_member": True,
            "external_conditions": "not_assigned; use nx_sim_external_temperature",
            "saved": False,
            "solver_launched": False,
            "results_stale": True,
        }
    except Exception as error:
        cleanup = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception:
                cleanup.append("builder_destroy")
        restored = False
        try:
            session.UndoToMark(mark, None)
            restored = snapshot(sim) == before
            if restored:
                session.DeleteUndoMark(mark, None)
        except Exception:
            cleanup.append("undo")
        outcome = "rolled_back" if restored and not cleanup else "partial"
        raise NXToolError(
            "NX_SIM_AUTHORING_FAILED" if outcome == "rolled_back" else "NX_SIM_RECOVERY_INCOMPLETE",
            "Flow boundary creation failed; inspect recovery outcome",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": outcome,
                "snapshot_restored": restored,
                "cleanup_issues": cleanup,
            },
        ) from error
