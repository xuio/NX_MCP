"""Observe the existing refined flow job, release its gate and audit its log."""

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
        tools = await client.list_tools()
        schema = next(t.inputSchema for t in tools.tools if t.name == "nx_sim_flow_setup")
        assert "coupled_steady" in schema["properties"]["action"]["enum"]
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        document = next(
            d["document"]["id"]
            for d in docs.structuredContent["documents"]
            if d["work"] and "E-development-steady-20260908-r1" in d["path"]
        )
        args = {
            "document": document,
            "action": "coupled_steady",
            "operation_id": "coupled-steady-public-r1",
        }
        first = await client.call_tool("nx_sim_flow_setup", args)
        assert not first.isError, first.structuredContent
        replay = await client.call_tool("nx_sim_flow_setup", args)
        assert not replay.isError, replay.structuredContent
        saved = await client.call_tool(
            "nx_sim_save", {"document": document, "operation_id": "coupled-boundaries-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\coupled-steady-public.json").write_text(
            json.dumps(
                {
                    "schema": schema,
                    "first": first.model_dump(mode="json"),
                    "replay": replay.model_dump(mode="json"),
                    "saved": saved.model_dump(mode="json"),
                },
                indent=2,
            )
        )


asyncio.run(main())
