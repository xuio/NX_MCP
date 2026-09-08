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

        async def call(name, args):
            response = await client.call_tool(name, args)
            if response.isError:
                raise RuntimeError(response.model_dump(mode="json"))
            return response.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100})
        original = next(d for d in docs["documents"] if d["work"])
        target = next(
            d
            for d in docs["documents"]
            if d["path"].endswith(r"F-input-export-20260908-r2\flow_input_r2.sim")
        )
        doc = target["document"]["id"]
        await call("nx_sim_activate", {"document": doc})
        try:
            pressure = await call("nx_sim_pressure_result", {"document": doc})
            total = await call(
                "nx_sim_pressure_result", {"document": doc, "field": "total_pressure"}
            )
            assert pressure["field"] == "Pressure - Element-Nodal"
            assert total["field"] == "Total Pressure - Element-Nodal"
            for result in (pressure, total):
                assert result["units"] == "Pa" and result["minimum"] <= result["maximum"]
                assert result["node_count"] > 0 and result["result_freshness"] == "not_verified"
            invalid = await client.call_tool(
                "nx_sim_pressure_result", {"document": doc, "loadcase_index": 10000}
            )
            assert invalid.isError
        finally:
            await call("nx_sim_activate", {"document": original["document"]["id"]})
        after = await call("nx_sim_documents", {"limit": 100})
        assert {d["path"]: d["modified"] for d in docs["documents"]} == {
            d["path"]: d["modified"] for d in after["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-pressure-result.json").write_text(
            json.dumps(
                {
                    "pressure": pressure,
                    "total_pressure": total,
                    "invalid_index": invalid.model_dump(mode="json"),
                    "document_flags_preserved": True,
                    "active_document_restored": True,
                },
                indent=2,
            )
        )
        print("Native public pressure and total-pressure readback verified")


asyncio.run(main())
