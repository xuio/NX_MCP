"""Verify restored evaluator tools through public MCP on isolated CAD fixtures."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "step-membership-limit.json").read_text())
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
    output = shared / "step-order-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        response = await client.call_tool(
            "nx_sim_solutions",
            {"document": context["document"], "include_membership": True, "limit": 1},
        )
        receipt["responses"]["solutions"] = response.model_dump(mode="json")
        record()
        assert not response.isError, response
        row = response.structuredContent["solutions"][0]
        assert row["step_count"] == 2
        assert row["membership"] == context["ordered"]
        receipt["passed"] = True
        receipt["scope"] = (
            "Native step ordering and global membership inspection; step-level load assignment remains unverified"
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
