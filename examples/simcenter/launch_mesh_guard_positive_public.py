"""Launch one unchanged 100-element mesh-guard analysis; never retry an existing job."""

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
    output = shared / "mesh-guard-positive-launch.json"

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

        job_id = "mesh-guard-positive-r1"
        before = await call("prior_job", "nx_sim_job_status", {"job_id": job_id}, error=True)
        assert before["code"] == "NX_SIM_JOB_NOT_FOUND", (
            "Existing job: inspect it; never relaunch this fixture"
        )
        source = await call(
            "open",
            "nx_sim_open",
            {"path": "ui-benchmarks/V-mesh-guard-export-20260909-r1/mesh_guard_v_r1.sim"},
        )
        sid = source["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        saved = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/V-mesh-guard-positive-20260909-r1/mesh_guard_positive_r1.sim",
                "operation_id": job_id + "-copy",
            },
        )
        sid = saved["document"]["id"]
        controls = await call(
            "controls",
            "nx_sim_steady_thermal_controls",
            {
                "document": sid,
                "maximum_temperature_change_k": 0.001,
                "iteration_limit": 100,
                "operation_id": job_id + "-controls",
            },
        )
        await call("save", "nx_sim_save", {"document": sid, "operation_id": job_id + "-save"})
        prepared = await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": job_id,
                "mesh_inspection_limit": 500,
                "operation_id": job_id + "-prepare",
            },
        )
        snapshot = await call("mesh", "nx_sim_mesh_state", {"document": sid})
        assert snapshot["mesh_state"]["counts"] == {"nodes": 45, "elements": 100}
        receipt.update(
            job_id=job_id,
            document=sid,
            mesh_state=snapshot["mesh_state"],
            prepared=prepared,
            controls=controls,
        )
        record()
        launched = await call(
            "launch",
            "nx_sim_launch",
            {"document": sid, "job_id": job_id, "operation_id": job_id + "-launch"},
        )
        assert not launched["replayed"]
        assert launched["observer"]["state"] == "started"
        receipt.update(passed=True, numerical_acceptance="not_yet_checked")
        record()


if __name__ == "__main__":
    asyncio.run(main())
