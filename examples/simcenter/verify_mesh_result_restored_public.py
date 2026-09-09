"""Verify restored result mesh, save only the test-modified FEM, and display the SIM."""

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
    output = shared / "mesh-result-restored-public.json"

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
        restored = json.loads((shared / "mesh-result-restoration.json").read_text())
        assert restored["restored"] and restored["fuse_restored"] and not restored["fuse_calls"]
        for change in restored["changed_flags"]:
            assert change["before"] == [restored["fem_path"], False]
            assert change["after"] == [restored["fem_path"], True]
        fem = await call("open_fem", "nx_sim_open", {"path": restored["fem_path"]})
        await call(
            "save_fem",
            "nx_sim_save",
            {"document": fem["document"]["id"], "operation_id": "mesh-result-restore-save-fem-r1"},
        )
        sid = fixture["document"]
        await call("activate", "nx_sim_activate", {"document": sid})
        identity = await call(
            "identity", "nx_sim_result_identity", {"document": sid, "job_id": fixture["job_id"]}
        )
        binding = identity["job_binding"]
        assert binding["associated_result_matches_observed_artifact"]
        assert binding["live_mesh_state"]["state"] == "matches"
        assert (
            identity["result_freshness"] == "not_verified"
            and binding["model_result_freshness"] == "not_verified"
        )
        assert not identity["engineering_accepted"]
        job = await call("job", "nx_sim_job_status", {"job_id": fixture["job_id"]})
        assert job["state"] == "solver_exited"
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
