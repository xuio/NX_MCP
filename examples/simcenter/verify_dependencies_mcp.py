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
        schema = next(t for t in available.tools if t.name == "nx_sim_dependencies")
        before = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        assert not before.isError
        current = next(
            d
            for d in before.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert current["path"].endswith("mcp_saved_copy.sim")
        document = current["document"]["id"]
        pages = []
        for offset in range(4):
            page = await client.call_tool(
                "nx_sim_dependencies", {"document": document, "offset": offset, "limit": 1}
            )
            assert not page.isError, page.structuredContent
            assert page.structuredContent["total"] == 3
            pages.append(page)
        assert pages[3].structuredContent["documents"] == []
        rows = [p.structuredContent["documents"][0] for p in pages[:3]]
        assert rows[0]["roles"] == ["simulation"] and rows[1]["roles"] == ["mesh"]
        assert "AssociatedCadPart" in rows[2]["roles"]
        assert rows[1]["path"].endswith("benchmark_4ba7072a1d7a_mesh.fem")
        invalid = await client.call_tool("nx_sim_dependencies", {"document": document, "limit": 0})
        assert invalid.isError
        after = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        assert not after.isError

        def view(data):
            return [
                (d["path"], d["modified"], d["work"], d["display"])
                for d in data.structuredContent["documents"]
            ]

        assert view(before) == view(after)
        result = {
            "transport": "real MCP stdio -> Simcenter UI bridge",
            "schema": schema.model_dump(mode="json"),
            "pages": [p.model_dump(mode="json") for p in pages],
            "invalid": invalid.model_dump(mode="json"),
            "session_flags_unchanged": True,
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-dependencies.json").write_text(
            json.dumps(result, indent=2)
        )
        print("Native MCP dependency inspection finished")


asyncio.run(main())
