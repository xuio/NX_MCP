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
        schema = next(t.inputSchema for t in tools.tools if t.name == "nx_sim_external_temperature")
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        document = next(
            d["document"]["id"]
            for d in docs.structuredContent["documents"]
            if d["work"] and "E-external-public-20260908-r1" in d["path"]
        )
        objects = await client.call_tool("nx_sim_objects", {"document": document})
        assert not objects.isError, objects.structuredContent
        boundaries = [
            r["object"]["id"]
            for r in objects.structuredContent["simulation_objects"]
            if r["descriptor"] in ("Inlet", "Opening")
        ]
        assert len(boundaries) == 2
        args = {
            "document": document,
            "boundaries": boundaries,
            "name": "External air 20 C",
            "temperature_c": 20.0,
            "operation_id": "external-temperature-public-r1",
        }
        first = await client.call_tool("nx_sim_external_temperature", args)
        assert not first.isError, first.structuredContent
        replay = await client.call_tool("nx_sim_external_temperature", args)
        assert not replay.isError, replay.structuredContent
        saved = await client.call_tool(
            "nx_sim_save", {"document": document, "operation_id": "external-temperature-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\external-temperature-public.json"
        ).write_text(
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
