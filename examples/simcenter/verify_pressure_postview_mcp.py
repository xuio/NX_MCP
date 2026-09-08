"""Read-only MCP verification on the isolated Windows Simcenter installation."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--field", choices=("pressure", "total_pressure"), default="pressure")
    parser.add_argument("--revision", default="01")
    options = parser.parse_args()
    selected = options.field
    suffix = "pressure" if selected == "pressure" else "total-pressure"
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
        schema = next(t for t in available.tools if t.name == "nx_sim_show_pressure")
        assert "operation_id" in schema.inputSchema["properties"]
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        target = next(
            d
            for d in docs.structuredContent["documents"]
            if d["path"].endswith(r"F-input-export-20260908-r2\flow_input_r2.sim")
        )
        document = target["document"]["id"]
        activated = await client.call_tool("nx_sim_activate", {"document": document})
        assert not activated.isError
        args = {
            "document": document,
            "name": "MCP duct " + selected,
            "field": selected,
            "operation_id": "show-duct-" + suffix + "-" + options.revision,
        }
        page = await client.call_tool("nx_sim_show_pressure", args)
        output = Path(rf"Z:\nx-mcp-integration\simcenter-discovery\stdio-{suffix}-postview.json")
        responses = {"created": page.model_dump(mode="json")}
        output.write_text(json.dumps(responses, indent=2))
        assert not page.isError, page.structuredContent
        assert page.structuredContent["readback"]["unit"] == "PressurePascals"
        expected_field = (
            "Pressure - Element-Nodal"
            if selected == "pressure"
            else "Total Pressure - Element-Nodal"
        )
        assert page.structuredContent["readback"]["field"] == expected_field
        replay = await client.call_tool("nx_sim_show_pressure", args)
        assert (
            not replay.isError
            and replay.structuredContent["postview_id"] == page.structuredContent["postview_id"]
        )
        invalid = await client.call_tool(
            "nx_sim_show_pressure",
            {
                **args,
                "loadcase_index": 10000,
                "operation_id": "show-duct-" + suffix + "-invalid-" + options.revision,
            },
        )
        assert invalid.isError
        responses.update(
            replay=replay.model_dump(mode="json"), invalid=invalid.model_dump(mode="json")
        )
        output.write_text(json.dumps(responses, indent=2))
        import base64
        import hashlib

        capture = await client.call_tool(
            "nx_screenshot", {"style": "current", "fit": True, "width": 1600, "height": 1000}
        )
        assert not capture.isError, capture.model_dump(mode="json")
        downloaded = await client.call_tool(
            "nx_download_file",
            {"path": capture.structuredContent["artifact_path"], "delivery": "image"},
        )
        blocks = [c for c in downloaded.content if c.type == "image"]
        assert len(blocks) == 1
        data = base64.b64decode(blocks[0].data)
        assert hashlib.sha256(data).hexdigest() == capture.structuredContent["sha256"]
        Path(rf"Z:\nx-mcp-integration\simcenter-discovery\{suffix}-contour.png").write_bytes(data)
        responses["capture"] = capture.structuredContent
        responses["inline_image_checksum_verified"] = True
        output.write_text(json.dumps(responses, indent=2))
        print("Native pressure postview, readback, replay and screenshot verified")


asyncio.run(main())
