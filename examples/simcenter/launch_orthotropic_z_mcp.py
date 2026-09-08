"""Prepare and launch the independently refined duct comparison once."""

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
        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        source = next(
            d
            for d in docs
            if d["work"] and d["path"].endswith("orthotropic-z-20260908-r1\\OrthoZR1_analysis.sim")
        )
        responses = {}
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-orthotropic-z-launch.json")

        def record():
            output.write_text(
                json.dumps(
                    {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": responses},
                    indent=2,
                )
            )

        copied = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": source["document"]["id"],
                "path": "ui-benchmarks/orthotropic-z-solve-20260908-r1/orthotropic_z_solve_r1.sim",
                "operation_id": "orthotropic-z-copy-01",
            },
        )
        responses["copy"] = copied.model_dump(mode="json")
        record()
        assert not copied.isError, copied.structuredContent
        args = {
            "document": copied.structuredContent["document"]["id"],
            "job_id": "orthotropic-z-thermal-01",
        }
        prepared = await client.call_tool(
            "nx_sim_prepare_solve", {**args, "operation_id": "orthotropic-z-prepare-01"}
        )
        responses["prepare"] = prepared.model_dump(mode="json")
        record()
        assert not prepared.isError, prepared.structuredContent
        import xml.etree.ElementTree as ET

        deck = ET.parse(prepared.structuredContent["input_path"]).getroot()
        table = deck.find("./PhysicalPropertyTableList/PhysicalPropertyTable")
        properties = {p.get("name"): p.findtext("Value") for p in table.findall("Property")}
        assert properties["Material Orientation Type"].strip() == "1"
        assert list(map(float, properties["Material Orientation"].split())) == [0, 1, 0, 0, 0, 1]
        assert list(map(float, properties["Material Orientation Origin"].split())) == [0, 0, 0]
        responses["frame_export_verified"] = {
            "type": 1,
            "material_x": [0, 1, 0],
            "material_y": [0, 0, 1],
            "material_z": [1, 0, 0],
        }
        record()
        launched = await client.call_tool(
            "nx_sim_launch", {**args, "operation_id": "orthotropic-z-launch-01"}
        )
        responses["launch"] = launched.model_dump(mode="json")
        record()
        assert not launched.isError, launched.structuredContent
        assert launched.structuredContent["observer"]["state"] == "started"
        resumed = await client.call_tool("nx_sim_observe_job", {"job_id": args["job_id"]})
        responses["observe_again"] = resumed.model_dump(mode="json")
        status = await client.call_tool("nx_sim_job_status", {"job_id": args["job_id"]})
        responses["status"] = status.model_dump(mode="json")
        record()
        assert not resumed.isError and resumed.structuredContent["observer"]["reused"]
        assert status.structuredContent["observer"]["thread_alive"]
        print(
            "Automatic observer running; this MCP client now disconnects. Reconnect separately to verify terminal state and release."
        )


asyncio.run(main())
