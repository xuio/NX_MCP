"""Native SIM document copying; shared FEM/CAD dependencies remain explicit."""

from pathlib import Path

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_identity import fingerprint_file


def save_sim_as(session, workspace, sim, path):
    import NXOpen.CAE as cae

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError(
            "NX_SIM_DOCUMENT_NOT_ACTIVE",
            "Activate the selected SIM first",
            details={"mutation_outcome": "not_started"},
        )
    target = workspace.resolve(path)
    source = workspace.ensure_inside(Path(sim.FullPath))
    if target.suffix.lower() != ".sim" or target == source or target.exists():
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Choose a new .sim path; existing files are not overwritten",
            details={"mutation_outcome": "not_started"},
        )
    if any(
        Path(part.FullPath).name.casefold() == target.name.casefold()
        for part in session.Parts
        if part.FullPath
    ):
        raise NXToolError(
            "NX_SIM_NAME_CONFLICT",
            "A document with this basename is loaded; choose a unique filename",
            details={"mutation_outcome": "not_started"},
        )
    original = fingerprint_file(source, maximum_bytes=1_073_741_824)
    fem_path = sim.FemPart.FullPath
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        status = sim.SaveAs(str(target))
        try:
            if status.NumberUnsavedParts or status.NumberUnsavedObjects:
                raise ValueError("Native SaveAs reported unsaved parts or objects")
        finally:
            status.Dispose()
        after = fingerprint_file(source, maximum_bytes=1_073_741_824)
        if after["sha256"] != original["sha256"] or not target.is_file():
            raise ValueError("Source preservation or target creation check failed")
        if Path(sim.FullPath) != target or sim.FemPart.FullPath != fem_path:
            raise ValueError("Unexpected document identity or FEM association after SaveAs")
        return {
            "source": original,
            "path": str(target),
            "source_file_unchanged": True,
            "work_path": session.Parts.BaseWork.FullPath,
            "display_path": session.Parts.BaseDisplay.FullPath,
            "shared_fem_path": fem_path,
            "independent_geometry_variant": False,
            "saved": True,
            "result_freshness": "not_verified",
            "next_step": "Reacquire document IDs. Duplicate and reassociate FEM/CAD before changing shared geometry or mesh.",
        }
    except Exception as error:
        raise NXToolError(
            "NX_SIM_SAVE_AS_FAILED",
            "SIM SaveAs failed or readback differs; inspect retained target and current document state",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "partial",
                "target": str(target),
                "target_exists": target.exists(),
                "current_path": sim.FullPath,
            },
        ) from error


def save_document(session, workspace, document):
    """Save one existing FEM/SIM, retaining the previous disk revision."""
    import shutil
    import uuid

    import NXOpen as nx
    import NXOpen.CAE as cae

    if not isinstance(document, (cae.SimPart, cae.FemPart)):
        raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select an existing FEM or SIM document")
    path = workspace.resolve(document.FullPath)
    if not path.is_file() or not document.IsFullyLoaded:
        raise NXToolError(
            "NX_SIM_SAVE_PRECONDITION",
            "Document must be fully loaded with an existing workspace file",
        )
    before = fingerprint_file(path, maximum_bytes=1_073_741_824)
    other_flags = {p.Tag: bool(p.IsModified) for p in session.Parts if p != document}
    # Solver exports require a clean SIM directory. Keep our backups outside it.
    backup_dir = workspace.resolve(workspace.root / "simcenter-save-backups" / uuid.uuid4().hex)
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = workspace.ensure_inside(backup_dir / path.name)
    shutil.copy2(path, backup)
    if fingerprint_file(backup, maximum_bytes=1_073_741_824)["sha256"] != before["sha256"]:
        raise NXToolError(
            "NX_SIM_BACKUP_FAILED",
            "Backup verification failed; native save was not called",
            details={"mutation_outcome": "not_started"},
        )
    try:
        status = document.Save(
            nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
        )
        try:
            if status.NumberUnsavedParts or status.NumberUnsavedObjects:
                raise ValueError("Native save reported unsaved parts or objects")
        finally:
            status.Dispose()
        if document.IsModified or document.FullPath != str(path):
            raise ValueError("Document remains modified or its path changed after save")
        if {p.Tag: bool(p.IsModified) for p in session.Parts if p != document} != other_flags:
            raise ValueError("Other loaded document flags changed during save")
        after = fingerprint_file(path, maximum_bytes=1_073_741_824)
        return {
            "saved": True,
            "path": str(path),
            "file": after,
            "previous_file": before,
            "backup_path": str(backup),
            "saved_components": False,
            "closed": False,
            "other_modified_flags_unchanged": True,
            "result_freshness": "not_verified",
        }
    except Exception as error:
        raise NXToolError(
            "NX_SIM_SAVE_FAILED",
            "Save failed verification; inspect current document and retained backup before retrying",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "partial",
                "path": str(path),
                "backup_path": str(backup),
                "reason": str(error),
            },
        ) from error


def open_document(session, workspace, path):
    """Open/display a FEM or SIM without saving or closing unrelated documents."""
    import os

    import NXOpen as nx
    import NXOpen.CAE as cae

    target = workspace.resolve(path)
    if target.suffix.lower() not in (".sim", ".fem"):
        raise NXToolError(
            "NX_SIM_DOCUMENT_TYPE",
            "Open requires a workspace .sim or .fem path",
            details={"mutation_outcome": "not_started"},
        )
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    matches = [
        p
        for p in session.Parts
        if p.FullPath and os.path.normcase(p.FullPath) == os.path.normcase(str(target))
    ]
    if len(matches) > 1:
        raise NXToolError(
            "NX_SIM_DOCUMENT_AMBIGUOUS",
            "Multiple loaded documents match this path",
            details={"mutation_outcome": "not_started"},
        )
    loaded = bool(matches)
    part = matches[0] if loaded else None
    if part is None and not target.is_file():
        raise NXToolError(
            "NX_NOT_FOUND",
            "Simulation file does not exist in the workspace",
            details={"mutation_outcome": "not_started"},
        )
    if not loaded:
        conflicting = [
            p.FullPath
            for p in session.Parts
            if p.FullPath and Path(p.FullPath).stem.casefold() == target.stem.casefold()
        ]
        if conflicting:
            raise NXToolError(
                "NX_SIM_NAME_CONFLICT",
                "NX requires distinct loaded basenames, including across FEM/SIM extensions",
                details={
                    "mutation_outcome": "not_started",
                    "conflicting_loaded_paths": conflicting,
                    "next_step": "Use a distinct analysis basename or explicitly close the conflicting document after saving approved edits",
                },
            )
    issues = []
    try:
        if part is None:
            options = session.Parts.LoadOptions
            previous_load_method = options.ComponentLoadMethod
            status = None
            try:
                # SIM/FEM dependencies may live in sibling workspace folders.
                # Respect their saved paths without changing the user's preference.
                options.ComponentLoadMethod = type(options).LoadMethod.AsSaved
                try:
                    part, status = session.Parts.OpenBaseDisplay(str(target))
                finally:
                    options.ComponentLoadMethod = previous_load_method
                if options.ComponentLoadMethod != previous_load_method:
                    raise NXToolError(
                        "NX_SIM_LOAD_OPTIONS", "Could not restore native load options"
                    )
                if status:
                    for index in range(status.NumberUnloadedParts):
                        issues.append(
                            {"path": status.GetPartName(index), "nx_code": status.GetStatus(index)}
                        )
            finally:
                if status:
                    status.Dispose()
        if not isinstance(part, (cae.FemPart, cae.SimPart)):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Native file is not a FEM or SIM")
        modified_after_open = bool(part.IsModified)
        if issues or not part.IsFullyLoaded:
            raise NXToolError(
                "NX_SIM_LOAD_INCOMPLETE",
                "Native load is incomplete; inspect missing dependencies before proceeding",
                details={"load_issues": issues},
            )
        if session.Parts.BaseDisplay != part:
            _, status = session.Parts.SetDisplay(part, False, False)
            if status:
                try:
                    for index in range(status.NumberUnloadedParts):
                        issues.append(
                            {"path": status.GetPartName(index), "nx_code": status.GetStatus(index)}
                        )
                finally:
                    status.Dispose()
            if issues or not part.IsFullyLoaded:
                raise NXToolError(
                    "NX_SIM_LOAD_INCOMPLETE",
                    "Display activation did not fully load the selected document",
                )
        session.Parts.SetWork(part)
        if session.ApplicationName != "UG_APP_SFEM":
            session.ApplicationSwitchImmediate("UG_APP_SFEM")
        if (
            session.Parts.BaseWork != part
            or session.Parts.BaseDisplay != part
            or session.ApplicationName != "UG_APP_SFEM"
        ):
            raise NXToolError(
                "NX_SIM_ACTIVATION_MISMATCH", "Requested simulation document did not activate"
            )
        changed = [
            p.FullPath
            for p in session.Parts
            if p.FullPath in before and bool(p.IsModified) != before[p.FullPath]
        ]
        part_units = getattr(part, "PartUnits", None)
        units = (
            None
            if part_units is None
            else "mm"
            if part_units == nx.BasePart.Units.Millimeters
            else "inch"
            if part_units == nx.BasePart.Units.Inches
            else None
        )
        return {
            "units": units,
            "coordinate_frame": "part_absolute",
            "part": part,
            "path": str(target),
            "already_loaded": loaded,
            "modified_after_native_open": None if loaded else modified_after_open,
            "modified_before_activation": modified_after_open,
            "modified": bool(part.IsModified),
            "fully_loaded": bool(part.IsFullyLoaded),
            "load_issues": issues,
            "changed_existing_part_flags": changed,
            "application": session.ApplicationName,
            "work_path": session.Parts.BaseWork.FullPath,
            "display_path": session.Parts.BaseDisplay.FullPath,
            "saved": False,
            "result_freshness": "not_verified",
            "warnings": [
                "Document has unsaved native state; inspect and explicitly save approved analysis changes before preparing a solve"
            ]
            if part.IsModified
            else [],
        }
    except Exception as error:
        raise NXToolError(
            getattr(error, "code", "NX_SIM_OPEN_FAILED"),
            "Simulation open/activation failed; inspect current documents before retrying",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": "partial",
                "requested_path": str(target),
                "document_loaded": part is not None,
                "already_loaded": loaded,
                "load_issues": issues,
                "next_step": "Inspect nx_sim_documents; no documents were saved or automatically closed",
            },
        ) from error
