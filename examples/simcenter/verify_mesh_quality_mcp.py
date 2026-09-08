"""Conduction setup through public MCP tools on the isolated Windows Simcenter installation."""

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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-mesh-quality.json")
        responses = {}

        async def call(name, args, key):
            result = await client.call_tool(name, args)
            responses[key] = result.model_dump(mode="json")
            output.write_text(
                json.dumps(
                    {"transport": "real MCP to Simcenter UI", "responses": responses}, indent=2
                )
            )
            assert not result.isError, result.structuredContent
            return result.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100}, "before")
        sim = next(d for d in docs["documents"] if d["work"] and d["document_type"] == "SimPart")
        assert sim["path"].endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim"), sim
        simid = sim["document"]["id"]
        deps = await call("nx_sim_dependencies", {"document": simid}, "dependencies")
        fempath = next(d["path"] for d in deps["documents"] if d["document_type"] == "FemPart")
        fem = next(d for d in docs["documents"] if d["path"] == fempath)
        quality = await call(
            "nx_sim_mesh_quality",
            {"document": fem["document"]["id"], "include_settings": True},
            "quality",
        )
        assert quality["element_count"] == 2658
        assert quality["tests"] and quality["settings"]
        assert quality["solve_readiness"] == "not_established"
        compact = await call("nx_sim_mesh_quality", {"document": fem["document"]["id"]}, "compact")
        assert "settings" not in compact
        assert compact["tests"] == quality["tests"]
        after = await call("nx_sim_documents", {"limit": 100}, "after")
        assert {d["path"]: d["modified"] for d in docs["documents"]} == {
            d["path"]: d["modified"] for d in after["documents"]
        }
        print("Native public mesh-quality check and criteria readback verified")


asyncio.run(main())
