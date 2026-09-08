"""Inspect the completed native flow job through the read-only public log audit."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
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
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        result = await client.call_tool(
            "nx_sim_job_status", {"job_id": "public-prepared-flow-01", "include_evidence": True}
        )
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-job-observer.json")
        output.write_text(json.dumps(result.model_dump(mode="json"), indent=2))
        assert not result.isError, result.structuredContent
        r = result.structuredContent
        assert r["state"] == "solver_exited" and r["revision"] == 3
        assert r["evidence"]["observer_adapter"] == 1
        assert r["evidence"]["input_comparison"]["xml_content_identical"]
        assert r["numerical_convergence"] == "not_established"
        print("Independent observer terminal record is visible through public MCP job status")


asyncio.run(main())
