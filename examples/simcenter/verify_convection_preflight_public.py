"""Verify convection dependencies through public MCP, persistence and native export."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "convection-environment-public.json").read_text())
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
    output = shared / "convection-environment-preflight.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        document = context["document"]
        faces = await call("faces", "nx_sim_faces", {"document": document})
        before = await call(
            "before",
            "nx_sim_constraints",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        error = await call(
            "invalid",
            "nx_sim_convection",
            {
                "document": document,
                "faces": [faces["faces"][0]["face"]["id"]],
                "coefficient_w_m2_k": 10.0,
                "name": "MCP_INVALID_DEPENDENCY",
                "provenance": "Preflight verification",
                "temperature_source": "fluid_ambient",
                "temperature_k": 293.15,
            },
            error=True,
        )
        assert error["details"]["mutation_outcome"] == "not_started"
        after = await call(
            "after",
            "nx_sim_constraints",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert before["constraints"] == after["constraints"]
        receipt.update(passed=True, model_unchanged=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
