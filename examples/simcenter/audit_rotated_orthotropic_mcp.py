"""Observe the existing orthotropic thermal job and retrieve temperatures."""

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
        import time

        output = Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\stdio-orthotropic-rotated-finish.json"
        )
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

        deadline = time.monotonic() + 240
        while True:
            status = await client.call_tool(
                "nx_sim_job_status",
                {"job_id": "orthotropic-rotated-thermal-01", "include_evidence": True},
            )
            responses["status_observations"].append(status.model_dump(mode="json"))
            record()
            assert not status.isError, status.structuredContent
            if status.structuredContent["state"] == "solver_exited":
                break
            assert time.monotonic() < deadline, (
                "Observation timeout; retain the existing job, never relaunch"
            )
            await asyncio.sleep(15)
        assert status.structuredContent["evidence"]["observer_adapter"] == 1
        assert status.structuredContent["evidence"]["input_comparison"]["xml_content_identical"]
        release = await client.call_tool(
            "nx_sim_release_job",
            {
                "job_id": "orthotropic-rotated-thermal-01",
                "operation_id": "orthotropic-rotated-release-01",
            },
        )
        responses["release"] = release.model_dump(mode="json")
        record()
        assert not release.isError and release.structuredContent["released"]
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        document = next(
            d["document"]["id"]
            for d in docs.structuredContent["documents"]
            if d["work"] and d["path"].endswith("rotated_ortho_solve_r1.sim")
        )
        result = await client.call_tool("nx_sim_temperature_result", {"document": document})
        responses["temperature"] = result.model_dump(mode="json")
        record()
        assert not result.isError, result.structuredContent
        print(
            "Orthotropic solver exited; temperature result retrieved. Numerical acceptance is separate."
        )


asyncio.run(main())
