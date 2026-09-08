"""Exercise native flow-document creation through the compact MCP agent surface.

Creates a new isolated fixture, without mesh or solve. Existing output directories
are refused; inspect request.json's operation ID before retrying an interrupted run.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    operation = "op_" + uuid.uuid4().hex
    arguments = {
        "folder": args.folder,
        "analysis_type": args.analysis_type,
        "length_mm": 160.0,
        "width_mm": 20.0,
        "height_mm": 20.0,
        "operation_id": operation,
    }
    (output / "request.json").write_text(json.dumps(arguments, indent=2))
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_SURFACE="agent",
        NX_MCP_WORKSPACE=args.workspace,
        NX_MCP_BRIDGE_DESCRIPTOR=args.bridge_descriptor,
    )
    async with (
        stdio_client(
            StdioServerParameters(command=sys.executable, args=["-m", "nx_mcp.server"], env=env)
        ) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        schema = await client.call_tool(
            "nx_discover_tools",
            {"query": "nx_sim_create_benchmark", "domain": "simulation", "include_schema": True},
        )
        if schema.isError:
            raise RuntimeError(schema.structuredContent)
        choices = schema.structuredContent["tools"][0]["inputSchema"]["properties"][
            "analysis_type"
        ]["enum"]
        if args.analysis_type not in choices:
            raise ValueError("Selected environment is absent from discovered schema")
        result = await client.call_tool(
            "nx_invoke",
            {"tool": "nx_sim_create_benchmark", "arguments": arguments, "detail": "full"},
        )
        (output / "receipt.json").write_text(json.dumps(result.structuredContent, indent=2))
        if result.isError:
            raise RuntimeError(result.structuredContent)
        actual = result.structuredContent
        expected = "Flow" if args.analysis_type == "flow" else "Coupled Thermal-Flow"
        if (
            actual["solution"]["analysis"] != expected
            or actual["mesh_created"]
            or actual["solve_launched"]
        ):
            raise ValueError("Native fixture readback mismatch")
        print("Native flow document creation verified through MCP; mesh and solve remain untested")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("workspace", "bridge-descriptor", "folder", "output"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--analysis-type", choices=["flow", "coupled_thermal_flow"], default="flow")
    asyncio.run(run(parser.parse_args()))
