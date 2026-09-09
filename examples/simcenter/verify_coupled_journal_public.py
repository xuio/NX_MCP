"""Isolated flow input export MCP verification on the isolated Windows Simcenter installation."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", type=int, default=1, choices=range(1, 101))
    parser.add_argument("--source-name", default="journal_public.sim")
    options = parser.parse_args()
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
        schema = next(t for t in available.tools if t.name == "nx_sim_export_input")
        rows = []
        for offset in range(0, 1000, 100):
            docs = await client.call_tool("nx_sim_documents", {"offset": offset, "limit": 100})
            assert not docs.isError
            page = docs.structuredContent["documents"]
            rows.extend(page)
            if len(page) < 100:
                break
        row = next(d for d in rows if d["work"] and d["document_type"] == "SimPart")
        assert "ui-benchmarks" in row["path"] and row["path"].endswith(options.source_name)
        setup = await client.call_tool(
            "nx_sim_flow_setup",
            {
                "document": row["document"]["id"],
                "action": "coupled_steady",
                "operation_id": "journal-public-setup-20260909-r1",
            },
        )
        assert not setup.isError, setup.structuredContent
        copied = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": row["document"]["id"],
                "path": "ui-benchmarks/E-journal-public-export-20260909-r1/export.sim",
                "operation_id": "journal-public-save-20260909-r1",
            },
        )
        assert not copied.isError, copied.structuredContent
        args = {
            "document": copied.structuredContent["document"]["id"],
            "operation_id": f"journal-public-export-20260908-{options.revision:02d}",
        }
        exported = await client.call_tool("nx_sim_export_input", args)
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\journal-public-export-r1.json")
        responses = {
            "setup": setup.model_dump(mode="json"),
            "copied": copied.model_dump(mode="json"),
            "exported": exported.model_dump(mode="json"),
        }
        output.write_text(
            json.dumps({"schema": schema.model_dump(mode="json"), "responses": responses}, indent=2)
        )
        assert not exported.isError, exported.structuredContent
        assert exported.structuredContent["validation"]["mesh_counts"]["elements"] == 2130
        assert not exported.structuredContent["solver_launched"]
        replay = await client.call_tool("nx_sim_export_input", args)
        assert not replay.isError
        assert (
            replay.structuredContent["input_identity"]
            == exported.structuredContent["input_identity"]
        )
        rejected = await client.call_tool(
            "nx_sim_export_input",
            {
                **args,
                "operation_id": f"journal-public-export-duplicate-20260908-{options.revision:02d}",
            },
        )
        assert rejected.isError
        responses.update(
            replay=replay.model_dump(mode="json"), rejected=rejected.model_dump(mode="json")
        )
        output.write_text(
            json.dumps(
                {
                    "transport": "real MCP stdio -> Simcenter UI bridge",
                    "schema": schema.model_dump(mode="json"),
                    "responses": responses,
                },
                indent=2,
            )
        )
        print("Native MCP flow export and retry checks finished")


asyncio.run(main())
