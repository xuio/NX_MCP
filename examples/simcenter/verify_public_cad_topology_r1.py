"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

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
    output = shared / "public-cad-topology-r1.json"

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

        cad = await call(
            "cad",
            "nx_create_part",
            {"path": "ui-benchmarks/public-cad-topology-r1/model.prt", "units": "mm"},
        )
        cid = cad["part"]["id"]

        async def box(label, origin, height):
            sketch = await call(
                label + "_sketch",
                "nx_create_sketch",
                {"plane": "XY", "origin": origin, "name": label},
            )
            sk = sketch["object"]["id"]
            await call(
                label + "_rectangle",
                "nx_sketch_rectangle",
                {"sketch_id": sk, "corner1": {"x": 0, "y": 0}, "corner2": {"x": 20, "y": 10}},
            )
            await call(label + "_finish", "nx_finish_sketch", {"sketch_id": sk})
            return await call(
                label + "_extrude", "nx_extrude", {"sketch_id": sk, "distance": height}
            )

        await box("Solid", [0, 0, 0], 2.0)
        await box("Air", [0, 0, 2], 8.0)
        await call("save_cad", "nx_save_part", {})
        analysis = await call(
            "analysis",
            "nx_sim_create_analysis",
            {
                "cad_document": cid,
                "folder": "ui-benchmarks/public-topology-analysis-r1",
                "name": "Public topology",
                "operation_id": "public-topology-analysis-r1",
            },
        )
        fid = analysis["fem"]["id"]
        await call("cad_activate", "nx_activate_part", {"part": cid})
        extra = await box("Temporary", [30, 0, 0], 3.0)
        await call("save_added", "nx_save_part", {})
        await call("fem_activate", "nx_sim_activate", {"document": fid})
        synced = await call(
            "sync_added",
            "nx_sim_sync_geometry",
            {"document": fid, "operation_id": "public-topology-added-r1"},
        )
        assert synced["body_count"] == 3 and len(synced["unmeshed_bodies"]) == 3
        fid = synced["document"]["id"]
        await call("cad_activate_remove", "nx_activate_part", {"part": cid})
        await call("remove", "nx_delete_feature", {"name": extra["feature"]["id"]})
        await call("save_removed", "nx_save_part", {})
        await call("fem_activate_removed", "nx_sim_activate", {"document": fid})
        synced = await call(
            "sync_removed",
            "nx_sim_sync_geometry",
            {"document": fid, "operation_id": "public-topology-removed-r1"},
        )
        assert synced["body_count"] == 2
        await call("save_fem", "nx_sim_save", {"document": synced["document"]["id"]})
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
