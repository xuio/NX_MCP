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
    output = shared / "temperature-regions-lifecycle.json"

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

        path = "ui-benchmarks/V-mesh-guard-positive-20260909-r1/mesh_guard_positive_r1.sim"
        opened = await call("open", "nx_sim_open", {"path": path})
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        identity = await call("identity", "nx_sim_result_identity", {"document": sid})
        digest = identity["files"][0]["sha256"]
        args = {"document": sid, "result_sha256": digest}
        before = await call("before", "nx_sim_temperature_regions", args)
        nodes = await call("nodes_before", "nx_sim_temperature_nodes", args)
        await call(
            "save", "nx_sim_save", {"document": sid, "operation_id": "region-lifecycle-save-v-r1"}
        )
        await call(
            "close",
            "nx_sim_close",
            {"document": sid, "operation_id": "region-lifecycle-close-v-r1"},
        )
        await call("stale", "nx_sim_temperature_regions", args, error=True)
        opened = await call("reopen", "nx_sim_open", {"path": path})
        fresh = opened["document"]["id"]
        assert fresh != sid
        await call("reactivate", "nx_sim_activate", {"document": fresh})
        args["document"] = fresh
        after = await call("after", "nx_sim_temperature_regions", args)
        new_nodes = await call("nodes_after", "nx_sim_temperature_nodes", args)
        for key in ("items", "total", "next_offset", "result_file"):
            assert before[key] == after[key]
            assert nodes[key] == new_nodes[key]
        await call(
            "show",
            "nx_sim_show_temperature",
            {"document": fresh, "operation_id": "region-lifecycle-show-v-r1"},
        )
        receipt.update(passed=True, solver_launched=False, document=fresh)
        record()


if __name__ == "__main__":
    asyncio.run(main())
