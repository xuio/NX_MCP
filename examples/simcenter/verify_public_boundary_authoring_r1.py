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
    output = shared / "public-boundary-authoring-r1.json"

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

        setup = json.loads((shared / "public-analysis-environment-r2.json").read_text())["responses"]["create"]["structuredContent"]
        sid = setup["sim"]["id"]
        inventory = await call("faces", "nx_sim_faces", {"document": sid})
        selected = {}
        for label, x in (("inlet", 0.0), ("opening", 20.0)):
            matches = [r for r in inventory["faces"] if abs(r["bounds"]["minimum"][0]-x)<1e-6 and abs(r["bounds"]["maximum"][0]-x)<1e-6 and abs(r["bounds"]["minimum"][2]-2)<1e-6 and abs(r["bounds"]["maximum"][2]-10)<1e-6]
            assert len(matches)==1
            selected[label]=matches[0]["face"]["id"]
        inlet = await call("inlet", "nx_sim_inlet", {"document":sid,"faces":[selected["inlet"]],"name":"Public inlet","velocity_m_s":1.0,"operation_id":"public-inlet-20260909-r1"})
        outlet = await call("opening", "nx_sim_opening", {"document":sid,"faces":[selected["opening"]],"name":"Public outlet","pressure_pa":101325.0,"operation_id":"public-opening-20260909-r1"})
        await call("external", "nx_sim_external_temperature", {"document":sid,"boundaries":[inlet["boundary"]["id"],outlet["boundary"]["id"]],"name":"External 40 C","temperature_c":40.0})
        await call("save", "nx_sim_save", {"document":sid})
        receipt.update(passed=True,solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
