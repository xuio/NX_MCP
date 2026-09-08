"""Observe the existing refined flow job, release its gate and audit its log."""

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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-heat-preflight.json")
        responses = {}

        async def call(key, name, args, error=False):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            output.write_text(json.dumps(responses, indent=2))
            assert bool(r.isError) == error, r
            return r.structuredContent

        before = await call("before", "nx_sim_documents", {"limit": 100})
        current = next(
            d
            for d in before["documents"]
            if d["work"] and d["path"].endswith("volume_solve_r1.sim")
        )
        doc = current["document"]["id"]
        faces = await call("faces", "nx_sim_faces", {"document": doc})
        body = faces["faces"][0]["body"]["id"]
        loads = await call(
            "loads_before",
            "nx_sim_loads",
            {"document": doc, "include_properties": True, "include_targets": True},
        )
        args = {
            "document": doc,
            "kind": "volume_generation",
            "value": 100000,
            "name": "Duplicate numerical source",
            "provenance": "preflight test; must not commit",
            "targets": [body],
            "operation_id": "heat-preflight-duplicate-r1",
        }
        duplicate = await call("duplicate", "nx_sim_distributed_heat", args, error=True)
        assert duplicate["code"] == "NX_SIM_DUPLICATE_HEAT_SOURCE"
        assert duplicate["details"]["mutation_outcome"] == "not_started"
        assert duplicate["details"]["next_step"]
        wrong = await call(
            "wrong_kind",
            "nx_sim_distributed_heat",
            {**args, "kind": "surface_flux", "operation_id": "heat-preflight-kind-r1"},
            error=True,
        )
        assert wrong["details"]["mutation_outcome"] == "not_started"
        after_loads = await call(
            "loads_after",
            "nx_sim_loads",
            {"document": doc, "include_properties": True, "include_targets": True},
        )
        assert loads["loads"] == after_loads["loads"]
        after = await call("after", "nx_sim_documents", {"limit": 100})
        assert before["documents"] == after["documents"]
        print(
            "Native MCP preflight errors explicitly not_started; loads and document state unchanged"
        )


asyncio.run(main())
