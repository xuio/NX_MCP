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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-orthotropic-material.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        listing = await client.list_tools()
        tool = next(t for t in listing.tools if t.name == "nx_sim_orthotropic_material")
        assert "operation_id" in tool.inputSchema["properties"]
        assert "conductivities_w_m_k" in tool.inputSchema["required"]
        responses["schema"] = tool.model_dump(mode="json")
        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        source = next(
            d
            for d in docs.structuredContent["documents"]
            if d["path"].endswith("VariantTxnR1_mesh.fem")
        )
        args = {
            "document": source["document"]["id"],
            "name": "MCP_STDIO_ORTHOTROPIC_R1",
            "conductivities_w_m_k": [12, 7, 0.4],
            "density_kg_m3": 1900,
            "heat_capacity_j_kg_k": 900,
            "provenance": "Synthetic MCP acceptance material; not production data",
        }
        bad = await call(
            "invalid_axes",
            tool.name,
            {
                **args,
                "conductivities_w_m_k": [12, 7],
                "operation_id": "ortho-stdio-invalid-r1",
            },
        )
        assert bad.isError and bad.structuredContent["code"] == "NX_INVALID_ARGUMENT"
        request = {**args, "operation_id": "ortho-stdio-create-r1"}
        created = await call("created", tool.name, request)
        assert not created.isError, created.structuredContent
        result = created.structuredContent
        assert result["properties"]["ThermalConductivity3"]["value"] == 0.4
        assert result["material"]["owner_part_path"] == source["path"]
        replay = await call("replay", tool.name, request)
        assert not replay.isError, replay.structuredContent
        assert replay.structuredContent["material"] == result["material"]
        duplicate = await call(
            "duplicate_name",
            tool.name,
            {
                **args,
                "operation_id": "ortho-stdio-duplicate-r1",
            },
        )
        assert duplicate.isError and duplicate.structuredContent["code"] == "NX_SIM_NAME_CONFLICT"
        output.write_text(json.dumps({"status": "passed", "responses": responses}, indent=2))
        print("Orthotropic MCP schema, rejection, create, replay and duplicate rejection passed")


asyncio.run(main())
