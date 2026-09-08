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
        assert any(t.name == "nx_sim_solutions" for t in available.tools)
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        page = await client.call_tool(
            "nx_sim_descriptors", {"document": document, "kind": "solution_step", "limit": 1}
        )
        assert not page.isError, page.structuredContent
        assert page.structuredContent["descriptors"] == [
            {
                "descriptor_name": "Step - Thermal Flow",
                "kind": "solution_step",
                "step_type_index": 0,
            }
        ]
        assert page.structuredContent["solution_applicability"] == "native_allowable_step"
        end = await client.call_tool(
            "nx_sim_descriptors", {"document": document, "kind": "solution_step", "offset": 1}
        )
        assert not end.isError and end.structuredContent["descriptors"] == []
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-step-descriptors.json").write_text(
            json.dumps(
                {
                    "page": page.model_dump(mode="json"),
                    "end": end.model_dump(mode="json"),
                    "modified_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Native public allowable-step discovery verified")


asyncio.run(main())
