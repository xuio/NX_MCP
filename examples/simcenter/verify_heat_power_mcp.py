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
        schema = next(t for t in available.tools if t.name == "nx_sim_heat_power")
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        sim = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert sim["path"].endswith("saved_convection.sim")
        faces = await client.call_tool("nx_sim_faces", {"document": sim["document"]["id"]})
        assert not faces.isError
        bodies = {f["body"]["id"] for f in faces.structuredContent["faces"]}
        assert len(bodies) == 1
        args = {
            "document": sim["document"]["id"],
            "body": bodies.pop(),
            "power_w": 0.1,
            "name": "MCP_INTERNAL_POWER",
            "provenance": "Assumed 0.1 W internal heat for isolated thermal authoring verification",
            "operation_id": "heat-power-author-01",
        }
        invalid = await client.call_tool(
            "nx_sim_heat_power", {**args, "power_w": -1, "operation_id": "heat-power-invalid-01"}
        )
        assert invalid.isError
        created = await client.call_tool("nx_sim_heat_power", args)
        responses = {
            "invalid": invalid.model_dump(mode="json"),
            "created": created.model_dump(mode="json"),
        }
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-heat-power.json")
        output.write_text(
            json.dumps({"schema": schema.model_dump(mode="json"), "responses": responses}, indent=2)
        )
        assert not created.isError, created.structuredContent
        assert (
            created.structuredContent["power_w"] == 0.1
            and created.structuredContent["target_count"] == 1
        )
        assert created.structuredContent["load"]["kind"] == "simulation_load"
        replay = await client.call_tool("nx_sim_heat_power", args)
        assert not replay.isError
        assert replay.structuredContent["load"]["id"] == created.structuredContent["load"]["id"]
        duplicate = await client.call_tool(
            "nx_sim_heat_power",
            {**args, "name": "DUPLICATE_BODY_POWER", "operation_id": "heat-power-duplicate-01"},
        )
        assert (
            duplicate.isError
            and duplicate.structuredContent["code"] == "NX_SIM_DUPLICATE_HEAT_SOURCE"
        )
        saved = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": sim["document"]["id"],
                "path": "ui-benchmarks/F-convection-mcp-20260908-r1/saved_power.sim",
                "operation_id": "heat-power-save-01",
            },
        )
        assert not saved.isError, saved.structuredContent
        responses.update(
            replay=replay.model_dump(mode="json"),
            duplicate=duplicate.model_dump(mode="json"),
            saved=saved.model_dump(mode="json"),
        )
        output.write_text(
            json.dumps(
                {
                    "transport": "real MCP to Simcenter UI",
                    "schema": schema.model_dump(mode="json"),
                    "responses": responses,
                },
                indent=2,
            )
        )
        print("Native MCP heat-power authoring verified")


asyncio.run(main())
