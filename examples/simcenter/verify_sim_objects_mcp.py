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
            compact = await call("nx_sim_objects", {"document": doc, "limit": 1})
            assert compact["next_offset"] == 1
            rows = []
            offset = 0
            while True:
                page = await call(
                    "nx_sim_objects",
                    {
                        "document": doc,
                        "offset": offset,
                        "limit": 1,
                        "include_properties": True,
                        "include_targets": True,
                    },
                )
                rows.extend(page["simulation_objects"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
                assert offset < 100
            inlet = next(r for r in rows if r["object"]["name"] == "Duct Inlet")
            assert inlet["descriptor"] == "Inlet"
            assert inlet["object"]["kind"] == "simulation_object"
            assert inlet["fan_binding"]["field"]["kind"] == "simulation_field"
            assert inlet["fan_binding"]["mode"] == 5
            assert inlet["fan_binding"]["scale_factor"] == 1
            assert any(r["descriptor"] == "Opening" for r in rows)
            assert any(t["count"] > 0 for t in inlet["target_sets"])
            assert "properties" not in compact["simulation_objects"][0]
        finally:
            await call("nx_sim_activate", {"document": original["document"]["id"]})
        final = await call("nx_sim_documents", {"limit": 100})
        assert {d["path"]: d["modified"] for d in docs["documents"]} == {
            d["path"]: d["modified"] for d in final["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-sim-objects.json").write_text(
            json.dumps(
                {
                    "compact": compact,
                    "rows": rows,
                    "document_flags_preserved": True,
                    "active_document_restored": True,
                },
                indent=2,
            )
        )
        print("Native MCP simulation object inventory and fan binding verified")


asyncio.run(main())
