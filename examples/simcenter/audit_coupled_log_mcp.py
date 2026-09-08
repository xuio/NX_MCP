"""Observe the existing coupled diagnostic and release only its verified terminal gate."""

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

        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\coupled-diagnostic-audit-public.json")
        responses = {"status_observations": []}

        def record():
            output.write_text(
                json.dumps(
                    {
                        "transport": "new MCP stdio client after launch client disconnected",
                        "responses": responses,
                    },
                    indent=2,
                )
            )

        audit = await client.call_tool(
            "nx_sim_flow_log",
            {"job_id": "coupled-diagnostic-r1", "log_name": "coupled_diagnostic_r1-Coupled_benchmark.log", "limit": 1},
        )
        responses["audit"] = audit.model_dump(mode="json")
        record()
        assert not audit.isError, audit.structuredContent
        summary = audit.structuredContent["coupled_summary"]
        assert summary["numerical_convergence"] == "failed"
        assert summary["ambient_temperature_degC"] == 0
        assert summary["iteration_limit_reached_without_convergence"]


if __name__ == "__main__":
    asyncio.run(main())
