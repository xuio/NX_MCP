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
        schema = next(t for t in available.tools if t.name == "nx_sim_faces")
        before = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not before.isError
        row = next(
            d
            for d in before.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )
        assert "F-input-export-20260908-r2" in row["path"]
        pages, faces, offset = [], [], 0
        for _ in range(20):
            page = await client.call_tool(
                "nx_sim_faces", {"document": row["document"]["id"], "offset": offset, "limit": 5}
            )
            assert not page.isError, page.structuredContent
            data = page.structuredContent
            assert data["coordinate_frame"] == "fem_part_absolute" and data["units"] == "mm"
            pages.append(page.model_dump(mode="json"))
            faces.extend(data["faces"])
            if data["next_offset"] is None:
                break
            offset = data["next_offset"]
        else:
            raise ValueError("Unexpected inventory size")
        assert len(faces) == data["total"] > 0
        assert len({f["face"]["id"] for f in faces}) == len(faces)
        assert all(f["face"]["owner_part_path"] == row["path"] for f in faces)
        invalid = await client.call_tool(
            "nx_sim_faces", {"document": row["document"]["id"], "limit": 0}
        )
        assert invalid.isError
        after = await client.call_tool("nx_sim_documents", {"limit": 100})

        def fields(response):
            return [
                (d["path"], d["work"], d["display"], d["modified"])
                for d in response.structuredContent["documents"]
            ]

        assert fields(before) == fields(after)
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-sim-faces.json").write_text(
            json.dumps(
                {
                    "transport": "real MCP to Simcenter UI bridge",
                    "schema": schema.model_dump(mode="json"),
                    "pages": pages,
                    "invalid": invalid.model_dump(mode="json"),
                    "document_flags_unchanged": True,
                },
                indent=2,
            )
        )
        print("Native MCP face inventory verification finished")


asyncio.run(main())
