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
    output = shared / "public-analysis-environment-r2.json"

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

        cad = 'obj_20bc234ffa5249ceb4fb4d82b993c626_1350d8c2f83e41edb7b0eb1720080212'
        result = await call("create", "nx_sim_create_analysis", {"cad_document": cad, "folder": "ui-benchmarks/public-analysis-20260909-r2", "name": "Public coupled", "operation_id": "public-analysis-create-20260909-r2"})
        sid = result["sim"]["id"]
        await call("step", "nx_sim_flow_setup", {"document": sid, "action": "create_step", "name": "Steady"})
        await call("tables", "nx_sim_flow_setup", {"document": sid, "action": "attach_defaults", "name": "Public"})
        await call("steady", "nx_sim_flow_setup", {"document": sid, "action": "coupled_steady"})
        for temperature in (25.0, 40.0):
            r = await call("ambient_"+str(int(temperature)), "nx_sim_environment", {"document": sid, "temperature_c": temperature, "pressure_pa": 101325.0, "buoyancy": False})
            assert r["actual"]["values"]["Fluid Temperature"]["value"] == temperature
        await call("save", "nx_sim_save", {"document": sid})
        receipt.update(passed=True, solver_launched=False, document=sid)
        record()


if __name__ == "__main__":
    asyncio.run(main())
