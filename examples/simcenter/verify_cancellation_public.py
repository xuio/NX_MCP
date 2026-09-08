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
    context = json.loads((shared / "cancel-contract-context.json").read_text())
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
    output = shared / "cancel-contract-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        tool = next(t for t in (await client.list_tools()).tools if t.name == "nx_sim_cancel")
        assert tool.annotations.readOnlyHint is False
        args = {
            "job_id": "accepted",
            "expected_revision": 0,
            "job_folder": context["job_folder"],
            "operation_id": "cancel-contract-public-r1",
        }
        for key in ("cancel", "replay"):
            response = await client.call_tool("nx_sim_cancel", args)
            receipt["responses"][key] = response.model_dump(mode="json")
            record()
            assert not response.isError, response
            data = response.structuredContent
            assert data["state"] == "cancelled" and data["revision"] == 1
            assert not data["solver_stop_requested"] and not data["launch_retry_allowed"]
        rejected = await client.call_tool(
            "nx_sim_cancel",
            {
                "job_id": "intent",
                "expected_revision": 1,
                "job_folder": context["job_folder"],
                "operation_id": "cancel-contract-rejected-r1",
            },
        )
        receipt["responses"]["intent_rejected"] = rejected.model_dump(mode="json")
        record()
        assert rejected.isError
        data = rejected.structuredContent
        if data["code"] == "NX_OPERATION_FAILED":
            data = data["details"]["error"]
        assert data["code"] == "NX_SIM_CANCELLATION_UNAVAILABLE"
        receipt["passed"] = True
        receipt["scope"] = context["verification_scope"]
        record()


if __name__ == "__main__":
    asyncio.run(main())
