"""NX 2606 scalar postviews with explicit ownership and readback."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.results import acquire_result


def retain_result(handles, sim, view, result):
    """NX reuses postview IDs across parts; retain every owned result separately."""
    import uuid

    handles[(int(sim.Tag), view, uuid.uuid4().hex)] = result


def present_result(session, sim):
    """Frame the committed view; presentation failures must not undo result creation."""
    presentation = {
        "information_window_closed": False,
        "view_fitted": False,
        "display_refreshed": False,
        "warnings": [],
    }
    for key, action in (
        ("information_window_closed", lambda: session.ListingWindow.CloseWindow()),
        ("view_fitted", lambda: sim.ModelingViews.WorkView.Fit()),
        ("display_refreshed", lambda: sim.ModelingViews.WorkView.UpdateDisplay()),
    ):
        try:
            action()
            presentation[key] = True
        except Exception as exc:
            presentation["warnings"].append(f"Result presentation ({key}): {exc}")
    return presentation


def show_temperature(
    session, sim, handles, *, loadcase_index=0, iteration_index=0, name="MCP temperature"
):
    return show_scalar(
        session,
        sim,
        handles,
        field_name="Temperature - Nodal",
        native_unit="Celsius",
        units="degC",
        loadcase_index=loadcase_index,
        iteration_index=iteration_index,
        name=name,
    )


def show_pressure(
    session,
    sim,
    handles,
    *,
    field="pressure",
    loadcase_index=0,
    iteration_index=0,
    name="MCP pressure",
):
    fields = {
        "pressure": "Pressure - Element-Nodal",
        "total_pressure": "Total Pressure - Element-Nodal",
    }
    if field not in fields:
        raise NXToolError("NX_INVALID_ARGUMENT", "field must be pressure or total_pressure")
    return show_scalar(
        session,
        sim,
        handles,
        field_name=fields[field],
        native_unit="PressurePascals",
        units="Pa",
        loadcase_index=loadcase_index,
        iteration_index=iteration_index,
        name=name,
    )


def show_scalar(
    session, sim, handles, *, field_name, native_unit, units, loadcase_index, iteration_index, name
):
    if any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index)):
        raise NXToolError("NX_INVALID_ARGUMENT", "Result indices must be nonnegative integers")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide a view name of 1..100 characters")
    if session.IsBatch or session.Parts.BaseWork != sim or session.Parts.BaseDisplay != sim:
        raise NXToolError(
            "NX_SIM_DOCUMENT_NOT_ACTIVE",
            "Display and activate the SIM in the interactive session first",
        )
    import NXOpen.CAE as cae

    post, manager = session.Post, session.ResultManager
    existing = set(post.GetPostviewIds())
    previous_main = post.GetMainPostviewIdInActivePart()
    result, owned = acquire_result(session, sim)
    params = view = None
    try:
        cases = result.GetLoadcases()
        if loadcase_index >= len(cases):
            raise ValueError("Loadcase index outside result")
        iterations = cases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise ValueError("Iteration index outside result")
        fields = [f for f in iterations[iteration_index].GetResultTypes() if f.Name == field_name]
        if len(fields) != 1:
            raise ValueError("Expected exactly one requested scalar field")
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(loadcase_index, iteration_index)
        params.SetGenericResultType(fields[0])
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject(native_unit))
        view = post.CreatePostviewForResult(0, result, bool(existing), params)
        if view in existing:
            raise ValueError("Native API did not return a new view")
        # NX 2606 rejects periods and colons even in short names (3960043).
        # Retain the request and report the transformation rather than hiding it.
        applied_name = name.replace(".", "_").replace(":", "_")
        post.PostviewRename(view, applied_name)
        post.PostviewUpdate(view)
        post.SetMainPostviewIdInActivePart(view)
        _, actual = post.GetResultForPostview(view)
        try:
            readback = {
                "loadcase_index": actual.GetLoadcase(),
                "iteration_index": actual.GetIteration(),
                "field": actual.GetGenericResultType().Name,
                "unit": actual.GetUnit().Name,
            }
        finally:
            manager.DeleteResultParameters(actual)
        if readback != {
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "field": field_name,
            "unit": native_unit,
        }:
            raise ValueError("Displayed result readback differs")
        if (
            not existing <= set(post.GetPostviewIds())
            or post.GetMainPostviewIdInActivePart() != view
        ):
            raise ValueError("Postview state differs after display")
        # Keep result alive for the visible view; never overwrite older retained handles.
        retain_result(handles, sim, view, result)
        presentation = present_result(session, sim)
        if applied_name != name:
            presentation["warnings"].append(
                "NX rejected-character compatibility: periods/colons in the view name were replaced with underscores"
            )
        return {
            "requested_name": name,
            "applied_name": applied_name,
            "name_normalized": applied_name != name,
            "postview_id": view,
            "postview_owner": sim.FullPath,
            "readback": readback,
            "units": units,
            "existing_view_ids": sorted(existing),
            "overlay": bool(existing),
            "main_postview_id": view,
            "saved": False,
            "presentation": presentation,
            "warnings": presentation["warnings"],
            "result_freshness": "not_verified",
            "reference_lifetime": "postview ID is document-local within this session; use postview_owner and reacquire after closure",
        }
    except Exception as error:
        issues = []
        if view is not None and view not in existing:
            try:
                post.PostviewDelete(view)
            except Exception:
                retain_result(handles, sim, view, result)
                issues.append("new_view_cleanup_failed")
        if previous_main in existing:
            try:
                post.SetMainPostviewIdInActivePart(previous_main)
            except Exception:
                issues.append("main_view_restore_failed")
        if owned and not issues:
            manager.DeleteResult(result)
        raise NXToolError(
            "NX_SIM_POSTVIEW_FAILED",
            "Scalar view failed; inspect current views",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "reason": str(error),
                "cleanup_issues": issues,
                "mutation_outcome": "partial" if issues else "rolled_back",
            },
        ) from error
    finally:
        if params is not None:
            manager.DeleteResultParameters(params)
