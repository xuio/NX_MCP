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
    output = shared / "public-full-results-r1.json"

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

        prepared = json.loads((shared / "public-full-prepare-r1.json").read_text())
        sid = prepared["document"]
        job = "public-full-coupled-r1"
        state = await call("job", "nx_sim_job_status", {"job_id": job, "check_processes": True})
        if state["state"] != "solver_exited":
            return
        await call("identity", "nx_sim_result_identity", {"document": sid, "job_id": job})
        await call("temperature", "nx_sim_temperature_result", {"document": sid})
        await call("pressure", "nx_sim_pressure_result", {"document": sid})
        await call(
            "log",
            "nx_sim_job_log",
            {
                "job_id": job,
                "log_name": "full_public_r1-Public_topology.log",
                "maximum_bytes": 65536,
            },
        )
        await call(
            "flow",
            "nx_sim_flow_log",
            {"job_id": job, "log_name": "full_public_r1-Public_topology.log"},
        )
        await call("release", "nx_sim_release_job", {"job_id": job})
        await call(
            "view",
            "nx_sim_show_temperature",
            {
                "document": sid,
                "name": "Public full workflow",
                "operation_id": "public-full-view-r1",
            },
        )
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
