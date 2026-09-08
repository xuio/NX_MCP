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
        schema = next(t for t in available.tools if t.name == "nx_sim_convection")
        docs = await client.call_tool("nx_sim_documents", {"limit": 100})
        current = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert "F-input-export-20260908-r2" in current["path"]
        rejected_flow = await client.call_tool(
            "nx_sim_convection",
            {
                "document": current["document"]["id"],
                "faces": [],
                "coefficient_w_m2_k": 10,
                "name": "must_reject",
                "provenance": "fixture",
                "operation_id": "convection-flow-reject-01",
            },
        )
        assert (
            rejected_flow.isError
            and rejected_flow.structuredContent["code"] == "NX_SIM_UNSUPPORTED"
        )
        created = await client.call_tool(
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/F-convection-mcp-20260908-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "convection-create-01",
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
        assert not page.isError and page.structuredContent["total"] == 6
        faces = [f["face"]["id"] for f in page.structuredContent["faces"]]
        args = {
            "document": sim["document"]["id"],
            "faces": faces,
            "coefficient_w_m2_k": 10,
            "name": "MCP_ASSUMED_CONVECTION",
            "provenance": "Assumed h=10 W/(m2 K); isolated MCP authoring verification, no CFD interface",
            "operation_id": "convection-author-01",
        }
        boundary = await client.call_tool("nx_sim_convection", args)
        responses = {
            "created": created.model_dump(mode="json"),
            "flow_rejection": rejected_flow.model_dump(mode="json"),
            "boundary": boundary.model_dump(mode="json"),
        }
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-convection.json")
        output.write_text(
            json.dumps({"schema": schema.model_dump(mode="json"), "responses": responses}, indent=2)
        )
        assert not boundary.isError, boundary.structuredContent
        assert boundary.structuredContent["committed_face_count"] == 6
        assert boundary.structuredContent["constraint"]["kind"] == "constraint"
        replay = await client.call_tool("nx_sim_convection", args)
        assert not replay.isError
        assert (
            replay.structuredContent["constraint"]["id"]
            == boundary.structuredContent["constraint"]["id"]
        )
        conflict = await client.call_tool(
            "nx_sim_convection", {**args, "operation_id": "convection-conflict-01"}
        )
        assert conflict.isError and conflict.structuredContent["code"] == "NX_SIM_NAME_CONFLICT"
        saved = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": sim["document"]["id"],
                "path": "ui-benchmarks/F-convection-mcp-20260908-r1/saved_convection.sim",
                "operation_id": "convection-save-01",
            },
        )
        assert not saved.isError, saved.structuredContent
        responses.update(
            replay=replay.model_dump(mode="json"),
            conflict=conflict.model_dump(mode="json"),
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
        print("Native convection authoring/replay/save verification finished")


asyncio.run(main())
