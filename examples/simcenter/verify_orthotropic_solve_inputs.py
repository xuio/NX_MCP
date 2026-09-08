"""Verify geometric sink coverage and load exact cloned CAD before solve preparation."""


def run(executor):
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.boundary_geometry import inspect_rectangular_patch
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    assert sim.FullPath.endswith("orthotropic_export_r1.sim")
    deps = inspect_direct(session, sim, executor.workspace)
    for row in deps["unresolved"]:
        expected = executor.workspace.resolve(
            "ui-benchmarks/orthotropic-conduction-20260908-r1/OrthotropicR1_cad_01.prt"
        )
        assert (
            row["association"] == "AssociatedCadPart"
            and executor.workspace.resolve(row["path"]) == expected
        )
        cad, status = session.Parts.OpenBase(str(expected))
        try:
            assert status is None or status.NumberUnloadedParts == 0
        finally:
            if status:
                status.Dispose()
    assert not inspect_direct(session, sim, executor.workspace)["unresolved"]
    root = ET.parse(
        executor.workspace.resolve(
            "ui-benchmarks/orthotropic-export-20260908-r1/orthotropic_export_r1-Conduction.xml"
        )
    ).getroot()
    mapping = sim.FemPart.BaseFEModel.FeelementLabelMap
    patches = []
    try:
        for fa in root.findall("./Constraints/TemperatureList/Temperature/Selection/fa"):
            label, face = map(int, fa.text.split())
            element = mapping.GetElement(label)
            nodes = element.GetCornerNodesOnFace(face - 1)
            patches.append(
                [
                    {"label": n.Label, "xyz": [n.Coordinates.X, n.Coordinates.Y, n.Coordinates.Z]}
                    for n in nodes
                ]
            )
    finally:
        mapping.Dispose()
    plane = patches[0][0]["xyz"][0]
    assert abs(plane) < 1e-7 or abs(plane - 100) < 1e-7
    coverage = inspect_rectangular_patch(
        patches, plane_x_mm=plane, minimum_yz_mm=[0, 0], maximum_yz_mm=[10, 10]
    )
    return {
        "sink_plane_x_mm": plane,
        "coverage": coverage,
        "dependencies_loaded": True,
        "solver_launched": False,
    }
