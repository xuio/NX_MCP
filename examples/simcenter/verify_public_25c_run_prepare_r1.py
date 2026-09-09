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
    output = shared / "public-25c-run-prepare-r1.json"

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

        source = json.loads((shared / "public-25c-prepare-r1.json").read_text())
        sid = source["responses"]["0_create"]["structuredContent"]["sim"]["id"]
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/public-run-25c-r1/public_25c_r1.sim",
                "operation_id": "public-25c-copy-r1",
            },
        )
        sid = copied["document"]["id"]
        await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": "public-user-cad-25c-r1",
                "operation_id": "public-25c-prepare-run-r1",
            },
        )
        receipt.update(
            passed=True, solver_launched=False, document=sid, job_id="public-user-cad-25c-r1"
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
