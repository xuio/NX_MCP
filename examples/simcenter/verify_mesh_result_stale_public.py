"""Verify stale result reporting after the bounded mesh edit; never solve."""

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
    output = shared / "mesh-result-stale-public.json"

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

        fixture = json.loads((shared / "mesh-guard-positive-launch.json").read_text())
        sid = fixture["document"]
        await call("activate", "nx_sim_activate", {"document": sid})
        identity = await call(
            "identity", "nx_sim_result_identity", {"document": sid, "job_id": fixture["job_id"]}
        )
        binding = identity["job_binding"]
        assert binding["associated_result_matches_observed_artifact"]
        assert binding["live_mesh_state"]["state"] == "changed"
        assert (
            identity["result_freshness"] == "stale" and binding["model_result_freshness"] == "stale"
        )
        assert not identity["engineering_accepted"]
        job = await call("job", "nx_sim_job_status", {"job_id": fixture["job_id"]})
        assert job["state"] == "solver_exited"
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
