"""Read-only MCP verification on the isolated Windows Simcenter installation."""

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
        available = await client.list_tools()
        schema = next(t for t in available.tools if t.name == "nx_sim_show_temperature")
        assert "operation_id" in schema.inputSchema["properties"]
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        assert any(
            d["work"] and d["path"].endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim")
            for d in docs.structuredContent["documents"]
        )
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        args = {
            "document": document,
            "name": "MCP uniform conduction temperature",
            "operation_id": "show-conduction-temperature-01",
        }
        page = await client.call_tool("nx_sim_show_temperature", args)
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-postview.json")
        responses = {"created": page.model_dump(mode="json")}
        output.write_text(json.dumps(responses, indent=2))
        assert not page.isError, page.structuredContent
        assert page.structuredContent["readback"]["unit"] == "Celsius"
        replay = await client.call_tool("nx_sim_show_temperature", args)
        assert (
            not replay.isError
            and replay.structuredContent["postview_id"] == page.structuredContent["postview_id"]
        )
        invalid = await client.call_tool(
            "nx_sim_show_temperature",
            {**args, "loadcase_index": 10000, "operation_id": "show-conduction-invalid-01"},
        )
        assert invalid.isError
        responses.update(
            replay=replay.model_dump(mode="json"), invalid=invalid.model_dump(mode="json")
        )
        output.write_text(json.dumps(responses, indent=2))
        print("Native temperature postview, readback and replay verified")


asyncio.run(main())
