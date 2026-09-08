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
        schema = next(t for t in available.tools if t.name == "nx_sim_result_identity")
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        page = await client.call_tool(
            "nx_sim_result_identity", {"document": document, "maximum_bytes": 100_000_000}
        )
        if page.isError:
            raise RuntimeError(page.structuredContent)
        assert page.structuredContent["result_freshness"] == "not_verified"
        assert page.structuredContent["engineering_accepted"] is False
        assert page.structuredContent["files"]
        invalid = await client.call_tool(
            "nx_sim_result_identity", {"document": document, "maximum_bytes": 0}
        )
        assert invalid.isError
        result = {
            "transport": "MCP stdio -> descriptor bridge -> NX UI thread",
            "schema": schema.model_dump(mode="json"),
            "page": page.model_dump(mode="json"),
            "invalid": invalid.model_dump(mode="json"),
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-result-identity.json").write_text(
            json.dumps(result, indent=2)
        )
        print("MCP stdio identity test finished")


asyncio.run(main())
