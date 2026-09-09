"""Verify public initial-condition lifecycle and exported selector/temperature; no solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
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
    output = shared / "sim-update-persistence-public.json"

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

        fixture = json.loads((shared / "sim-update-fixture-public.json").read_text())
        paths = fixture["paths"]
        opened_fem = await call("open_fem", "nx_sim_open", {"path": paths["fem"]})
        fid = opened_fem["document"]["id"]
        await call("save_fem", "nx_sim_save", {"document": fid})
        opened_sim = await call("open_sim", "nx_sim_open", {"path": paths["sim"]})
        sid = opened_sim["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        await call(
            "before_loads",
            "nx_sim_loads",
            {"document": sid, "include_properties": True, "include_targets": True},
        )
        await call("save_sim", "nx_sim_save", {"document": sid})
        await call("close_sim", "nx_sim_close", {"document": sid})
        reopened = await call("reopen", "nx_sim_open", {"path": paths["sim"]})
        sid = reopened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": sid})
        await call(
            "after_loads",
            "nx_sim_loads",
            {"document": sid, "include_properties": True, "include_targets": True},
        )
        exported = await call(
            "export",
            "nx_sim_export_input",
            {"document": sid, "operation_id": "sim-update-export-r1"},
        )
        receipt.update(
            completed=True,
            paths=paths,
            export=exported,
            solver_launched=False,
            numerical_acceptance="not_established",
            next_step="Inspect exported mesh and compare saved assignment state against native pre-export receipt",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
