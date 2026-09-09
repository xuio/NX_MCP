"""Public local sizing, persistence and two-block meshing fixture; no solve."""

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
    output = shared / "local-size-public.json"

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
            t.model_dump(mode="json") for t in tools.tools if t.name == "nx_sim_face_size"
        ]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/L-face-size-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "block_origins_mm": [[0, 0, 0], [20, 0, 0]],
                "operation_id": "face-size-fixture-r1",
            },
        )
        opened = await call("open", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        faces = await call("faces", "nx_sim_faces", {"document": fid})
        target = next(
            r["face"]["id"]
            for r in faces["faces"]
            if abs(r["bounds"]["minimum"][0] - 20) < 1e-6
            and abs(r["bounds"]["maximum"][0] - 20) < 1e-6
        )
        args = {
            "document": fid,
            "faces": [target],
            "size_mm": 1.0,
            "operation_id": "face-size-create-r1",
        }
        await call(
            "invalid",
            "nx_sim_face_size",
            {**args, "size_mm": 0, "operation_id": "face-size-invalid-r1"},
            error=True,
        )
        created = await call("create", "nx_sim_face_size", args)
        replay = await call("replay", "nx_sim_face_size", args)
        assert created["controls"] == replay["controls"]
        await call(
            "overlap",
            "nx_sim_face_size",
            {**args, "operation_id": "face-size-overlap-r1"},
            error=True,
        )
        before = await call("before", "nx_sim_mesh_controls", {"document": fid})
        assert before["total"] == 1 and before["controls"][0]["size_mm"] == 1
        await call("save_fem", "nx_sim_save", {"document": fid})
        opened_sim = await call("open_sim", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = opened_sim["document"]["id"]
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        await call(
            "stale",
            "nx_sim_face_size",
            {"document": fid, "faces": [target], "size_mm": 1},
            error=True,
        )
        opened = await call("reopen", "nx_sim_open", {"path": fixture["paths"]["fem"]})
        fid = opened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": fid})
        after = await call("after", "nx_sim_mesh_controls", {"document": fid})
        assert after["total"] == 1 and after["controls"][0]["size_mm"] == 1
        assert (
            before["controls"][0]["faces"][0]["journal_id"]
            == after["controls"][0]["faces"][0]["journal_id"]
        )
        assert before["controls"][0]["control"]["id"] != after["controls"][0]["control"]["id"]
        faces = await call("faces_reopened", "nx_sim_faces", {"document": fid})
        bodies = list(dict.fromkeys(r["body"]["id"] for r in faces["faces"]))
        assert len(bodies) == 2
        await call(
            "mesh",
            "nx_sim_mesh_plan",
            {
                "document": fid,
                "regions": [{"body": body, "kind": "solid", "size_mm": 5} for body in bodies],
                "operation_id": "face-size-mesh-r1",
            },
        )
        await call("quality", "nx_sim_mesh_quality", {"document": fid})
        await call("save_meshed", "nx_sim_save", {"document": fid})
        receipt.update(
            passed=True,
            document=fid,
            path=fixture["paths"]["fem"],
            solver_launched=False,
            numerical_acceptance="not_established",
            mesh_effect="native per-block topology audit follows",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
