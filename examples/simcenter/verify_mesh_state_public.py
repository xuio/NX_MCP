"""Verify public initial-condition lifecycle and exported selector/temperature; no solve."""

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
    output = shared / "mesh-state-public.json"

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
            t.model_dump(mode="json") for t in tools.tools if t.name == "nx_sim_mesh_state"
        ]
        assert receipt["schemas"]
        path = r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\U-sim-update-export-20260909-r1\sim_update_export_u_r1.sim"
        opened = await call("open", "nx_sim_open", {"path": path})
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        first = await call("first", "nx_sim_mesh_state", {"document": sid})
        again = await call("repeat", "nx_sim_mesh_state", {"document": sid})
        assert first["mesh_state"] == again["mesh_state"]
        assert first["mesh_state"]["counts"] == {"elements": 182, "nodes": 73}
        fid = first["document"]["id"]
        fempath = first["mesh_state"]["owner_path"]
        await call(
            "budget", "nx_sim_mesh_state", {"document": sid, "maximum_entities": 10}, error=True
        )
        await call(
            "invalid_budget",
            "nx_sim_mesh_state",
            {"document": sid, "maximum_entities": 0},
            error=True,
        )
        await call("inactive_fem", "nx_sim_mesh_state", {"document": fid}, error=True)
        await call("save_fem", "nx_sim_save", {"document": fid})
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        await call("close_fem", "nx_sim_close", {"document": fid})
        await call("stale", "nx_sim_mesh_state", {"document": fid}, error=True)
        reopened = await call("reopen", "nx_sim_open", {"path": fempath})
        newfid = reopened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": newfid})
        final = await call("final", "nx_sim_mesh_state", {"document": newfid})
        assert final["mesh_state"] == first["mesh_state"]
        assert final["document"]["id"] != fid
        receipt.update(passed=True, solver_launched=False, full_model_freshness="not_verified")
        record()


if __name__ == "__main__":
    asyncio.run(main())
