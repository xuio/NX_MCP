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
        solutions = await client.call_tool("nx_sim_solutions", {"document": document})
        assert not solutions.isError
        target = next(
            r
            for r in solutions.structuredContent["solutions"]
            if r["solution"]["name"] == "MCP_SELECTION_PROBE"
        )
        assert not target["active"]
        args = {
            "document": document,
            "solution": target["solution"]["id"],
            "limit": 2,
            "include_properties": True,
        }
        first = await client.call_tool("nx_sim_steps", args)
        assert not first.isError, first.structuredContent
        assert first.structuredContent["next_offset"] == 2
        second = await client.call_tool("nx_sim_steps", {**args, "offset": 2})
        assert not second.isError
        rows = first.structuredContent["steps"] + second.structuredContent["steps"]
        times = [next(p["value"] for p in r["properties"] if p["name"] == "End Time") for r in rows]
        assert times == [0, 10, 20]
        assert len({r["step"]["id"] for r in rows}) == 3
        assert all(r["step"]["kind"] == "simulation_step" for r in rows)
        after = await client.call_tool("nx_sim_solutions", {"document": document})
        assert (
            next(r for r in after.structuredContent["solutions"] if r["active"])["solution"]["name"]
            == "Conduction"
        )
        docs_after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in docs_after.structuredContent["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-steps.json").write_text(
            json.dumps(
                {
                    "first": first.model_dump(mode="json"),
                    "second": second.model_dump(mode="json"),
                    "times_s": times,
                    "active_solution_preserved": True,
                    "document_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Native paged inactive-solution step readback verified")


asyncio.run(main())
