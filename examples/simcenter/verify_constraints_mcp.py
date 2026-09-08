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
        schema = next(t for t in available.tools if t.name == "nx_sim_constraints")
        before = await client.call_tool("nx_sim_documents", {"limit": 100})
        sim = next(
            d
            for d in before.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert sim["path"].endswith("saved_convection.sim")
        args = {"document": sim["document"]["id"]}
        compact = await client.call_tool("nx_sim_constraints", args)
        assert not compact.isError, compact.structuredContent
        expanded = await client.call_tool(
            "nx_sim_constraints", {**args, "include_targets": True, "include_properties": True}
        )
        assert not expanded.isError, expanded.structuredContent
        row = next(
            c
            for c in expanded.structuredContent["constraints"]
            if c["constraint"]["display_name"] == "MCP_ASSUMED_CONVECTION"
        )
        assert row["coefficient_basis"] == "assumed" and row["provenance"]
        assert sum(s["count"] for s in row["target_sets"]) == 6
        assert all("face" in m for s in row["target_sets"] for m in s["members"])
        assert (
            float(
                next(
                    p["expression"]
                    for p in row["properties"]
                    if p["name"] == "Convection Coefficient"
                )
            )
            == 10
        )
        empty = await client.call_tool(
            "nx_sim_constraints", {**args, "offset": expanded.structuredContent["total"]}
        )
        assert not empty.isError and not empty.structuredContent["constraints"]
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert before.structuredContent["documents"] == after.structuredContent["documents"]
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-constraints.json").write_text(
            json.dumps(
                {
                    "schema": schema.model_dump(mode="json"),
                    "compact": compact.model_dump(mode="json"),
                    "expanded": expanded.model_dump(mode="json"),
                    "empty": empty.model_dump(mode="json"),
                    "documents_unchanged": True,
                },
                indent=2,
            )
        )
        print("Native MCP constraint inventory verified")


asyncio.run(main())
