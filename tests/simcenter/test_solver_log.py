from nx_mcp.simcenter.solver_log import inspect_solver_log


def test_observed_translator_failure_overrides_completed_footer():
    # Sanitized excerpt from conduction-solve-01 on native NX 2606.
    report = inspect_solver_log(
        "| NX2TMG - FATAL ERROR 1747 |\n"
        "| There are no steps in this Simcenter 3D Multiphysics solution. |\n"
        "Run aborted due to fatal errors.\nSolve completed at:\n"
    )
    assert report["state"] == "failed"
    assert report["stage"] == "translation"
    assert report["translator_fatal_codes"] == [1747]
    assert report["numerical_convergence"] == "not_established"
    assert report["results_validated"] is False


def test_footer_alone_does_not_prove_success():
    assert inspect_solver_log("Solve completed at: 22:41")["state"] == "unknown"
    assert inspect_solver_log("")["state"] == "unknown"


def test_unknown_fatal_abort_and_repeated_codes():
    assert inspect_solver_log("Run aborted due to fatal errors.")["state"] == "failed"
    assert inspect_solver_log("NX2TMG - FATAL ERROR 1747\nNX2TMG - FATAL ERROR 1747")[
        "translator_fatal_codes"
    ] == [1747]


def test_malformed_native_ambient_export_is_rejected():
    from nx_mcp.simcenter.solver_log import inspect_input_xml

    # Shape observed in exports 07 and 09; the opening Property tag is missing.
    report = inspect_input_xml(
        b'<SolutionFile><AmbientConditions> interpolation="Unknown" persistent="0">'
        b"</Property></AmbientConditions></SolutionFile>"
    )
    assert report["state"] == "invalid"
    assert report["reason"] == "malformed_xml"


def test_well_formed_deck_is_not_numerical_readiness():
    from nx_mcp.simcenter.solver_log import inspect_input_xml

    report = inspect_input_xml(
        b"<SolutionFile><SolutionStepList><SolutionStep/></SolutionStepList></SolutionFile>"
    )
    assert report["state"] == "well_formed"
    assert report["step_definitions"] == 1
    assert report["solve_readiness"] == "not_established"
    assert inspect_input_xml(b"<arbitrary/>")["state"] == "invalid"
    assert inspect_input_xml(b"<!DOCTYPE foo><SolutionFile/>")["state"] == "invalid"


def test_mesh_counts_include_elements_inside_every_set():
    from nx_mcp.simcenter.solver_log import inspect_input_xml

    report = inspect_input_xml(
        b"<SolutionFile><ElementList><Set><E>1 1 2 3 4</E><E>2 2 3 4 5</E></Set><Set><E>3 3 4 5 6</E></Set></ElementList><NodeList><N>1 0 0 0</N><N>2 1 0 0</N></NodeList></SolutionFile>"
    )
    assert report["mesh_counts"]["elements"] == 3
    assert report["mesh_counts"]["element_sets"] == 2
    assert report["mesh_counts"]["nodes"] == 2
    assert inspect_input_xml(b"<SolutionFile/>")["mesh_counts"] is None
