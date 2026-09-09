"""Public mixed solid/fluid mesh plan with wall layers; no solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    env = dict(os.environ)
    env.update(
        PYTHONPATH=r"C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src",
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_WORKSPACE=r"D:\CAD\SIMCENTER_MCP_WORKSPACE",
        NX_MCP_BRIDGE_DESCRIPTOR=r"C:\Users\cadadmin\AppData\Local\nx-mcp\simcenter-bridge.json",
        NX_MCP_SURFACE="full",
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "nx_mcp.server"], env=env
    )
    receipt = {"responses": {}}
    output = shared / "mesh-plan-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        tools = await client.list_tools()
        receipt["schemas"] = [
            t.model_dump(mode="json") for t in tools.tools if t.name == "nx_sim_mesh_plan"
        ]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/M-mixed-mesh-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "block_origins_mm": [[0, 0, 0], [20, 0, 0]],
                "analysis_type": "coupled_thermal_flow",
                "operation_id": "mixed-mesh-fixture-r1",
            },
        )
        opened = await call("open", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        inventory = await call("faces", "nx_sim_faces", {"document": fid})
        solid = next(r["body"]["id"] for r in inventory["faces"] if r["bounds"]["maximum"][0] < 11)
        fluid = next(r["body"]["id"] for r in inventory["faces"] if r["bounds"]["minimum"][0] > 19)
        walls = [
            r["face"]["id"]
            for r in inventory["faces"]
            if r["body"]["id"] == fluid
            and abs(r["bounds"]["maximum"][0] - r["bounds"]["minimum"][0] - 10) < 1e-6
        ]
        assert len(walls) == 4
        await call(
            "layers",
            "nx_sim_boundary_layers",
            {
                "document": fid,
                "faces": walls,
                "first_layer_mm": 0.1,
                "layers": 3,
                "growth_rate": 1.2,
            },
        )
        regions = [
            {"body": solid, "kind": "solid", "size_mm": 5},
            {"body": fluid, "kind": "fluid", "size_mm": 3},
        ]
        await call(
            "missing_body",
            "nx_sim_mesh_plan",
            {"document": fid, "regions": regions[:1]},
            error=True,
        )
        args = {"document": fid, "regions": regions, "operation_id": "mixed-mesh-create-r1"}
        created = await call("create", "nx_sim_mesh_plan", args)
        replay = await call("replay", "nx_sim_mesh_plan", args)
        assert created["counts"] == replay["counts"]
        assert [r["meshes"] for r in created["regions"]] == [r["meshes"] for r in replay["regions"]]
        assert created["regions"][0]["element_type"] == "Linear Tetrahedron"
        assert created["regions"][1]["element_type"] == "Fluid Linear Tetrahedron"
        assert len(created["regions"][1]["meshes"]) >= 2
        await call(
            "existing_rejected",
            "nx_sim_mesh_plan",
            {"document": fid, "regions": regions},
            error=True,
        )
        await call("quality", "nx_sim_mesh_quality", {"document": fid})
        await call("save_fem", "nx_sim_save", {"document": fid})
        sim = await call("open_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = sim["document"]["id"]
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        await call("stale_fem", "nx_sim_mesh_quality", {"document": fid}, error=True)
        opened = await call("reopen", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": fid})
        reopened_quality = await call("quality_reopened", "nx_sim_mesh_quality", {"document": fid})
        assert reopened_quality["element_count"] == created["counts"]["elements"]
        controls = await call("controls_reopened", "nx_sim_mesh_controls", {"document": fid})
        assert controls["total"] == 1 and len(controls["controls"][0]["faces"]) == 4
        receipt.update(
            passed=True,
            document=fid,
            path=fixture["paths"]["fem"],
            solver_launched=False,
            numerical_acceptance="not_established",
            scope="Public body plan creation, primary builder readback, replay and quality inspection; layer topology audited separately",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
