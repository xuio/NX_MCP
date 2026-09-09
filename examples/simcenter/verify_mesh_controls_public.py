"""Public mesh-control lifecycle fixture; no mesh or solve requested."""

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
    output = shared / "mesh-controls-public.json"

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
            t.model_dump(mode="json")
            for t in tools.tools
            if t.name in ["nx_sim_boundary_layers", "nx_sim_mesh_controls", "nx_sim_faces"]
        ]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/M-controls-public-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "mesh-controls-fixture-r1",
            },
        )
        opened_sim = await call("open_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = opened_sim["document"]["id"]
        await call("activate_sim", "nx_sim_activate", {"document": sid})
        occurrence = await call("sim_faces", "nx_sim_faces", {"document": sid})
        opened = await call("open_fem", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("activate_fem", "nx_sim_activate", {"document": fid})
        inventory = await call("faces", "nx_sim_faces", {"document": fid})
        assert inventory["selection_scope"] == "fem_prototype" and inventory["total"] == 6
        faces = [row["face"]["id"] for row in inventory["faces"][:2]]
        args = {
            "document": fid,
            "faces": faces,
            "first_layer_mm": 0.1,
            "layers": 3,
            "growth_rate": 1.2,
        }
        await call(
            "wrong_owner",
            "nx_sim_boundary_layers",
            {**args, "faces": [occurrence["faces"][0]["face"]["id"]]},
            error=True,
        )
        await call(
            "duplicate",
            "nx_sim_boundary_layers",
            {**args, "faces": [faces[0], faces[0]]},
            error=True,
        )
        await call("invalid_layers", "nx_sim_boundary_layers", {**args, "layers": 0}, error=True)
        empty = await call("empty", "nx_sim_mesh_controls", {"document": fid})
        assert empty["total"] == 0
        args["operation_id"] = "mesh-controls-create-r1"
        created = await call("create", "nx_sim_boundary_layers", args)
        replay = await call("replay", "nx_sim_boundary_layers", args)
        assert created["control"]["id"] == replay["control"]["id"]
        await call(
            "existing_rejected",
            "nx_sim_boundary_layers",
            {**args, "operation_id": "mesh-controls-existing-r1"},
            error=True,
        )
        before = await call("before", "nx_sim_mesh_controls", {"document": fid})
        assert before["total"] == 1 and len(before["controls"][0]["faces"]) == 2
        paged = await call(
            "page", "nx_sim_mesh_controls", {"document": fid, "offset": 1, "limit": 1}
        )
        assert paged["controls"] == [] and paged["total"] == 1
        await call("save", "nx_sim_save", {"document": fid})
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        await call("stale", "nx_sim_mesh_controls", {"document": fid}, error=True)
        opened = await call("reopen", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": fid})
        after = await call("after", "nx_sim_mesh_controls", {"document": fid})
        assert after["total"] == 1
        a, b = before["controls"][0], after["controls"][0]
        for key in [
            "first_layer_mm",
            "layers",
            "growth_rate",
            "height_mode",
            "dimension",
            "native_thickness",
        ]:
            assert a[key] == b[key], (key, a, b)
        assert b["first_layer_mm"] == 0.1 and b["layers"] == 3 and b["growth_rate"] == 1.2
        assert a["control"]["id"] != b["control"]["id"]
        assert sorted(f["journal_id"] for f in a["faces"]) == sorted(
            f["journal_id"] for f in b["faces"]
        )
        assert sorted(x["journal_id"] for x in a["body_targets"]) == sorted(
            x["journal_id"] for x in b["body_targets"]
        )
        receipt.update(
            passed=True,
            mesh_generated=False,
            solver_launched=False,
            numerical_acceptance="not_established",
            scope="FEM face selection, creation/readback/replay/paging and save/reopen; stored controls only",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
