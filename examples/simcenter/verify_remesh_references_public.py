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
    output = shared / "remesh-references-public.json"

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

        path = r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\L-face-size-20260909-r1\benchmark_d5f46585b1fa_mesh.fem"
        if "--restore-display" in sys.argv:
            receipt = json.loads(output.read_text())
            opened = await call("restore_display_open", "nx_sim_open", {"path": path})
            await call(
                "restore_display_activate",
                "nx_sim_activate",
                {"document": opened["document"]["id"]},
            )
            receipt["display_restored"] = True
            record()
            return
        simpath = path.replace("_mesh.fem", "_analysis.sim")
        opened = await call("open", "nx_sim_open", {"path": path})
        fid = opened["document"]["id"]
        opened_sim = await call("open_sim", "nx_sim_open", {"path": simpath})
        sid = opened_sim["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        controls = await call("controls", "nx_sim_mesh_controls", {"document": fid})
        assert controls["total"] == 1 and controls["controls"][0]["size_mm"] == 2
        cid = controls["controls"][0]["control"]["id"]
        await call(
            "restore_size",
            "nx_sim_face_size_edit",
            {
                "document": fid,
                "control": cid,
                "size_mm": 1,
                "operation_id": "local-edit-restore-r1",
            },
        )
        args = {"document": fid, "operation_id": "local-remesh-restore-r1"}
        result = await call("remesh", "nx_sim_remesh", args)
        assert result["before_counts"]["elements"] == 341 and result["counts"]["elements"] == 1076
        assert set(result["references_invalidated"]) == {path, simpath}
        assert len(result["settings"]) == 2
        for row in result["settings"]:
            assert row["mesh"]["kind"] == "simulation_mesh"
            assert len(row["bodies"]) == 1 and row["bodies"][0]["kind"] == "body"
            assert "body_tags" not in row
        replay = await call("replay", "nx_sim_remesh", args)
        assert replay["settings"] == result["settings"]
        await call("stale_sim", "nx_sim_dependencies", {"document": sid}, error=True)
        newfid = result["document"]["id"]
        faces = await call("faces", "nx_sim_faces", {"document": newfid})
        bodyids = {row["body"]["id"] for row in faces["faces"]}
        assert bodyids == {row["bodies"][0]["id"] for row in result["settings"]}
        await call("quality", "nx_sim_mesh_quality", {"document": newfid})
        await call("save", "nx_sim_save", {"document": newfid})
        reopened = await call("reacquire_sim", "nx_sim_open", {"path": simpath})
        newsid = reopened["document"]["id"]
        assert newsid != sid
        await call("save_sim", "nx_sim_save", {"document": newsid})
        await call("close_sim", "nx_sim_close", {"document": newsid})
        await call("reactivate_fem", "nx_sim_activate", {"document": newfid})
        receipt.update(
            passed=True, solver_launched=False, numerical_acceptance="not_established", path=path
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
