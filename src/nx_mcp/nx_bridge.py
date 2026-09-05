"""NX-process command executor and manual bridge lifecycle."""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nx_mcp.bridge import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeDescriptor,
    BridgeServer,
    MainThreadDispatcher,
    ObjectRegistry,
    default_descriptor_path,
)
from nx_mcp.runtime import NXToolError, ObjectKind
from nx_mcp.workspace import Workspace


class NXOpenExecutor:
    """Executes the certified bridge commands against one live NX session."""

    _MODEL_MUTATIONS = {
        "nx_create_sketch",
        "nx_sketch_line",
        "nx_sketch_rectangle",
        "nx_finish_sketch",
        "nx_extrude",
        "nx_revolve",
        "nx_sketch_arc",
        "nx_hole",
        "nx_boolean",
    }

    def __init__(
        self,
        session: Any,
        nxopen: Any,
        nx_version: str,
        workspace: Workspace,
        *,
        enable_experimental: bool = False,
        enable_journal: bool = False,
    ) -> None:
        self.session = session
        self.nxopen = nxopen
        self.nx_version = nx_version
        self.workspace = workspace
        self.enable_experimental = enable_experimental
        self.enable_journal = enable_experimental and enable_journal
        self.objects = ObjectRegistry()
        self._undo_marks: list[Any] = []
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "nx_status": self._status,
            "nx_create_part": self._create_part,
            "nx_open_part": self._open_part,
            "nx_save_part": self._save_part,
            "nx_close_part": self._close_part,
            "nx_export_step": self._export_step,
            "nx_list_sketches": lambda: self._list_objects("Sketches", "sketch"),
            "nx_list_bodies": lambda: self._list_objects("Bodies", "body"),
            "nx_list_features": lambda: self._list_objects("Features", "feature"),
            "nx_create_sketch": self._create_sketch,
            "nx_sketch_line": self._sketch_line,
            "nx_sketch_rectangle": self._sketch_rectangle,
            "nx_finish_sketch": self._finish_sketch,
            "nx_extrude": self._extrude,
            "nx_undo": self._undo,
            "nx_fit_view": self._fit_view,
            "nx_revolve": self._revolve,
            "nx_sketch_arc": self._sketch_arc_legacy,
            "nx_hole": self._hole,
            "nx_boolean": self._boolean,
            "nx_screenshot": self._screenshot,
        }

    def execute(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(method)
        if handler is None:
            if self.enable_experimental:
                from nx_mcp.experimental import execute_legacy

                return execute_legacy(
                    method,
                    params,
                    self.workspace,
                    enable_journal=self.enable_journal,
                )
            raise NXToolError("NX_TOOL_NOT_FOUND", f"Unsupported bridge command: {method}")
        undo_mark = None
        try:
            if method in self._MODEL_MUTATIONS:
                undo_mark = self.session.SetUndoMark(
                    self.nxopen.Session.MarkVisibility.Visible,
                    f"NX MCP: {method}",
                )
            result = handler(**params)
            if undo_mark is not None:
                self._undo_marks.append(undo_mark)
            return result
        except NXToolError as error:
            if undo_mark is not None:
                self._rollback(undo_mark, error)
            raise
        except Exception as error:
            if undo_mark is not None:
                self._rollback(undo_mark, error)
            raise NXToolError(
                "NX_API_ERROR",
                str(error),
                nx_code=getattr(error, "ErrorCode", None),
            ) from error

    def _rollback(self, undo_mark: Any, original_error: Exception) -> None:
        try:
            self.session.UndoToMark(undo_mark, None)
        except Exception as rollback_error:
            raise NXToolError(
                "NX_ROLLBACK_FAILED",
                f"Operation failed and rollback also failed: {rollback_error}",
                details={"operation_error": str(original_error)},
            ) from rollback_error

    def _work_part(self, *, required: bool = True) -> Any | None:
        part = getattr(self.session.Parts, "Work", None)
        if part is None and required:
            raise NXToolError(
                "NX_NO_WORK_PART",
                "No work part is open.",
                suggestion="Use nx_open_part or nx_create_part first.",
            )
        return part

    @staticmethod
    def _name(value: Any, fallback: str) -> str:
        name = getattr(value, "Name", fallback)
        return str(name() if callable(name) else name)

    @staticmethod
    def _part_id(part: Any) -> str:
        native_id = getattr(part, "Tag", None)
        return f"part_{native_id if native_id is not None else id(part)}"

    def _reference(self, value: Any, kind: ObjectKind, part: Any, fallback: str) -> dict[str, Any]:
        return self.objects.register(
            value,
            kind=kind,
            name=self._name(value, fallback),
            part_id=self._part_id(part),
        ).model_dump()

    def _status(self) -> dict[str, Any]:
        part = self._work_part(required=False)
        return {
            "connected": True,
            "nx_version": self.nx_version,
            "bridge_protocol": BRIDGE_PROTOCOL_VERSION,
            "active_part": self._reference(part, "part", part, "Part") if part else None,
        }

    def _list_objects(self, collection_name: str, kind: ObjectKind) -> dict[str, Any]:
        part = self._work_part()
        collection = getattr(part, collection_name)
        values = list(collection)
        return {
            "objects": [self._reference(value, kind, part, kind.title()) for value in values],
            "message": f"Found {len(values)} {kind}(s).",
        }

    def _create_part(self, path: str, units: str = "mm") -> dict[str, Any]:
        if units not in {"mm", "inch"}:
            raise NXToolError("NX_INVALID_ARGUMENT", "units must be 'mm' or 'inch'")
        destination = self.workspace.ensure_inside(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        builder = self.session.Parts.FileNew()
        try:
            builder.TemplateFileName = (
                "model-plain-1-mm-template.prt"
                if units == "mm"
                else "model-plain-1-inch-template.prt"
            )
            builder.Units = (
                self.nxopen.Part.Units.Millimeters
                if units == "mm"
                else self.nxopen.Part.Units.Inches
            )
            builder.NewFileName = str(destination)
            builder.DisplayPartOption = self.nxopen.DisplayPartOption.AllowAdditional
            part = builder.Commit() or self._work_part()
        finally:
            builder.Destroy()
        return {
            "part": self._reference(part, "part", part, destination.stem),
            "message": f"Created part: {self._name(part, destination.stem)}",
        }

    def _open_part(self, path: str) -> dict[str, Any]:
        source = self.workspace.ensure_inside(path)
        if not source.is_file():
            raise NXToolError("NX_FILE_NOT_FOUND", f"Part file does not exist: {source.name}")
        load_status = None
        try:
            part, load_status = self.session.Parts.OpenBaseDisplay(str(source))
        finally:
            if load_status is not None:
                load_status.Dispose()
        work_part = self._work_part(required=False)
        if work_part is not None:
            part = work_part
        return {
            "part": self._reference(part, "part", part, source.stem),
            "message": f"Opened part: {self._name(part, source.stem)}",
        }

    def _save_part(self) -> dict[str, Any]:
        part = self._work_part()
        part.Save(
            self.nxopen.BasePart.SaveComponents.TrueValue,
            self.nxopen.BasePart.CloseAfterSave.FalseValue,
        )
        self._undo_marks.clear()
        return {"message": f"Saved part: {self._name(part, 'Part')}"}

    def _close_part(self, save: bool = True) -> dict[str, Any]:
        part = self._work_part()
        part_name = self._name(part, "Part")
        part_id = self._part_id(part)
        if save:
            self._save_part()
        part.Close(
            self.nxopen.BasePart.CloseWholeTree.TrueValue,
            self.nxopen.BasePart.CloseModified.CloseModified,
            None,
        )
        self.objects.invalidate_part(part_id)
        self._undo_marks.clear()
        return {"message": f"Closed part: {part_name}"}

    def _export_step(self, path: str) -> dict[str, Any]:
        self._work_part()
        destination = self.workspace.ensure_inside(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        builder = self.session.DexManager.CreateStepCreator()
        try:
            builder.OutputFile = str(destination)
            builder.Commit()
        finally:
            builder.Destroy()
        return {
            "path": str(destination),
            "message": f"Exported STEP: {destination.name}",
        }

    def _create_sketch(self, plane: str = "XY", name: str | None = None) -> dict[str, Any]:
        normals = {"XY": (0.0, 0.0, 1.0), "XZ": (0.0, 1.0, 0.0), "YZ": (1.0, 0.0, 0.0)}
        if plane not in normals:
            raise NXToolError("NX_INVALID_ARGUMENT", "plane must be XY, XZ, or YZ")
        part = self._work_part()
        normal = self.nxopen.Vector3d(*normals[plane])
        placement_plane = part.Planes.CreatePlane(
            self.nxopen.Point3d(0.0, 0.0, 0.0),
            normal,
            self.nxopen.SmartObject.UpdateOption.WithinModeling,
        )
        builder = part.Sketches.CreateSketchInPlaceBuilder2(self.nxopen.Sketch.Null)
        try:
            builder.PlaneReference = placement_plane
            sketch = builder.Commit()
        finally:
            builder.Destroy()
        if name:
            sketch.SetName(name)
        sketch.Activate(self.nxopen.Sketch.ViewReorient.TrueValue)
        reference = self.objects.register(
            sketch,
            kind="sketch",
            name=self._name(sketch, name or "Sketch"),
            part_id=self._part_id(part),
        )
        return {
            "object": reference.model_dump(),
            "message": f"Created sketch: {reference.name}",
        }

    def _create_sketch_line(
        self,
        sketch: Any,
        part: Any,
        start: dict[str, Any],
        end: dict[str, Any],
    ) -> dict[str, Any]:
        start_point = self.nxopen.Point3d(float(start["x"]), float(start["y"]), 0.0)
        end_point = self.nxopen.Point3d(float(end["x"]), float(end["y"]), 0.0)
        curve = part.Curves.CreateLine(start_point, end_point)
        sketch.AddGeometry(curve, self.nxopen.Sketch.InferConstraintsOption.InferNoConstraints)
        return self._reference(curve, "curve", part, "Line")

    def _sketch_line(
        self,
        sketch_id: str,
        start: dict[str, Any],
        end: dict[str, Any],
    ) -> dict[str, Any]:
        part = self._work_part()
        sketch = self.objects.resolve(
            sketch_id,
            expected_kind="sketch",
            part_id=self._part_id(part),
        )
        reference = self._create_sketch_line(sketch, part, start, end)
        return {"object": reference, "message": f"Created line: {reference['name']}"}

    def _sketch_rectangle(
        self,
        sketch_id: str,
        corner1: dict[str, Any],
        corner2: dict[str, Any],
    ) -> dict[str, Any]:
        part = self._work_part()
        sketch = self.objects.resolve(
            sketch_id,
            expected_kind="sketch",
            part_id=self._part_id(part),
        )
        x1, y1 = float(corner1["x"]), float(corner1["y"])
        x2, y2 = float(corner2["x"]), float(corner2["y"])
        if x1 == x2 or y1 == y2:
            raise NXToolError("NX_INVALID_ARGUMENT", "Rectangle width and height must be non-zero")
        corners = [
            {"x": x1, "y": y1},
            {"x": x2, "y": y1},
            {"x": x2, "y": y2},
            {"x": x1, "y": y2},
        ]
        references = [
            self._create_sketch_line(sketch, part, corners[index], corners[(index + 1) % 4])
            for index in range(4)
        ]
        return {"objects": references, "message": "Created sketch rectangle"}

    def _finish_sketch(self, sketch_id: str) -> dict[str, Any]:
        part = self._work_part()
        sketch = self.objects.resolve(
            sketch_id,
            expected_kind="sketch",
            part_id=self._part_id(part),
        )
        sketch.Deactivate(
            self.nxopen.Sketch.ViewReorient.TrueValue,
            self.nxopen.Sketch.UpdateLevel.Model,
        )
        reference = self.objects.register(
            sketch,
            kind="sketch",
            name=self._name(sketch, "Sketch"),
            part_id=self._part_id(part),
        )
        return {"object": reference.model_dump(), "message": f"Finished sketch: {reference.name}"}

    def _extrude(self, sketch_id: str, distance: float, reverse: bool = False) -> dict[str, Any]:
        if distance <= 0:
            raise NXToolError("NX_INVALID_ARGUMENT", "distance must be greater than zero")
        part = self._work_part()
        sketch = self.objects.resolve(
            sketch_id,
            expected_kind="sketch",
            part_id=self._part_id(part),
        )
        bodies_before = list(part.Bodies)
        section = part.Sections.CreateSection()
        rule = part.ScRuleFactory.CreateRuleCurveFeature(
            [sketch.Feature],
            self.nxopen.DisplayableObject.Null,
            part.ScRuleFactory.CreateRuleOptions(),
        )
        section.AddToSection(
            [rule],
            self.nxopen.NXObject.Null,
            self.nxopen.NXObject.Null,
            self.nxopen.NXObject.Null,
            self.nxopen.Point3d(0.0, 0.0, 0.0),
            self.nxopen.Section.Mode.Create,
            False,
        )
        direction = part.Directions.CreateDirection(
            sketch,
            self.nxopen.Sense.Reverse if reverse else self.nxopen.Sense.Forward,
            self.nxopen.SmartObject.UpdateOption.WithinModeling,
        )
        builder = part.Features.CreateExtrudeBuilder(self.nxopen.Features.Feature.Null)
        try:
            builder.Section = section
            builder.Direction = direction
            builder.Limits.StartExtend.Value.RightHandSide = "0"
            builder.Limits.EndExtend.Value.RightHandSide = str(distance)
            builder.BooleanOperation.Type = (
                self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Create
            )
            builder.AllowSelfIntersectingSection(True)
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        feature_bodies = list(feature.GetBodies()) if hasattr(feature, "GetBodies") else []
        if feature_bodies:
            body = feature_bodies[0]
        else:
            new_bodies = [body for body in part.Bodies if body not in bodies_before]
            if not new_bodies:
                raise NXToolError("NX_OPERATION_FAILED", "Extrude did not create a body")
            body = new_bodies[0]
        return {
            "feature": self._reference(feature, "feature", part, "Extrude"),
            "body": self._reference(body, "body", part, "Body"),
            "message": f"Extruded {self._name(sketch, 'Sketch')} by {distance}",
        }

    def _undo(self) -> dict[str, Any]:
        if not self._undo_marks:
            raise NXToolError("NX_UNDO_UNAVAILABLE", "No NX MCP operation is available to undo")
        part = self._work_part()
        self.session.UndoToMark(self._undo_marks.pop(), None)
        self.objects.invalidate_part(self._part_id(part))
        return {"message": "Undo successful"}

    def _fit_view(self) -> dict[str, Any]:
        part = self._work_part()
        part.ModelingViews.WorkView.Fit()
        return {"message": "View fitted"}

    def _find_sketch(self, name: str) -> Any:
        part = self._work_part()
        for sketch in part.Sketches:
            sketch_name = self._name(sketch, "Sketch")
            if sketch_name == name or sketch_name.endswith(name):
                return sketch
        raise NXToolError("NX_NOT_FOUND", f"Sketch not found: {name}")

    def _revolve(
        self,
        angle: float = 360.0,
        axis: str = "Z",
        sketch_name: str | None = None,
        boolean: str = "none",
    ) -> dict[str, Any]:
        if angle <= 0 or angle > 360:
            raise NXToolError("NX_INVALID_ARGUMENT", "angle must be greater than 0 and at most 360")
        if not sketch_name:
            raise NXToolError("NX_INVALID_ARGUMENT", "sketch_name is required")
        vectors = {
            "X": (1.0, 0.0, 0.0),
            "Y": (0.0, 1.0, 0.0),
            "Z": (0.0, 0.0, 1.0),
            "-X": (-1.0, 0.0, 0.0),
            "-Y": (0.0, -1.0, 0.0),
            "-Z": (0.0, 0.0, -1.0),
        }
        axis_key = axis.strip().upper()
        if axis_key not in vectors:
            raise NXToolError("NX_INVALID_ARGUMENT", "axis must be X, Y, Z, -X, -Y, or -Z")
        boolean_types = {
            "none": self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Create,
            "unite": self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
            "subtract": self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            "intersect": self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Intersect,
        }
        boolean_key = boolean.strip().lower()
        if boolean_key not in boolean_types:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "boolean must be none, unite, subtract, or intersect"
            )
        part = self._work_part()
        sketch = self._find_sketch(sketch_name)
        section = part.Sections.CreateSection()
        rule = part.ScRuleFactory.CreateRuleCurveFeature(
            [sketch.Feature],
            self.nxopen.DisplayableObject.Null,
            part.ScRuleFactory.CreateRuleOptions(),
        )
        section.AddToSection(
            [rule],
            self.nxopen.NXObject.Null,
            self.nxopen.NXObject.Null,
            self.nxopen.NXObject.Null,
            self.nxopen.Point3d(0.0, 0.0, 0.0),
            self.nxopen.Section.Mode.Create,
            False,
        )
        vector = self.nxopen.Vector3d(*vectors[axis_key])
        origin = part.Points.CreatePoint(self.nxopen.Point3d(0.0, 0.0, 0.0))
        direction = part.Directions.CreateDirection(origin, vector)
        revolve_axis = part.Axes.CreateAxis(
            origin,
            direction,
            self.nxopen.SmartObject.UpdateOption.WithinModeling,
        )
        builder = part.Features.CreateRevolveBuilder(self.nxopen.Features.Feature.Null)
        try:
            builder.Section = section
            builder.Axis = revolve_axis
            builder.Limits.StartExtend.Value.RightHandSide = "0"
            builder.Limits.EndExtend.Value.RightHandSide = str(angle)
            builder.BooleanOperation.Type = boolean_types[boolean_key]
            if boolean_key != "none":
                bodies = list(part.Bodies)
                if not bodies:
                    raise NXToolError("NX_NO_TARGET_BODY", "No target body is available")
                builder.BooleanOperation.SetTargetBodies(bodies)
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        return {
            "feature": self._reference(feature, "feature", part, "Revolve"),
            "angle": angle,
            "axis": axis_key,
            "message": f"Revolved {self._name(sketch, sketch_name)} by {angle} degrees",
        }

    def _sketch_arc_legacy(
        self,
        cx: float,
        cy: float,
        radius: float,
        start_angle: float,
        end_angle: float,
    ) -> dict[str, Any]:
        import math

        if radius <= 0:
            raise NXToolError("NX_INVALID_ARGUMENT", "radius must be greater than zero")
        if start_angle == end_angle:
            raise NXToolError("NX_INVALID_ARGUMENT", "start_angle and end_angle must differ")
        part = self._work_part()
        arc = part.Curves.CreateArc(
            self.nxopen.Point3d(cx, cy, 0.0),
            self.nxopen.Vector3d(1.0, 0.0, 0.0),
            self.nxopen.Vector3d(0.0, 1.0, 0.0),
            radius,
            math.radians(start_angle),
            math.radians(end_angle),
        )
        reference = self._reference(arc, "curve", part, "Arc")
        return {
            "object": reference,
            "center": [cx, cy],
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
            "message": "Created arc",
        }

    def _hole(
        self,
        diameter: float,
        depth: float,
        x: float,
        y: float,
        z: float,
    ) -> dict[str, Any]:
        if diameter <= 0 or depth <= 0:
            raise NXToolError("NX_INVALID_ARGUMENT", "diameter and depth must be greater than zero")
        part = self._work_part()
        bodies = list(part.Bodies)
        if not bodies:
            raise NXToolError("NX_NO_TARGET_BODY", "Create a solid body before creating a hole")
        builder = part.Features.CreateCylinderBuilder(self.nxopen.Features.Feature.Null)
        try:
            builder.Origin = self.nxopen.Point3d(x, y, z)
            builder.Direction = self.nxopen.Vector3d(0.0, 0.0, 1.0)
            builder.Diameter.RightHandSide = str(diameter)
            builder.Height.RightHandSide = str(depth)
            builder.BooleanOption.Type = (
                self.nxopen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
            )
            builder.BooleanOption.SetTargetBodies([bodies[0]])
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        return {
            "feature": self._reference(feature, "feature", part, "Hole"),
            "diameter": diameter,
            "depth": depth,
            "location": [x, y, z],
            "message": "Created cylindrical hole along +Z",
        }

    def _resolve_body(self, value: str, part: Any) -> Any:
        try:
            return self.objects.resolve(
                value,
                expected_kind="body",
                part_id=self._part_id(part),
            )
        except NXToolError:
            pass
        bodies = list(part.Bodies)
        for index, body in enumerate(bodies, start=1):
            names = {
                self._name(body, f"body_{index}"),
                f"body_{index}",
                str(getattr(body, "JournalIdentifier", "")),
            }
            if value in names:
                return body
        raise NXToolError("NX_NOT_FOUND", f"Body not found: {value}")

    def _boolean(self, boolean_type: str, targets: list[str]) -> dict[str, Any]:
        type_map = {
            "unite": self.nxopen.Features.FeatureBooleanType.Unite,
            "subtract": self.nxopen.Features.FeatureBooleanType.Subtract,
            "intersect": self.nxopen.Features.FeatureBooleanType.Intersect,
        }
        key = boolean_type.strip().lower()
        if key not in type_map:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "boolean_type must be unite, subtract, or intersect"
            )
        if len(targets) < 2:
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "targets must contain the target body followed by at least one tool body",
            )
        part = self._work_part()
        bodies = [self._resolve_body(value, part) for value in targets]
        builder = part.Features.CreateBooleanBuilder(self.nxopen.Features.BooleanFeature.Null)
        try:
            builder.Operation = type_map[key]
            builder.Target = bodies[0]
            builder.Tools.Add(bodies[1:])
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        return {
            "feature": self._reference(feature, "feature", part, "Boolean"),
            "boolean_type": key,
            "targets": targets,
            "message": f"Boolean {key} completed",
        }

    def _screenshot(self, path: str) -> dict[str, Any]:
        destination = self.workspace.ensure_inside(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
  $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
  $bitmap.Save($env:NX_MCP_SCREENSHOT_PATH, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
  $graphics.Dispose()
  $bitmap.Dispose()
}
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        environment = dict(os.environ)
        environment["NX_MCP_SCREENSHOT_PATH"] = str(destination)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=environment,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0 or not destination.is_file():
            message = (completed.stderr or completed.stdout or "screen capture failed").strip()
            raise NXToolError("NX_SCREENSHOT_FAILED", message)
        return {"path": str(destination), "message": f"Screenshot saved to {destination.name}"}


@dataclass
class BridgeRuntime:
    server: BridgeServer
    dispatcher: MainThreadDispatcher
    descriptor: BridgeDescriptor
    descriptor_path: Path

    def stop(self) -> None:
        self.dispatcher.stop()
        self.server.stop()
        try:
            current = BridgeDescriptor.read(self.descriptor_path)
            if current.token == self.descriptor.token:
                self.descriptor_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


_runtime: BridgeRuntime | None = None


def _detect_nx_version(session: Any) -> str:
    try:
        value = session.GetEnvironmentVariableValue("UGII_VERSION")
        if value:
            return str(value)
    except Exception:
        pass
    return "NX build unknown"


def start_bridge(
    workspace_root: str | Path,
    *,
    descriptor_path: str | Path | None = None,
    allow_unverified_threading: bool = False,
) -> BridgeDescriptor:
    """Start the Python feasibility bridge from inside NX.

    NXOpen threading must be validated on the target build before this gate is
    enabled for a pilot. If it fails, the agreed fallback is a minimal C# bridge.
    """
    global _runtime
    if _runtime is not None:
        return _runtime.descriptor
    if (
        not allow_unverified_threading
        and os.environ.get("NX_MCP_ALLOW_UNVERIFIED_PYTHON_BRIDGE") != "1"
    ):
        raise RuntimeError(
            "Python bridge execution has not been verified on this NX build. "
            "Set NX_MCP_ALLOW_UNVERIFIED_PYTHON_BRIDGE=1 only for the real-NX feasibility test."
        )

    import NXOpen

    session = NXOpen.Session.GetSession()
    executor = NXOpenExecutor(
        session,
        NXOpen,
        _detect_nx_version(session),
        Workspace(workspace_root),
        enable_experimental=os.environ.get("NX_MCP_ENABLE_EXPERIMENTAL") == "1",
        enable_journal=os.environ.get("NX_MCP_ENABLE_JOURNAL") == "1",
    )
    token = secrets.token_hex(32)
    dispatcher = MainThreadDispatcher(executor.execute)
    server = BridgeServer(dispatcher.call, token=token)
    server.start()
    descriptor = BridgeDescriptor.create(
        server.port,
        executor.nx_version,
        token=token,
    )
    destination = Path(descriptor_path) if descriptor_path else default_descriptor_path()
    descriptor.write(destination)
    _runtime = BridgeRuntime(server, dispatcher, descriptor, destination)
    return descriptor


def pump_bridge(timeout: float = 0.1) -> int:
    """Run pending bridge calls on the NX journal's main thread."""
    if _runtime is None:
        return 0
    return _runtime.dispatcher.drain(timeout=timeout)


def stop_bridge() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None
