"""Native result retention across SIM-local postview IDs; leaves pressure visible."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import postviews

    importlib.reload(postviews)
    session = executor.session
    pressure = session.Parts.BaseWork
    if not pressure.FullPath.endswith(r"F-input-export-20260908-r2\flow_input_r2.sim"):
        raise ValueError("Activate isolated pressure SIM")
    thermal = next(
        p
        for p in session.Parts
        if p.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim")
    )
    handles = executor._sim_post_result_handles
    before = dict(handles)
    try:
        _, status = session.Parts.SetDisplay(thermal, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(thermal)
        temperature = postviews.show_temperature(
            session, thermal, handles, name="MCP retained thermal contour"
        )
    finally:
        _, status = session.Parts.SetDisplay(pressure, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(pressure)
    pressure_view = postviews.show_pressure(
        session, pressure, handles, name="MCP retained pressure contour"
    )
    assert len(handles) == len(before) + 2
    assert all(handles[key] is value for key, value in before.items())
    assert pressure_view["postview_owner"] != temperature["postview_owner"]
    return {
        "temperature": temperature,
        "pressure": pressure_view,
        "retained_count_before": len(before),
        "retained_count_after": len(handles),
        "previous_handles_preserved": True,
        "pressure_left_visible": True,
    }
