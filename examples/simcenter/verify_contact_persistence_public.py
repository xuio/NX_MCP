"""Verify contact authoring through the public MCP using an isolated fixture."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "contact-public.json").read_text())
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
    receipt = {"responses": {}}
    output = shared / "contact-persistence-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        before = context["responses"]["inventory"]["structuredContent"]["simulation_objects"][0]
        doc = context["reopened"]["document"]["id"]
        after = await call(
            "reopened_inventory",
            "nx_sim_objects",
            {"document": doc, "include_properties": True, "include_targets": True},
        )
        row = next(
            r for r in after["simulation_objects"] if r["object"]["name"] == "MCP_PUBLIC_CONTACT_R1"
        )
        keys = {
            "Override Secondary Region",
            "Specify Region Side to Apply to",
            "Type",
            "Total Resistance",
        }
        props = lambda r: [p for p in r["properties"] if p["name"] in keys]
        assert props(before) == props(row)
        assert row["provenance"] == before["provenance"]
        assert [t["count"] for t in row["target_sets"]] == [1, 1]
        receipt["passed"] = True
        receipt["scope"] = (
            "Reopened native contact properties, provenance and per-side counts through public MCP; native geometry association checked separately"
        )
        receipt["open_warning"] = context["reopened"]["warnings"]
        record()


if __name__ == "__main__":
    asyncio.run(main())
