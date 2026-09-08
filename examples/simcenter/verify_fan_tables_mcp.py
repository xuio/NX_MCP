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
            if "F-fan-reopen-20260908-r1" in d["path"] and d["document_type"] == "SimPart"
        )
        doc = target["document"]["id"]
        await call("nx_sim_activate", {"document": doc})
        try:
            before = await call("nx_sim_fan_tables", {"document": doc})
            args = {
                "document": doc,
                "name": "Public MCP synthetic fan r1",
                "points": [[0, 1], [0.0002, 0.5], [0.0004, 0]],
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": 1.2,
                "stall_region": "Not modelled; synthetic",
                "provenance_kind": "assumed",
                "provenance_source": "Public MCP fixture only",
                "operation_id": "fan-table-public-20260908-r1",
            }
            created = await call("nx_sim_fan_table", args)
            assert created["field"]["kind"] == "simulation_field"
            replay = await call("nx_sim_fan_table", args)
            assert replay["field"]["id"] == created["field"]["id"]
            after = await call("nx_sim_fan_tables", {"document": doc, "include_samples": True})
            assert after["total"] == before["total"] + 1
            row = next(r for r in after["tables"] if r["field"]["id"] == created["field"]["id"])
            assert row["readback"]["flow_m3_s"] == [0, 0.0002, 0.0004]
            compact = await call("nx_sim_fan_tables", {"document": doc, "limit": 1})
            assert compact["next_offset"] == 1
            assert "points" not in compact["tables"][0]["manifest"]
            duplicate_args = {k: v for k, v in args.items() if k != "operation_id"}
            duplicate = await client.call_tool("nx_sim_fan_table", duplicate_args)
            assert duplicate.isError
            unchanged = await call("nx_sim_fan_tables", {"document": doc})
            assert unchanged["total"] == after["total"]
        finally:
            await call("nx_sim_activate", {"document": original["document"]["id"]})
        final_docs = await call("nx_sim_documents", {"limit": 100})
        assert {
            d["path"]: d["modified"] for d in docs["documents"] if d["path"] != target["path"]
        } == {
            d["path"]: d["modified"] for d in final_docs["documents"] if d["path"] != target["path"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-fan-tables.json").write_text(
            json.dumps(
                {
                    "created": created,
                    "inventory": after,
                    "compact": compact,
                    "replay_deduplicated": True,
                    "duplicate": duplicate.model_dump(mode="json"),
                    "other_document_flags_preserved": True,
                    "active_document_restored": True,
                },
                indent=2,
            )
        )
        print("Public MCP fan table creation, readback and retry verified")


asyncio.run(main())
