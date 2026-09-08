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
        schema = next(t for t in available.tools if t.name == "nx_sim_temperature_result")
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
            "nx_sim_temperature_result",
            {"document": document, "loadcase_index": 0, "iteration_index": 0},
        )
        if page.isError:
            raise RuntimeError(page.structuredContent)
        assert page.structuredContent["result_freshness"] == "not_verified"
        assert page.structuredContent["units"] == "degC"
        assert page.structuredContent["minimum"] == 20
        assert abs(page.structuredContent["maximum"] - 22.500463485717773) < 1e-8
        assert page.structuredContent["node_count"] == 756
        out_of_range = await client.call_tool(
            "nx_sim_temperature_result", {"document": document, "loadcase_index": 100000}
        )
        assert out_of_range.isError
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        invalid = await client.call_tool(
            "nx_sim_temperature_result", {"document": document, "loadcase_index": -1}
        )
        assert invalid.isError
        result = {
            "transport": "MCP stdio -> descriptor bridge -> NX UI thread",
            "schema": schema.model_dump(mode="json"),
            "page": page.model_dump(mode="json"),
            "invalid": invalid.model_dump(mode="json"),
            "out_of_range": out_of_range.model_dump(mode="json"),
            "modified_flags_unchanged": True,
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-temperature-result.json").write_text(
            json.dumps(result, indent=2)
        )
        print("MCP temperature results and invalid-index checks passed")


asyncio.run(main())
