"""Read committed selector/coefficient state after public MCP tests; no solve."""


def run(executor):
    import json
    from pathlib import Path

    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "head-loss-public-context.json").read_text())
    public = json.loads((shared / "head-loss-selectors-public.json").read_text())
    assert public["passed"]
    rows = []
    for case in context["cases"]:
        boundary = executor.objects.resolve(case["opening"], expected_kind="simulation_object")
        table = boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
        props = table.PropertyTable
        coefficient, unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        selectors = [props.GetIntegerPropertyValue(k) for k in ("Type", "Proportional to")]
        assert coefficient == case["coefficient"] and selectors == case["selectors"]
        rows.append(
            {
                "path": case["path"],
                "coefficient": coefficient,
                "units": unit.Name if unit else "dimensionless",
                "selectors": selectors,
                "rejected_edits_preserved_or_success_restored": True,
            }
        )
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(flags.get(path) == value for path, value in context["original_flags"].items())
    original = next(
        p for p in executor.session.Parts if p.FullPath == context["original_work_path"]
    )
    _, status = executor.session.Parts.SetDisplay(original, False, False)
    if status:
        status.Dispose()
    executor.session.Parts.SetWork(original)
    assert executor.session.Parts.BaseWork == original
    result = {
        "passed": True,
        "rows": rows,
        "unrelated_modified_flags_preserved": True,
        "original_work_part_restored": True,
        "solver_launched": False,
        "scope": "Native/public MCP selectors, compare-and-set, replay and committed readback; no export/numerical acceptance",
    }
    (shared / "head-loss-public-readback.json").write_text(json.dumps(result, indent=2))
    return result
