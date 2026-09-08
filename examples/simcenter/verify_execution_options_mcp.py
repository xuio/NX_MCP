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
        compact = await client.call_tool("nx_sim_solutions", {"document": document})
        expanded = await client.call_tool(
            "nx_sim_solutions", {"document": document, "include_execution_options": True}
        )
        assert not compact.isError and not expanded.isError
        compact_rows = compact.structuredContent["solutions"]
        rows = expanded.structuredContent["solutions"]
        assert rows and len(rows) == len(compact_rows)
        assert all("execution_options" not in r for r in compact_rows)
        assert all("properties" not in r for r in rows)
        for row in rows:
            options = row["execution_options"]
            assert options and not options["settings_applied_by_call"]
            assert not options["licence_checkout_tested"]
            props = {p["name"]: p for p in options["properties"]}
            assert not any("licen" in name.lower() for name in props)
            assert props["Remote Solve"]["value"] is False
            assert props["Maximum Number of CPUs"]["value"] == 1
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-execution-options.json").write_text(
            json.dumps(
                {
                    "compact": compact.model_dump(mode="json"),
                    "expanded": expanded.model_dump(mode="json"),
                    "modified_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Native public execution-options readback verified")


asyncio.run(main())
