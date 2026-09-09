"""Reject changed mesh before launch; run only inside the bounded restoration harness."""

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
    output = shared / "mesh-guard-rejection-public.json"

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

        fixture = json.loads((shared / "mesh-guard-fixture-public.json").read_text())
        armed = json.loads((shared / "mesh-guard-armed.json").read_text())
        opened = await call("open", "nx_sim_open", {"path": fixture["analysis_path"]})
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        snapshot = await call("changed_mesh", "nx_sim_mesh_state", {"document": sid})
        assert snapshot["mesh_state"]["counts"] == armed["before"]["counts"]
        assert snapshot["mesh_state"]["sha256"] != armed["before"]["sha256"]
        rejected = await call(
            "launch_rejected",
            "nx_sim_launch",
            {
                "document": sid,
                "job_id": fixture["job_id"],
                "operation_id": "mesh-guard-rejected-launch-r1",
            },
            error=True,
        )
        assert rejected["code"] == "NX_SIM_MESH_STATE_CHANGED"
        assert rejected["details"]["mutation_outcome"] == "not_started"
        job = await call(
            "job_after_rejection",
            "nx_sim_job_status",
            {"job_id": fixture["job_id"], "include_manifest": True},
        )
        assert job["state"] == "accepted" and job["revision"] == 0
        assert job["manifest"]["live_mesh_state"]["sha256"] == armed["before"]["sha256"]
        await call(
            "cancel",
            "nx_sim_cancel",
            {
                "job_id": fixture["job_id"],
                "expected_revision": 0,
                "operation_id": "mesh-guard-cancel-r1",
            },
        )
        final = await call("cancelled", "nx_sim_job_status", {"job_id": fixture["job_id"]})
        assert final["state"] == "cancelled"
        receipt.update(passed=True, solver_launched=False, job_state="cancelled")
        record()


if __name__ == "__main__":
    asyncio.run(main())
