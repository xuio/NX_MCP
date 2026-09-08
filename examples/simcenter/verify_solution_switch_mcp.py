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
        responses = {}

        async def call(name, args, key):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            Path(
                r"Z:\nx-mcp-integration\simcenter-discovery\stdio-solution-switch.json"
            ).write_text(json.dumps(responses, indent=2))
            assert not r.isError, r.structuredContent
            return r.structuredContent

        page = await call("nx_sim_solutions", {"document": document}, "before")
        original = next(r for r in page["solutions"] if r["active"])["solution"]["id"]
        target = next(
            r for r in page["solutions"] if r["solution"]["name"] == "MCP_SELECTION_PROBE"
        )["solution"]["id"]
        try:
            switched = await call(
                "nx_sim_select_solution",
                {
                    "document": document,
                    "solution": target,
                    "operation_id": "distinct-solution-switch-01",
                },
                "switched",
            )
            assert not switched["already_active"]
            page = await call("nx_sim_solutions", {"document": document}, "readback")
            assert [r["solution"]["id"] for r in page["solutions"] if r["active"]] == [target]
            other = next(
                d
                for d in docs.structuredContent["documents"]
                if d["document_type"] == "SimPart" and d["document"]["id"] != document
            )
            foreign = await call(
                "nx_sim_solutions", {"document": other["document"]["id"]}, "foreign_inventory"
            )
            foreignid = foreign["solutions"][0]["solution"]["id"]
            rejected = await client.call_tool(
                "nx_sim_select_solution",
                {
                    "document": document,
                    "solution": foreignid,
                    "operation_id": "foreign-solution-reject-01",
                },
            )
            responses["foreign_rejected"] = rejected.model_dump(mode="json")
            assert (
                rejected.isError and rejected.structuredContent["code"] == "NX_SIM_SELECTION_OWNER"
            )
        finally:
            await call(
                "nx_sim_select_solution",
                {
                    "document": document,
                    "solution": original,
                    "operation_id": "restore-conduction-solution-01",
                },
                "restored",
            )
        final = await call("nx_sim_solutions", {"document": document}, "final")
        assert [r["solution"]["id"] for r in final["solutions"] if r["active"]] == [original]
        print("Distinct solution switch, foreign-owner rejection and restoration verified")


asyncio.run(main())
