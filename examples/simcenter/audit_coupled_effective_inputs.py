"""Audit scale, BC membership and resistance applicability on the retained diagnostic."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if not any(
        folder in sim.FullPath
        for folder in (
            "E-external-diagnostic-20260908-r1",
            "E-external-reopen-20260908-r1",
            "E-finned-layer-extended-20260908-r1",
        )
    ):
        raise ValueError("Activate the isolated completed external diagnostic")
    solution = sim.Simulation.ActiveSolution

    def ref(obj):
        return {
            "journal_id": obj.JournalIdentifier,
            "name": obj.Name,
            "owner": obj.OwningPart.FullPath,
        }

    def fields(table):
        rows = []
        for i in range(table.GetPropertyCount()):
            name = table.GetPropertyNameByIndex(i)
            if (
                table.GetBasePropertyType(name)
                != nx.BasePropertyTable.BasePropertyType.ScalarFieldWrapper
            ):
                continue
            wrapper = table.GetScalarFieldWrapperPropertyValue(name)
            if wrapper is None:
                rows.append({"property": name, "representation": "unset"})
                continue
            expression, field = wrapper.GetExpression(), wrapper.GetField()
            row = {"property": name, "expression": None, "field": None}
            if expression is not None:
                row["expression"] = {
                    "formula": expression.GetFormula(),
                    "units": expression.Units.Name if expression.Units else None,
                    "value": expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression),
                }
            if field is not None:
                row["field"] = ref(field)
                row["scale"] = wrapper.GetFieldScaleFactor()
            row["representation"] = (
                "expression"
                if expression is not None
                else "field"
                if field is not None
                else "unset"
            )
            rows.append(row)
        return rows

    def membership(container):
        row = {
            "owner": ref(container),
            "bcs": [ref(b) for b in container.GetBcs()],
            "unfoldered_bcs": [ref(b) for b in container.GetUnfolderedBcs()],
            "folders": [ref(f) for f in container.GetFolders()],
        }
        return row

    data = {
        "solution": membership(solution),
        "steps": [],
        "document_boundaries": [],
        "solution_fields": fields(solution.PropertyTable),
        "ambient_pressure_mode": solution.PropertyTable.GetIntegerPropertyValue("Ambient Pressure"),
        "tables": [],
        "solver_launched": False,
        "numerical_acceptance": False,
    }
    data["solution"]["conflict_override_count"] = solution.ConflictBcOverrideCount
    for i in range(solution.StepCount):
        data["steps"].append({"index": i, **membership(solution.GetStepByIndex(i))})
    for kind, objects in [
        ("loads", sim.Simulation.Loads),
        ("constraints", sim.Simulation.Constraints),
        ("simulation_objects", sim.Simulation.SimulationObjects),
    ]:
        for obj in objects:
            row = {"kind": kind, **ref(obj), "fields": fields(obj.PropertyTable)}
            if kind == "simulation_objects":
                row["descriptor"] = obj.DescriptorName
                if obj.DescriptorName in ("Inlet", "Opening"):
                    table = obj.PropertyTable.GetNamedPropertyTablePropertyValue("Inlet Conditions")
                    row["external_conditions"] = ref(table) if table else None
            data["document_boundaries"].append(row)
    for table in sim.ModelingObjectPropertyTables:
        row = {
            "name": table.Name,
            "descriptor": table.DescriptorType,
            "fields": fields(table.PropertyTable),
        }
        if table.DescriptorType == "Head Loss":
            row["selectors"] = {
                key: table.PropertyTable.GetIntegerPropertyValue(key)
                for key in ("Type", "Proportional to")
            }
        if table.DescriptorType == "External Conditions":
            row["reference"] = ref(table)
            row["temperature_option"] = table.PropertyTable.GetIntegerPropertyValue(
                "Temperature Option"
            )
        data["tables"].append(row)
    return data


def validate_finned_snapshot(data):
    """Reject audit gaps for this exact fixture, not certify general state freshness."""
    import math

    expected = {"Generic solid 0.1 W", "Coupled Inlet", "Coupled Opening"}
    solution = data["solution"]
    owner = solution["owner"]["owner"]
    members = solution["bcs"]
    if len(members) != 3 or {b["name"] for b in members} != expected:
        raise ValueError("Unexpected selected-solution membership")
    if any(b["owner"] != owner for b in members):
        raise ValueError("Boundary owner differs")
    if solution["folders"] or solution["conflict_override_count"]:
        raise ValueError("Folder/override semantics require separate verification")
    if solution["unfoldered_bcs"] != members:
        raise ValueError("Unfoldered membership differs")
    steps = data["steps"]
    if len(steps) != 1 or steps[0]["index"] != 0:
        raise ValueError("Unexpected step sequence")
    if steps[0]["owner"]["owner"] != owner:
        raise ValueError("Step owner differs")
    if steps[0]["bcs"] or steps[0]["unfoldered_bcs"] or steps[0]["folders"]:
        raise ValueError("Unexpected step membership")
    boundaries = data["document_boundaries"]
    if len(boundaries) != 3 or {(b["journal_id"], b["owner"]) for b in boundaries} != {
        (b["journal_id"], b["owner"]) for b in members
    }:
        raise ValueError("Document inventory and effective membership differ")
    if any(t["descriptor"] == "Head Loss" for t in data["tables"]):
        raise ValueError("Head-loss selectors require separate verification")
    if data["ambient_pressure_mode"] != 1:
        raise ValueError("Altitude-derived pressure expected")

    def constant(rows, name, value, unit):
        found = [r for r in rows if r["property"] == name]
        if len(found) != 1:
            raise ValueError("Missing or duplicate constant " + name)
        row = found[0]
        if row["representation"] != "expression" or row.get("field") is not None:
            raise ValueError("Field definition/scale requires separate verification: " + name)
        expr = row["expression"]
        if (
            expr["units"] != unit
            or not math.isfinite(expr["value"])
            or abs(expr["value"] - value) > 1e-9
        ):
            raise ValueError("Constant value or units differ: " + name)

    constant(data["solution_fields"], "Fluid Temperature", 0.0, "Celsius")
    heat = next(b for b in boundaries if b["name"] == "Generic solid 0.1 W")
    constant(heat["fields"], "Heat Load", 0.1, "HeatFlow_Metric2")
    tables = [t for t in data["tables"] if t["descriptor"] == "External Conditions"]
    if len(tables) != 1 or tables[0]["temperature_option"] != 0:
        raise ValueError("Explicit external temperature expected")
    constant(tables[0]["fields"], "Temperature Value", 20.0, "Celsius")
    for boundary in boundaries:
        if (
            boundary["name"] != "Generic solid 0.1 W"
            and boundary.get("external_conditions") != tables[0]["reference"]
        ):
            raise ValueError("External conditions binding differs")
        for row in boundary["fields"]:
            if row.get("field") is not None:
                raise ValueError("Boundary field definition/scale requires separate verification")
    return {
        "fixture_effective_inputs": "verified_snapshot",
        "F1": "active heat and boundary temperatures are expression-backed; no boundary fields",
        "F2": "exact solution membership and empty single step verified",
        "F3": "no head-loss tables; inapplicable to this fixture",
        "general_freshness": "not_verified",
        "physical_acceptance": False,
    }
