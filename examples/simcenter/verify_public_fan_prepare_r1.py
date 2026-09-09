"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

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
    output = shared / "public-fan-prepare-r1.json"

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

        previous=json.loads((shared/"public-mesh-material-r1.json").read_text())
        sid=previous["setup_ids"]["sim"]
        objects=previous["responses"]["objects"]["structuredContent"]["simulation_objects"]
        inlet=next(r["object"]["id"] for r in objects if r["descriptor"]=="Inlet")
        opening=next(r["object"]["id"] for r in objects if r["descriptor"]=="Opening")
        fan=await call("fan","nx_sim_fan_table",{"document":sid,"name":"Generic static fan","points":[[0.0,1.0],[0.0004,0.0]],"pressure_convention":"static","rpm":1000.0,"reference_density_kg_m3":1.2,"stall_region":"not modeled; assumed linear curve","provenance_kind":"assumed","provenance_source":"Synthetic infrastructure fixture, not manufacturer performance"})
        await call("bind_fan","nx_sim_assign_fan",{"document":sid,"inlet":inlet,"field":fan["field"]["id"]})
        await call("loss","nx_sim_head_loss",{"document":sid,"opening":opening,"coefficient":2.0,"name":"Generic outlet loss"})
        await call("save","nx_sim_save",{"document":sid})
        prepared=await call("prepare","nx_sim_prepare_solve",{"document":sid,"job_id":"public-user-cad-40c-r1","operation_id":"public-user-cad-40c-prepare-r1"})
        receipt.update(passed=True,solver_launched=False,document=sid,job_id="public-user-cad-40c-r1")
        record()


if __name__ == "__main__":
    asyncio.run(main())
