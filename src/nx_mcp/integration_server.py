"""Uniform MCP envelopes and workspace-scoped artifacts for the NX 2606 bridge."""

from __future__ import annotations
import base64
import hashlib
import inspect
import json
import os
import uuid
from typing import Any, Literal
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from nx_mcp.runtime import NXToolError
from nx_mcp.workspace import WorkspaceViolation
from nx_mcp.recovery import OperationStore


# Signature-only definitions are used to publish the actual bridge arguments.
def nx_create_sketch(
    plane: Literal["XY", "XZ", "YZ"] = "XY",
    name: str | None = None,
    origin: list[float] | None = None,
    x_axis: list[float] | None = None,
    y_axis: list[float] | None = None,
):
    pass


def nx_open_part(path: str, work: bool = True, display: bool = True):
    pass


def nx_activate_part(part: str, work: bool = True, display: bool = True):
    pass


def nx_close_part(save: bool = True, part: str | None = None):
    pass


def nx_sketch_info(sketch_id: str):
    pass


def nx_sketch_arc(
    cx: float,
    cy: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    sketch_id: str | None = None,
):
    pass


def nx_edit_feature(name: str, params: dict[str, float]):
    pass


def nx_pattern(
    features: list[str],
    pattern_type: Literal["linear"] = "linear",
    direction: Literal["X", "Y", "Z", "-X", "-Y", "-Z"] = "X",
    spacing: float = 10,
    count: int = 2,
):
    pass


def nx_import_geometry(
    path: str,
    flatten: bool = False,
    target: Literal["work_part", "new_part"] = "work_part",
    output_path: str | None = None,
):
    pass


def nx_get_bounding_box(
    body: str | None = None,
    scope: Literal["auto", "part", "assembly"] = "auto",
    precision: Literal["conservative", "exact"] = "conservative",
):
    pass


def nx_checkpoint(label: str = "checkpoint"):
    pass


def nx_checkpoint_state():
    pass


def nx_rollback(checkpoint_id: str):
    pass


def nx_operation_status(operation_id: str):
    pass


def nx_cancel_operation(operation_id: str):
    pass


def nx_list_topology(body: str):
    pass


def nx_measure_volume(body: str | None = None, scope: Literal["auto", "part", "assembly"] = "auto"):
    pass


def nx_package_assembly(path: str):
    pass


def nx_add_component(
    part_path: str,
    name: str | None = None,
    translation: list[float] | None = None,
    rotation_matrix: list[list[float]] | None = None,
):
    pass


def nx_set_component_transform(
    component: str, translation: list[float], rotation_matrix: list[list[float]]
):
    pass


def nx_batch(operations: list[dict[str, Any]]):
    pass


def nx_capabilities():
    pass


def nx_rename_object(object_id: str, name: str):
    pass


def nx_revolve(
    angle: float = 360,
    axis: Literal["X", "Y", "Z", "-X", "-Y", "-Z"] = "Z",
    sketch_name: str | None = None,
    boolean: Literal["none", "unite", "subtract", "intersect"] = "none",
):
    pass


def nx_workspace_list(path: str = "."):
    pass


def nx_download_file(path: str, offset: int = 0, length: int = 262144):
    pass


def nx_upload_file(path: str, data_base64: str, sha256: str, total_size: int, offset: int = 0):
    pass


DESCRIPTIONS = {
    "nx_create_sketch": "Create an active sketch with explicit part-space origin and orthonormal basis. XY: X,Y,+Z; XZ: X,Z,-Y; YZ: Y,Z,+X. Curve coordinates use the returned local basis. Lengths in work-part units.",
    "nx_sketch_info": "Read the actual sketch origin, basis, normal and owned curve coordinates in part space. IDs preferred.",
    "nx_sketch_arc": "Add an arc to the active owning sketch using local coordinates; radius in work-part units and angles in degrees. Full circle: start=0,end=360. Pass sketch_id explicitly.",
    "nx_edit_feature": "Edit native EXTRUDE distance or linear PATTERN_FEATURE count/spacing. Unsupported parameters fail and roll back. IDs or unique case-insensitive names/journal IDs accepted.",
    "nx_pattern": "Create an associative native linear feature pattern. Count includes seed; 16 instances at pitch 16.5 of a 14-wide seed span 261.5. Work-part units.",
    "nx_import_geometry": "Import STEP through installed NX Step214Importer into the work part for solids, or target=new_part with a new output_path for assemblies; flatten=false preserves structure. Reports new directly-owned bodies and resulting components. Translator files are not undone.",
    "nx_get_bounding_box": "Native UF bounds; precision selects conservative or exact (exact requires axis-aligned WCS). auto includes recursive assembly geometry when present; part includes directly owned bodies; assembly includes both. Coordinates and units are work-part absolute.",
    "nx_activate_part": "Activate an already loaded part by ID or unique path/name without closing other parts. Display activation also changes work part under NX rules.",
    "nx_open_part": "Open or reuse a loaded workspace .prt and activate it; work/display flags are explicit. Does not recreate loaded parts.",
    "nx_close_part": "Close only the specified loaded part (ID), or current work part; preserves its component tree and unrelated parts. save defaults true.",
    "nx_checkpoint": "Create an in-session model undo checkpoint. NX v2606 saves expire native marks; create a new checkpoint after save. Restart/close also invalidates checkpoints.",
    "nx_checkpoint_state": "Inspect available checkpoint IDs and retained model-operation history. Read-only calls retain marks. Native NX save can expire them; availability is checked against NX.",
    "nx_rollback": "Rollback to an in-session checkpoint. Rejects rollback across mutations to unrelated parts. Reacquire object IDs afterward; save explicitly to persist.",
    "nx_operation_status": "Read durable request state without waiting on the NX thread: running, committed, failed, unknown. Unknown never authorizes blind retry.",
    "nx_cancel_operation": "Request cooperative cancellation of a running batch between child operations. Cannot interrupt a single NXOpen call; inspect final outcome.",
    "nx_batch": "Execute 1–100 sketch-curve/add-component/placement operations serially on the NX thread under one rollback mark. Structural preflight, progress, cancellation; all-or-rollback for model changes. Supply one stable operation_id for safe retry.",
    "nx_add_component": "Add a .prt occurrence with initial translation and right-handed row-major 3x3 rotation. Work-part coordinates; p_parent=R*p_local+t. Returns typed occurrence.",
    "nx_set_component_transform": "Assign absolute translation and row-major rotation to an immediate child. Read-back verified; repeating the same placement is idempotent. Activate owning subassembly for nested placement.",
    "nx_reposition_component": "Relative translation and rotation of immediate child in work-part coordinates. Degrees, Rz*Ry*Rx. Use a stable operation_id for retry; use nx_set_component_transform for absolute placement.",
    "nx_measure_distance": "Measure minimum BREP distance for body, face, edge, feature-body or component pairs, including nested occurrences. Returns closest points, accuracy and work-part units. Zero does not prove interference.",
    "nx_list_topology": "Enumerate faces and edges of a body as session-scoped opaque references. References become stale after rollback/close; topology edits can invalidate them.",
    "nx_rename_object": "Rename a referenced object and return its actual NX-normalized display name. Reacquire references afterward.",
    "nx_workspace_list": "List files/directories within the configured workspace; sizes and SHA-256 checksums for files. Internal operation storage is excluded.",
    "nx_download_file": "Retrieve a workspace artifact as base64 chunks up to 256 KiB, with full-file SHA-256, size and offset. Does not read outside workspace.",
    "nx_upload_file": "Upload .prt/.step/.stp/.png/.json/.zip/.txt/.pdf chunks (max 256 KiB) into a new workspace file. Requires final SHA-256 and total size, sequential offsets. Repeated identical chunks are safe; existing differing files are never overwritten.",
    "nx_package_assembly": "Package the saved active assembly and all loaded prototype dependencies into a new workspace ZIP with a SHA-256 manifest. Refuses unsaved referenced parts and files outside the workspace.",
    "nx_capabilities": "NX-version-specific integration manifest. API presence, real-test evidence and unavailable capabilities are separate. Batch NX has no model viewport.",
    "nx_screenshot": "Capture the interactive Windows desktop to PNG. This is NOT a screenshot of the batch NX model. Retrieve bytes through nx_download_file; batch-model camera rendering is unavailable.",
}

READ_ONLY = {
    "nx_status",
    "nx_list_sketches",
    "nx_list_features",
    "nx_list_bodies",
    "nx_list_components",
    "nx_list_open_parts",
    "nx_get_bounding_box",
    "nx_measure_volume",
    "nx_measure_distance",
    "nx_measure_angle",
    "nx_get_feature_info",
    "nx_sketch_info",
    "nx_list_topology",
    "nx_checkpoint_state",
    "nx_capabilities",
    "nx_operation_status",
    "nx_workspace_list",
    "nx_download_file",
}
SIDE = {
    "nx_workspace_list",
    "nx_download_file",
    "nx_upload_file",
    "nx_operation_status",
    "nx_cancel_operation",
}
PATHS = {
    "nx_create_part": "path",
    "nx_open_part": "path",
    "nx_export_step": "path",
    "nx_add_component": "part_path",
    "nx_import_geometry": "path",
    "nx_screenshot": "path",
    "nx_save_as": "path",
    "nx_export_drawing_pdf": "path",
}


def envelope(payload, error=False):
    payload = {"status": "error" if error else "success", "warnings": [], "units": None, **payload}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
        isError=error,
    )


def configure(mcp, bridge, workspace):
    if workspace is None:
        return
    existing = dict(mcp._tool_manager._tools)
    definitions = {
        name: obj
        for name, obj in globals().items()
        if name.startswith("nx_") and inspect.isfunction(obj)
    }
    names = set(existing) | set(definitions)
    for name in names:
        old = existing.get(name)
        fn = definitions.get(name) or old.fn
        sig = inspect.signature(fn)
        # Resolve postponed annotations in the original callable's module.
        from typing import get_type_hints

        hints = get_type_hints(fn)
        parameters = [
            p.replace(annotation=hints.get(p.name, p.annotation)) for p in sig.parameters.values()
        ]
        if name not in READ_ONLY and name not in SIDE and name != "nx_package_assembly":
            parameters.append(
                inspect.Parameter(
                    "operation_id",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=None,
                    annotation=str | None,
                )
            )
        sig = sig.replace(parameters=parameters, return_annotation=CallToolResult)

        def factory(method, signature):
            async def proxy(**kwargs):
                try:
                    bound = signature.bind(**kwargs)
                    bound.apply_defaults()
                    params = dict(bound.arguments)
                    if "operation_id" in params and method not in {
                        "nx_operation_status",
                        "nx_cancel_operation",
                    }:
                        params["operation_id"] = params["operation_id"] or (
                            "op_" + uuid.uuid4().hex
                        )
                    if method == "nx_package_assembly":
                        result = await package_assembly(bridge, workspace, params["path"])
                    elif method in SIDE:
                        result = artifact_call(method, params, workspace)
                    else:
                        if path_key := PATHS.get(method):
                            if params.get(path_key) is not None:
                                params[path_key] = str(workspace.resolve(params[path_key]))
                        if method == "nx_import_geometry" and params.get("output_path"):
                            params["output_path"] = str(workspace.resolve(params["output_path"]))
                        if method == "nx_batch":
                            for op in params["operations"]:
                                if op.get("method") == "nx_add_component" and "part_path" in op.get(
                                    "params", {}
                                ):
                                    op["params"]["part_path"] = str(
                                        workspace.resolve(op["params"]["part_path"])
                                    )
                        result = await bridge.call(method, params)
                    return envelope(result, error=result.get("status") == "error")
                except (NXToolError, WorkspaceViolation, ValueError, TypeError) as e:
                    error = (
                        e
                        if isinstance(e, NXToolError)
                        else NXToolError("NX_INVALID_ARGUMENT", str(e))
                    )
                    if "params" in locals() and params.get("operation_id"):
                        error.details.setdefault("operation_id", params["operation_id"])
                        error.details.setdefault("mutation_outcome", "unknown")
                    return envelope(error.as_dict(), True)

            proxy.__name__ = method
            proxy.__signature__ = signature
            return proxy

        if old:
            mcp.remove_tool(name)
        description = DESCRIPTIONS.get(name, (old.description if old else name))
        description = description.replace("EXPERIMENTAL: ", "")
        if description.strip() == name:
            description = (
                "Experimental NX operation; semantics and installed API support have not been validated. "
                + name
            )
        mcp.add_tool(
            factory(name, sig),
            name=name,
            description=description,
            structured_output=False,
            annotations=ToolAnnotations(
                readOnlyHint=name in READ_ONLY,
                idempotentHint=name in READ_ONLY or name == "nx_set_component_transform",
            ),
        )
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config["extra"] = "forbid"
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()
    original_call = mcp.call_tool

    async def uniform_call(name, arguments):
        try:
            return await original_call(name, arguments)
        except Exception as error:
            return envelope(
                NXToolError(
                    "NX_INVALID_ARGUMENT", str(error), details={"mutation_outcome": "not_started"}
                ).as_dict(),
                True,
            )

    mcp.call_tool = uniform_call
    mcp._mcp_server.call_tool(validate_input=False)(uniform_call)
    mcp._mcp_server.instructions = "Siemens NX v2606 integration. Use nx_capabilities for tested scope. Use client-supplied operation_id for mutation retry; query receipts after transport failure. No general certification is claimed."


def artifact_call(method, p, workspace):
    store = OperationStore(workspace.root)
    if method == "nx_operation_status":
        return store.get(p["operation_id"])
    if method == "nx_cancel_operation":
        record = store.get(p["operation_id"])
        if record["state"] != "running" or record.get("method") != "nx_batch":
            raise NXToolError("NX_NOT_CANCELLABLE", "Only running batches accept cancellation")
        store.path(p["operation_id"]).with_suffix(".cancel").touch()
        return {
            "status": "success",
            "operation_id": p["operation_id"],
            "cancellation_requested": True,
        }
    path = workspace.resolve(p["path"])
    if ".nx-mcp" in path.relative_to(workspace.root).parts:
        raise NXToolError("NX_PATH_RESERVED", "Internal service state is not an artifact")

    def metadata(file):
        h = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return {
            "path": str(file.relative_to(workspace.root)),
            "size": file.stat().st_size,
            "sha256": h.hexdigest(),
        }

    if method == "nx_workspace_list":
        items = []
        for f in sorted(path.iterdir()):
            if f.name == ".nx-mcp":
                continue
            workspace.ensure_inside(f)
            items.append(
                metadata(f) | {"kind": "file"}
                if f.is_file()
                else {"path": str(f.relative_to(workspace.root)), "kind": "directory"}
            )
        return {"status": "success", "entries": items, "count": len(items)}
    if method == "nx_download_file":
        if p["offset"] < 0 or not 1 <= p["length"] <= 262144:
            raise NXToolError("NX_INVALID_ARGUMENT", "Invalid chunk offset/length")
        meta = metadata(path)
        with path.open("rb") as stream:
            stream.seek(p["offset"])
            data = stream.read(p["length"])
        return {
            "status": "success",
            **meta,
            "offset": p["offset"],
            "data_base64": base64.b64encode(data).decode(),
            "eof": p["offset"] + len(data) >= meta["size"],
        }
    if path.suffix.lower() not in {
        ".prt",
        ".step",
        ".stp",
        ".png",
        ".json",
        ".zip",
        ".txt",
        ".pdf",
    }:
        raise NXToolError(
            "NX_UNSUPPORTED_FILE_TYPE", "Upload is limited to CAD and review artifacts"
        )
    if not 0 <= p["offset"] <= p["total_size"] <= 256 * 1024 * 1024:
        raise NXToolError("NX_INVALID_ARGUMENT", "Invalid offset or total_size (max 256 MiB)")
    if len(p["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in p["sha256"]):
        raise NXToolError("NX_INVALID_ARGUMENT", "Expected lowercase SHA-256")
    data = base64.b64decode(p["data_base64"], validate=True)
    if len(data) > 262144 or p["offset"] + len(data) > p["total_size"]:
        raise NXToolError("NX_INVALID_ARGUMENT", "Chunk exceeds limit")
    if path.exists():
        meta = metadata(path)
        if meta["sha256"] == p["sha256"] and meta["size"] == p["total_size"]:
            return {"status": "success", **meta, "committed": True, "replayed": True}
        raise NXToolError("NX_FILE_EXISTS", "Existing file differs; choose a new destination")
    staging = workspace.root / ".nx-mcp" / "uploads"
    staging.mkdir(exist_ok=True, parents=True)
    key = hashlib.sha256(
        (str(path) + "|" + p["sha256"] + "|" + str(p["total_size"])).encode()
    ).hexdigest()
    temp = staging / key
    size = temp.stat().st_size if temp.exists() else 0
    if p["offset"] < size:
        with temp.open("rb") as f:
            f.seek(p["offset"])
            previous = f.read(len(data))
        if previous != data:
            raise NXToolError("NX_UPLOAD_CONFLICT", "Retried chunk differs from staged data")
    elif p["offset"] == size:
        with temp.open("ab") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    else:
        raise NXToolError("NX_UPLOAD_GAP", "Chunks must be contiguous")
    complete = temp.stat().st_size == p["total_size"]
    if complete:
        if metadata(temp)["sha256"] != p["sha256"]:
            raise NXToolError(
                "NX_CHECKSUM_MISMATCH",
                "Uploaded bytes do not match SHA-256; choose a corrected upload",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive destination creation prevents overwrite races between clients.
        os.link(temp, path)  # Atomic exclusive publication on the same filesystem.
        temp.unlink()
    return {
        "status": "success",
        "path": str(path.relative_to(workspace.root)),
        "received": size + len(data) if p["offset"] == size else size,
        "committed": complete,
        "sha256": p["sha256"],
    }


async def package_assembly(bridge, workspace, path):
    import zipfile

    destination = workspace.resolve(path)
    if destination.suffix.lower() != ".zip":
        raise NXToolError("NX_INVALID_ARGUMENT", "Package path must end with .zip")
    opened = await bridge.call("nx_list_open_parts", {})
    active = next(p for p in opened["parts"] if p["work"])
    components = await bridge.call("nx_list_components", {})
    paths = {active["path"]} | {c["part_path"] for c in components["components"]}
    for p in opened["parts"]:
        if p["path"] in paths and p["modified"]:
            raise NXToolError(
                "NX_UNSAVED_PART", "Save referenced parts before packaging: " + p["path"]
            )
    manifest = []
    for p in sorted(paths):
        file = workspace.ensure_inside(p)
        if not file.is_file():
            raise NXToolError("NX_FILE_NOT_FOUND", str(file))
        manifest.append(
            {
                "path": str(file.relative_to(workspace.root)).replace("\\", "/"),
                "size": file.stat().st_size,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = workspace.root / ".nx-mcp" / ("package-" + uuid.uuid4().hex + ".zip")
    temp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in manifest:
                archive.write(workspace.resolve(item["path"]), item["path"])
            archive.writestr(
                "nx-assembly-manifest.json",
                json.dumps(
                    {"assembly": active, "components": components, "files": manifest}, indent=2
                ),
            )
        os.link(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return {
        "status": "success",
        "path": str(destination.relative_to(workspace.root)),
        "size": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "prototype_files": len(paths) - 1,
        "component_instances": components["count"],
        "files": manifest,
    }
