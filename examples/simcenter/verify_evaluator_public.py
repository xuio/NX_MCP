"""Verify restored evaluator tools through public MCP on isolated CAD fixtures."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "evaluator-public-context.json").read_text())
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
    receipt = {"responses": {}}
    output = shared / "evaluator-public-verification.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        for key, name, args in [
            (
                "continuity",
                "nx_surface_continuity",
                {
                    "first": context["references"][0],
                    "second": context["references"][1],
                    "samples": 21,
                },
            ),
            (
                "dxf",
                "nx_export_planar_dxf",
                {"source": context["planar_face"], "path": context["dxf_path"]},
            ),
        ]:
            response = await client.call_tool(name, args)
            receipt["responses"][key] = response.model_dump(mode="json")
            record()
            assert not response.isError, response
            data = response.structuredContent
            if key == "continuity":
                assert data["checks"] == {"G0": True, "G1": True, "G2": True}
            else:
                assert data["entity_counts"] == {"CIRCLE": 1}
        receipt["passed"] = True
        record()


if __name__ == "__main__":
    asyncio.run(main())
