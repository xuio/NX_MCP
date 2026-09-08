"""Verify orthotropic material schema, native creation and operation replay."""

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
        responses = {}
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-material-inspection.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        fem = next(d for d in docs.structuredContent["documents"]
                   if d["path"].endswith("OrthoZR1_mesh.fem"))
        args = {"document": fem["document"]["id"], "limit": 1}
        materials = await call("materials", "nx_sim_materials", args)
        assert not materials.isError, materials.structuredContent
        collectors = await call("collectors", "nx_sim_collectors", args)
        assert not collectors.isError, collectors.structuredContent
        row = collectors.structuredContent["collectors"][0]
        assert len(row["state_sha256"]) == 64
        assert row["orientation"]["native_selector"] == 1
        repeat = await call("repeat", "nx_sim_collectors", args)
        assert repeat.structuredContent["collectors"] == collectors.structuredContent["collectors"]
        bad = await call("invalid_page", "nx_sim_collectors", {**args, "limit": 101})
        assert bad.isError and bad.structuredContent["code"] == "NX_INVALID_ARGUMENT"
        output.write_text(json.dumps({"status": "passed", "responses": responses}, indent=2))
        print("Material and collector MCP inspection, stable repeat, invalid paging passed")


asyncio.run(main())
