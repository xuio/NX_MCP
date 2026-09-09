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
    output = shared / "sim-update-export-public.json"

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

        fixture = json.loads((shared / "sim-update-fixture-public.json").read_text())
        sim = await call("open", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        sid = sim["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        saved = await call(
            "save_as",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/U-sim-update-export-20260909-r1/sim_update_export_u_r1.sim",
                "operation_id": "sim-update-export-saveas-r1",
            },
        )
        sid = saved["document"]["id"]
        exported = await call(
            "export",
            "nx_sim_export_input",
            {"document": sid, "operation_id": "sim-update-isolated-export-r1"},
        )
        receipt.update(
            completed=True,
            export=exported,
            solver_launched=False,
            numerical_acceptance="not_established",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
