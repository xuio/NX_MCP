"""Live NX 2606 engineering acceptance; isolated parts and session restoration.

NX_MCP_URL selects the deployed server. NX_VALIDATION_OUTPUT holds receipts and
artifacts. NX_VALIDATION_GROUP optionally restricts a rerun to one named group.
"""

import asyncio
import base64
import hashlib
import json
import math
import os
import traceback
import uuid
from pathlib import Path, PureWindowsPath

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    output = Path(os.environ.get("NX_VALIDATION_OUTPUT", "engineering-results"))
    output.mkdir(parents=True, exist_ok=True)
    prefix = "engineering-validation-" + uuid.uuid4().hex[:8]
    result = {"groups": [], "fixture": prefix}
    async with (
        streamablehttp_client(os.environ["NX_MCP_URL"]) as (read, write, _),
        ClientSession(read, write) as client,
    ):
        await client.initialize()

        async def call(method, **params):
            response = await client.call_tool(method, params)
            if response.isError:
                raise RuntimeError((method, response.structuredContent))
            if method == "nx_render_view":
                images = [c for c in response.content if c.type == "image"]
                assert len(images) == 1, "Native render was not delivered inline"
                data = base64.b64decode(images[0].data)
                assert hashlib.sha256(data).hexdigest() == response.structuredContent["sha256"]
                (output / "native-render.png").write_bytes(data)
            return response.structuredContent

        def close(actual, expected):
            assert math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-10), (actual, expected)

        async def group(name, fn):
            if os.environ.get("NX_VALIDATION_GROUP") not in {None, name}:
                return
            try:
                value = await fn()
                result["groups"].append({"name": name, "passed": True, "result": value})
            except Exception:
                result["groups"].append(
                    {"name": name, "passed": False, "error": traceback.format_exc()}
                )
            (output / "engineering-validation.json").write_text(json.dumps(result, indent=2))
            print(name, result["groups"][-1]["passed"], flush=True)

        async def new(name):
            return await call("nx_create_part", path=prefix + "/" + name + ".prt", units="mm")

        async def profile(w=10, h=10, origin=None):
            s = (await call("nx_create_sketch", origin=origin))["object"]["id"]
            await call(
                "nx_sketch_rectangle",
                sketch_id=s,
                corner1={"x": 0, "y": 0},
                corner2={"x": w, "y": h},
            )
            await call("nx_finish_sketch", sketch_id=s)
            return s

        async def box(name):
            await new(name)
            s = await profile()
            return await call("nx_extrude", sketch_id=s, distance=10)

        async def volume(body=None):
            return (await call("nx_measure_volume", body=body))["volume_mm3"]

        async def face(body, normal, order="highest"):
            return (
                await call(
                    "nx_find_geometry",
                    owner=body,
                    geometry_type="plane",
                    normal=normal,
                    order=order,
                )
            )["items"][0]["object"]["id"]

        async def assembly(name):
            await box(name + "_prototype")
            path = (await call("nx_list_open_parts"))["parts"]
            source = next(p["path"] for p in path if p["work"])
            await call("nx_save_part")
            await new(name + "_assembly")
            return (await call("nx_add_component", part_path=source, name="seed"))["object"][
                "id"
            ], source

        before = await call("nx_list_open_parts")
        assert not any(p["modified"] for p in before["parts"]), (
            "Save the current session before native acceptance"
        )
        work = next((p for p in before["parts"] if p["work"]), None)
        display = next((p for p in before["parts"] if p["display"]), None)
        try:
            assert len((await client.list_tools()).tools) == 124

            async def limits():
                await new("offset")
                s = await profile()
                await call("nx_extrude", sketch_id=s, distance=5, start=-2)
                close(await volume(), 700)
                b = await call("nx_get_bounding_box")
                close(b["min"][2], -2)
                close(b["max"][2], 5)
                await new("symmetric")
                s = await profile()
                await call("nx_extrude", sketch_id=s, distance=8, symmetric=True)
                close(await volume(), 800)
                b = await call("nx_get_bounding_box")
                close(b["min"][2], -4)
                close(b["max"][2], 4)
                f = await box("through")
                s = await profile(2, 2, [2, 2, -2])
                await call(
                    "nx_extrude",
                    sketch_id=s,
                    end_type="through_all",
                    boolean="subtract",
                    targets=[f["body"]["id"]],
                )
                close(await volume(), 960)
                f = await box("until")
                target = await face(f["body"]["id"], [0, 0, 1])
                s = await profile(2, 2)
                r = await call("nx_extrude", sketch_id=s, end_type="up_to_face", target_face=target)
                close(await volume(r["body"]["id"]), 40)
                return {"offset_volume": 700, "through_volume": 960, "until_volume": 40}

            await group("extrusion_limits", limits)

            async def shell_loft_draft():
                f = await box("shell")
                top = await face(f["body"]["id"], [0, 0, 1])
                await call("nx_shell", body=f["body"]["id"], thickness=1, remove_faces=[top])
                close(await volume(), 424)
                await new("loft")
                a = await profile()
                b = await profile(6, 6, [2, 2, 10])
                await call("nx_loft", sketches=[a, b])
                close(await volume(), 1960 / 3)
                f = await box("draft")
                side = await face(f["body"]["id"], [1, 0, 0])
                bottom = await face(f["body"]["id"], [0, 0, -1], "lowest")
                await call(
                    "nx_draft", faces=[side], stationary_face=bottom, direction=[0, 0, 1], angle=5
                )
                close(abs(await volume() - 1000), 500 * math.tan(math.radians(5)))
                return {
                    "shell_volume": 424,
                    "loft_volume": 1960 / 3,
                    "draft_volume": await volume(),
                }

            await group("shell_loft_draft", shell_loft_draft)

            async def motion():
                f = await box("motion")
                rotation = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
                op = "test-copy-" + uuid.uuid4().hex
                params = {
                    "bodies": [f["body"]["id"]],
                    "translation": [20, 30, 40],
                    "rotation_matrix": rotation,
                    "copy": True,
                    "operation_id": op,
                }
                r = await call("nx_transform_bodies", **params)
                again = await call("nx_transform_bodies", **params)
                assert r["feature"]["id"] == again["feature"]["id"]
                close(await volume(), 2000)
                r = await call(
                    "nx_transform_bodies",
                    feature=r["feature"]["id"],
                    translation=[40, 30, 40],
                    rotation_matrix=rotation,
                )
                bounds = await call("nx_get_bounding_box", body=r["body"]["id"])
                assert bounds["min"] == [30, 30, 40], bounds
                await call("nx_save_part")
                await call("nx_close_part")
                await call("nx_open_part", path=prefix + "/motion.prt")
                close(await volume(), 2000)
                return bounds

            await group("associative_motion_persistence_retry", motion)

            async def materials():
                f = await box("material")
                await call(
                    "nx_set_material",
                    bodies=[f["body"]["id"]],
                    name="ValidationAluminum",
                    density=2700,
                )
                r = await call("nx_mass_properties")
                close(r["mass_kg"], 0.0027)
                for x in r["center_of_gravity_m"]:
                    close(x, 0.005)
                for i in range(3):
                    close(r["inertia_tensor_centroid_kg_m2"][i][i], 4.5e-8)
                await call("nx_save_part")
                await new("material_subassembly")
                for translation in [[0, 0, 0], [20, 0, 0]]:
                    await call(
                        "nx_add_component",
                        part_path=prefix + "/material.prt",
                        translation=translation,
                    )
                await call("nx_save_part")
                await new("material_assembly")
                await call(
                    "nx_add_component",
                    part_path=prefix + "/material_subassembly.prt",
                    translation=[10, 20, 30],
                    rotation_matrix=[[0, -1, 0], [1, 0, 0], [0, 0, 1]],
                )
                nested = await call("nx_mass_properties", scope="assembly")
                close(nested["mass_kg"], 0.0054)
                for actual, expected in zip(
                    nested["center_of_gravity_m"], [0.005, 0.035, 0.035], strict=True
                ):
                    close(actual, expected)
                return {"part": r, "nested_assembly": nested}

            await group("physical_material_mass_inertia", materials)

            async def arrays():
                a, _ = await assembly("array")
                r = await call(
                    "nx_component_array",
                    component=a,
                    pattern_type="rectangular",
                    count=3,
                    spacing=20,
                    direction=[1, 0, 0],
                    count_y=2,
                    spacing_y=30,
                    direction_y=[0, 1, 0],
                )
                r = await call(
                    "nx_edit_component_pattern",
                    pattern=r["object"]["id"],
                    count=4,
                    count_y=3,
                    spacing_y=40,
                )
                assert r["total_instances"] == 12
                poses = {tuple(p["translation"]) for p in r["instances"]}
                assert poses == {(20 * x, 40 * y, 0) for x in range(4) for y in range(3)}, poses
                a, _ = await assembly("circular")
                r = await call(
                    "nx_component_array",
                    component=a,
                    pattern_type="circular",
                    count=4,
                    center=[0, 0, 0],
                    axis=[0, 0, 1],
                    angle=90,
                )
                r = await call(
                    "nx_edit_component_pattern", pattern=r["object"]["id"], count=5, angle=60
                )
                assert r["total_instances"] == 5
                return {"rectangular_positions": sorted(poses), "circular_count": 5}

            await group("component_arrays_and_edits", arrays)

            async def constraints():
                a, source = await assembly("constraints")
                b = (
                    await call(
                        "nx_add_component", part_path=source, name="moving", translation=[30, 0, 0]
                    )
                )["object"]["id"]
                await call("nx_assembly_constraint", constraint_type="fix", component=a)
                fa = await face(a, [1, 0, 0])
                fb = await face(b, [-1, 0, 0], "lowest")
                r = await call(
                    "nx_assembly_constraint",
                    constraint_type="distance",
                    component=b,
                    geometry=fb,
                    target_component=a,
                    target_geometry=fa,
                    value=5,
                    alignment="opposite",
                )
                close((await call("nx_measure_distance", obj1=a, obj2=b))["distance"], 5)
                await call("nx_edit_assembly_constraint", constraint=r["object"]["id"], value=12)
                close((await call("nx_measure_distance", obj1=a, obj2=b))["distance"], 12)
                await call(
                    "nx_edit_assembly_constraint", constraint=r["object"]["id"], suppressed=True
                )
                await call(
                    "nx_edit_assembly_constraint", constraint=r["object"]["id"], suppressed=False
                )
                close((await call("nx_measure_distance", obj1=a, obj2=b))["distance"], 12)
                return await call("nx_list_assembly_constraints")

            await group("assembly_constraint_geometry", constraints)

            async def copy_project():
                await assembly("copy")
                await call("nx_save_part")
                r = await call("nx_copy_project", path=prefix + "/projects/copied", prefix="COPY_")
                assert r["references_verified"] and r["dependency_count"] == 1
                return r

            await group("project_copy_dependencies", copy_project)

            async def primitives():
                results = {}
                for name, kw, area in [
                    ("circle", {"radius": 2}, 4 * math.pi),
                    ("slot", {"width": 10, "height": 4}, 24 + 4 * math.pi),
                    ("rounded_rectangle", {"width": 10, "height": 6, "radius": 1}, 56 + math.pi),
                ]:
                    await new(name)
                    s = (await call("nx_create_sketch"))["object"]["id"]
                    await call(
                        "nx_sketch_primitive", sketch_id=s, primitive=name, center=[0, 0], **kw
                    )
                    await call("nx_finish_sketch", sketch_id=s)
                    await call("nx_extrude", sketch_id=s, distance=3)
                    close(await volume(), area * 3)
                    results[name] = await volume()
                return results

            await group("sketch_primitives", primitives)

            async def recovery():
                f = await box("recovery")
                checkpoint = await call("nx_checkpoint", label="engineering recovery")
                top = await face(f["body"]["id"], [0, 0, 1])
                failed = await client.call_tool(
                    "nx_shell",
                    {
                        "body": f["body"]["id"],
                        "thickness": 100,
                        "remove_faces": [top],
                        "operation_id": "bad-shell-" + uuid.uuid4().hex,
                    },
                )
                assert failed.isError, "Impossible shell unexpectedly succeeded"
                close(await volume(), 1000)
                await call(
                    "nx_transform_bodies",
                    bodies=[f["body"]["id"]],
                    translation=[20, 0, 0],
                    rotation_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    copy=True,
                )
                close(await volume(), 2000)
                await call("nx_rollback", checkpoint_id=checkpoint["checkpoint_id"])
                close(await volume(), 1000)
                return {"failed_operation": failed.structuredContent, "restored_volume": 1000}

            await group("failed_mutation_and_checkpoint_rollback", recovery)

            async def rendering():
                await box("render")
                await call("nx_fit_view")
                return await call(
                    "nx_render_view",
                    width=800,
                    height=600,
                    lighting=2,
                    background="color",
                    color=[0.2, 0.3, 0.4],
                )

            await group("native_render_inline_artifact", rendering)
        finally:
            for p in (await call("nx_list_open_parts"))["parts"]:
                if prefix in p["path"]:
                    await call("nx_close_part", part=p["part"]["id"], save=False)
            if display:
                await call("nx_open_part", path=display["path"])
            if work:
                await call(
                    "nx_activate_part", part=work["part"]["id"], work=True, display=work == display
                )
            after = await call("nx_list_open_parts")

            def norm(p):
                return str(PureWindowsPath(p["path"])).casefold()

            assert sorted(map(norm, before["parts"])) == sorted(map(norm, after["parts"]))
            assert not any(p["modified"] for p in after["parts"])
            result["restored_parts"] = len(after["parts"])
            result["passed"] = sum(g["passed"] for g in result["groups"])
            (output / "engineering-validation.json").write_text(json.dumps(result, indent=2))
        if not all(g["passed"] for g in result["groups"]):
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
