"""Creation-only orthotropic porous resistance; numerical semantics need a coupon."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.internal_fan import snapshot

DESCRIPTOR = "Porous Blockage - Orthotropic"


def validate(name, permeability_m2, loss_per_m, laminar):
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a unique name of 1..120 characters")
    if type(laminar) is not bool:
        raise NXToolError("NX_INVALID_ARGUMENT", "laminar must be boolean")
    converted = []
    for values, factor, positive in [(permeability_m2, 1e6, True), (loss_per_m, 0.001, False)]:
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply three XYZ coefficients")
        row = []
        for value in values:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise NXToolError("NX_INVALID_ARGUMENT", "Coefficients must be finite numbers")
            native = value * factor
            if not math.isfinite(native) or (native <= 0 if positive else native < 0):
                raise NXToolError(
                    "NX_INVALID_ARGUMENT", "Permeability must be positive and loss nonnegative"
                )
            row.append(native)
        converted.append(row)
    return converted


def inventory(sim):
    return {**snapshot(sim), "frames": sorted(int(x.Tag) for x in sim.CoordinateSystems)}


def create(session, sim, bodies, name, permeability_m2, loss_per_m, laminar):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    permeability, losses = validate(name, permeability_m2, loss_per_m, laminar)
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Flow or Coupled Thermal-Flow"
        )
    if sim.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Requires millimeter SIM")
    if (
        not bodies
        or len(bodies) > 100
        or any(b is None or b.OwningPart != sim or not b.IsOccurrence for b in bodies)
    ):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select 1..100 direct SIM body occurrences")
    expected = {int(b.Tag) for b in bodies}
    if len(expected) != len(bodies):
        raise NXToolError("NX_INVALID_ARGUMENT", "Duplicate bodies")
    for obj in sim.Simulation.SimulationObjects:
        if obj.Name.casefold() == name.casefold():
            raise NXToolError("NX_SIM_NAME_CONFLICT", "Simulation object name already exists")
        if "Blockage" in obj.DescriptorName:
            for index in range(obj.TargetSetManager.TargetSetCount):
                _, members = obj.TargetSetManager.GetTargetSetMembers(index)
                if any(m.Obj is not None and int(m.Obj.Tag) in expected for m in members):
                    raise NXToolError("NX_SIM_SELECTION_OVERLAP", "Body already has a blockage")
    guard = require_solver_idle()
    before = inventory(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP porous resistance")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(DESCRIPTOR, name)
        if builder.TargetSetManager.TargetSetCount != 1:
            raise ValueError("Unexpected target-set count")
        props = builder.PropertyTable
        frame = sim.CoordinateSystems.CreateCoordinateSystem(
            nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(1.0, 0.0, 0.0), nx.Vector3d(0.0, 1.0, 0.0)
        )
        props.SetCoordinateSystemPropertyValue("Orientation CSYS", frame)
        flags = {
            "Flow is Laminar in Blockage": laminar,
            "Orthotropic Inertial Resistance": True,
            "Orthotropic Permeability": True,
        }
        for key, value in flags.items():
            props.SetBooleanPropertyValue(key, value)
        scalar_values = {}
        for axis, k, c in zip("XYZ", permeability, losses, strict=True):
            scalar_values[f"{axis} Permeability Value"] = (k, "SquareMilliMeter")
            scalar_values[f"{axis} Loss Coefficient per Length"] = (c, "CoefficientPerMilliMeter")
        for key, (value, unit_name) in scalar_values.items():
            props.SetBaseScalarWithDataPropertyValue(
                key, value, sim.UnitCollection.FindObject(unit_name)
            )
        members = []
        for body in bodies:
            member = cae.SetObject()
            member.Obj, member.SubType, member.SubId = body, cae.CaeSetObjectSubType.NotSet, 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
        boundary = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        props = boundary.PropertyTable
        if boundary.DescriptorName != DESCRIPTOR or boundary.OwningPart != sim:
            raise ValueError("Committed descriptor/owner differs")
        if any(props.GetBooleanPropertyValue(k) != v for k, v in flags.items()):
            raise ValueError("Committed flags differ")
        if props.GetCoordinateSystemPropertyValue("Orientation CSYS") != frame:
            raise ValueError("Committed frame differs")
        matrix, origin = frame.Orientation.Element, frame.Origin
        actual_frame = [
            origin.X,
            origin.Y,
            origin.Z,
            matrix.Xx,
            matrix.Xy,
            matrix.Xz,
            matrix.Yx,
            matrix.Yy,
            matrix.Yz,
            matrix.Zx,
            matrix.Zy,
            matrix.Zz,
        ]
        if any(
            abs(a - b) > 1e-10
            for a, b in zip(actual_frame, [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1], strict=True)
        ):
            raise ValueError("Frame is not global Cartesian")
        readback = {}
        for key, (value, unit_name) in scalar_values.items():
            observed, unit = props.GetBaseScalarWithDataPropertyValue(key)
            if unit.Name != unit_name or not math.isclose(
                observed, value, rel_tol=1e-12, abs_tol=0.0
            ):
                raise ValueError("Committed coefficient or unit differs: " + key)
            readback[key] = {"value": observed, "unit": unit.Name}
        _, targets = boundary.TargetSetManager.GetTargetSetMembers(0)
        if len(targets) != len(bodies) or {int(m.Obj.Tag) for m in targets} != expected:
            raise ValueError("Committed body selection differs")
        if not any(obj.Tag == boundary.Tag for obj in sol.GetBcs()):
            raise ValueError("Boundary absent from active solution")
        return {
            "boundary": boundary,
            "descriptor": DESCRIPTOR,
            "target_count": len(targets),
            "coordinate_frame": "SIM absolute Cartesian",
            "native_coefficients": readback,
            "flags": flags,
            "solver_preflight": guard,
            "saved": False,
            "results_stale": True,
            "solver_launched": False,
            "numerical_acceptance": False,
            "warnings": [
                "Native authoring, body export and resistance-law convention require isolated validation before production use."
            ],
        }
    except Exception as error:
        cleanup = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception as exc:
                cleanup.append(str(exc))
        restored = False
        try:
            session.UndoToMark(mark, None)
            restored = inventory(sim) == before
            if restored:
                session.DeleteUndoMark(mark, None)
        except Exception as exc:
            cleanup.append(str(exc))
        outcome = "rolled_back" if restored and not cleanup else "partial"
        raise NXToolError(
            "NX_SIM_AUTHORING_FAILED" if outcome == "rolled_back" else "NX_SIM_RECOVERY_INCOMPLETE",
            "Porous resistance creation failed",
            details={
                "mutation_outcome": outcome,
                "snapshot_restored": restored,
                "operation_error": str(error),
                "cleanup_errors": cleanup,
            },
        ) from error
