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
        schema = next(t for t in available.tools if t.name == "nx_sim_temperature")
        created = await client.call_tool(
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/A-temperature-mcp-20260908-r1",
                "length_mm": 100,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "temperature-create-01",
            },
        )
        assert not created.isError, created.structuredContent
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        sim = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        page = await client.call_tool("nx_sim_faces", {"document": sim["document"]["id"]})
        assert not page.isError
        faces = [
            f["face"]["id"]
            for f in page.structuredContent["faces"]
            if abs(f["bounds"]["minimum"][0]) < 1e-8 and abs(f["bounds"]["maximum"][0]) < 1e-8
        ]
        assert len(faces) == 1
        args = {
            "document": sim["document"]["id"],
            "faces": faces,
            "temperature_k": 293.15,
            "name": "MCP_FIXED_TEMPERATURE",
            "provenance": "Prescribed 293.15 K cold end for isolated conduction authoring benchmark",
            "operation_id": "temperature-author-01",
        }
        invalid = await client.call_tool(
            "nx_sim_temperature",
            {**args, "temperature_k": -1, "operation_id": "temperature-invalid-01"},
        )
        assert invalid.isError
        boundary = await client.call_tool("nx_sim_temperature", args)
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-temperature.json")
        responses = {
            "created": created.model_dump(mode="json"),
            "invalid": invalid.model_dump(mode="json"),
            "boundary": boundary.model_dump(mode="json"),
        }
        output.write_text(
            json.dumps({"schema": schema.model_dump(mode="json"), "responses": responses}, indent=2)
        )
        assert not boundary.isError, boundary.structuredContent
        assert boundary.structuredContent["temperature_k"] == 293.15
        assert boundary.structuredContent["committed_face_count"] == 1
        prop = next(
            p for p in boundary.structuredContent["properties"] if p["name"] == "Temperature"
        )
        assert prop["unit_symbol"] == "K", prop
        replay = await client.call_tool("nx_sim_temperature", args)
        assert (
            not replay.isError
            and replay.structuredContent["constraint"]["id"]
            == boundary.structuredContent["constraint"]["id"]
        )
        saved = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": sim["document"]["id"],
                "path": "ui-benchmarks/A-temperature-mcp-20260908-r1/saved_temperature.sim",
                "operation_id": "temperature-save-01",
            },
        )
        assert not saved.isError, saved.structuredContent
        responses.update(replay=replay.model_dump(mode="json"), saved=saved.model_dump(mode="json"))
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
        print("Native MCP prescribed temperature verified")


asyncio.run(main())
