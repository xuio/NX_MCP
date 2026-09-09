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
    output = shared / "room-fan-availability-public-r1.json"

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

        path = "ui-benchmarks/E-room-fan-half-run-20260909-r1/half_r1.sim"
        opened = await call("open", "nx_sim_open", {"path": path})
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        identity = await call("identity", "nx_sim_result_identity", {"document": sid})
        digest = identity["files"][0]["sha256"]
        args = {"document": sid, "result_sha256": digest}
        regions = await call("regions", "nx_sim_temperature_regions", args)
        assert sorted(
            (r["defined_node_count"], r["undefined_node_count"]) for r in regions["items"]
        ) == [(0, 11528), (6238, 0)]
        page = await call(
            "tail", "nx_sim_temperature_nodes", {**args, "offset": 17666, "limit": 100}
        )
        assert len(page["items"]) == 100 and page["next_offset"] is None
        assert all(r["temperature"] is None and r["defined"] is False for r in page["items"])
        await call(
            "wrong_digest",
            "nx_sim_temperature_nodes",
            {**args, "result_sha256": "0" * 64},
            error=True,
        )
        receipt.update(passed=True, solver_launched=False, document=sid)
        record()


if __name__ == "__main__":
    asyncio.run(main())
