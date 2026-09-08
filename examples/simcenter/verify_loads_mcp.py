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
        schema = next(t for t in available.tools if t.name == "nx_sim_loads")
        before = await client.call_tool("nx_sim_documents", {"limit": 100})
        sim = next(
            d
            for d in before.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert sim["path"].endswith("saved_power.sim")
        args = {"document": sim["document"]["id"]}
        compact = await client.call_tool("nx_sim_loads", args)
        assert not compact.isError, compact.structuredContent
        expanded = await client.call_tool(
            "nx_sim_loads", {**args, "include_targets": True, "include_properties": True}
        )
        assert not expanded.isError, expanded.structuredContent
        row = next(
            c
            for c in expanded.structuredContent["loads"]
            if c["load"]["display_name"] == "MCP_INTERNAL_POWER"
        )
        assert row["energy_accounting"] == "internal_heat" and row["provenance"]
        assert sum(s["count"] for s in row["target_sets"]) == 1
        assert all("body" in m for s in row["target_sets"] for m in s["members"])
        assert (
            float(next(p["expression"] for p in row["properties"] if p["name"] == "Heat Load"))
            == 0.1
        )
        power = next(p for p in row["properties"] if p["name"] == "Heat Load")
        assert power["unit_symbol"] == "W", power
        empty = await client.call_tool(
            "nx_sim_loads", {**args, "offset": expanded.structuredContent["total"]}
        )
        assert not empty.isError and not empty.structuredContent["loads"]
        constraints = await client.call_tool(
            "nx_sim_constraints", {**args, "include_properties": True, "include_targets": True}
        )
        assert not constraints.isError
        assert (
            sum(
                s["count"]
                for c in constraints.structuredContent["constraints"]
                for s in c["target_sets"]
            )
            == 6
        )
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert before.structuredContent["documents"] == after.structuredContent["documents"]
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-loads.json").write_text(
            json.dumps(
                {
                    "schema": schema.model_dump(mode="json"),
                    "compact": compact.model_dump(mode="json"),
                    "expanded": expanded.model_dump(mode="json"),
                    "empty": empty.model_dump(mode="json"),
                    "documents_unchanged": True,
                    "constraint_regression": constraints.model_dump(mode="json"),
                },
                indent=2,
            )
        )
        print("Native MCP load inventory verified")


asyncio.run(main())
