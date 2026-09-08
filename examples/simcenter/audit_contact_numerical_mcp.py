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

        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-solve-finish.json")
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
                {"job_id": "contact-resistance-r1", "include_evidence": True},
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
            {"job_id": "contact-resistance-r1", "operation_id": "contact-release-r1"},
        )
        responses["release"] = release.model_dump(mode="json")
        record()
        assert not release.isError and release.structuredContent["released"]
        prepared = json.loads(
            Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-job-prepared.json").read_text()
        )
        document = prepared["benchmark_document"]
        result = await client.call_tool("nx_sim_temperature_result", {"document": document})
        responses["temperature"] = result.model_dump(mode="json")
        record()
        assert not result.isError, result.structuredContent
        identity = await client.call_tool(
            "nx_sim_result_identity", {"document": document, "job_id": "contact-resistance-r1"}
        )
        responses["identity"] = identity.model_dump(mode="json")
        record()
        assert not identity.isError, identity.structuredContent
        assert identity.structuredContent["job_binding"]["live_thermal_state"]["state"] == "matches"
        shown = await client.call_tool(
            "nx_sim_show_temperature",
            {"document": document, "operation_id": "contact-show-r1"},
        )
        responses["visible_result"] = shown.model_dump(mode="json")
        record()
        assert not shown.isError, shown.structuredContent
        print(
            "Contact solver exited; temperature result retrieved. Heat-balance acceptance is separate."
        )


asyncio.run(main())
