"""Verify agent discovery, result inventory and image delivery against an active SIM.

Run on the NX host with its MCP Python environment. Creates only a viewport PNG
and test receipts; requires an existing SIM with results and a displayed contour.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_WORKSPACE=str(Path(args.workspace).resolve()),
        NX_MCP_BRIDGE_DESCRIPTOR=str(Path(args.bridge_descriptor).resolve()),
        NX_MCP_SURFACE="agent",
    )
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=["-m", "nx_mcp.server"], env=env)
    ) as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        available = await client.list_tools()

        async def call(name, args):
            value = await client.call_tool(name, args)
            if value.isError:
                raise RuntimeError(value.structuredContent)
            return value

        discovery = await call(
            "nx_discover_tools",
            {
                "query": "nx_sim_result_inventory",
                "domain": "simulation",
                "include_schema": True,
                "include_output_schema": False,
            },
        )
        if discovery.structuredContent["tools"][0]["name"] != "nx_sim_result_inventory":
            raise ValueError("Discovery mismatch")
        docs = await call(
            "nx_invoke",
            {"tool": "nx_sim_documents", "arguments": {"limit": 100}, "detail": "full"},
        )
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        page = await call(
            "nx_invoke",
            {
                "tool": "nx_sim_result_inventory",
                "arguments": {"document": document, "offset": args.result_offset, "limit": 2},
                "detail": "compact",
            },
        )
        capture = await call(
            "nx_screenshot", {"style": "current", "fit": False, "width": 1600, "height": 1000}
        )
        image = await call(
            "nx_download_file",
            {"path": capture.structuredContent["artifact_path"], "delivery": "image"},
        )
        blocks = [c for c in image.content if c.type == "image"]
        if len(blocks) != 1:
            raise ValueError("Expected inline image delivery")
        data = base64.b64decode(blocks[0].data)
        if hashlib.sha256(data).hexdigest() != capture.structuredContent["sha256"]:
            raise ValueError("Delivered image checksum mismatch")
        result = {
            "transport": "MCP stdio agent surface -> NX UI bridge",
            "core_tool_count": len(available.tools),
            "discovery": discovery.structuredContent,
            "page": page.structuredContent,
            "capture": capture.structuredContent,
            "inline_image": {
                "mime_type": blocks[0].mimeType,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        }
        (output / "receipt.json").write_text(json.dumps(result, indent=2))
        (output / "contour.png").write_bytes(data)
        print("MCP agent discovery, inventory, capture and inline image delivery completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--bridge-descriptor", required=True)
    parser.add_argument(
        "--output", required=True, help="New output directory; existing directories are rejected"
    )
    parser.add_argument("--result-offset", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(main(args))
