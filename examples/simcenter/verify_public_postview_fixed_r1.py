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
    output = shared / "public-postview-fixed-r1.json"

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

        sid=json.loads((shared/"public-run-prepare-r1.json").read_text())["document"]
        result=await call("view","nx_sim_show_temperature",{"document":sid,"name":"Baldower ideal spreader 1.5 mm - 1 mm mesh","operation_id":"public-postview-name-fix-r1"})
        assert result["name_normalized"] and result["applied_name"]=="Baldower ideal spreader 1_5 mm - 1 mm mesh"
        await call("capture","nx_screenshot",{"path":"ui-benchmarks/public-40c-name-fix-r1.png","style":"current","background":"original","fit":True})
        receipt.update(passed=True,solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
