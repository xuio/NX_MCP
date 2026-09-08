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
        assert any(
            d["work"] and d["path"].endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim")
            for d in docs.structuredContent["documents"]
        )
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        page = await client.call_tool(
            "nx_sim_solutions", {"document": document, "limit": 1, "include_properties": True}
        )
        assert not page.isError, page.structuredContent
        row = next(r for r in page.structuredContent["solutions"] if r["active"])
        assert row["solution"]["kind"] == "simulation_solution" and row["analysis"] == "Thermal"
        args = {
            "document": document,
            "solution": row["solution"]["id"],
            "operation_id": "select-current-thermal-01",
        }
        selected = await client.call_tool("nx_sim_select_solution", args)
        assert not selected.isError and selected.structuredContent["already_active"]
        invalid = await client.call_tool("nx_sim_solutions", {"document": document, "limit": 0})
        assert invalid.isError
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-solutions.json").write_text(
            json.dumps(
                {
                    "inventory": page.model_dump(mode="json"),
                    "selected": selected.model_dump(mode="json"),
                    "invalid": invalid.model_dump(mode="json"),
                    "modified_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Native public solution inventory and already-active selection verified")


asyncio.run(main())
