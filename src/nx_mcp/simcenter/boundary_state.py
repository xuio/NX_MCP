"""Observed live thermal boundary state; not complete physics freshness."""

from nx_mcp.simcenter.collector_state import state_hash


def stable_boundary_values(value):
    """Exclude only transient field tags from semantic comparison, not inspection."""
    if isinstance(value, list):
        return [stable_boundary_values(item) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                {k: v for k, v in item.items() if k != "tag"}
                if key == "field_reference" and isinstance(item, dict)
                else stable_boundary_values(item)
            )
            for key, item in value.items()
        }
    return value


def _container_membership(sim, container, errors):
    def ref(obj):
        if obj.OwningPart != sim:
            raise ValueError("Boundary membership owner differs from SIM")
        return {"journal_id": obj.JournalIdentifier, "owner_path": sim.FullPath}

    bcs = sorted((ref(b) for b in container.GetBcs()), key=lambda r: r["journal_id"])
    plain = sorted((ref(b) for b in container.GetUnfolderedBcs()), key=lambda r: r["journal_id"])
    folders = [ref(f) for f in container.GetFolders()]
    if folders or plain != bcs:
        errors.append({"reason": "unsupported_folder_membership", "owner": ref(container)})
    if len({r["journal_id"] for r in bcs}) != len(bcs):
        errors.append({"reason": "ambiguous_boundary_membership", "owner": ref(container)})
    return {"owner": ref(container), "bcs": bcs, "unfoldered_bcs": plain, "folders": folders}


def capture_step_membership(sim, step):
    """Direct step membership only; global conditions/inheritance are not inferred."""
    errors = []
    try:
        result = _container_membership(sim, step, errors)
    except Exception as error:
        result = {}
        errors.append(
            {"reason": "membership_read_failed", "nx_code": getattr(error, "ErrorCode", None)}
        )
    return {
        **result,
        "errors": errors,
        "comparison_verified": not errors,
        "scope": "direct_step_membership; excludes solution-level conditions and inferred inheritance",
    }


def capture_effective_membership(sim, solution=None):
    """Inspect direct solution/step membership; reject unhandled folder/override semantics."""
    errors = []

    def members(container):
        return _container_membership(sim, container, errors)

    result = {"solution": None, "steps": [], "errors": errors}
    try:
        solution = sim.Simulation.ActiveSolution if solution is None else solution
        if solution is None:
            raise ValueError("No selected solution")
        result["solution"] = members(solution)
        count = solution.ConflictBcOverrideCount
        result["solution"]["conflict_override_count"] = count
        if count:
            errors.append({"reason": "unsupported_conflict_overrides"})
        if not 0 <= solution.StepCount <= 1000:
            raise ValueError("Step count exceeds supported inventory limit")
        for index in range(solution.StepCount):
            result["steps"].append({"index": index, **members(solution.GetStepByIndex(index))})
    except Exception as error:
        errors.append(
            {"reason": "membership_read_failed", "nx_code": getattr(error, "ErrorCode", None)}
        )
    result["comparison_verified"] = not errors
    result["sha256"] = (
        state_hash({"solution": result["solution"], "steps": result["steps"]})
        if not errors
        else None
    )
    return result


def capture_boundary_state(sim, nx):
    from nx_mcp.simcenter.properties import read_properties

    membership = capture_effective_membership(sim)
    rows, errors, unsupported = [], list(membership["errors"]), []
    collections = [
        ("loads", sim.Simulation.Loads),
        ("constraints", sim.Simulation.Constraints),
    ]
    try:
        collections.append(("simulation_objects", sim.Simulation.SimulationObjects))
    except Exception:
        errors.append({"reason": "simulation_object_inventory_unavailable"})
    for category, collection in collections:
        for boundary in collection:
            row = {
                "category": category,
                "journal_id": boundary.JournalIdentifier,
                "descriptor": boundary.PropertyTable.DescriptorNeutralName,
                "properties": read_properties(boundary.PropertyTable, nx),
                "targets": [],
            }
            for prop in row["properties"]:
                if prop.get("inspection_status") == "read_failed":
                    errors.append(
                        {
                            "boundary": row["journal_id"],
                            "property": prop["name"],
                            "reason": "read_failed",
                        }
                    )
                elif prop.get("inspection_status"):
                    unsupported.append(
                        {
                            "boundary": row["journal_id"],
                            "property": prop["name"],
                            "reason": prop["inspection_status"],
                        }
                    )
                if prop.get("representation") == "expression":
                    try:
                        wrapper = boundary.PropertyTable.GetScalarFieldWrapperPropertyValue(
                            prop["name"]
                        )
                        expression = wrapper.GetExpression()
                        prop["evaluated_value"] = expression.GetValueUsingUnits(
                            nx.Expression.UnitsOption.Expression
                        )
                    except Exception:
                        errors.append(
                            {
                                "boundary": row["journal_id"],
                                "property": prop["name"],
                                "reason": "evaluation_failed",
                            }
                        )
            for index in range(boundary.TargetSetManager.TargetSetCount):
                _, members = boundary.TargetSetManager.GetTargetSetMembers(index)
                targets = []
                for member in members:
                    if member is None or member.Obj is None:
                        targets.append(None)
                    else:
                        obj = member.Obj
                        targets.append(
                            {
                                "journal_id": obj.JournalIdentifier,
                                "owner_path": obj.OwningPart.FullPath,
                                "type": type(obj).__name__,
                                "subtype": str(member.SubType),
                                "sub_id": member.SubId,
                            }
                        )
                row["targets"].append({"index": index, "members": targets})
            rows.append(row)
    inspected = {row["journal_id"] for row in rows}
    containers = ([membership["solution"]] if membership["solution"] else []) + membership["steps"]
    for container in containers:
        for member in container["bcs"]:
            if member["journal_id"] not in inspected:
                errors.append(
                    {"reason": "uninspected_effective_boundary", "boundary": member["journal_id"]}
                )
    rows.sort(key=lambda row: (row["category"], row["journal_id"]))
    return {
        "owner_path": sim.FullPath,
        "boundaries": rows,
        "effective_membership": membership,
        "errors": errors,
        "uninspected_properties": unsupported,
        "sha256": state_hash(
            {
                "inventory": stable_boundary_values(rows),
                "effective_membership": membership["sha256"],
            }
        )
        if not errors and not unsupported
        else None,
        "comparison_verified": not errors and not unsupported,
        "scope": "observed_boundary_values_and_selected_solution_ordered_step_membership_v4",
        "full_model_freshness": "not_verified",
    }
