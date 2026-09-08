"""Verify public temperature field selection on the completed coupled diagnostic."""

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
        schema = next(t.inputSchema for t in tools.tools if t.name == "nx_sim_temperature_result")
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        document = next(
            d["document"]["id"]
            for d in docs.structuredContent["documents"]
            if d["work"] and "E-external-diagnostic-20260908-r1" in d["path"]
        )
        responses = {}
        out = Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\coupled-temperature-fields-public.json"
        )
        assert set(schema["properties"]["location"]["enum"]) == {
            "nodal",
            "elemental",
            "element_nodal",
        }
        for location in ("nodal", "elemental", "element_nodal"):
            response = await client.call_tool(
                "nx_sim_temperature_result", {"document": document, "location": location}
            )
            responses[location] = response.model_dump(mode="json")
            out.write_text(json.dumps({"schema": schema, "responses": responses}, indent=2))
            assert not response.isError, response.structuredContent
            assert response.structuredContent["field_location"] == location
            assert response.structuredContent["units"] == "degC"
        assert 20 < responses["element_nodal"]["structuredContent"]["minimum"] < 20.1
        assert 22 < responses["element_nodal"]["structuredContent"]["maximum"] < 22.2
        assert 43 < responses["nodal"]["structuredContent"]["maximum"] < 43.3


asyncio.run(main())
