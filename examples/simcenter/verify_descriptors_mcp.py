"""Inspect the completed native flow job through the read-only public log audit."""

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
        schema = next(t for t in available.tools if t.name == "nx_sim_descriptors")
        before = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        thermal = next(
            d
            for d in before
            if d["path"].endswith("A-thermal-export-20260908-r1\\thermal_input_r1.sim")
        )
        assert not thermal["work"]
        args = {
            "document": thermal["document"]["id"],
            "kind": "load",
            "name_contains": "heat",
            "limit": 1,
        }
        first = await client.call_tool("nx_sim_descriptors", args)
        second = await client.call_tool("nx_sim_descriptors", {**args, "offset": 1})
        constraints = await client.call_tool(
            "nx_sim_descriptors",
            {"document": args["document"], "kind": "constraint", "name_contains": "convection"},
        )
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        preserved = {d["path"]: (d["modified"], d["work"], d["display"]) for d in before} == {
            d["path"]: (d["modified"], d["work"], d["display"]) for d in after
        }
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-descriptors.json")
        output.write_text(
            json.dumps(
                {
                    "schema": schema.model_dump(mode="json"),
                    "first": first.model_dump(mode="json"),
                    "second": second.model_dump(mode="json"),
                    "constraints": constraints.model_dump(mode="json"),
                    "document_state_preserved": preserved,
                },
                indent=2,
            )
        )
        assert not first.isError and not second.isError and not constraints.isError
        assert (
            first.structuredContent["unfiltered_total"] == 17
            and first.structuredContent["total"] == 3
        )
        assert first.structuredContent["descriptors"][0]["descriptor_name"] == "Heat Load"
        assert second.structuredContent["descriptors"][0]["descriptor_name"] == "Heat Flux"
        assert constraints.structuredContent["total"] == 3 and preserved
        print("Public native descriptor discovery passed on inactive Thermal SIM; state preserved")


asyncio.run(main())
