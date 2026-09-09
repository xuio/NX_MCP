"""Versioned NX 2606 Python adapter. All methods run on the existing NX thread."""

from __future__ import annotations

from contextlib import suppress

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.capabilities import inspect_capabilities


def dispose_status(value):
    if value is not None:
        value.Dispose()


def documents(session):
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    rows = []
    for part in session.Parts:
        rows.append(
            {
                "path": part.FullPath,
                "name": part.Name,
                "document_type": type(part).__name__,
                "modified": bool(part.IsModified),
                "work": part == work,
                "display": part == display,
                "units": "mm" if str(part.PartUnits) == "1" else "inch",
                "coordinate_frame": "part_absolute",
            }
        )
    return rows


class SimcenterMixin:
    def _sim_create_analysis(self, cad_document, folder, name):
        from nx_mcp.simcenter.analysis_documents import create

        cad = self.objects.resolve(cad_document, expected_kind="part")
        return create(self, cad, folder, name)

    def _sim_environment(self, document, temperature_c, pressure_pa, buoyancy):
        from nx_mcp.simcenter.environment import configure

        sim = self.objects.resolve(document, expected_kind="part")
        self.workspace.resolve(sim.FullPath)
        return configure(self.session, sim, temperature_c, pressure_pa, buoyancy)

    def _sim_fluid_material(
        self,
        document,
        collectors,
        name,
        density_kg_m3,
        viscosity_pa_s,
        conductivity_w_m_k,
        heat_capacity_j_kg_k,
        provenance,
    ):
        from nx_mcp.simcenter.fluid_material import assign_fluid_material
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        fem = self.objects.resolve(document, expected_kind="part")
        self.workspace.resolve(fem.FullPath)
        selected = [self.objects.resolve(ref, expected_kind="mesh_collector") for ref in collectors]
        if not selected or len({int(c.Tag) for c in selected}) != len(selected):
            raise NXToolError("NX_INVALID_ARGUMENT", "Select distinct fluid collectors")
        require_solver_idle()
        result = assign_fluid_material(
            self.session,
            fem,
            selected,
            name,
            provenance,
            density_kg_m3,
            viscosity_pa_s,
            conductivity_w_m_k,
            heat_capacity_j_kg_k,
        )
        material = result.pop("material")
        result["material"] = self._reference(material, "material", fem, name)
        result["collectors"] = [
            self._reference(c, "mesh_collector", fem, "collector") for c in selected
        ]
        result["results_stale"] = True
        return result

    def _sim_inlet(self, document, faces, name, velocity_m_s, alignment="normal_to_face"):
        return self._sim_create_flow_boundary(
            document, faces, "inlet", name, velocity_m_s, alignment
        )

    def _sim_opening(self, document, faces, name, pressure_pa, alignment="normal_to_face"):
        return self._sim_create_flow_boundary(
            document, faces, "opening", name, pressure_pa, alignment
        )

    def _sim_create_flow_boundary(self, document, faces, kind, name, value, alignment):
        from nx_mcp.simcenter.flow_boundaries import create

        sim = self.objects.resolve(document, expected_kind="part")
        self.workspace.resolve(sim.FullPath)
        selected = [self.objects.resolve(ref, expected_kind="face") for ref in faces]
        result = create(self.session, sim, selected, kind, name, value, alignment)
        boundary = result.pop("boundary")
        result["boundary"] = self._reference(boundary, "simulation_object", sim, kind)
        result["faces"] = [self._reference(face, "face", sim, "face") for face in selected]
        return result

    def _sim_cancel(self, job_id, expected_revision, job_folder="simcenter-jobs"):
        from nx_mcp.simcenter.cancellation import cancel_unlaunched

        return cancel_unlaunched(self.workspace, job_id, expected_revision, job_folder)

    def _sim_scale_fan_table(self, document, source_field, name, rpm):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.fan_field import create_fan_table, inspect_fan_table
        from nx_mcp.simcenter.fan_scaling import scale_curve
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        self.workspace.resolve(sim.FullPath)
        table = self.objects.resolve(source_field, expected_kind="simulation_field")
        if table not in list(sim.FieldManager.Fields):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Source field must belong to this SIM")
        source = inspect_fan_table(sim, table)["manifest"]
        curve = scale_curve(source, name, rpm)
        require_solver_idle()
        result = create_fan_table(self.session, sim, curve)
        created = result.pop("table")
        result["field"] = self._reference(created, "simulation_field", sim, name)
        result["scaling"] = {
            "source_field": source_field,
            "rpm_ratio": rpm / source["rpm"],
            "density_unchanged": True,
            "acoustics_predicted": False,
            "operating_point_calculated": False,
        }
        return result

    def _sim_temperature_material(
        self, document, name, conductivity_samples, heat_capacity_samples, density_kg_m3, provenance
    ):
        from nx_mcp.simcenter.temperature_material import create

        fem = self.objects.resolve(document, expected_kind="part")
        self.workspace.resolve(fem.FullPath)
        result = create(
            self.session,
            fem,
            name,
            conductivity_samples,
            heat_capacity_samples,
            density_kg_m3,
            provenance,
        )
        material = result.pop("material")
        fields = result.pop("fields")
        return {
            "material": self._reference(material, "material", fem, "material"),
            "fields": {
                key: self._reference(value, "simulation_field", fem, "field")
                for key, value in fields.items()
            },
            **result,
        }

    def _sim_material_frame(
        self, document, collector, expected_state_sha256, origin_mm, x_axis, y_axis
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.collector_state import inspect_collector
        from nx_mcp.simcenter.material_orientation import assign_frame

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        self.workspace.resolve(fem.FullPath)
        target = self.objects.resolve(collector, expected_kind="mesh_collector")
        if target not in list(fem.BaseFEModel.MeshManager.GetMeshCollectors()):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Collector does not belong to this FEM")
        if fem.PartUnits != self.nxopen.BasePart.Units.Millimeters:
            raise NXToolError("NX_SIM_UNSUPPORTED", "Select a millimeter FEM")
        before = inspect_collector(fem, target, self._reference, "mm")
        if not before.get("state_sha256"):
            raise NXToolError("NX_SIM_READBACK_FAILED", "Cannot inspect current collector state")
        if before["state_sha256"] != expected_state_sha256:
            raise NXToolError("NX_SIM_REVISION_MISMATCH", "Collector changed; inspect it again")
        table = target.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
            "Solid Property"
        ).PropertyTable
        _, frame, mark = assign_frame(
            self.session,
            self.nxopen,
            fem,
            target,
            origin_mm=origin_mm,
            x_axis=x_axis,
            y_axis=y_axis,
            expected_type=before["orientation"]["native_selector"],
            expected_frame=table.GetCoordinateSystemPropertyValue("material orientation"),
        )
        try:
            after = inspect_collector(fem, target, self._reference, "mm")
            if (
                not after.get("state_sha256")
                or after.get("material") != before["material"]
                or after.get("material_inherited") != before["material_inherited"]
            ):
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Frame edit changed assignment")
        except Exception as error:
            outcome = "rolled_back"
            try:
                self.session.UndoToMark(mark, None)
                self.session.DeleteUndoMark(mark, None)
            except Exception:
                outcome = "partial"
            raise NXToolError(
                "NX_SIM_MATERIAL_FRAME_FAILED",
                "Collector readback failed after frame edit",
                details={"mutation_outcome": outcome},
            ) from error
        self._history.append(
            {
                "mark": mark,
                "part_id": self._part_id(fem),
                "operation_id": self._current_operation,
                "method": "nx_sim_material_frame",
            }
        )
        return {"collector_state": after, "frame": frame, "saved": False, "solve_launched": False}

    def _sim_assign_material(self, document, collector, material, expected_state_sha256):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.material_assignment import assign_material

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        self.workspace.resolve(fem.FullPath)
        target = self.objects.resolve(collector, expected_kind="mesh_collector")
        physical_material = self.objects.resolve(material, expected_kind="material")
        result, mark = assign_material(
            self.session,
            self.nxopen,
            fem,
            target,
            physical_material,
            self._reference,
            expected_state_sha256,
        )
        self._history.append(
            {
                "mark": mark,
                "part_id": self._part_id(fem),
                "operation_id": self._current_operation,
                "method": "nx_sim_assign_material",
            }
        )
        return result

    def _sim_collectors(self, document, offset=0, limit=20):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.collector_state import inspect_collectors

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        self.workspace.resolve(fem.FullPath)
        units = "mm" if fem.PartUnits == self.nxopen.BasePart.Units.Millimeters else "inch"
        return inspect_collectors(fem, self._reference, units, offset, limit)

    def _sim_materials(self, document, offset=0, limit=20):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.material_inventory import inspect_materials

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        self.workspace.resolve(fem.FullPath)
        return inspect_materials(fem, self.nxopen, self._reference, offset=offset, limit=limit)

    def _sim_orthotropic_material(
        self,
        document,
        name,
        conductivities_w_m_k,
        density_kg_m3,
        heat_capacity_j_kg_k,
        provenance,
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.directional_material import create_orthotropic

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        self.workspace.resolve(fem.FullPath)
        if fem.PartUnits != self.nxopen.BasePart.Units.Millimeters:
            raise NXToolError("NX_SIM_UNSUPPORTED", "Select a millimeter FEM document")
        material, actual, mark = create_orthotropic(
            self.session,
            self.nxopen,
            fem,
            conductivities=conductivities_w_m_k,
            density=density_kg_m3,
            heat_capacity=heat_capacity_j_kg_k,
            name=name,
            provenance=provenance,
        )
        self._history.append(
            {
                "mark": mark,
                "part_id": self._part_id(fem),
                "operation_id": self._current_operation,
                "method": "nx_sim_orthotropic_material",
            }
        )
        return {"material": self._reference(material, "material", fem, name), **actual}

    def _sim_variant_plan(self, document, folder, name, saved_snapshot=False):
        from nx_mcp.simcenter.dependencies import inspect_direct
        from nx_mcp.simcenter.variant_plan import plan_variant

        sim = self.objects.resolve(document, expected_kind="part")
        return plan_variant(
            self.workspace,
            inspect_direct(self.session, sim, self.workspace),
            folder=folder,
            name=name,
            saved_snapshot=saved_snapshot,
            loaded_paths=[p.FullPath for p in self.session.Parts],
        )

    def _sim_variant_receipt(self, folder, expected_plan_sha256):
        from nx_mcp.simcenter.variant_clone import read_clone_receipt

        return read_clone_receipt(self.workspace, folder, expected_plan_sha256)

    def _sim_variant_create(
        self, document, folder, name, expected_plan_sha256, saved_snapshot=False
    ):
        from nx_mcp.simcenter.variant_clone import execute_clone_plan

        target = self.workspace.resolve(folder)
        if target.exists():
            return self._sim_variant_receipt(str(target), expected_plan_sha256)
        plan = self._sim_variant_plan(document, str(target), name, saved_snapshot)
        if plan["plan_sha256"] != expected_plan_sha256:
            raise NXToolError(
                "NX_SIM_PLAN_MISMATCH",
                "Source files or variant arguments changed since planning",
                details={
                    "mutation_outcome": "not_started",
                    "next_step": "Inspect a new variant plan",
                },
            )
        return execute_clone_plan(self.session, self.workspace, plan)

    def _sim_close(self, document):
        import NXOpen as nx
        import NXOpen.CAE as cae

        from nx_mcp.assembly_loading import dependent_assemblies
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        require_solver_idle()
        part = self.objects.resolve(document, expected_kind="part")
        if not isinstance(part, (cae.FemPart, cae.SimPart)):
            raise NXToolError(
                "NX_SIM_DOCUMENT_TYPE",
                "Select a loaded FEM or SIM",
                details={"mutation_outcome": "not_started"},
            )
        self.workspace.resolve(part.FullPath)
        if part.IsModified:
            raise NXToolError(
                "NX_SIM_UNSAVED_DOCUMENT",
                "Save approved analysis changes explicitly before closing",
                details={"mutation_outcome": "not_started"},
            )
        parents = set(dependent_assemblies(self, part))
        if isinstance(part, cae.FemPart):
            for other in self.session.Parts:
                if isinstance(other, cae.SimPart) and other.FemPart == part:
                    parents.add(other.FullPath)
        if parents:
            raise NXToolError(
                "NX_SIM_DOCUMENT_IN_USE",
                "Loaded documents depend on this analysis part",
                details={"mutation_outcome": "not_started", "dependent_documents": sorted(parents)},
            )
        loaded = {int(p.Tag): self._reference(p, "part", p, "part") for p in self.session.Parts}
        flags = {int(p.Tag): bool(p.IsModified) for p in self.session.Parts}
        target_tag = int(part.Tag)
        failure = None
        try:
            part.Close(
                nx.BasePart.CloseWholeTree.FalseValue,
                nx.BasePart.CloseModified.DontCloseModified,
                None,
            )
        except Exception as error:
            failure = error
        remaining = {int(p.Tag): p for p in self.session.Parts}
        closed = [ref for tag, ref in loaded.items() if tag not in remaining]
        closed_ids = {r["part_id"] for r in closed}
        for tag, ref in loaded.items():
            if tag not in remaining:
                self.objects.invalidate_part(ref["part_id"])
                self._part_generations.pop(tag, None)
        self._history = [h for h in self._history if h["part_id"] not in closed_ids]
        self._checkpoints = {
            k: v for k, v in self._checkpoints.items() if v["part_id"] not in closed_ids
        }
        changed = [
            loaded[tag]["owner_part_path"]
            for tag, p in remaining.items()
            if tag in flags and bool(p.IsModified) != flags[tag]
        ]
        if failure is not None or target_tag in remaining or changed:
            raise NXToolError(
                "NX_SIM_CLOSE_INCOMPLETE",
                "Native close did not complete cleanly; inspect current documents",
                nx_code=getattr(failure, "ErrorCode", None),
                details={
                    "mutation_outcome": "partial",
                    "closed_parts": closed,
                    "target_still_loaded": target_tag in remaining,
                    "changed_remaining_flags": changed,
                },
            )
        return {
            "closed_parts": closed,
            "closed_count": len(closed),
            "remaining_count": len(remaining),
            "saved": False,
            "discarded_modified_parts": False,
            "work_path": self.session.Parts.BaseWork.FullPath
            if self.session.Parts.BaseWork
            else None,
            "display_path": self.session.Parts.BaseDisplay.FullPath
            if self.session.Parts.BaseDisplay
            else None,
            "warnings": [
                "NX may unload unused dependencies; reacquire document references before continuing"
            ],
        }

    def _sim_open(self, path):
        from nx_mcp.simcenter.documents import open_document
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        require_solver_idle()
        result = open_document(self.session, self.workspace, path)
        part = result.pop("part")
        return {"document": self._reference(part, "part", part, "part"), **result}

    def _sim_scenario_apply(
        self, document, path, region_targets, expected_preview_sha256, format="json", metadata=None
    ):
        from nx_mcp.simcenter.scenario_apply import apply_scenario
        from nx_mcp.simcenter.scenario_import import verify_preview
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        plan = self._sim_scenario_preview(document, path, region_targets, format, metadata)
        verify_preview(expected_preview_sha256, plan["preview_sha256"])
        require_solver_idle()
        sim = self.objects.resolve(document, expected_kind="part")
        component = list(sim.ComponentAssembly.RootComponent.GetChildren())[0]
        targets = [
            component.FindOccurrence(self.objects.resolve(a["target"], expected_kind="body"))
            for a in plan["assignments"]
        ]
        if any(t is None for t in targets):
            raise NXToolError(
                "NX_SIM_SELECTION_OWNER", "Scenario selection changed before application"
            )
        result = apply_scenario(self.session, sim, plan, targets)
        for row in result["loads"]:
            row["load"] = self._reference(row["load"], "simulation_load", sim, "heat load")
        return result

    def _sim_scenario_preview(self, document, path, region_targets, format="json", metadata=None):
        import hashlib

        import NXOpen.CAE as cae

        from nx_mcp.simcenter.scenario_import import (
            assignment_plan,
            parse_scenario,
            preview_identity,
        )

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a loaded SIM document")
        source = self.workspace.resolve(path)
        if not source.is_file():
            raise NXToolError("NX_NOT_FOUND", "Scenario must be an existing workspace file")
        with source.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        try:
            plan = assignment_plan(parse_scenario(raw, format, metadata), region_targets)
        except ValueError as error:
            raise NXToolError(
                "NX_SIM_SCENARIO_INVALID",
                str(error),
                details={
                    "mutation_outcome": "not_started",
                    "next_step": "Correct the scenario or exact region mapping, then preview again",
                },
            ) from error
        root = sim.ComponentAssembly.RootComponent
        children = list(root.GetChildren()) if root else []
        if len(children) != 1 or children[0].Prototype != sim.FemPart:
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Preview requires a direct single-FEM SIM")
        resolved = []
        for assignment in plan["assignments"]:
            body = self.objects.resolve(assignment["target"], expected_kind="body")
            if body.OwningPart != sim.FemPart:
                raise NXToolError(
                    "NX_SIM_SELECTION_OWNER", "Heat target must belong to this SIM's FEM"
                )
            occurrence = children[0].FindOccurrence(body)
            if occurrence is None:
                raise NXToolError(
                    "NX_SIM_SELECTION_OWNER", "No SIM occurrence for the selected body"
                )
            resolved.append(int(occurrence.Tag))
            assignment["resolved_body"] = self._reference(body, "body", sim.FemPart, "body")
        if len(set(resolved)) != len(resolved):
            raise NXToolError(
                "NX_SIM_DUPLICATE_HEAT_SOURCE", "Object aliases resolve to the same heat target"
            )
        return {
            **plan,
            "source_path": str(source),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "preview_sha256": preview_identity(
                document, hashlib.sha256(raw).hexdigest(), plan["scenario_sha256"], region_targets
            ),
            "target_resolution": "live_FEM_bodies_verified",
            "document": self._reference(sim, "part", sim, "part"),
            "existing_load_conflicts": "not_checked",
            "ready_to_apply": False,
            "next_step": "Inspect existing loads and boundaries before applying the scenario",
        }

    def _sim_job_logs(self, job_id, job_folder="simcenter-jobs", offset=0, limit=20):
        from nx_mcp.simcenter.jobs import JobStore
        from nx_mcp.simcenter.log_reader import list_job_logs

        return list_job_logs(
            JobStore(self.workspace, job_folder), job_id, offset=offset, limit=limit
        )

    def _sim_job_log(
        self,
        job_id,
        log_name,
        job_folder="simcenter-jobs",
        offset=0,
        maximum_bytes=8192,
        file_identity=None,
    ):
        from nx_mcp.simcenter.jobs import JobStore
        from nx_mcp.simcenter.log_reader import read_job_log

        return read_job_log(
            JobStore(self.workspace, job_folder),
            job_id,
            log_name,
            offset=offset,
            maximum_bytes=maximum_bytes,
            file_identity=file_identity,
        )

    def _sim_head_loss(self, document, opening, coefficient, expected_coefficient=None, name=None):
        from nx_mcp.simcenter.head_loss import set_opening_head_loss

        sim = self.objects.resolve(document, expected_kind="part")
        boundary = self.objects.resolve(opening, expected_kind="simulation_object")
        result = set_opening_head_loss(
            self.session, sim, boundary, coefficient, expected_coefficient, name
        )
        result["opening"] = self._reference(boundary, "simulation_object", sim, "opening")
        return result

    def _sim_external_temperature(self, document, boundaries, name, temperature_c):
        from nx_mcp.simcenter.external_conditions import assign_external_temperature

        sim = self.objects.resolve(document, expected_kind="part")
        selected = [
            self.objects.resolve(ref, expected_kind="simulation_object") for ref in boundaries
        ]
        result = assign_external_temperature(self.session, sim, selected, name, temperature_c)
        table = result.pop("table")
        result["conditions"] = self._reference(
            table, "simulation_object", sim, "external conditions"
        )
        result["boundaries"] = [
            self._reference(b, "simulation_object", sim, "boundary") for b in selected
        ]
        return result

    def _sim_assign_fan(self, document, inlet, field):
        from nx_mcp.simcenter.fan_boundary import assign_static_fan

        sim = self.objects.resolve(document, expected_kind="part")
        boundary = self.objects.resolve(inlet, expected_kind="simulation_object")
        table = self.objects.resolve(field, expected_kind="simulation_field")
        result = assign_static_fan(self.session, sim, boundary, table)
        result["inlet"] = self._reference(boundary, "simulation_object", sim, "inlet")
        result["field"] = self._reference(table, "simulation_field", sim, "field")
        # Native tags are internal readback evidence, not public selection handles.
        result["binding"].pop("field_tag", None)
        result["previous_binding"].pop("field_tag", None)
        return result

    def _sim_scalar_table(self, document, name, axis, quantity, samples, provenance):
        from nx_mcp.simcenter.scalar_tables import create

        sim = self.objects.resolve(document, expected_kind="part")
        result = create(
            self.session,
            sim,
            {
                "name": name,
                "axis": axis,
                "quantity": quantity,
                "samples": samples,
                "provenance": provenance,
            },
        )
        table = result.pop("table")
        return {"field": self._reference(table, "simulation_field", sim, "field"), **result}

    def _sim_scalar_tables(self, document, offset=0, limit=20, include_samples=False):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter import scalar_tables

        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(include_samples) is not bool
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "offset >= 0, limit 1..100, include_samples boolean"
            )
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        fields = sorted(
            [f for f in sim.FieldManager.Fields if scalar_tables.registered(f)],
            key=lambda f: (f.Name, int(f.Tag)),
        )
        rows = []
        for field in fields[offset : offset + limit]:
            row = scalar_tables.compact(scalar_tables.inspect(sim, field), include_samples)
            row["field"] = self._reference(field, "simulation_field", sim, "field")
            rows.append(row)
        return {
            "tables": rows,
            "total": len(fields),
            "next_offset": offset + limit if offset + limit < len(fields) else None,
            "result_freshness": "not_verified",
        }

    def _sim_fan_table(
        self,
        document,
        name,
        points,
        pressure_convention,
        rpm,
        reference_density_kg_m3,
        stall_region,
        provenance_kind,
        provenance_source,
        scaling_rpm_range=None,
        scaling_validity=None,
    ):
        from nx_mcp.simcenter.fan_field import create_fan_table

        if (
            not isinstance(points, (list, tuple))
            or not 2 <= len(points) <= 1000
            or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points)
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Supply 2..1000 [flow_m3_s, pressure_Pa] pairs"
            )
        sim = self.objects.resolve(document, expected_kind="part")
        result = create_fan_table(
            self.session,
            sim,
            {
                "name": name,
                "points": [{"flow_m3_s": q, "pressure_Pa": p} for q, p in points],
                "pressure_convention": pressure_convention,
                "rpm": rpm,
                "reference_density_kg_m3": reference_density_kg_m3,
                "stall_region": stall_region,
                "provenance": {"kind": provenance_kind, "source": provenance_source},
                "scaling_rpm_range": scaling_rpm_range,
                "scaling_validity": scaling_validity,
            },
        )
        table = result.pop("table")
        result["field"] = self._reference(table, "simulation_field", sim, "field")
        return result

    def _sim_fan_tables(self, document, offset=0, limit=20, include_samples=False):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.fan_field import inspect_fan_table

        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(include_samples) is not bool
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "offset >= 0, limit 1..100, include_samples boolean"
            )
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        fields = [
            field
            for field in sim.FieldManager.Fields
            if field.HasUserAttribute(
                "NX_MCP_FAN_MANIFEST_HEADER", self.nxopen.NXObject.AttributeType.String, -1
            )
        ]
        rows = []
        for field in fields[offset : offset + limit]:
            row = inspect_fan_table(sim, field)
            row["field"] = self._reference(field, "simulation_field", sim, "field")
            row["sample_count"] = len(row["manifest"]["points"])
            if not include_samples:
                row["manifest"].pop("points")
                row.pop("readback")
            rows.append(row)
        return {
            "tables": rows,
            "total": len(fields),
            "next_offset": offset + limit if offset + limit < len(fields) else None,
            "result_freshness": "not_verified",
        }

    def _sim_steps(
        self,
        document,
        solution,
        offset=0,
        limit=20,
        include_properties=False,
        include_membership=False,
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.properties import read_properties

        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(include_properties) is not bool
            or type(include_membership) is not bool
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "offset >= 0, limit 1..100, expansion flags boolean"
            )
        sim = self.objects.resolve(document, expected_kind="part")
        sol = self.objects.resolve(solution, expected_kind="simulation_solution")
        if (
            not isinstance(sim, cae.SimPart)
            or sol.OwningPart != sim
            or sol not in list(sim.Simulation.Solutions)
        ):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Solution must belong to the selected SIM")
        rows = []
        for index in range(offset, min(offset + limit, sol.StepCount)):
            step = sol.GetStepByIndex(index)
            row = {
                "step": self._reference(step, "simulation_step", sim, "step"),
                "index": index,
                "step_type": step.StepType,
                "active_in_solution": step == sol.ActiveStep,
            }
            if include_properties:
                row["properties"] = read_properties(step.PropertyTable, self.nxopen)
            if include_membership:
                from nx_mcp.simcenter.boundary_state import capture_step_membership

                row["membership"] = capture_step_membership(sim, step)
            rows.append(row)
        return {
            "solution": self._reference(sol, "simulation_solution", sim, "solution"),
            "solution_active": sol == sim.Simulation.ActiveSolution,
            "steps": rows,
            "total": sol.StepCount,
            "next_offset": offset + limit if offset + limit < sol.StepCount else None,
            "index_lifetime": "Reacquire after step creation, removal or reordering",
            "result_freshness": "not_verified",
        }

    def _sim_initial_conditions(self, document, mode, temperature_k=None):
        from nx_mcp.simcenter.initial_conditions import configure

        sim = self.objects.resolve(document, expected_kind="part")
        try:
            result = configure(self.session, sim, mode, temperature_k)
        except ValueError as error:
            raise NXToolError("NX_INVALID_ARGUMENT", str(error)) from error
        result["solution"] = self._reference(
            sim.Simulation.ActiveSolution, "simulation_solution", sim, "solution"
        )
        return result

    def _sim_transient_setup(
        self, document, output_times_s, max_temperature_change_k=0.05, min_time_step_s=0.01
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.time_controls import configure_transient_steps

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        solution = sim.Simulation.ActiveSolution
        if (
            solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType != "Thermal"
        ):
            raise NXToolError("NX_SIM_UNSUPPORTED", "Requires NX MULTIPHYSICS Thermal")
        try:
            return configure_transient_steps(
                self.session,
                sim,
                output_times_s,
                max_temperature_change_k=max_temperature_change_k,
                min_time_step_s=min_time_step_s,
            )
        except ValueError as error:
            raise NXToolError("NX_INVALID_ARGUMENT", str(error)) from error

    def _sim_solutions(
        self,
        document,
        offset=0,
        limit=20,
        include_properties=False,
        include_execution_options=False,
        include_membership=False,
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.properties import read_properties

        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(include_properties) is not bool
            or type(include_execution_options) is not bool
            or type(include_membership) is not bool
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "offset >= 0, limit 1..100, expansion flags must be boolean"
            )
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        solutions = list(sim.Simulation.Solutions)
        rows = []
        for sol in solutions[offset : offset + limit]:
            row = {
                "solution": self._reference(sol, "simulation_solution", sim, "solution"),
                "solver": sol.SolverType,
                "analysis": sol.AnalysisType,
                "solution_type": sol.SolutionType,
                "active": sol == sim.Simulation.ActiveSolution,
                "step_count": sol.StepCount,
            }
            if include_properties:
                row["properties"] = read_properties(sol.PropertyTable, self.nxopen)
            if include_membership:
                from nx_mcp.simcenter.boundary_state import capture_effective_membership

                row["membership"] = capture_effective_membership(sim, sol)
            if include_execution_options:
                options = sol.SolverOptionsPropertyTable
                row["execution_options"] = (
                    None
                    if options is None
                    else {
                        "descriptor_neutral_name": options.DescriptorNeutralName,
                        "descriptor_specific_name": options.DescriptorSpecificName,
                        "properties": read_properties(options, self.nxopen),
                        "settings_applied_by_call": False,
                        "licence_checkout_tested": False,
                    }
                )
            rows.append(row)
        return {
            "solutions": rows,
            "total": len(solutions),
            "next_offset": offset + limit if offset + limit < len(solutions) else None,
            "result_freshness": "not_verified",
        }

    def _sim_select_solution(self, document, solution):
        import NXOpen.CAE as cae

        sim = self.objects.resolve(document, expected_kind="part")
        sol = self.objects.resolve(solution, expected_kind="simulation_solution")
        if not isinstance(sim, cae.SimPart) or self.session.Parts.BaseWork != sim:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
        if sol.OwningPart != sim or sol not in list(sim.Simulation.Solutions):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Solution does not belong to this SIM")
        previous = sim.Simulation.ActiveSolution
        if previous != sol:
            try:
                sim.Simulation.ActiveSolution = sol
                if sim.Simulation.ActiveSolution != sol:
                    raise ValueError("Active solution readback differs")
            except Exception as error:
                try:
                    sim.Simulation.ActiveSolution = previous
                    restored = sim.Simulation.ActiveSolution == previous
                except Exception:
                    restored = False
                raise NXToolError(
                    "NX_SIM_ACTIVATION_FAILED",
                    "Solution selection failed",
                    nx_code=getattr(error, "ErrorCode", None),
                    details={"mutation_outcome": "rolled_back" if restored else "partial"},
                ) from error
        return {
            "solution": self._reference(sol, "simulation_solution", sim, "solution"),
            "active": True,
            "already_active": previous == sol,
            "saved": False,
            "result_freshness": "not_verified",
        }

    def _sim_mesh_quality(self, document, include_settings=False):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.quality import check_mesh_quality

        if type(include_settings) is not bool:
            raise NXToolError("NX_INVALID_ARGUMENT", "include_settings must be boolean")
        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a standalone FEM document")
        meshes = list(fem.BaseFEModel.MeshManager.GetMeshes())
        if not meshes:
            raise NXToolError("NX_SIM_NO_MESH", "Generate a mesh before checking quality")
        result = check_mesh_quality(fem, meshes)
        if result["element_count"] <= 0:
            raise NXToolError("NX_SIM_EMPTY_CHECK", "Native checker tested no elements")
        if not include_settings:
            result.pop("settings")
        return {
            "document": self._reference(fem, "part", fem, "part"),
            "mesh_count": len(meshes),
            "error_occurrences": sum(t["errors"] for t in result["tests"]),
            "warning_occurrences": sum(t["warnings"] for t in result["tests"]),
            "count_semantics": "Sum across tests; an element can contribute to multiple tests",
            "solve_readiness": "not_established",
            **result,
        }

    def _sim_show_pressure(
        self, document, field="pressure", loadcase_index=0, iteration_index=0, name="MCP pressure"
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.postviews import show_pressure

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        if not hasattr(self, "_sim_post_result_handles"):
            self._sim_post_result_handles = {}
        return show_pressure(
            self.session,
            sim,
            self._sim_post_result_handles,
            field=field,
            loadcase_index=loadcase_index,
            iteration_index=iteration_index,
            name=name,
        )

    def _sim_show_temperature(
        self, document, loadcase_index=0, iteration_index=0, name="MCP temperature"
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.postviews import show_temperature

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        if not hasattr(self, "_sim_post_result_handles"):
            self._sim_post_result_handles = {}
        return show_temperature(
            self.session,
            sim,
            self._sim_post_result_handles,
            loadcase_index=loadcase_index,
            iteration_index=iteration_index,
            name=name,
        )

    def _sim_save(self, document):
        from nx_mcp.simcenter.documents import save_document

        part = self.objects.resolve(document, expected_kind="part")
        return save_document(self.session, self.workspace, part)

    def _sim_distributed_heat(
        self, document, targets, kind, value, name, provenance, overlap_policy="reject"
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.distributed_heat import (
            create_distributed_heat,
            preflight,
            validate_density,
        )

        with preflight():
            validate_density(kind, value)
            sim = self.objects.resolve(document, expected_kind="part")
            if not isinstance(sim, cae.SimPart):
                raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
            self.workspace.resolve(sim.FullPath)
            if (
                not isinstance(targets, list)
                or not 1 <= len(targets) <= 1000
                or any(not isinstance(t, str) for t in targets)
                or len(set(targets)) != len(targets)
            ):
                raise NXToolError("NX_INVALID_ARGUMENT", "Supply 1..1000 distinct typed target IDs")
            target_kind = "face" if kind == "surface_flux" else "body"
            objects = [self.objects.resolve(t, expected_kind=target_kind) for t in targets]
            if target_kind == "body":
                components = list(sim.ComponentAssembly.RootComponent.GetChildren())
                if len(components) != 1 or components[0].Prototype != sim.FemPart:
                    raise NXToolError(
                        "NX_SIM_UNSUPPORTED", "Select a SIM with one direct FEM occurrence"
                    )
                converted = []
                for obj in objects:
                    if obj.OwningPart == sim.FemPart:
                        obj = components[0].FindOccurrence(obj)
                    if obj is None or obj.OwningPart != sim:
                        raise NXToolError(
                            "NX_SIM_SELECTION_OWNER", "Body is outside this SIM's FEM"
                        )
                    converted.append(obj)
                objects = converted
        result = create_distributed_heat(
            self.session,
            sim,
            objects,
            kind=kind,
            value=value,
            name=name,
            provenance=provenance,
            overlap_policy=overlap_policy,
        )
        load = result.pop("load")
        return {
            "load": self._reference(load, "simulation_load", sim, kind),
            "targets": [self._reference(t, target_kind, sim, target_kind) for t in objects],
            **result,
        }

    def _sim_gravity(self, document, bodies, acceleration_m_s2, name):
        from nx_mcp.simcenter.gravity import create, validate

        validate(acceleration_m_s2, name)
        sim = self.objects.resolve(document, expected_kind="part")
        if (
            not isinstance(bodies, list)
            or not bodies
            or any(not isinstance(b, str) for b in bodies)
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply FEM prototype body IDs")
        prototypes = [self.objects.resolve(b, expected_kind="body") for b in bodies]
        if not hasattr(sim, "Simulation"):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM")
        components = list(sim.ComponentAssembly.RootComponent.GetChildren())
        if (
            len(components) != 1
            or components[0].Prototype != sim.FemPart
            or any(b.OwningPart != sim.FemPart for b in prototypes)
        ):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Select bodies from the SIM's direct FEM")
        if {int(body.Tag) for body in prototypes} != {int(body.Tag) for body in sim.FemPart.Bodies}:
            raise NXToolError(
                "NX_SIM_UNSUPPORTED",
                "Select every FEM body: selective gravity is not verified in the coupled solver export",
                details={"mutation_outcome": "not_started"},
            )
        result = create(
            self.session,
            sim,
            [components[0].FindOccurrence(b) for b in prototypes],
            acceleration_m_s2,
            name,
        )
        load = result.pop("load")
        return {
            "load": self._reference(load, "simulation_load", sim, "gravity"),
            "bodies": [self._reference(b, "body", sim.FemPart, "body") for b in prototypes],
            **result,
        }

    def _sim_heat_power(self, document, body, power_w, name, provenance, overlap_policy="reject"):
        from nx_mcp.simcenter.heat_loads import create_body_power

        sim = self.objects.resolve(document, expected_kind="part")
        solution = getattr(getattr(sim, "Simulation", None), "ActiveSolution", None)
        if (
            self.session.Parts.BaseWork != sim
            or solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType not in ("Thermal", "Coupled Thermal-Flow")
        ):
            raise NXToolError(
                "NX_SIM_UNSUPPORTED",
                "Activate an NX MULTIPHYSICS Thermal or Coupled Thermal-Flow SIM for body power assignment",
                details={"mutation_outcome": "not_started"},
            )
        prototype = self.objects.resolve(body, expected_kind="body")
        components = list(sim.ComponentAssembly.RootComponent.GetChildren())
        if (
            prototype.OwningPart != sim.FemPart
            or len(components) != 1
            or components[0].Prototype != sim.FemPart
        ):
            raise NXToolError(
                "NX_SIM_SELECTION_OWNER",
                "Select a prototype body from this SIM's direct FEM face inventory",
            )
        occurrence = components[0].FindOccurrence(prototype)
        result = create_body_power(
            self.session, sim, occurrence, power_w, name, provenance, overlap_policy=overlap_policy
        )
        load = result.pop("load")
        return {
            "load": self._reference(load, "simulation_load", sim, "heat load"),
            "target_body": self._reference(occurrence, "body", sim, "body"),
            **result,
        }

    def _sim_heat_schedule(
        self, document, body, field, name, provenance, scale=1.0, overlap_policy="reject"
    ):
        from nx_mcp.simcenter.heat_loads import create_body_power

        sim = self.objects.resolve(document, expected_kind="part")
        solution = getattr(getattr(sim, "Simulation", None), "ActiveSolution", None)
        if (
            self.session.Parts.BaseWork != sim
            or solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType != "Thermal"
        ):
            raise NXToolError(
                "NX_SIM_UNSUPPORTED",
                "Activate an NX MULTIPHYSICS Thermal SIM for body power assignment",
                details={"mutation_outcome": "not_started"},
            )
        schedule_field = self.objects.resolve(field, expected_kind="simulation_field")
        prototype = self.objects.resolve(body, expected_kind="body")
        components = list(sim.ComponentAssembly.RootComponent.GetChildren())
        if (
            prototype.OwningPart != sim.FemPart
            or len(components) != 1
            or components[0].Prototype != sim.FemPart
        ):
            raise NXToolError(
                "NX_SIM_SELECTION_OWNER",
                "Select a prototype body from this SIM's direct FEM face inventory",
            )
        occurrence = components[0].FindOccurrence(prototype)
        result = create_body_power(
            self.session,
            sim,
            occurrence,
            0.0,
            name,
            provenance,
            overlap_policy=overlap_policy,
            schedule_field=schedule_field,
            schedule_scale=scale,
        )
        load = result.pop("load")
        return {
            "load": self._reference(load, "simulation_load", sim, "heat load"),
            "target_body": self._reference(occurrence, "body", sim, "body"),
            **result,
        }

    def _sim_constraints(
        self, document, offset=0, limit=20, include_properties=False, include_targets=False
    ):
        return SimcenterMixin._sim_boundary_inventory(
            self,
            document,
            offset,
            limit,
            include_properties,
            include_targets,
            collection="constraints",
        )

    def _sim_loads(
        self, document, offset=0, limit=20, include_properties=False, include_targets=False
    ):
        return SimcenterMixin._sim_boundary_inventory(
            self, document, offset, limit, include_properties, include_targets, collection="loads"
        )

    def _sim_objects(
        self, document, offset=0, limit=20, include_properties=False, include_targets=False
    ):
        return SimcenterMixin._sim_boundary_inventory(
            self,
            document,
            offset,
            limit,
            include_properties,
            include_targets,
            collection="simulation_objects",
        )

    def _sim_boundary_inventory(
        self,
        document,
        offset=0,
        limit=20,
        include_properties=False,
        include_targets=False,
        collection="constraints",
    ):
        from nx_mcp.simcenter.properties import read_properties

        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be 1..100")
        if any(type(flag) is not bool for flag in (include_properties, include_targets)):
            raise NXToolError("NX_INVALID_ARGUMENT", "Inspection expansion flags must be booleans")
        sim = self.objects.resolve(document, expected_kind="part")
        if self.session.Parts.BaseWork != sim or not hasattr(sim, "Simulation"):
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
        sources = {
            "constraints": ("Constraints", "constraint", "constraint"),
            "loads": ("Loads", "load", "simulation_load"),
            "simulation_objects": ("SimulationObjects", "object", "simulation_object"),
        }
        if collection not in sources:
            raise NXToolError("NX_INVALID_ARGUMENT", "Unsupported boundary collection")
        source_name, reference_key, reference_kind = sources[collection]
        source = getattr(sim.Simulation, source_name)
        constraints = sorted(source, key=lambda bc: (bc.Name, int(bc.Tag)))
        rows = []
        for bc in constraints[offset : offset + limit]:
            row = {
                reference_key: self._reference(bc, reference_kind, sim, reference_key),
                "native_type": type(bc).__name__,
                "target_set_count": bc.TargetSetManager.TargetSetCount,
            }
            if collection == "simulation_objects":
                row["descriptor"] = bc.DescriptorName
                if bc.DescriptorName == "Inlet":
                    wrapper = bc.PropertyTable.GetScalarFieldWrapperPropertyValue("Fan Curve")
                    field = wrapper.GetField() if wrapper else None
                    row["fan_binding"] = {
                        "mode": bc.PropertyTable.GetIntegerPropertyValue("Mode Option"),
                        "field": self._reference(field, "simulation_field", sim, "field")
                        if field
                        else None,
                        "scale_factor": wrapper.GetFieldScaleFactor() if wrapper else None,
                        "interpretation": "mode 5 static fan inlet verified for NX 2606 Flow and Coupled Thermal-Flow",
                    }
                if bc.DescriptorName == "Opening" and include_properties:
                    table = bc.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
                    row["head_loss"] = None
                    if table is not None:
                        coefficient, unit = table.PropertyTable.GetBaseScalarWithDataPropertyValue(
                            "Head Loss Coefficient"
                        )
                        row["head_loss"] = {
                            "table_name": table.Name,
                            "coefficient": coefficient,
                            "units": unit.Name if unit else "dimensionless",
                            "convention": "native Head Loss coefficient; general pressure-loss convention not independently verified",
                        }
            for title, key in (
                ("NX_MCP_PROVENANCE", "provenance"),
                ("NX_MCP_COEFFICIENT_BASIS", "coefficient_basis"),
                ("NX_MCP_ENERGY_ACCOUNTING", "energy_accounting"),
                ("NX_MCP_HEAT_OVERLAP_POLICY", "overlap_policy"),
            ):
                row[key] = (
                    bc.GetStringUserAttribute(title, -1)
                    if bc.HasUserAttribute(title, self.nxopen.NXObject.AttributeType.String, -1)
                    else None
                )
            if include_properties:
                row["properties"] = read_properties(bc.PropertyTable, self.nxopen)
            if include_targets:
                targets = []
                for index in range(bc.TargetSetManager.TargetSetCount):
                    _, members = bc.TargetSetManager.GetTargetSetMembers(index)
                    slot_count = len(members)
                    members = [member for member in members if member is not None]
                    values = []
                    for member in members[:100]:
                        obj = member.Obj
                        item = {
                            "native_type": type(obj).__name__,
                            "subtype": str(member.SubType),
                            "sub_id": member.SubId,
                        }
                        if (
                            obj is not None
                            and "Face" in type(obj).__name__
                            and obj.OwningPart == sim
                        ):
                            item["face"] = self._reference(obj, "face", sim, "face")
                        elif (
                            obj is not None
                            and "Body" in type(obj).__name__
                            and obj.OwningPart == sim
                        ):
                            item["body"] = self._reference(obj, "body", sim, "body")
                        else:
                            item["reference_status"] = "unsupported_target_kind"
                        values.append(item)
                    targets.append(
                        {
                            "index": index,
                            "count": len(members),
                            "native_slot_count": slot_count,
                            "empty_slot_count": slot_count - len(members),
                            "members": values,
                            "truncated": len(members) > 100,
                        }
                    )
                row["target_sets"] = targets
            rows.append(row)
        return {
            collection: rows,
            "total": len(constraints),
            "next_offset": offset + limit if offset + limit < len(constraints) else None,
            "scope": "SIM "
            + collection
            + " collection only; other boundary collections are separate",
        }

    def _sim_steady_thermal_controls(
        self,
        document,
        maximum_temperature_change_k,
        iteration_limit=10000,
        relative_heat_balance=None,
    ):
        from nx_mcp.simcenter.steady_controls import configure

        sim = self.objects.resolve(document, expected_kind="part")
        result = configure(
            self.session, sim, maximum_temperature_change_k, iteration_limit, relative_heat_balance
        )
        owner = result.pop("table")
        return {
            "parameter_table": self._reference(
                owner, "simulation_parameter_table", sim, "thermal parameters"
            ),
            "solution": self._reference(
                sim.Simulation.ActiveSolution, "simulation_solution", sim, "solution"
            ),
            **result,
        }

    def _sim_contact(self, document, primary_faces, secondary_faces, mode, value, name, provenance):
        from nx_mcp.simcenter.contact import create_contact

        sim = self.objects.resolve(document, expected_kind="part")
        for ids in (primary_faces, secondary_faces):
            if (
                not isinstance(ids, list)
                or not 1 <= len(ids) <= 1000
                or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != len(ids)
            ):
                raise NXToolError(
                    "NX_INVALID_ARGUMENT", "Supply 1..1000 distinct face IDs per region"
                )
        primary = [self.objects.resolve(i, expected_kind="face") for i in primary_faces]
        secondary = [self.objects.resolve(i, expected_kind="face") for i in secondary_faces]
        result = create_contact(
            self.session, sim, primary, secondary, mode, value, name, provenance
        )
        boundary = result.pop("boundary")
        return {
            "contact": self._reference(boundary, "simulation_object", sim, "contact"),
            "primary_faces": [self._reference(f, "face", sim, "face") for f in primary],
            "secondary_faces": [self._reference(f, "face", sim, "face") for f in secondary],
            **result,
        }

    def _sim_radiation_object(self, document, faces, name, provenance, **options):
        from nx_mcp.simcenter.radiation_objects import create

        sim = self.objects.resolve(document, expected_kind="part")
        if not hasattr(sim, "Simulation"):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        if (
            not isinstance(faces, list)
            or not 1 <= len(faces) <= 1000
            or len(set(faces)) != len(faces)
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Supply 1..1000 distinct SIM face IDs",
                details={"mutation_outcome": "not_started"},
            )
        targets = [self.objects.resolve(face, expected_kind="face") for face in faces]
        result = create(self.session, sim, targets, name, provenance, **options)
        boundary = result.pop("boundary")
        return {
            "object": self._reference(boundary, "simulation_object", sim, "radiation"),
            "faces": [self._reference(face, "face", sim, "face") for face in targets],
            **result,
        }

    def _sim_emissivity_override(self, document, faces, emissivity, name, provenance, side="both"):
        return SimcenterMixin._sim_radiation_object(
            self,
            document,
            faces,
            name,
            provenance,
            kind="emissivity",
            emissivity=emissivity,
            side=side,
        )

    def _sim_enclosure_radiation(
        self, document, faces, name, provenance, include_radiative_environment=True
    ):
        return SimcenterMixin._sim_radiation_object(
            self,
            document,
            faces,
            name,
            provenance,
            kind="enclosure",
            include_environment=include_radiative_environment,
        )

    def _sim_environment_radiation(
        self,
        document,
        faces,
        effective_emissivity,
        name,
        provenance,
        temperature_source="radiative_ambient",
        temperature_k=None,
    ):
        from nx_mcp.simcenter.radiation import create_environment

        sim = self.objects.resolve(document, expected_kind="part")
        if not hasattr(sim, "Simulation"):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM document")
        if (
            not isinstance(faces, list)
            or not 1 <= len(faces) <= 1000
            or len(set(faces)) != len(faces)
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Supply 1..1000 distinct SIM face IDs",
                details={"mutation_outcome": "not_started"},
            )
        targets = [self.objects.resolve(face, expected_kind="face") for face in faces]
        result = create_environment(
            self.session,
            sim,
            targets,
            effective_emissivity,
            name,
            provenance,
            temperature_source,
            temperature_k,
        )
        boundary = result.pop("boundary")
        return {
            "constraint": self._reference(boundary, "constraint", sim, "radiation"),
            "faces": [self._reference(face, "face", sim, "face") for face in targets],
            **result,
        }

    def _sim_convection(
        self,
        document,
        faces,
        coefficient_w_m2_k,
        name,
        provenance,
        temperature_source="fluid_ambient",
        temperature_k=None,
    ):
        from nx_mcp.simcenter.boundaries import create_convection

        sim = self.objects.resolve(document, expected_kind="part")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM first")
        solution = getattr(getattr(sim, "Simulation", None), "ActiveSolution", None)
        if (
            solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType != "Thermal"
        ):
            raise NXToolError(
                "NX_SIM_UNSUPPORTED",
                "Assumed convection authoring is restricted to thermal-only solutions; coupled interfaces require separate treatment",
                details={"mutation_outcome": "not_started"},
            )
        if (
            not isinstance(faces, list)
            or not 1 <= len(faces) <= 1000
            or len(set(faces)) != len(faces)
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply 1..1000 distinct SIM face IDs")
        targets = [self.objects.resolve(face, expected_kind="face") for face in faces]
        result = create_convection(
            self.session,
            sim,
            targets,
            coefficient_w_m2_k,
            name,
            provenance,
            temperature_source,
            temperature_k,
        )
        boundary = result.pop("boundary")
        result.pop("committed_face_tags", None)
        return {
            "constraint": self._reference(boundary, "constraint", sim, "convection"),
            "faces": [self._reference(face, "face", sim, "face") for face in targets],
            "solver_launched": False,
            **result,
        }

    def _sim_temperature(self, document, faces, temperature_k, name, provenance):
        from nx_mcp.simcenter.boundaries import create_temperature

        sim = self.objects.resolve(document, expected_kind="part")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM first")
        solution = getattr(getattr(sim, "Simulation", None), "ActiveSolution", None)
        if (
            solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType != "Thermal"
        ):
            raise NXToolError(
                "NX_SIM_UNSUPPORTED",
                "Prescribed temperature authoring is restricted to thermal-only solutions; coupled interfaces require separate treatment",
                details={"mutation_outcome": "not_started"},
            )
        if (
            not isinstance(faces, list)
            or not 1 <= len(faces) <= 1000
            or len(set(faces)) != len(faces)
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply 1..1000 distinct SIM face IDs")
        targets = [self.objects.resolve(face, expected_kind="face") for face in faces]
        result = create_temperature(self.session, sim, targets, temperature_k, name, provenance)
        boundary = result.pop("boundary")
        result.pop("committed_face_tags", None)
        return {
            "constraint": self._reference(boundary, "constraint", sim, "temperature"),
            "faces": [self._reference(face, "face", sim, "face") for face in targets],
            "solver_launched": False,
            **result,
        }

    def _sim_face_size(self, document, faces, size_mm):
        from nx_mcp.simcenter.local_size import create

        fem = self.objects.resolve(document, expected_kind="part")
        try:
            return create(self, fem, faces, size_mm)
        except ValueError as error:
            raise NXToolError("NX_INVALID_ARGUMENT", str(error)) from error

    def _sim_face_size_edit(self, document, control, size_mm):
        from nx_mcp.simcenter.local_size import edit

        fem = self.objects.resolve(document, expected_kind="part")
        target = self.objects.resolve(control, expected_kind="simulation_mesh_control")
        try:
            return edit(self, fem, target, size_mm)
        except ValueError as error:
            raise NXToolError("NX_INVALID_ARGUMENT", str(error)) from error

    def _sim_mesh_state(self, document, maximum_entities=200000):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.mesh_state import capture

        part = self.objects.resolve(document, expected_kind="part")
        if self.session.Parts.BaseWork != part:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the requested FEM or SIM")
        fem = part.FemPart if isinstance(part, cae.SimPart) else part
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_UNSUPPORTED", "Select a standalone FEM or its active SIM")
        try:
            result = capture(fem, maximum_entities=maximum_entities)
        except NXToolError:
            raise
        except ValueError as error:
            raise NXToolError("NX_SIM_MESH_STATE_INVALID", str(error)) from error
        except Exception as error:
            raise NXToolError(
                "NX_SIM_MESH_STATE_UNAVAILABLE",
                str(error),
                nx_code=getattr(error, "ErrorCode", None),
            ) from error
        return {"document": self._reference(fem, "part", fem, "FEM"), "mesh_state": result}

    def _sim_sync_geometry(self, document):
        from nx_mcp.simcenter.geometry_sync import synchronize

        fem = self.objects.resolve(document, expected_kind="part")
        result = synchronize(self, fem)
        bodies = {int(body.Tag): body for body in fem.Bodies}
        result["unmeshed_bodies"] = [
            self._reference(bodies[tag], "body", fem, "body")
            for tag in result.pop("unmeshed_body_tags")
        ]
        return {"document": self._reference(fem, "part", fem, "FEM"), **result}

    def _sim_remesh(self, document, size_mm=None):
        from nx_mcp.simcenter.remesh import regenerate

        fem = self.objects.resolve(document, expected_kind="part")
        result = regenerate(self, fem, size_mm=size_mm)
        bodies = {int(body.Tag): body for body in fem.Bodies}
        meshes = list(fem.BaseFEModel.MeshManager.GetMeshes())
        for row, mesh in zip(result["settings"], meshes, strict=True):
            row["mesh"] = self._reference(mesh, "simulation_mesh", fem, "mesh")
            row["bodies"] = [
                self._reference(bodies[tag], "body", fem, "body") for tag in row.pop("body_tags")
            ]
        return {"document": self._reference(fem, "part", fem, "FEM"), **result}

    def _sim_mesh_controls(self, document, offset=0, limit=50):
        from nx_mcp.simcenter.mesh_controls import inventory

        fem = self.objects.resolve(document, expected_kind="part")
        return inventory(self.session, fem, self.nxopen, self._reference, offset, limit)

    def _sim_boundary_layers(self, document, faces, first_layer_mm, layers, growth_rate):
        from nx_mcp.simcenter.boundary_layers import create_boundary_layers
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(faces, list) or not 1 <= len(faces) <= 1000:
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply 1..1000 FEM face IDs")
        resolved = [self.objects.resolve(face, expected_kind="face") for face in faces]
        require_solver_idle()
        result = create_boundary_layers(
            self.session,
            fem,
            resolved,
            first_layer_mm=first_layer_mm,
            layers=layers,
            growth_rate=growth_rate,
        )
        result["control"] = self._reference(
            result["control"], "simulation_mesh_control", fem, "control"
        )
        result["faces"] = [self._reference(face, "face", fem, "face") for face in resolved]
        result["results_stale"] = True
        return result

    def _sim_faces(self, document, offset=0, limit=50):
        from nx_mcp.simcenter.selections import face_inventory

        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be 1..100")
        sim = self.objects.resolve(document, expected_kind="part")
        inventory = face_inventory(self.session, sim)
        rows, fem = inventory.pop("rows"), inventory.pop("fem")
        return {
            "faces": [
                {
                    "face": self._reference(row["face"], "face", sim, "face"),
                    "body": self._reference(row["body"], "body", fem, "body"),
                    "bounds": row["bounds"],
                }
                for row in rows[offset : offset + limit]
            ],
            "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "fem_path": fem.FullPath,
            **inventory,
        }

    def _sim_descriptors(self, document, kind="load", offset=0, limit=50, name_contains=None):
        from nx_mcp.simcenter.descriptors import descriptor_inventory

        sim = self.objects.resolve(document, expected_kind="part")
        return descriptor_inventory(sim, kind, offset, limit, name_contains)

    def _sim_observe_job(self, job_id, job_folder="simcenter-jobs", maximum_seconds=3600):
        from nx_mcp.simcenter.observer_worker import ensure_observer

        registry = getattr(self, "_sim_observer_workers", None)
        if registry is None:
            registry = self._sim_observer_workers = {}
        return {
            "job_id": job_id,
            "observer": ensure_observer(
                registry, self.workspace, job_id, job_folder, maximum_seconds
            ),
            "solver_launched": False,
        }

    def _sim_release_job(self, job_id, job_folder="simcenter-jobs"):
        from nx_mcp.simcenter.jobs import JobStore
        from nx_mcp.simcenter.launch_gate import release_launch_gate

        return release_launch_gate(JobStore(self.workspace, job_folder), job_id)

    def _sim_flow_log(self, job_id, log_name, job_folder="simcenter-jobs", offset=0, limit=50):
        from nx_mcp.simcenter.flow_audit import audit_job_flow_log

        return audit_job_flow_log(self.workspace, job_id, log_name, job_folder, offset, limit)

    def _sim_launch(self, document, job_id, job_folder="simcenter-jobs"):
        from nx_mcp.simcenter.native_launch import launch_prepared

        sim = self.objects.resolve(document, expected_kind="part")
        from nx_mcp.simcenter.observer_worker import ensure_observer

        registry = getattr(self, "_sim_observer_workers", None)
        if registry is None:
            registry = self._sim_observer_workers = {}
        try:
            result = launch_prepared(self.session, self.workspace, sim, job_id, job_folder)
        except NXToolError as error:
            if error.code == "NX_SIM_LAUNCH_UNCERTAIN":
                try:
                    error.details["observer"] = ensure_observer(
                        registry, self.workspace, job_id, job_folder
                    )
                except Exception:
                    error.details["observer"] = {
                        "state": "not_started",
                        "solver_relaunch_allowed": False,
                    }
            raise
        try:
            result["observer"] = ensure_observer(registry, self.workspace, job_id, job_folder)
        except Exception as error:
            result["observer"] = {
                "state": "not_started",
                "error_type": type(error).__name__,
                "solver_relaunch_allowed": False,
            }
        return result

    def _sim_prepare_solve(
        self, document, job_id, job_folder="simcenter-jobs", mesh_inspection_limit=200000
    ):
        from nx_mcp.simcenter.preparation import prepare_solve

        sim = self.objects.resolve(document, expected_kind="part")
        return prepare_solve(
            self.session, self.workspace, sim, job_id, job_folder, mesh_inspection_limit
        )

    def _sim_export_input(self, document):
        from nx_mcp.simcenter.input_export import export_flow_input

        sim = self.objects.resolve(document, expected_kind="part")
        return export_flow_input(self.session, self.workspace, sim)

    def _sim_dependencies(self, document, offset=0, limit=50):
        from nx_mcp.simcenter.dependencies import inspect_direct

        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be 1..100")
        sim = self.objects.resolve(document, expected_kind="part")
        result = inspect_direct(self.session, sim, self.workspace)
        rows = result.pop("rows")
        page = []
        for row in rows[offset : offset + limit]:
            part = row.pop("part")
            page.append({"document": self._reference(part, "part", part, "part"), **row})
        return {
            "documents": page,
            "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            **result,
        }

    def _sim_save_as(self, document, path):
        from nx_mcp.simcenter.documents import save_sim_as

        sim = self.objects.resolve(document, expected_kind="part")
        previous_id = self._part_id(sim)
        previous_path = sim.FullPath
        try:
            result = save_sim_as(self.session, self.workspace, sim, path)
        finally:
            # SaveAs can change identity even if subsequent readback fails.
            if sim.FullPath != previous_path:
                self.objects.invalidate_part(previous_id)
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_job_status(
        self,
        job_id,
        job_folder="simcenter-jobs",
        include_manifest=False,
        include_evidence=False,
        check_processes=False,
        include_launch_gate=False,
    ):
        from nx_mcp.simcenter.jobs import JobStore

        if any(
            type(flag) is not bool
            for flag in (include_manifest, include_evidence, check_processes, include_launch_gate)
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Expansion flags must be booleans")
        job = JobStore(self.workspace, job_folder).inspect(job_id)
        result = {
            key: value
            for key, value in job.items()
            if key not in ("manifest", "record", "process_binding_evidence")
        }
        result.update(
            observed_at=job.get("record", {}).get("observed_at"),
            observation_kind="persisted_record",
            live_process_state="not_checked",
            job_folder=str(self.workspace.resolve(job_folder)),
            units=None,
        )
        import os

        observer_key = os.path.normcase(str(self.workspace.resolve(job_folder) / job_id))
        worker = getattr(self, "_sim_observer_workers", {}).get(observer_key)
        result["observer"] = {"tracked_in_this_nx_process": worker is not None}
        if worker is not None:
            result["observer"].update(
                thread_alive=worker["thread"].is_alive(), log_path=str(worker["path"])
            )
        if include_manifest and "manifest" in job:
            result["manifest"] = job["manifest"]
        if include_evidence and "record" in job:
            result["evidence"] = job["record"]["evidence"]
            result["process_binding_evidence"] = job.get("process_binding_evidence")
        if check_processes:
            from nx_mcp.simcenter.job_processes import observe_job_processes

            result["live_processes"] = observe_job_processes(job)
            result["live_process_state"] = result["live_processes"]["state"]
        if include_launch_gate:
            from nx_mcp.simcenter.launch_gate import inspect_launch_gate

            result["launch_gate"] = inspect_launch_gate(self.workspace)
        return result

    def _sim_capabilities(self):
        return inspect_capabilities(self.session)

    def _sim_documents(self, offset=0, limit=20):
        if offset < 0 or not 1 <= limit <= 100:
            raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0 and limit between 1 and 100")
        rows = documents(self.session)
        for row, part in zip(rows, self.session.Parts, strict=True):
            row["document"] = self._reference(part, "part", part, "part")
        return {
            "documents": rows[offset : offset + limit],
            "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
        }

    def _sim_create_benchmark(
        self,
        folder,
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        analysis_type="thermal",
        wall_thickness_mm=None,
        block_origins_mm=None,
    ):
        """Create a new isolated CAD/FEM/SIM set; never save a pre-existing document."""
        import math

        import NXOpen.CAE as cae

        nx = self.nxopen
        if any(
            not math.isfinite(v) or not 0 < v <= 10000 for v in (length_mm, width_mm, height_mm)
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Dimensions must be finite and in (0, 10000] mm"
            )
        configurations = {
            "thermal": ("Thermal", "Thermal", "Conduction"),
            "flow": ("Flow", "Flow", "Flow benchmark"),
            "coupled_thermal_flow": ("Coupled Thermal-Flow", "Thermal-Flow", "Coupled benchmark"),
        }
        if not isinstance(analysis_type, str) or analysis_type not in configurations:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "analysis_type must be thermal, flow or coupled_thermal_flow"
            )
        analysis, solution_type, solution_name = configurations[analysis_type]
        if wall_thickness_mm is not None and (
            type(wall_thickness_mm) not in (int, float)
            or not math.isfinite(wall_thickness_mm)
            or not 0 < wall_thickness_mm < min(length_mm, width_mm, height_mm) / 2
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Wall thickness must leave a positive interior cavity"
            )
        from nx_mcp.simcenter.benchmark_geometry import validate_block_origins

        origins = validate_block_origins(block_origins_mm, (length_mm, width_mm, height_mm))
        if wall_thickness_mm is not None and origins != [(0.0, 0.0, 0.0)]:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Hollow benchmark requires the single default origin"
            )
        target = self.workspace.resolve(folder)
        if target.exists():
            raise NXToolError("NX_SIM_TARGET_EXISTS", "Use a new isolated analysis folder")
        # NX rejects duplicate loaded basenames even when their folders differ.
        # Deterministic folder-specific names allow multiple isolated studies.
        import hashlib

        prefix = "benchmark_" + hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:12]
        paths = {
            "cad": target / f"{prefix}_geometry.prt",
            "fem": target / f"{prefix}_mesh.fem",
            "sim": target / f"{prefix}_analysis.sim",
        }
        old_display, old_work = self.session.Parts.BaseDisplay, self.session.Parts.BaseWork
        opened = []
        target.mkdir(parents=True)
        stage = "cad"
        try:
            cad = self.session.Parts.NewBaseDisplay(
                str(paths["cad"]), nx.BasePart.Units.Millimeters
            )
            opened.append(cad)
            for origin in origins:
                builder = cad.Features.CreateBlockFeatureBuilder(None)
                try:
                    builder.SetOriginAndLengths(
                        nx.Point3d(*origin), str(length_mm), str(width_mm), str(height_mm)
                    )
                    builder.CommitFeature()
                finally:
                    builder.Destroy()
            if len(list(cad.Bodies)) != len(origins):
                raise NXToolError(
                    "NX_SIM_GEOMETRY_MISMATCH", "Created body count differs from requested blocks"
                )
            if wall_thickness_mm is not None:
                wall = float(wall_thickness_mm)
                builder = cad.Features.CreateBlockFeatureBuilder(None)
                try:
                    builder.SetOriginAndLengths(
                        nx.Point3d(wall, wall, wall),
                        str(length_mm - 2 * wall),
                        str(width_mm - 2 * wall),
                        str(height_mm - 2 * wall),
                    )
                    builder.SetBooleanOperationAndTarget(
                        nx.Features.Feature.BooleanType.Subtract, list(cad.Bodies)[0]
                    )
                    builder.CommitFeature()
                finally:
                    builder.Destroy()
                shell_bodies = list(cad.Bodies)
                if len(shell_bodies) != 1 or not shell_bodies[0].IsSolidBody:
                    raise NXToolError(
                        "NX_SIM_GEOMETRY_MISMATCH", "Expected one hollow enclosure solid"
                    )
                units = [
                    cad.UnitCollection.FindObject(n)
                    for n in (
                        "SquareMilliMeter",
                        "CubicMilliMeter",
                        "Kilogram",
                        "MilliMeter",
                        "Newton",
                    )
                ]
                mass = cad.MeasureManager.NewMassProperties(units, 0.999, shell_bodies)
                try:
                    mass.InformationUnit = nx.MeasureBodies.AnalysisUnit.KilogramMillimeter
                    expected_volume = length_mm * width_mm * height_mm - (
                        (length_mm - 2 * wall) * (width_mm - 2 * wall) * (height_mm - 2 * wall)
                    )
                    if abs(float(mass.Volume) - expected_volume) > max(
                        1e-6, expected_volume * 1e-6
                    ):
                        raise NXToolError(
                            "NX_SIM_GEOMETRY_MISMATCH",
                            "Hollow enclosure volume differs from its dimensions",
                        )
                finally:
                    mass.Dispose()
            dispose_status(
                cad.Save(
                    nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
                )
            )
            stage = "fem"
            fem = self.session.Parts.NewBaseDisplay(
                str(paths["fem"]), nx.BasePart.Units.Millimeters
            )
            opened.append(fem)
            options = fem.NewFemCreationOptions()
            sync = fem.NewFemSynchronizeOptions()
            try:
                options.SetCadData(cad, "")
                options.SetSolverOptions(
                    "NX MULTIPHYSICS", analysis, cae.BaseFemPart.AxisymAbstractionType.NotSet
                )
                options.SetGeometryOptions(
                    cae.FemCreationOptions.UseBodiesOption.AllBodies, [], sync
                )
                fem.FinalizeCreation(options)
            finally:
                # The installed Python API uses Dispose, not .NET FreeResource.
                options.Dispose()
            stage = "sim"
            sim = self.session.Parts.NewBaseDisplay(
                str(paths["sim"]), nx.BasePart.Units.Millimeters
            )
            opened.append(sim)
            sim.FinalizeCreation(fem, ["NX MCP isolated analysis benchmark"])
            stage = "solution"
            solution = sim.Simulation.CreateSolution(
                "NX MULTIPHYSICS",
                analysis,
                solution_type,
                solution_name,
                cae.SimSimulation.AxisymAbstractionType.NotSet,
            )
            actual = {
                "solver": solution.SolverType,
                "analysis": solution.AnalysisType,
                "solution": solution.SolutionType,
            }
            if actual != {
                "solver": "NX MULTIPHYSICS",
                "analysis": analysis,
                "solution": solution_type,
            }:
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH",
                    "Created solution differs from requested environment",
                )
            if analysis_type == "thermal":
                stage = "thermal_parameter_tables"
                actual["parameter_tables"] = []
                for descriptor, key in (
                    ("Thermal Parameters", "Thermal Parameters"),
                    ("Multiphysics Thermal Output Requests", "Thermal Output Requests"),
                ):
                    table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
                        descriptor, "NX MULTIPHYSICS - Thermal", "NX MULTIPHYSICS", key, 0
                    )
                    solution.PropertyTable.SetNamedPropertyTablePropertyValue(key, table)
                    committed = solution.PropertyTable.GetNamedPropertyTablePropertyValue(key)
                    if committed != table:
                        raise NXToolError(
                            "NX_SIM_READBACK_MISMATCH", "Thermal parameter table was not associated"
                        )
                    actual["parameter_tables"].append(
                        {
                            "property": key,
                            "descriptor": committed.DescriptorType,
                            "name": committed.Name,
                        }
                    )
                stage = "thermal_step"
                import NXOpen.UF as uf

                native = uf.UFSession.GetUFSession()
                descriptor = native.Sf.SolutionAskDescriptorNx(solution.Tag)
                allowed = [
                    native.Sfl.StepDescriptorAskNameNx(
                        native.Sfl.SolutionAskNthAllowableStepDescriptorNx(descriptor, i)
                    )
                    for i in range(solution.AllowedStepTypeCount)
                ]
                if allowed.count("Step - Thermal") != 1:
                    raise NXToolError(
                        "NX_SIM_STEP_UNAVAILABLE",
                        "Expected one registered Step - Thermal descriptor",
                    )
                step = solution.CreateStep(allowed.index("Step - Thermal"), True, "Conduction")
                # NX 2606: value 0 was verified by the native steady conduction benchmark.
                step.PropertyTable.SetIntegerPropertyValue("Solution Type", 0)
                if step.PropertyTable.GetIntegerPropertyValue("Solution Type") != 0:
                    raise NXToolError(
                        "NX_SIM_READBACK_MISMATCH", "Steady thermal step was not committed"
                    )
                from nx_mcp.simcenter.properties import read_properties

                actual["step"] = {
                    "name": step.Name,
                    "descriptor": "Step - Thermal",
                    "active": solution.ActiveStep == step,
                    "properties": read_properties(step.PropertyTable, nx),
                }
            else:
                import NXOpen.UF as uf

                from nx_mcp.simcenter.properties import read_properties

                native = uf.UFSession.GetUFSession()
                descriptor = native.Sf.SolutionAskDescriptorNx(solution.Tag)
                actual["allowed_steps"] = [
                    native.Sfl.StepDescriptorAskNameNx(
                        native.Sfl.SolutionAskNthAllowableStepDescriptorNx(descriptor, i)
                    )
                    for i in range(solution.AllowedStepTypeCount)
                ]
                actual["properties"] = read_properties(solution.PropertyTable, nx)
                actual["configuration_state"] = "requires_flow_configuration"
                actual["step_created"] = False
            stage = "save"
            for part in opened:
                dispose_status(
                    part.Save(
                        nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
                    )
                )
            return {
                "paths": {k: str(p) for k, p in paths.items()},
                "solution": actual,
                "documents": [
                    row
                    for row in documents(self.session)
                    if row["path"] in {str(p) for p in paths.values()}
                ],
                "units": "mm",
                "coordinate_frame": "part_absolute",
                "body_count": len(list(fem.Bodies)),
                "block_origins_mm": [list(origin) for origin in origins],
                "mesh_created": False,
                "solve_launched": False,
            }
        except Exception as exc:
            cleanup_errors = []
            for part in reversed(opened):
                try:
                    part.Close(
                        nx.BasePart.CloseWholeTree.FalseValue,
                        nx.BasePart.CloseModified.CloseModified,
                        None,
                    )
                except Exception:
                    cleanup_errors.append("Could not close analysis document")
            if old_display:
                _, status = self.session.Parts.SetDisplay(old_display, False, False)
                dispose_status(status)
            if old_work:
                self.session.Parts.SetWork(old_work)
            raise NXToolError(
                "NX_SIM_CREATE_FAILED",
                f"Analysis creation failed during {stage}: {exc}",
                nx_code=getattr(exc, "ErrorCode", None),
                details={
                    "stage": stage,
                    "mutation_outcome": "partial",
                    "partial_files": [str(p) for p in paths.values() if p.exists()],
                    "cleanup_errors": cleanup_errors,
                    "next_step": "Inspect retained files; retry with a new folder after resolving the reported error",
                },
            ) from exc

    def _sim_mesh_plan(self, document, regions):
        from nx_mcp.simcenter.mesh_plan import generate

        fem = self.objects.resolve(document, expected_kind="part")
        try:
            return generate(self, fem, regions)
        except ValueError as error:
            raise NXToolError("NX_INVALID_ARGUMENT", str(error)) from error

    def _sim_mesh(self, document, size_mm=5.0):
        import math

        import NXOpen.CAE as cae

        from nx_mcp.simcenter.properties import read_properties

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document from nx_sim_documents")
        if fem.PartUnits != self.nxopen.BasePart.Units.Millimeters:
            raise NXToolError("NX_SIM_UNITS", "This adapter currently requires a millimeter FEM")
        if not math.isfinite(size_mm) or not 0 < size_mm <= 10000:
            raise NXToolError("NX_INVALID_ARGUMENT", "size_mm must be finite and in (0, 10000]")
        bodies = list(fem.Bodies)
        manager = fem.BaseFEModel.MeshManager
        if not bodies or manager.GetMeshes():
            raise NXToolError(
                "NX_SIM_MESH_PRECONDITION",
                "Requires bodies and no existing mesh; remeshing is not yet implemented",
            )
        _, load_status = self.session.Parts.SetDisplay(fem, False, False)
        dispose_status(load_status)
        self.session.Parts.SetWork(fem)
        mark = self.session.SetUndoMark(
            self.nxopen.Session.MarkVisibility.Visible, "NX MCP Simcenter mesh"
        )
        builder = None
        try:
            builder = manager.CreateMesh3dTetBuilder(None)
            if "Linear Tetrahedron" not in builder.ElementType.GetElementTypeNames():
                raise NXToolError(
                    "NX_SIM_ELEMENT_UNAVAILABLE", "Solver does not offer Linear Tetrahedron"
                )
            builder.ElementType.ElementTypeName = "Linear Tetrahedron"
            builder.ElementType.DestinationCollector.AutomaticMode = True
            builder.AutoSizeOption = False
            builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size",
                float(size_mm),
                fem.UnitCollection.FindObject("MilliMeter"),
            )
            builder.SelectionList.Add(bodies)
            meshes = builder.CommitMesh()
            if not meshes:
                raise NXToolError("NX_SIM_MESH_EMPTY", "Native mesher returned no meshes")
            actual = []
            for mesh in meshes:
                inspector = manager.CreateMesh3dTetBuilder(mesh)
                try:
                    actual.append(
                        {
                            "name": mesh.Name,
                            "type": type(mesh).__name__,
                            "owner": fem.FullPath,
                            "element_type": inspector.ElementType.ElementTypeName,
                            "properties": read_properties(inspector.PropertyTable, self.nxopen),
                        }
                    )
                finally:
                    inspector.Destroy()
            elements, nodes = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
            try:
                counts = {"elements": elements.NumElements, "nodes": nodes.NumNodes}
            finally:
                elements.Dispose()
                nodes.Dispose()
            self._history.append(
                {
                    "mark": mark,
                    "part_id": self._part_id(fem),
                    "operation_id": self._current_operation,
                    "method": "nx_sim_mesh",
                }
            )
            return {
                "meshes": actual,
                "counts": counts,
                "units": "mm",
                "coordinate_frame": "part_absolute",
                "saved": False,
                "quality_validation": "not_performed",
            }
        except Exception as exc:
            if builder is not None:
                # Preserve the operation failure; rollback still runs.
                with suppress(Exception):
                    builder.Destroy()
                builder = None
            try:
                self.session.UndoToMark(mark, None)
                self.session.DeleteUndoMark(mark, None)
            except Exception as rollback:
                raise NXToolError(
                    "NX_ROLLBACK_FAILED",
                    "Native mesh rollback failed",
                    details={
                        "mutation_outcome": "partial",
                        "operation_error": str(exc),
                        "rollback_error": str(rollback),
                    },
                ) from exc
            raise NXToolError(
                "NX_SIM_MESH_FAILED",
                str(exc),
                nx_code=getattr(exc, "ErrorCode", None),
                details={"mutation_outcome": "rolled_back"},
            ) from exc
        finally:
            if builder is not None:
                builder.Destroy()

    def _sim_material(
        self,
        document,
        name,
        conductivity_w_m_k,
        density_kg_m3,
        heat_capacity_j_kg_k,
        provenance,
        assign_all_solid_collectors=False,
    ):
        import math

        import NXOpen.CAE as cae

        from nx_mcp.simcenter.properties import read_properties

        fem = self.objects.resolve(document, expected_kind="part")
        if not isinstance(fem, cae.FemPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a FEM document")
        values = {
            "ThermalConductivity": (conductivity_w_m_k, "ThermalConductivity_Metric3"),
            "MassDensityConstant": (density_kg_m3, "KilogramPerCubicMeter"),
            "SpecificHeat": (heat_capacity_j_kg_k, "SpecificHeat_Metric2"),
        }
        if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v, _ in values.values()):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Thermal properties must be positive finite SI values"
            )
        if not name.strip() or not provenance.strip() or len(name) > 100 or len(provenance) > 2000:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Provide a name (1..100) and provenance (1..2000 characters)"
            )
        materials = fem.MaterialManager.PhysicalMaterials
        if any(m.Name.casefold() == name.casefold() for m in materials):
            raise NXToolError(
                "NX_SIM_NAME_CONFLICT", "A material with that name already exists in this FEM"
            )
        collectors = (
            [
                c
                for c in fem.BaseFEModel.MeshManager.GetMeshCollectors()
                if c.CollectorNeutralType == "Solid"
            ]
            if assign_all_solid_collectors
            else []
        )
        if assign_all_solid_collectors and not collectors:
            raise NXToolError(
                "NX_SIM_NO_COLLECTORS", "Mesh the FEM before requesting solid collector assignment"
            )
        units = {key: fem.UnitCollection.FindObject(unit) for key, (_, unit) in values.items()}
        _, status = self.session.Parts.SetDisplay(fem, False, False)
        dispose_status(status)
        self.session.Parts.SetWork(fem)
        # Activation must precede the mark: switching documents can invalidate marks.
        mark = self.session.SetUndoMark(
            self.nxopen.Session.MarkVisibility.Visible, "NX MCP thermal material"
        )
        builder = None
        try:
            builder = materials.CreatePhysicalMaterialBuilder(
                self.nxopen.PhysicalMaterial.Type.Isotropic
            )
            builder.Name = name
            builder.Description = provenance
            builder.AddToMaterialLibraryToggle = False
            for key, (value, _) in values.items():
                expression = fem.Expressions.CreateSystemNumberExpression(
                    str(float(value)), units[key]
                )
                wrapper = fem.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
                builder.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
            material = builder.Commit()
            assignments = []
            for collector in collectors:
                table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                    "Solid Property"
                ).PropertyTable
                options = fem.NewMaterialOptions()
                try:
                    options.Material = material
                    options.MaterialInherited = False
                    table.SetPhysicalMaterialPropertyValue("material", options)
                finally:
                    options.Dispose()
                actual = table.GetPhysicalMaterialPropertyValue("material")
                try:
                    if actual.Material != material or actual.MaterialInherited:
                        raise NXToolError(
                            "NX_SIM_READBACK_MISMATCH",
                            "Collector material did not match the committed assignment",
                        )
                    assignments.append(
                        {
                            "collector": self._reference(
                                collector, "mesh_collector", fem, "collector"
                            ),
                            "material_name": actual.Material.Name,
                            "inherited": False,
                        }
                    )
                finally:
                    actual.Dispose()
            properties = [
                p
                for p in read_properties(material.GetPropTable(), self.nxopen)
                if p["name"] in values
            ]
            if len(properties) != 3 or any(p.get("inspection_status") for p in properties):
                raise NXToolError(
                    "NX_SIM_READBACK_FAILED", "Could not inspect all committed thermal properties"
                )
            self._history.append(
                {
                    "mark": mark,
                    "part_id": self._part_id(fem),
                    "operation_id": self._current_operation,
                    "method": "nx_sim_material",
                }
            )
            return {
                "material": self._reference(material, "material", fem, name),
                "properties": properties,
                "assignments": assignments,
                "provenance": provenance,
                "saved": False,
                "solve_launched": False,
            }
        except Exception as exc:
            if builder is not None:
                # Preserve the operation failure; rollback still runs.
                with suppress(Exception):
                    builder.Destroy()
                builder = None
            outcome = "rolled_back"
            try:
                self.session.UndoToMark(mark, None)
                self.session.DeleteUndoMark(mark, None)
            except Exception:
                outcome = "partial"
            raise NXToolError(
                "NX_SIM_MATERIAL_FAILED",
                str(exc),
                nx_code=getattr(exc, "ErrorCode", None),
                details={
                    "mutation_outcome": outcome,
                    "next_step": "Inspect the FEM materials and collectors before retrying",
                },
            ) from exc
        finally:
            if builder is not None:
                builder.Destroy()

    def _sim_activate(self, document):
        import NXOpen.CAE as cae

        part = self.objects.resolve(document, expected_kind="part")
        if not isinstance(part, (cae.FemPart, cae.SimPart)):
            raise NXToolError(
                "NX_SIM_DOCUMENT_TYPE", "Select a loaded FEM or SIM from nx_sim_documents"
            )
        before = self.session.ApplicationName
        try:
            _, load_status = self.session.Parts.SetDisplay(part, False, False)
            dispose_status(load_status)
            self.session.Parts.SetWork(part)
            if self.session.ApplicationName != "UG_APP_SFEM":
                self.session.ApplicationSwitchImmediate("UG_APP_SFEM")
            if (
                self.session.ApplicationName != "UG_APP_SFEM"
                or self.session.Parts.BaseDisplay != part
                or self.session.Parts.BaseWork != part
            ):
                raise NXToolError(
                    "NX_SIM_ACTIVATION_MISMATCH",
                    "Simulation application or document did not activate",
                )
            return {
                "application_before": before,
                "application": self.session.ApplicationName,
                "documents": self._sim_documents(),
                "saved": False,
            }
        except Exception as exc:
            raise NXToolError(
                "NX_SIM_ACTIVATION_FAILED",
                str(exc),
                nx_code=getattr(exc, "ErrorCode", None),
                details={
                    "mutation_outcome": "partial",
                    "next_step": "Inspect nx_status and nx_sim_documents for current activation state",
                },
            ) from exc

    def _sim_pressure_result(self, document, field="pressure", loadcase_index=0, iteration_index=0):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.flow_results import pressure_extrema

        if any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index)):
            raise NXToolError("NX_INVALID_ARGUMENT", "Result indices must be nonnegative integers")
        if field not in ("pressure", "total_pressure"):
            raise NXToolError("NX_INVALID_ARGUMENT", "field must be pressure or total_pressure")
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError(
                "NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate this SIM with nx_sim_activate"
            )
        if sim.Simulation.ActiveSolution is None:
            raise NXToolError("NX_SIM_NO_SOLUTION", "Select a solution before inspecting results")
        try:
            result = pressure_extrema(
                self.session,
                sim,
                field=field,
                loadcase_index=loadcase_index,
                iteration_index=iteration_index,
            )
        except ValueError as error:
            raise NXToolError("NX_SIM_RESULT_SELECTION", str(error)) from error
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_temperature_nodes(
        self,
        document,
        result_sha256,
        loadcase_index=0,
        iteration_index=0,
        offset=0,
        limit=100,
        maximum_bytes=1_073_741_824,
    ):
        from nx_mcp.simcenter.nodal_results import temperature_nodes
        from nx_mcp.simcenter.result_reader import read_bound

        return read_bound(
            self,
            document,
            result_sha256,
            temperature_nodes,
            maximum_bytes,
            loadcase_index=loadcase_index,
            iteration_index=iteration_index,
            offset=offset,
            limit=limit,
        )

    def _sim_temperature_regions(
        self,
        document,
        result_sha256,
        dimension="3d",
        loadcase_index=0,
        iteration_index=0,
        offset=0,
        limit=10,
        maximum_entities=200000,
        maximum_bytes=1_073_741_824,
    ):
        from nx_mcp.simcenter.region_results import temperature_regions
        from nx_mcp.simcenter.result_reader import read_bound

        return read_bound(
            self,
            document,
            result_sha256,
            temperature_regions,
            maximum_bytes,
            dimension=dimension,
            loadcase_index=loadcase_index,
            iteration_index=iteration_index,
            offset=offset,
            limit=limit,
            maximum_entities=maximum_entities,
        )

    def _sim_temperature_result(
        self, document, loadcase_index=0, iteration_index=0, location="nodal"
    ):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.results import temperature_extrema

        if any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index)):
            raise NXToolError("NX_INVALID_ARGUMENT", "Result indices must be nonnegative integers")
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError(
                "NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate this SIM with nx_sim_activate"
            )
        if sim.Simulation.ActiveSolution is None:
            raise NXToolError("NX_SIM_NO_SOLUTION", "Select a solution before inspecting results")
        try:
            result = temperature_extrema(
                self.session,
                sim,
                loadcase_index=loadcase_index,
                iteration_index=iteration_index,
                location=location,
            )
        except ValueError as error:
            raise NXToolError("NX_SIM_RESULT_SELECTION", str(error)) from error
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_result_inventory(self, document, offset=0, limit=50):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.results import iteration_inventory

        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be between 1 and 200")
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError(
                "NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate this SIM with nx_sim_activate"
            )
        if sim.Simulation.ActiveSolution is None:
            raise NXToolError("NX_SIM_NO_SOLUTION", "Select a solution before inspecting results")
        result = iteration_inventory(self.session, sim, offset=offset, limit=limit)
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_result_identity(self, document, maximum_bytes=1_073_741_824, job_id=None):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.result_identity import inspect_result_identity

        if type(maximum_bytes) is not int or maximum_bytes < 1:
            raise NXToolError("NX_INVALID_ARGUMENT", "maximum_bytes must be a positive integer")
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        if self.session.Parts.BaseWork != sim:
            raise NXToolError(
                "NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate this SIM with nx_sim_activate"
            )
        solution = sim.Simulation.ActiveSolution
        if solution is None:
            raise NXToolError("NX_SIM_NO_SOLUTION", "Select a solution before inspecting results")
        job = None
        if job_id is not None:
            from nx_mcp.simcenter.jobs import JobStore
            from nx_mcp.simcenter.result_binding import require_job_owner

            job = JobStore(self.workspace).inspect(job_id)
            require_job_owner(
                self.workspace,
                job,
                path=sim.FullPath,
                solution=solution.Name,
                solver=solution.SolverType,
                analysis=solution.AnalysisType,
            )
        result = inspect_result_identity(solution, self.workspace, maximum_bytes=maximum_bytes)
        if job is not None:
            from nx_mcp.simcenter.dependencies import inspect_direct
            from nx_mcp.simcenter.result_binding import audit_job_result
            from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state

            remaining = maximum_bytes - sum(row["bytes"] for row in result["files"])
            if remaining < 1:
                raise NXToolError(
                    "NX_INVALID_ARGUMENT",
                    "Increase maximum_bytes to audit result and dependency files together",
                )
            from nx_mcp.simcenter import mesh_guard

            live_mesh_state = None
            mesh_inspection_error = None
            manifest = job.get("manifest", {})
            if "live_mesh_state" in manifest:
                try:
                    limit = manifest.get("mesh_inspection_limit")
                    mesh_guard.validate_budget(limit)
                    live_mesh_state = mesh_guard.capture(sim, limit)
                except NXToolError as error:
                    mesh_inspection_error = error.as_dict()
            result["job_binding"] = audit_job_result(
                self.workspace,
                job,
                inspect_direct(self.session, sim, self.workspace),
                result["files"],
                maximum_bytes=remaining,
                live_thermal_state=capture_analysis_thermal_state(sim),
                live_mesh_state=live_mesh_state,
                mesh_inspection_error=mesh_inspection_error,
            )
            if result["job_binding"]["model_result_freshness"] == "stale":
                result["result_freshness"] = "stale"
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_flow_convergence(self, document, residual, flow_imbalance_fraction, iteration_limit):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.flow_controls import configure_convergence

        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        result = configure_convergence(
            self.session,
            sim,
            residual=residual,
            flow_imbalance_fraction=flow_imbalance_fraction,
            iteration_limit=iteration_limit,
        )
        return {"document": self._reference(sim, "part", sim, "part"), **result}

    def _sim_flow_setup(self, document, action, name="Flow"):
        import NXOpen.CAE as cae

        from nx_mcp.simcenter.flow import (
            attach_default_tables,
            configure_coupled_steady,
            create_initial_step,
        )
        from nx_mcp.simcenter.solver_guard import require_solver_idle

        require_solver_idle()

        if action not in ("create_step", "attach_defaults", "coupled_steady"):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "action must be create_step, attach_defaults, or coupled_steady",
            )
        sim = self.objects.resolve(document, expected_kind="part")
        if not isinstance(sim, cae.SimPart):
            raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select a SIM from nx_sim_documents")
        solution = sim.Simulation.ActiveSolution
        if solution is None or solution.AnalysisType not in ("Flow", "Coupled Thermal-Flow"):
            raise NXToolError(
                "NX_SIM_SOLUTION_TYPE", "Select a Flow or Coupled Thermal-Flow solution"
            )
        operation = {
            "create_step": create_initial_step,
            "attach_defaults": attach_default_tables,
            "coupled_steady": configure_coupled_steady,
        }[action]
        result = operation(self.session, sim, name)
        return {"document": self._reference(sim, "part", sim, "part"), "action": action, **result}
