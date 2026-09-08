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
        schema = next(t for t in available.tools if t.name == "nx_sim_save_as")
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        assert not docs.isError
        row = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        document = row["document"]["id"]
        assert row["path"].endswith("unique_job_copy.sim")
        invalid = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": document,
                "path": row["path"],
                "operation_id": "verify-saveas-reject-20260908-01",
            },
        )
        assert invalid.isError
        args = {
            "document": document,
            "path": "ui-benchmarks/F-sim-copy-20260908-r1/mcp_saved_copy.sim",
            "operation_id": "verify-saveas-20260908-01",
        }
        copied = await client.call_tool("nx_sim_save_as", args)
        assert not copied.isError, copied.structuredContent
        assert copied.structuredContent["source_file_unchanged"] is True
        assert copied.structuredContent["independent_geometry_variant"] is False
        replay = await client.call_tool("nx_sim_save_as", args)
        assert not replay.isError, replay.structuredContent
        assert (
            replay.structuredContent["document"]["id"] == copied.structuredContent["document"]["id"]
        )
        stale = await client.call_tool("nx_sim_result_inventory", {"document": document})
        assert stale.isError
        result = {
            "transport": "real MCP stdio -> Simcenter UI bridge",
            "schema": schema.model_dump(mode="json"),
            "responses": {
                k: v.model_dump(mode="json")
                for k, v in {
                    "invalid": invalid,
                    "copied": copied,
                    "replay": replay,
                    "stale": stale,
                }.items()
            },
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-sim-saveas.json").write_text(
            json.dumps(result, indent=2)
        )
        print("Native MCP SIM SaveAs verification finished")


asyncio.run(main())
