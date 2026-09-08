from types import SimpleNamespace as NS

from nx_mcp.simcenter.boundary_state import capture_boundary_state


def attach_solution(sim, bcs):
    if not hasattr(sim.Simulation, "SimulationObjects"):
        sim.Simulation.SimulationObjects = []
    solution = NS(
        JournalIdentifier="Solution[1]",
        OwningPart=sim,
        ConflictBcOverrideCount=0,
        StepCount=0,
        GetBcs=lambda: bcs,
        GetUnfolderedBcs=lambda: bcs,
        GetFolders=lambda: [],
    )
    for bc in bcs:
        bc.OwningPart = sim
    sim.Simulation.ActiveSolution = solution
    return solution


def test_evaluated_expression_change_invalidates_hash(monkeypatch):
    import nx_mcp.simcenter.boundary_state as module

    state = {"value": 1}
    expression = NS(GetValueUsingUnits=lambda units: state["value"])
    table = NS(
        DescriptorNeutralName="Heat Load",
        GetScalarFieldWrapperPropertyValue=lambda name: NS(GetExpression=lambda: expression),
    )
    load = NS(
        JournalIdentifier="Load[power]", PropertyTable=table, TargetSetManager=NS(TargetSetCount=0)
    )
    sim = NS(FullPath="test.sim", Simulation=NS(Loads=[load], Constraints=[]))
    attach_solution(sim, [load])
    nx = NS(Expression=NS(UnitsOption=NS(Expression=1)))
    monkeypatch.setattr(
        module,
        "read_properties",
        lambda *args: [
            {"name": "Heat Load", "representation": "expression", "expression": "power_parameter"}
        ],
    )
    first = capture_boundary_state(sim, nx)
    state["value"] = 2
    second = capture_boundary_state(sim, nx)
    assert first["sha256"] != second["sha256"]
    assert first["full_model_freshness"] == "not_verified"


def test_read_failure_never_returns_verified_hash(monkeypatch):
    import nx_mcp.simcenter.boundary_state as module

    monkeypatch.setattr(
        module,
        "read_properties",
        lambda *args: [{"name": "Temperature", "inspection_status": "read_failed"}],
    )
    load = NS(
        JournalIdentifier="BC",
        PropertyTable=NS(DescriptorNeutralName="Temperature"),
        TargetSetManager=NS(TargetSetCount=0),
    )
    result = capture_boundary_state(
        NS(FullPath="test.sim", Simulation=NS(Loads=[], Constraints=[load])), None
    )
    assert result["sha256"] is None and result["errors"]


def field_fixture():
    state = {"scale": 1.0, "formula": "10", "tag": 7}
    field = NS(
        FieldExpressionUnits=NS(Name="Watt"),
        JournalIdentifier="Field[heat]",
        OwningPart=NS(FullPath="a.sim"),
        Tag=7,
        GetFieldExpressionString=lambda: state["formula"],
    )
    wrapper = NS(
        GetExpression=lambda: None,
        GetField=lambda: field,
        GetFieldScaleFactor=lambda: state["scale"],
    )
    table = NS(
        DescriptorNeutralName="Heat Load",
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda i: "Heat Load",
        GetBasePropertyType=lambda k: 6,
        GetScalarFieldWrapperPropertyValue=lambda k: wrapper,
    )
    load = NS(
        JournalIdentifier="Heat[1]", PropertyTable=table, TargetSetManager=NS(TargetSetCount=0)
    )
    sim = NS(FullPath="a.sim", Simulation=NS(Loads=[load], Constraints=[]))
    nx = NS(
        BasePropertyTable=NS(
            BasePropertyType=NS(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
        )
    )
    attach_solution(sim, [load])
    return state, field, sim, nx


def test_scale_only_change_changes_effective_value_and_hash():
    state, _, sim, nx = field_fixture()
    first = capture_boundary_state(sim, nx)
    state["scale"] = 2.0
    second = capture_boundary_state(sim, nx)
    assert first["sha256"] and second["sha256"] != first["sha256"]
    assert second["boundaries"][0]["properties"][0]["evaluated_value"] == 20


def test_replacing_field_changes_hash_even_with_same_value():
    _, field, sim, nx = field_fixture()
    before = capture_boundary_state(sim, nx)
    field.Tag = 8
    field.JournalIdentifier = "Field[replacement]"
    assert capture_boundary_state(sim, nx)["sha256"] != before["sha256"]


def test_uninspected_expression_or_table_never_satisfies_comparison(monkeypatch):
    monkeypatch.setattr(
        "nx_mcp.simcenter.field_definition.read_supported_table", lambda field: None
    )
    state, field, sim, nx = field_fixture()
    state["formula"] = "power_parameter * time"
    result = capture_boundary_state(sim, nx)
    assert result["sha256"] is None and not result["comparison_verified"]
    del field.GetFieldExpressionString
    result = capture_boundary_state(sim, nx)
    assert result["sha256"] is None
    assert result["uninspected_properties"][0]["reason"] == "unsupported_field_type"
    # Opaque changes to such a table remain unverifiable, never an equal valid hash.
    field.table_data = [10, 20, 30]
    assert capture_boundary_state(sim, nx)["sha256"] is None


def test_membership_change_without_document_deletion_changes_hash():
    _, _, sim, nx = field_fixture()
    before = capture_boundary_state(sim, nx)
    sim.Simulation.ActiveSolution.GetBcs = lambda: []
    sim.Simulation.ActiveSolution.GetUnfolderedBcs = lambda: []
    after = capture_boundary_state(sim, nx)
    assert before["boundaries"] == after["boundaries"]
    assert before["sha256"] and after["sha256"] and before["sha256"] != after["sha256"]


def test_selected_solution_and_step_order_are_part_of_fingerprint():
    _, _, sim, nx = field_fixture()
    solution = sim.Simulation.ActiveSolution
    before = capture_boundary_state(sim, nx)
    solution.JournalIdentifier = "Solution[2]"
    assert capture_boundary_state(sim, nx)["sha256"] != before["sha256"]
    steps = [
        NS(
            JournalIdentifier=f"Step[{i}]",
            OwningPart=sim,
            GetBcs=lambda: [],
            GetUnfolderedBcs=lambda: [],
            GetFolders=lambda: [],
        )
        for i in range(2)
    ]
    solution.StepCount = 2
    solution.GetStepByIndex = lambda i: steps[i]
    before = capture_boundary_state(sim, nx)
    steps.reverse()
    assert capture_boundary_state(sim, nx)["sha256"] != before["sha256"]


def test_unhandled_override_or_folder_prevents_verified_comparison():
    _, _, sim, nx = field_fixture()
    solution = sim.Simulation.ActiveSolution
    solution.ConflictBcOverrideCount = 1
    assert capture_boundary_state(sim, nx)["sha256"] is None
    solution.ConflictBcOverrideCount = 0
    solution.GetFolders = lambda: [NS(JournalIdentifier="Folder[1]", OwningPart=sim)]
    assert capture_boundary_state(sim, nx)["sha256"] is None


def test_moving_condition_between_steps_changes_hash():
    _, _, sim, nx = field_fixture()
    load = sim.Simulation.Loads[0]
    lists = [[load], []]
    solution = sim.Simulation.ActiveSolution
    steps = [
        NS(
            JournalIdentifier=f"Step[{i}]",
            OwningPart=sim,
            GetBcs=lambda i=i: lists[i],
            GetUnfolderedBcs=lambda i=i: lists[i],
            GetFolders=lambda: [],
        )
        for i in range(2)
    ]
    solution.StepCount = 2
    solution.GetStepByIndex = lambda i: steps[i]
    before = capture_boundary_state(sim, nx)
    lists[:] = [[], [load]]
    after = capture_boundary_state(sim, nx)
    assert before["sha256"] and after["sha256"] and before["sha256"] != after["sha256"]
    assert before["boundaries"] == after["boundaries"]


def test_member_without_property_inventory_cannot_be_verified():
    _, _, sim, nx = field_fixture()
    uninspected = NS(JournalIdentifier="Contact[1]", OwningPart=sim)
    solution = sim.Simulation.ActiveSolution
    solution.GetBcs = lambda: [uninspected]
    solution.GetUnfolderedBcs = lambda: [uninspected]
    result = capture_boundary_state(sim, nx)
    assert result["sha256"] is None
    assert result["errors"][0]["reason"] == "uninspected_effective_boundary"


def test_explicit_solution_inspection_does_not_use_or_change_active_solution():
    from nx_mcp.simcenter.boundary_state import capture_effective_membership

    _, _, sim, _ = field_fixture()
    active = sim.Simulation.ActiveSolution
    other = attach_solution(sim, [])
    other.JournalIdentifier = "Solution[other]"
    sim.Simulation.ActiveSolution = active
    result = capture_effective_membership(sim, other)
    assert result["comparison_verified"]
    assert result["solution"]["owner"]["journal_id"] == "Solution[other]"
    assert result["solution"]["bcs"] == []
    assert sim.Simulation.ActiveSolution is active


def test_field_unit_alias_preserves_native_symbol_and_scaled_value():
    _, field, sim, nx = field_fixture()
    field.FieldExpressionUnits = NS(Name="HeatFlow_Metric2", Symbol="W")
    result = capture_boundary_state(sim, nx)
    prop = result["boundaries"][0]["properties"][0]
    assert prop["units"] == "HeatFlow_Metric2"
    assert prop["unit_symbol"] == "W"
    assert prop["evaluated_value"] == 10.0


def test_effective_simulation_object_values_are_part_of_state():
    state, _, sim, nx = field_fixture()
    inlet = sim.Simulation.Loads.pop()
    inlet.JournalIdentifier = "SimulationObject[Inlet]"
    sim.Simulation.SimulationObjects = [inlet]
    attach_solution(sim, [inlet])
    before = capture_boundary_state(sim, nx)
    state["scale"] = 2
    after = capture_boundary_state(sim, nx)
    assert before["sha256"] and after["sha256"] != before["sha256"]
    assert after["boundaries"][0]["category"] == "simulation_objects"


def test_supported_table_definition_and_scale_each_invalidate_boundary_hash(monkeypatch):
    state, field, sim, nx = field_fixture()
    del field.GetFieldExpressionString
    pressure = [1.0, 0.0]
    monkeypatch.setattr(
        "nx_mcp.simcenter.field_definition.read_supported_table",
        lambda field: {
            "kind": "validated_fan_table",
            "native_samples_si": {"pressure_Pa": list(pressure)},
        },
    )
    first = capture_boundary_state(sim, nx)
    assert first["comparison_verified"] and first["sha256"]
    pressure[0] = 2.0
    changed_table = capture_boundary_state(sim, nx)
    assert first["sha256"] != changed_table["sha256"]
    state["scale"] = 3.0
    changed_scale = capture_boundary_state(sim, nx)
    assert changed_table["sha256"] != changed_scale["sha256"]


def test_field_runtime_tag_does_not_change_semantic_hash_but_identity_does():
    state, field, sim, nx = field_fixture()
    first = capture_boundary_state(sim, nx)
    field.Tag += 123
    reopened = capture_boundary_state(sim, nx)
    assert first["sha256"] == reopened["sha256"]
    assert first["boundaries"] != reopened["boundaries"]
    field.JournalIdentifier = "replacement field"
    assert capture_boundary_state(sim, nx)["sha256"] != reopened["sha256"]


def test_direct_step_membership_does_not_inherit_solution_conditions():
    from nx_mcp.simcenter.boundary_state import capture_step_membership

    _, _, sim, _ = field_fixture()
    step = NS(
        OwningPart=sim,
        JournalIdentifier="step",
        GetBcs=lambda: [],
        GetUnfolderedBcs=lambda: [],
        GetFolders=lambda: [],
    )
    direct = capture_step_membership(sim, step)
    assert direct["comparison_verified"] and direct["bcs"] == []
    assert "excludes solution-level" in direct["scope"]
    step.GetFolders = lambda: [NS(OwningPart=sim, JournalIdentifier="folder")]
    assert not capture_step_membership(sim, step)["comparison_verified"]
    step.OwningPart = object()
    assert not capture_step_membership(sim, step)["comparison_verified"]
