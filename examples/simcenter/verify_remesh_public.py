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
    output = shared / "remesh-public.json"

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
            if t.name in {"nx_sim_face_size_edit", "nx_sim_remesh"}
        ]
        assert len(receipt["schemas"]) == 2
        path = r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\L-face-size-20260909-r1\benchmark_d5f46585b1fa_mesh.fem"
        opened = await call("open", "nx_sim_open", {"path": path})
        fid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        controls = await call("controls", "nx_sim_mesh_controls", {"document": fid})
        row = controls["controls"][0]
        assert controls["total"] == 1 and row["size_mm"] == 1
        cid = row["control"]["id"]
        face = row["faces"][0]["id"]
        args = {
            "document": fid,
            "control": cid,
            "size_mm": 2.0,
            "operation_id": "local-edit-public-r1",
        }
        await call(
            "invalid",
            "nx_sim_face_size_edit",
            {**args, "size_mm": 0, "operation_id": "local-edit-invalid-r1"},
            error=True,
        )
        edit = await call("edit", "nx_sim_face_size_edit", args)
        replay = await call("edit_replay", "nx_sim_face_size_edit", args)
        assert edit["control"] == replay["control"]
        assert edit["control"]["size_mm"] == 2
        assert edit["control"]["faces"] == row["faces"]
        remesh_args = {"document": fid, "operation_id": "local-remesh-public-r1"}
        regenerated = await call("remesh", "nx_sim_remesh", remesh_args)
        assert regenerated["before_counts"]["elements"] == 1076
        assert regenerated["counts"]["elements"] == 341
        replay = await call("remesh_replay", "nx_sim_remesh", remesh_args)
        assert (
            replay["document"] == regenerated["document"]
            and replay["counts"] == regenerated["counts"]
        )
        new_id = regenerated["document"]["id"]
        assert new_id != fid
        await call("stale_document", "nx_sim_mesh_controls", {"document": fid}, error=True)
        await call(
            "stale_control",
            "nx_sim_face_size_edit",
            {"document": new_id, "control": cid, "size_mm": 1},
            error=True,
        )
        await call(
            "stale_face",
            "nx_sim_face_size",
            {"document": new_id, "faces": [face], "size_mm": 1},
            error=True,
        )
        current = await call("current", "nx_sim_mesh_controls", {"document": new_id})
        assert current["controls"][0]["size_mm"] == 2
        assert current["controls"][0]["faces"][0]["journal_id"] == row["faces"][0]["journal_id"]
        await call("quality", "nx_sim_mesh_quality", {"document": new_id})
        await call("save", "nx_sim_save", {"document": new_id})
        await call("close", "nx_sim_close", {"document": new_id})
        reopened = await call("reopen", "nx_sim_open", {"path": path})
        new_id = reopened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": new_id})
        after = await call("persisted_controls", "nx_sim_mesh_controls", {"document": new_id})
        assert after["controls"][0]["size_mm"] == 2
        assert after["controls"][0]["faces"][0]["journal_id"] == row["faces"][0]["journal_id"]
        await call("persisted_quality", "nx_sim_mesh_quality", {"document": new_id})
        receipt.update(
            passed=True,
            document=new_id,
            path=path,
            solver_launched=False,
            numerical_acceptance="not_established",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
